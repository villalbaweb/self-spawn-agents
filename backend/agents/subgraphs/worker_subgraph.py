"""
Native LangGraph Worker Subgraph (Epic 4.1).

Lightweight execution subgraph for recursive nodes that SKIPS:
- semantic_splitter (task already scoped by parent supervisor)
- supervisor (no need for full graph planning)
- synthesizer (results returned directly)

Flow: 
  START → execute → validate → END

For complex tasks, uses a lightweight mini-planner that creates
parallel workers without the full orchestration overhead.

Cost Comparison:
  Full app_graph: 5-8 LLM calls (splitter + supervisor + workers + synthesizer)
  Worker subgraph: 2-5 LLM calls (complexity check + mini-plan + workers)

Benefits:
- ~60% reduction in LLM calls per recursion level
- Native state visibility in parent graph
- Parallel execution of sub-tasks
- No redundant decomposition of already-scoped tasks
"""
from typing import Dict, Any, List
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from agents.subgraphs.state import WorkerState
from agents.workers.generic import generic_worker_node
from agents.evaluate_confidence import evaluate_confidence
from agents.dependencies import MAX_RECURSION_DEPTH, llm_mini
from agents.cost import CostTrackingCallback, CostTracker
import asyncio
import time
import json
import re


# --- LAZY SUBGRAPH REFERENCE (for recursive spawning) ---
_compiled_subgraph = None

def _get_compiled_subgraph():
    """
    Lazy getter for the compiled subgraph.
    Avoids circular reference at module load time.
    Called at runtime when recursion is needed.
    """
    global _compiled_subgraph
    if _compiled_subgraph is None:
        # This will be set after module loads (see bottom of file)
        pass
    return _compiled_subgraph


# --- LIGHTWEIGHT MINI-PLANNER ---

class MiniTask(BaseModel):
    """A single task in the mini execution plan."""
    id: str = Field(..., description="Unique task ID (e.g., 'research_oauth')")
    agent_type: str = Field(..., description="Agent type: Researcher, Coder, or Reviewer")
    instruction: str = Field(..., description="Specific instruction for this task")


class MiniPlan(BaseModel):
    """Lightweight execution plan - no dependencies, all parallel."""
    tasks: List[MiniTask] = Field(..., description="List of 2-4 parallel tasks")
    reasoning: str = Field(..., description="Brief explanation of the plan")


async def create_mini_plan(task: str, subject: str, root_task_id: str = None, config: RunnableConfig = None) -> MiniPlan:
    """
    Lightweight planner that creates 2-4 parallel tasks.
    Much simpler than full supervisor - no dependencies, no recursive flags.
    """
    plan_prompt = f"""You are a lightweight task planner. Break this task into 2-4 PARALLEL sub-tasks.

<subject>{subject}</subject>
<task>{task}</task>

RULES:
- Maximum 4 sub-tasks (prefer 2-3)
- All tasks run in PARALLEL (no dependencies)
- Each task should be completable by a single agent
- Agent types: Researcher (search/research), Coder (code/implementation), Reviewer (review/test)
- Keep instructions focused and specific

Output a JSON object with "tasks" array and "reasoning" string."""

    try:
        messages = [
            SystemMessage(content="You are a lightweight task planner. Output valid JSON only."),
            HumanMessage(content=plan_prompt)
        ]
        
        # Cost tracking - use root_task_id for consistent attribution
        cost_callback = CostTrackingCallback(task_id=root_task_id, node_name="mini_planner")
        llm_config: RunnableConfig = {"callbacks": [cost_callback]}
        
        structured_llm = llm_mini.with_structured_output(MiniPlan)
        plan = await structured_llm.ainvoke(messages, config=llm_config)
        
        # Record to global tracker
        tracker = CostTracker.get_instance()
        for record in cost_callback.records:
            tracker._add_record(record)
        print(f"💰 [mini_planner] Cost: ${cost_callback.get_total_cost():.6f}")
        
        return plan, cost_callback.to_usage_stats()
        
    except Exception as e:
        print(f"⚠️ [MiniPlanner] Failed to create plan: {e}")
        # Fallback: single research task
        return MiniPlan(
            tasks=[MiniTask(id="fallback_research", agent_type="Researcher", instruction=task)],
            reasoning=f"Fallback due to planning error: {e}"
        ), {}


async def execute_mini_plan(
    plan: MiniPlan, 
    state: WorkerState, 
    config: RunnableConfig = None,
    subgraph_ref = None,  # Lazy reference to avoid circular import
    initial_usage: Dict[str, float] = None
) -> Dict[str, Any]:
    """
    Execute all tasks in the mini-plan in parallel.
    
    RECURSIVE CAPABILITY:
    If a mini-task is itself complex (exceeds complexity threshold),
    it spawns a NEW worker_subgraph at depth+1 instead of direct execution.
    This enables multi-level decomposition without full app_graph overhead.
    
    Returns aggregated results and agent data.
    """
    parent_id = state.get("parent_node_id", "worker")
    current_depth = state.get("depth", 0)
    next_depth = current_depth + 1
    subject = state.get("subject", "")
    budget_config = state.get("budget_config") or {}
    usage_stats = state.get("usage_stats") or {}
    root_task_id = state.get("root_task_id", "")
    node_usage = initial_usage or {}
    
    print(f"🔀 [MiniOrchestrator] Executing {len(plan.tasks)} parallel tasks at depth {current_depth}...")
    
    async def run_single_task(mini_task: MiniTask) -> Dict[str, Any]:
        """
        Execute a single mini-task.
        
        If task is complex AND we haven't hit depth limit, spawn a new 
        worker_subgraph recursively. Otherwise, execute directly.
        """
        task_id = f"{parent_id}_{mini_task.id}"
        
        # Enrich with subject context
        enriched_instruction = mini_task.instruction
        if subject:
            enriched_instruction = f"<subject>{subject}</subject>\n\n<task>\n{mini_task.instruction}\n</task>"
        
        try:
            start_time = time.time()
            
            # Check if this child task needs its own subgraph
            can_recurse = next_depth < MAX_RECURSION_DEPTH and subgraph_ref is not None
            needs_sub_decomposition = False
            
            if can_recurse:
                needs_sub_decomposition = await should_decompose(mini_task.instruction, config, root_task_id=root_task_id)
            
            if needs_sub_decomposition:
                # --- RECURSIVE PATH: Spawn child worker_subgraph ---
                print(f"   ↳ [MiniTask {mini_task.id}] Complex, spawning child subgraph at depth {next_depth}")
                
                child_state = {
                    "task": mini_task.instruction,
                    "subject": subject,
                    "parent_node_id": task_id,
                    "root_task_id": root_task_id,
                    "depth": next_depth,
                    "results": {},
                    "all_agents": [],
                    "all_edges": [],
                    "global_signal": state.get("global_signal"),
                    "usage_stats": {}, # Child will return its own delta
                    "budget_config": {
                        **budget_config,
                        "external_cost": (state.get("usage_stats", {}).get("cost", 0.0) + 
                                         node_usage.get("cost", 0.0))
                    },
                }
                
                sub_result = await subgraph_ref.ainvoke(child_state, config)
                execution_time = time.time() - start_time
                
                # Extract output from nested results
                child_results = sub_result.get("results", {})
                output = child_results.get(task_id, str(child_results))
                child_agents = sub_result.get("all_agents", [])
                child_edges = sub_result.get("all_edges", [])
                
                return {
                    "task_id": mini_task.id,
                    "output": output,
                    "usage_stats": sub_result.get("usage_stats", {}),
                    "agent_data": {
                        "id": task_id,
                        "role": f"{mini_task.agent_type} (subgraph)",
                        "status": "completed",
                        "depth": current_depth,
                        "instruction": mini_task.instruction,
                        "output": output[:500] if len(output) > 500 else output,
                        "execution_time_seconds": round(execution_time, 2),
                        "spawned_children": len(child_agents),
                        "orchestration_mode": "recursive"
                    },
                    "child_agents": child_agents,
                    "child_edges": child_edges,
                    "error": None
                }
            
            else:
                # --- DIRECT PATH: Single worker execution ---
                worker_state = {
                    "depth": current_depth,
                    "subject": subject,
                    "budget_config": budget_config,
                    "usage_stats": usage_stats,
                    "root_task_id": root_task_id
                }
                
                result = await generic_worker_node(
                    worker_state, 
                    enriched_instruction, 
                    mini_task.agent_type, 
                    config
                )
                execution_time = time.time() - start_time
                
                output = result.get("output", "")
                meta = result.get("metadata", {})
                
                return {
                    "task_id": mini_task.id,
                    "output": output,
                    "usage_stats": result.get("usage_stats", {}),
                    "agent_data": {
                        "id": task_id,
                        "role": mini_task.agent_type,
                        "status": meta.get("status", "completed"),
                        "depth": current_depth,
                        "instruction": mini_task.instruction,
                        "output": output[:500] if len(output) > 500 else output,
                        "execution_time_seconds": round(execution_time, 2),
                        "tool_used": meta.get("tool_used"),
                        "confidence_score": meta.get("confidence_score", 0.5),
                        "orchestration_mode": "direct"
                    },
                    "child_agents": [],
                    "child_edges": [],
                    "error": None
                }
                
        except Exception as e:
            return {
                "task_id": mini_task.id,
                "output": f"[Error: {str(e)}]",
                "agent_data": {
                    "id": task_id,
                    "role": mini_task.agent_type,
                    "status": "error",
                    "depth": current_depth,
                    "instruction": mini_task.instruction,
                    "output": str(e)
                },
                "child_agents": [],
                "child_edges": [],
                "error": str(e)
            }
    
    # Execute all tasks in parallel
    results = await asyncio.gather(*[run_single_task(t) for t in plan.tasks])
    
    # Aggregate results (including recursive child results)
    all_outputs = {}
    all_agents = []
    all_edges = []
    usage_stats = {"steps": len(plan.tasks)}
    
    for r in results:
        all_outputs[r["task_id"]] = r["output"]
        all_agents.append(r["agent_data"])
        
        # Merge usage stats from this task
        task_usage = r.get("usage_stats", {})
        for key, val in task_usage.items():
            if key in usage_stats:
                usage_stats[key] += val
            else:
                usage_stats[key] = val
        
        # Include child agents/edges from recursive spawns
        all_agents.extend(r.get("child_agents", []))
        all_edges.extend(r.get("child_edges", []))
        
        # Create edge from parent to each child
        all_edges.append({
            "source": parent_id,
            "target": r["agent_data"]["id"],
            "depth": current_depth,
            "type": "hierarchy"
        })
    
    # Combine outputs into summary
    combined_output = "\n\n---\n\n".join([
        f"**{t_id}**:\n{output}" 
        for t_id, output in all_outputs.items()
    ])
    
    return {
        "output": combined_output,
        "all_agents": all_agents,
        "all_edges": all_edges,
        "usage_stats": usage_stats
    }


# --- COMPLEXITY ANALYSIS ---

async def should_decompose(task: str, config: RunnableConfig = None, root_task_id: str = None) -> bool:
    """
    Quick check if task needs decomposition into sub-tasks.
    Uses heuristics first, then LLM if uncertain.
    
    IMPORTANT: Tasks marked recursive:true by supervisor should ALWAYS
    pass through here and be decomposed. The supervisor already did
    high-level analysis - trust its judgment.
    
    Args:
        task: The task to analyze
        config: RunnableConfig for LLM calls
        root_task_id: Task ID for cost attribution
    """
    task_lower = task.lower()
    
    # Heuristic 1: Check for explicit multi-part indicators FIRST
    # These trump the length check
    strong_indicators = [
        "oauth", "jwt", "rbac", "authentication", "authorization",
        "multiple", "several", "components", "modules", "layers",
        "step 1", "step 2", "first,", "then,", "finally,",
        "1.", "2.", "3.",  # Numbered lists
    ]
    strong_matches = sum(1 for ind in strong_indicators if ind in task_lower)
    
    # If we have 2+ strong indicators, decompose regardless of length
    if strong_matches >= 2:
        print(f"   [should_decompose] TRUE - {strong_matches} strong indicators found")
        return True, {}
    
    # Heuristic 2: Conjunction complexity (multiple things joined by 'and')
    and_count = task_lower.count(" and ")
    if and_count >= 2:
        print(f"   [should_decompose] TRUE - {and_count} 'and' conjunctions (multi-part task)")
        return True, {}
    
    # Heuristic 3: Short tasks without indicators are simple
    if len(task) < 100 and strong_matches == 0:
        print(f"   [should_decompose] FALSE - short task ({len(task)} chars), no indicators")
        return False, {}
    
    # Heuristic 4: Additional weak indicators
    weak_indicators = [
        " with ", "frontend", "backend", "database", "api",
        "integration", "service", "system", "implement"
    ]
    weak_matches = sum(1 for ind in weak_indicators if ind in task_lower)
    
    total_matches = strong_matches + weak_matches
    if total_matches >= 3:
        print(f"   [should_decompose] TRUE - {total_matches} total indicators")
        return True, {}
    if total_matches == 0:
        print(f"   [should_decompose] FALSE - no complexity indicators")
        return False, {}
    
    # Uncertain (1-2 indicators) - use quick LLM check
    try:
        print(f"   [should_decompose] Uncertain ({total_matches} indicators), asking LLM...")
        check_prompt = f"""Does this task need to be broken into 2+ parallel sub-tasks, or can ONE agent handle it?

Task: {task[:500]}

Reply with ONLY "DECOMPOSE" or "SINGLE"."""
        
        messages = [
            SystemMessage(content="You classify task complexity. One word answer only."),
            HumanMessage(content=check_prompt)
        ]
        
        # Cost tracking - use root_task_id for consistent attribution
        cost_callback = CostTrackingCallback(task_id=root_task_id, node_name="complexity_check")
        llm_config: RunnableConfig = {"callbacks": [cost_callback]}
        
        response = await llm_mini.ainvoke(messages, config=llm_config)
        
        # Record to global tracker
        tracker = CostTracker.get_instance()
        for record in cost_callback.records:
            tracker._add_record(record)
        
        result = "DECOMPOSE" in response.content.upper()
        print(f"   [should_decompose] LLM says: {'DECOMPOSE' if result else 'SINGLE'}")
        return result, cost_callback.to_usage_stats()
        
    except Exception as e:
        print(f"   [should_decompose] LLM check failed: {e}, defaulting to FALSE")
        return False, {} # Default to simple on error


# --- MAIN EXECUTION NODE ---

async def execute_node(state: WorkerState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Smart execution node with lightweight orchestration.
    
    For simple tasks: Direct execution (1 LLM call)
    For complex tasks: Mini-plan + parallel execution (2-5 LLM calls)
    
    This is MUCH cheaper than full app_graph which costs 5-8 LLM calls.
    """
    task = state.get("task", "")
    subject = state.get("subject", "")
    parent_id = state.get("parent_node_id", "worker")
    current_depth = state.get("depth", 0)
    root_task_id = state.get("root_task_id")  # For cost attribution
    
    print(f"🔧 [WorkerSubgraph] Processing at depth {current_depth}: {task[:80]}...")
    
    # --- PRE-FLIGHT SAFETY CHECKS ---
    
    # 1. Global interrupt signal (Zombie Pruning)
    if state.get("global_signal") == "INTERRUPT":
        print(f"🛑 [WorkerSubgraph] Aborted due to global INTERRUPT signal.")
        return {
            "results": {parent_id: "[Aborted: Global interrupt signal]"},
            "all_agents": [{
                "id": parent_id,
                "role": "SubWorker",
                "status": "aborted",
                "depth": current_depth,
                "instruction": task,
                "output": ""
            }],
            "all_edges": []
        }
    
    # 2. Depth limit
    if current_depth >= MAX_RECURSION_DEPTH:
        print(f"🛑 [WorkerSubgraph] Depth limit reached ({current_depth} >= {MAX_RECURSION_DEPTH})")
        return {
            "results": {parent_id: f"[Depth limit reached: {current_depth}]"},
            "all_agents": [{
                "id": parent_id,
                "role": "SubWorker",
                "status": "depth_limited",
                "depth": current_depth,
                "instruction": task,
                "output": ""
            }],
            "all_edges": []
        }
    
    # 3. Budget check
    budget_config = state.get("budget_config") or {}
    usage_stats = state.get("usage_stats") or {}
    max_cost = budget_config.get("max_cost")
    current_cost = (budget_config.get("external_cost", 0.0) + 
                    usage_stats.get("cost", 0.0))
    
    if max_cost is not None and current_cost >= max_cost:
        print(f"💰 [WorkerSubgraph] Budget limit reached: ${current_cost:.2f}")
        return {
            "results": {parent_id: f"[Budget limit reached: ${current_cost:.2f}]"},
            "global_signal": "INTERRUPT",
            "all_agents": [{
                "id": parent_id,
                "role": "SubWorker",
                "status": "budget_exceeded",
                "depth": current_depth,
                "instruction": task,
                "output": ""
            }],
            "all_edges": []
        }
    
    # --- DECIDE EXECUTION PATH ---
    start_time = time.time()
    needs_decomposition, decomp_usage = await should_decompose(task, config, root_task_id=root_task_id)
    
    # Track node-local usage (deltas)
    node_usage = {}
    for k, v in decomp_usage.items():
        node_usage[k] = node_usage.get(k, 0) + v

    if needs_decomposition and current_depth < MAX_RECURSION_DEPTH - 1:
        # --- PATH A: MINI-ORCHESTRATION ---
        print(f"🔀 [WorkerSubgraph] Complex task detected, creating mini-plan...")
        
        plan, plan_usage = await create_mini_plan(task, subject, root_task_id=root_task_id, config=config)
        print(f"📋 [WorkerSubgraph] Plan: {len(plan.tasks)} tasks - {plan.reasoning[:50]}")
        
        # Merge planner usage
        for k, v in plan_usage.items():
            node_usage[k] = node_usage.get(k, 0) + v
        
        # Pass self-reference for recursive spawning capability
        # worker_subgraph is defined at module level, available after compilation
        result = await execute_mini_plan(plan, state, config, subgraph_ref=_get_compiled_subgraph(), initial_usage=node_usage)
        execution_time = time.time() - start_time
        
        # Create orchestrator agent record
        orchestrator_agent = {
            "id": parent_id,
            "role": "MiniOrchestrator",
            "status": "completed",
            "depth": current_depth,
            "instruction": task,
            "output": f"Orchestrated {len(plan.tasks)} sub-tasks",
            "execution_time_seconds": round(execution_time, 2),
            "orchestration_mode": "mini"
        }
        
        # Aggregate usage from mini-plan (mini-plan summary already includes all child usage)
        final_usage = dict(node_usage)
        for k, v in result["usage_stats"].items():
            final_usage[k] = final_usage.get(k, 0) + v

        return {
            "results": {parent_id: result["output"]},
            "usage_stats": final_usage,
            "all_agents": [orchestrator_agent] + result["all_agents"],
            "all_edges": result["all_edges"]
        }
    
    else:
        # --- PATH B: DIRECT EXECUTION ---
        print(f"⚡ [WorkerSubgraph] Simple task, direct execution...")
        
        enriched_task = task
        if subject:
            enriched_task = f"<subject>{subject}</subject>\n\n<task>\n{task}\n</task>"
        
        # root_task_id already extracted at start of function
        worker_state = {
            "depth": current_depth,
            "subject": subject,
            "budget_config": budget_config,
            "usage_stats": state.get("usage_stats", {}), # Pass current total for internal budget checks
            "root_task_id": root_task_id
        }
        
        try:
            result = await generic_worker_node(worker_state, enriched_task, "Researcher", config)
            output = result.get("output", str(result))
            meta = result.get("metadata", {})
            execution_time = time.time() - start_time
            
            agent_data = {
                "id": parent_id,
                "role": "SubWorker",
                "status": meta.get("status", "completed"),
                "depth": current_depth,
                "instruction": task,
                "output": output[:500] if len(output) > 500 else output,
                "execution_time_seconds": round(execution_time, 2),
                "tool_used": meta.get("tool_used"),
                "confidence_score": meta.get("confidence_score", 0.5),
                "orchestration_mode": "direct"
            }
            
            # Combine complexity check usage with worker usage
            final_usage = dict(node_usage)
            worker_usage = result.get("usage_stats", {})
            for k, v in worker_usage.items():
                final_usage[k] = final_usage.get(k, 0) + v
            
            # Ensure steps is incremented correctly (1 step for the worker)
            final_usage["steps"] = final_usage.get("steps", 0) + 1

            return {
                "results": {parent_id: output},
                "usage_stats": final_usage,
                "all_agents": [agent_data],
                "all_edges": []
            }
            
        except Exception as e:
            print(f"❌ [WorkerSubgraph] Execution error: {e}")
            return {
                "results": {parent_id: f"[Error: {str(e)}]"},
                "all_agents": [{
                    "id": parent_id,
                    "role": "SubWorker",
                    "status": "error",
                    "depth": current_depth,
                    "instruction": task,
                    "output": str(e)
                }],
                "all_edges": []
            }


async def validate_node(state: WorkerState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Validate the execution result using confidence evaluation.
    """
    parent_id = state.get("parent_node_id", "worker")
    results = state.get("results", {})
    task = state.get("task", "")
    root_task_id = state.get("root_task_id")
    
    output = results.get(parent_id, "")
    
    # Skip validation for error/abort states
    if not output or output.startswith("["):
        return {"confidence_score": 0.0, "confidence_reasoning": "Skipped: execution failed or aborted"}
    
    print(f"🔍 [WorkerSubgraph] Validating output quality...")
    
    try:
        evaluation, val_usage = await evaluate_confidence(task, output, config, root_task_id=root_task_id)
        return {
            "confidence_score": evaluation.get("confidence_score", 0.5),
            "confidence_reasoning": evaluation.get("confidence_reasoning", ""),
            "usage_stats": val_usage
        }
    except Exception as e:
        print(f"⚠️ [WorkerSubgraph] Validation error: {e}")
        return {"confidence_score": 0.5, "confidence_reasoning": f"Validation failed: {e}"}


# --- BUILD THE SUBGRAPH ---

def build_worker_subgraph() -> StateGraph:
    """
    Build the Worker Subgraph.
    
    Flow: START → execute → validate → END
    
    The execute node handles both simple and complex tasks internally,
    using mini-orchestration when needed instead of full app_graph.
    
    RECURSIVE SPAWNING:
    When execute_node creates a mini-plan, each child task can itself
    spawn a new worker_subgraph if it's complex enough. This is enabled
    by passing `_get_compiled_subgraph()` to `execute_mini_plan()`.
    """
    graph = StateGraph(WorkerState)
    
    graph.add_node("execute", execute_node)
    graph.add_node("validate", validate_node)
    
    graph.add_edge(START, "execute")
    graph.add_edge("execute", "validate")
    graph.add_edge("validate", END)
    
    return graph


# Pre-compiled subgraph for reuse
worker_subgraph = build_worker_subgraph().compile()

# Register the compiled subgraph for recursive spawning
_compiled_subgraph = worker_subgraph
