from typing import Dict, Any, Annotated, List
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from core.state.orchestrator_state import AgentState, replace, merge_lists
from agents.task_executor import task_executor_node
from schemas.blueprint import AppBlueprint, AgentInfo, EdgeInfo
from core.persistence import checkpointer
from agents.recursive_executor import recursive_executor
from core.state.worker_state import WorkerState
from config.settings import MAX_RECURSION_DEPTH
from langgraph.types import interrupt, Command
import json
import uuid
import os
from datetime import datetime

async def graph_executor_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Builds and executes a dynamic LangGraph based on the graph_plan.
    Extracts execution blueprint with system prompts for visualization.
    """
    plan = state.get("graph_plan", {})
    nodes = plan.get("nodes", [])
    task = state.get("task", "Unknown Task")
    
    if not nodes:
        print("⚠️ No nodes in plan to execute.")
        return {}
        
    # --- 1. COMPILE GRAPH (Deterministic based on plan) ---
    # We re-compile every time, but since it's the same plan, it's fine.
    # The inner graph uses the SAME AgentState as the outer graph.
    workflow = StateGraph(AgentState)
    blueprint_edges = []

    # Add Nodes
    for node in nodes:
        node_id = node["id"]
        instruction = node["instruction"]
        agent_type = node["agent_type"]
        dependencies = node.get("dependencies", [])
        is_recursive = node.get("recursive", False)
        
        if is_recursive:
            # RECURSIVE NODE: Use native WorkerSubgraph (Epic 4.1)
            # This is a lightweight subgraph that SKIPS semantic_splitter and supervisor
            # It uses mini-planning internally if the task needs decomposition
            async def _recursive_node_fn(s: AgentState, config: RunnableConfig, _instr=instruction, _id=node_id, _deps=dependencies):
                current_depth = s.get("depth", 0)
                budget_config = s.get("budget_config") or {}
                usage_stats = s.get("usage_stats") or {}
                
                # --- PRE-FLIGHT SAFETY CHECKS ---
                # 1. Zombie Pruning: Check if a sibling has signaled an interrupt
                if s.get("global_signal") == "INTERRUPT":
                    print(f"🛑 [SafetyCheck] Recursive node '{_id}' aborted due to global INTERRUPT signal.")
                    return {
                        "results": {_id: "[Aborted: Sibling branch triggered interrupt]"},
                        "metadata": {_id: {"status": "aborted", "agent_role": "SubOrchestrator"}},
                        "all_agents": [{"id": _id, "role": "SubOrchestrator", "status": "aborted", "depth": current_depth, "instruction": _instr, "output": ""}],
                        "all_edges": []
                    }

                # 2. Budget Check
                max_cost = budget_config.get("max_cost")
                current_cost = usage_stats.get("cost", 0.0)

                if max_cost is not None and current_cost >= max_cost:
                    print(f"💰 [SafetyCheck] Budget limit reached before recursive node '{_id}'.")
                    return {
                        "results": {_id: f"[Budget Limit Reached: ${current_cost:.2f}]"},
                        "metadata": {_id: {"status": "budget_exceeded", "agent_role": "SubOrchestrator"}},
                        "global_signal": "INTERRUPT",
                        "all_agents": [{"id": _id, "role": "SubOrchestrator", "status": "budget_exceeded", "depth": current_depth, "instruction": _instr, "output": ""}],
                        "all_edges": []
                    }

                # 3. Depth Check
                print(f"🔄 [RecursiveNode] Native WorkerSubgraph for: {_instr[:50]}... (Depth: {current_depth})")
                
                if current_depth >= MAX_RECURSION_DEPTH:
                    print(f"🛑 [RecursiveNode] Depth limit reached ({current_depth} >= {MAX_RECURSION_DEPTH})")
                    return {
                        "results": {_id: f"[Depth limit reached: {current_depth}]"},
                        "metadata": {_id: {"agent_role": "Skipped"}},
                        "all_agents": [{"id": _id, "role": "SubOrchestrator", "status": "depth_limited", "depth": current_depth, "instruction": _instr, "output": ""}],
                        "all_edges": [],
                        "usage_stats": {"steps": 1}
                    }
                
                # --- BUILD CONTEXT FROM DEPENDENCIES ---
                context_parts = []
                results = s.get("results", {})
                if _deps:
                    for dep_id in _deps:
                        if dep_id in results:
                            dep_output = results[dep_id]
                            truncated = dep_output[:2000] + "..." if len(dep_output) > 2000 else dep_output
                            context_parts.append(f"<input_data source=\"{dep_id}\">\n{truncated}\n</input_data>")
                
                if context_parts:
                    enriched_task = "\n".join(context_parts) + f"\n\n<task>{_instr}</task>"
                else:
                    enriched_task = f"<task>{_instr}</task>"
                
                # Extract root_task_id for cost attribution
                # Prefer root_task_id from state (passed down from parent), fall back to config
                root_task_id = s.get("root_task_id") or (config.get("configurable", {}).get("thread_id", "") if config else "")
                
                # --- INVOKE NATIVE WORKER SUBGRAPH ---
                # Uses lightweight mini-planner instead of full app_graph
                # Flow: execute (with optional mini-plan) → validate
                sub_state: WorkerState = {
                    "task": enriched_task,
                    "subject": s.get("subject", ""),
                    "parent_node_id": _id,
                    "root_task_id": root_task_id,
                    "depth": current_depth + 1,
                    "results": {},
                    "all_agents": [],
                    "all_edges": [],
                    "global_signal": s.get("global_signal", ""),
                    "usage_stats": {}, # Use empty for subgraph to return ONLY the delta
                    "budget_config": {
                        **(s.get("budget_config") or {}),
                        "external_cost": (s.get("usage_stats") or {}).get("cost", 0.0)
                    },
                    "confidence_score": 0.0,
                    "confidence_reasoning": ""
                }
                
                try:
                    final_sub_state = await recursive_executor.ainvoke(sub_state, config=config)
                except Exception as e:
                    print(f"❌ [RecursiveNode] RecursiveExecutor failed: {e}")
                    return {
                        "results": {_id: f"[Subgraph error: {str(e)}]"},
                        "metadata": {_id: {"status": "error", "agent_role": "SubOrchestrator"}},
                        "all_agents": [{"id": _id, "role": "SubOrchestrator", "status": "error", "depth": current_depth, "instruction": _instr, "output": str(e)}],
                        "all_edges": [],
                        "usage_stats": {"steps": 1}
                    }
                
                # --- EXTRACT RESULTS ---
                sub_results = final_sub_state.get("results", {})
                sub_agents = final_sub_state.get("all_agents", [])
                sub_edges = final_sub_state.get("all_edges", [])
                sub_usage = final_sub_state.get("usage_stats", {})
                confidence = final_sub_state.get("confidence_score", 0.5)
                
                # Get output from results (keyed by parent_node_id)
                result_output = sub_results.get(_id, str(sub_results))
                
                # Build hierarchy edges connecting parent to child agents
                # Build hierarchy edges connecting parent to DIRECT child agents only
                hierarchy_edges = []
                # sub_agents contains ALL descendants (flattened). 
                # We only want to draw edges to immediate children (depth + 1) to form a tree.
                # Grandchildren will have edges from their respective parents in sub_edges.
                
                seen_child_ids = set()
                for sub_agent in sub_agents:
                    # Set parent node for compound node rendering (avoid self-parenting)
                    if sub_agent["id"] != _id:
                        # Backend logic: Propagate parent ID to all descendants for compound node grouping if needed
                        if "parent" not in sub_agent or not sub_agent["parent"]:
                            sub_agent["parent"] = _id

                        # Visualization logic: Only draw EDGE to direct children
                        # (Check depth to avoid connecting to grandchildren)
                        # Also prevent duplicate edges if sub_agents has duplicate IDs (e.g. status updates)
                        if sub_agent.get("depth") == current_depth + 1:
                            if sub_agent["id"] not in seen_child_ids:
                                hierarchy_edges.append({
                                    "source": _id, 
                                    "target": sub_agent["id"],
                                    "depth": current_depth, 
                                    "type": "hierarchy"
                                })
                                seen_child_ids.add(sub_agent["id"])


                # Create parent orchestrator agent record
                parent_agent = {
                    "id": _id, 
                    "role": "SubOrchestrator",
                    "instruction": _instr, 
                    "output": result_output[:500] if len(result_output) > 500 else result_output,
                    "tools": [], 
                    "depth": current_depth,
                    "status": "completed",
                    "confidence_score": confidence
                }
                
                # Propagate usage from subgraph (Properly merge all keys)
                usage_update = {"steps": 1}
                for key, val in sub_usage.items():
                    if key in usage_update:
                        usage_update[key] += val
                    else:
                        usage_update[key] = val
                
                # Check if subgraph triggered interrupt
                global_signal = final_sub_state.get("global_signal", "")

                return_data = {
                    "results": {_id: result_output},
                    "metadata": {_id: {"agent_role": "SubOrchestrator", "confidence_score": confidence, "cost_usd": sub_usage.get("cost", 0.0)}},
                    "all_agents": sub_agents + [parent_agent],
                    "all_edges": hierarchy_edges + sub_edges,
                    "usage_stats": usage_update
                }
                
                if global_signal:
                    return_data["global_signal"] = global_signal
                    
                return return_data
            
            workflow.add_node(node_id, _recursive_node_fn)
        else:
            # NORMAL AGENT NODE
            async def _node_fn(s: AgentState, config: RunnableConfig, _instr=instruction, _type=agent_type, _id=node_id, _deps=dependencies):
                # --- PRE-FLIGHT SAFETY CHECKS ---
                # 1. Zombie Pruning: Check if a sibling has signaled an interrupt
                if s.get("global_signal") == "INTERRUPT":
                    print(f"🛑 [SafetyCheck] Node '{_id}' aborted due to global INTERRUPT signal.")
                    return {
                        "results": {_id: "[Aborted: Sibling branch triggered interrupt]"},
                        "metadata": {_id: {"status": "aborted", "agent_role": _type}},
                        "all_agents": [{"id": _id, "role": _type, "status": "aborted", "depth": s.get("depth", 0), "instruction": _instr, "output": ""}],
                        "all_edges": []
                    }

                # 2. Budget Check: Verify cost hasn't exceeded limit
                budget_config = s.get("budget_config") or {}
                usage_stats = s.get("usage_stats") or {}
                max_cost = budget_config.get("max_cost")
                max_steps = budget_config.get("max_steps")
                current_cost = usage_stats.get("cost", 0.0)
                current_steps = usage_stats.get("steps", 0)

                if max_cost is not None and current_cost >= max_cost:
                    print(f"💰 [SafetyCheck] Budget limit reached (${current_cost:.2f} >= ${max_cost:.2f}). Triggering interrupt.")
                    interrupt_data = {"type": "tier3_interrupt", "reason": "budget_exceeded", "current_cost": current_cost, "max_cost": max_cost}
                    return {
                        "results": {_id: f"[Budget Limit Reached: ${current_cost:.2f}]"},
                        "metadata": {_id: {"status": "budget_exceeded", "agent_role": _type}},
                        "global_signal": "INTERRUPT",
                        "all_agents": [{"id": _id, "role": _type, "status": "budget_exceeded", "depth": s.get("depth", 0), "instruction": _instr, "output": ""}],
                        "all_edges": []
                    }

                if max_steps is not None and current_steps >= max_steps:
                    print(f"🔢 [SafetyCheck] Max steps limit reached ({current_steps} >= {max_steps}). Triggering interrupt.")
                    return {
                        "results": {_id: f"[Max Steps Limit Reached: {current_steps}]"},
                        "metadata": {_id: {"status": "max_steps_exceeded", "agent_role": _type}},
                        "global_signal": "INTERRUPT",
                        "all_agents": [{"id": _id, "role": _type, "status": "max_steps_exceeded", "depth": s.get("depth", 0), "instruction": _instr, "output": ""}],
                        "all_edges": []
                    }

                # --- EXECUTE NODE ---
                context_parts = []
                results = s.get("results", {})
                if _deps:
                    for dep_id in _deps:
                        if dep_id in results:
                            dep_output = results[dep_id]
                            truncated = dep_output[:2000] + "..." if len(dep_output) > 2000 else dep_output
                            context_parts.append(f"<input_data source=\"{dep_id}\">\n{truncated}\n</input_data>")
                            
                subject = s.get("subject", "")
                subject_block = f"<input_data type=\"subject\">{subject}</input_data>\n" if subject else ""
                enriched_instruction = f"{subject_block}" + "\n".join(context_parts) + f"\n\n<task>{_instr}</task>"
                
                result = await task_executor_node(s, enriched_instruction, _type, config)
                
                meta = result.get("metadata", {})
                current_depth = s.get("depth", 0)
                agent_data = {
                    "id": _id,
                    "role": meta.get("agent_role", _type),
                    "system_prompt": meta.get("system_prompt", ""),
                    "instruction": _instr,
                    "output": result["output"],
                    "tools": meta.get("tools", []),
                    "depth": current_depth,
                    "status": meta.get("status", "completed")
                }
                # Transfer other metadata fields
                for key in ["execution_time_seconds", "tool_used", "tools_available", "error_message", "confidence_score", "confidence_reasoning", "low_confidence_flag", "warning"]:
                    if key in meta:
                        agent_data[key] = meta[key]

                # Use actual cost tracked by callback if available
                step_cost = meta.get("cost_usd") or meta.get("estimated_cost", 0.0)
                usage_update = {"steps": 1, "cost": step_cost}
                
                # Merge full usage stats from result (tokens, calls, etc)
                if "usage_stats" in result:
                    for key, val in result["usage_stats"].items():
                        if key != "steps": # handled above
                            usage_update[key] = val
                
                # --- TIER 2 WARNING: Budget approaching limit ---
                warning_message = None
                new_cost = current_cost + step_cost
                if max_cost is not None and new_cost > max_cost * 0.8:
                    warning_message = f"Budget Warning: {(new_cost / max_cost * 100):.0f}% used (${new_cost:.2f}/${max_cost:.2f})"
                    print(f"⚠️ [Tier2Warning] {warning_message}")

                # Check if this node triggered a Tier 3 interrupt (low confidence)
                node_return = {
                    "results": {_id: result["output"]},
                    "metadata": {_id: meta},
                    "all_agents": [agent_data],
                    "all_edges": [],
                    "usage_stats": usage_update
                }
                
                # Attach warning to agent_data if present
                if warning_message:
                    agent_data["warning"] = warning_message

                # If low confidence, set global signal to pause siblings
                if meta.get("low_confidence_flag"):
                    print(f"⚠️ [SafetyCheck] Node '{_id}' flagged low confidence. Setting global INTERRUPT signal.")
                    node_return["global_signal"] = "INTERRUPT"

                return node_return
                
            workflow.add_node(node_id, _node_fn)
    
    # Add Edges
    nodes_with_parents = set()
    for node in nodes:
        node_id = node["id"]
        dependencies = node.get("dependencies", [])
        if dependencies:
            for parent_id in dependencies:
                if any(n["id"] == parent_id for n in nodes):
                    workflow.add_edge(parent_id, node_id)
                    nodes_with_parents.add(node_id)
                    blueprint_edges.append(EdgeInfo(source=parent_id, target=node_id))
        
    for node in nodes:
        if node["id"] not in nodes_with_parents:
            workflow.add_edge(START, node["id"])
            
    parent_ids = set()
    for node in nodes:
        for dep in node.get("dependencies", []):
            parent_ids.add(dep)
            
    for node in nodes:
        if node["id"] not in parent_ids:
            workflow.add_edge(node["id"], END)
            
    # --- SAVE BLUEPRINT SNAPSHOT ---
    try:
        run_id = config.get("configurable", {}).get("thread_id", str(uuid.uuid4()))
        blueprint_agents = []
        for node in nodes:
            blueprint_agents.append(AgentInfo(
                id=node["id"],
                role=node["agent_type"],
                system_prompt="[Pending Execution]",
                instruction=node["instruction"],
                tools=[],
                parent=None
            ))
        
        blueprint = AppBlueprint(
            run_id=run_id,
            task=task,
            agents=blueprint_agents,
            edges=blueprint_edges,
            execution_flow=[n["id"] for n in nodes],
            timestamp=datetime.now().isoformat(),
            depth=state.get("depth", 0)
        )
        
        os.makedirs("blueprints", exist_ok=True)
        with open(f"blueprints/{run_id}.json", "w") as f:
            f.write(blueprint.model_dump_json())
        print(f"📄 Blueprint saved to blueprints/{run_id}.json")
    except Exception as e:
        print(f"⚠️ Failed to save blueprint: {e}")
            
    # Compile with SHARED memory (accessed at runtime after initialization)
    app = workflow.compile(checkpointer=checkpointer.get_checkpointer())
    
    # --- 2. MANAGE INNER STATE ---
    # Retrieve or Create Persistent Thread ID
    inner_thread_id = state.get("inner_thread_id")
    if not inner_thread_id:
        inner_thread_id = str(uuid.uuid4())
        print(f"🆕 Initializing new inner graph thread: {inner_thread_id}")
    else:
        print(f"🔄 Resuming existing inner graph thread: {inner_thread_id}")
        
    inner_config = {"configurable": {"thread_id": inner_thread_id}}
    
    # helper for aggregation
    def _aggregate_graph_data(inner_state_data: Dict[str, Any]):
        # Data is already aggregated by nodes during execution
        return inner_state_data.get("all_agents", []), inner_state_data.get("all_edges", [])

    # --- 3. MAIN EXECUTION LOOP ---
    # Use a while loop to handle execution, but RETURN a Command after interrupt
    # to persist the inner_thread_id in the outer graph state
    while True:
        inner_state = await app.aget_state(inner_config)
        
        if inner_state.next:
            # --- INTERRUPT PATH: Inner graph is paused ---
            print(f"⏸️ Inner graph paused at: {inner_state.next}. Bubbling up interrupt...")
            
            # 🔍 [Interrupt Debug] Log inner graph interrupt details
            print(f"🔍 [Interrupt Debug] Inner Graph Interrupt:")
            print(f"   - Paused nodes: {list(inner_state.next)}")
            print(f"   - Depth: {state.get('depth', 0)}")
            
            # 1. Aggregate State
            agg_agents, agg_edges = _aggregate_graph_data(inner_state.values)
            inner_interrupts = [t.interrupts for t in inner_state.tasks if t.interrupts] if inner_state.tasks else []
            
            # 🔍 [Interrupt Debug] Log interrupt objects found
            if inner_interrupts:
                interrupt_count = sum(len(i_list) for i_list in inner_interrupts)
                print(f"   - Inner interrupts found: {interrupt_count}")
                for i_list in inner_interrupts:
                    for i in i_list:
                        if hasattr(i, 'id'):
                            print(f"     • Interrupt ID: {i.id}")
            
            confidence_score = 0.0
            confidence_reasoning = ""
            
            # CRITICAL FIX: Process ALL interrupted agents, not just the first one
            paused_nodes = list(inner_state.next) if inner_state.next else []
            if inner_interrupts:
                for idx, i_list in enumerate(inner_interrupts):
                    for i in i_list:
                        val = i.value if hasattr(i, "value") else i
                        if isinstance(val, dict) and val.get("type") == "tier3_interrupt":
                            # Get the corresponding paused node ID for this interrupt
                            agent_id = paused_nodes[idx] if idx < len(paused_nodes) else val.get("agent_id", f"node_{idx+1}")
                            
                            # Use the first interrupt's confidence for the main interrupt event
                            if confidence_score == 0.0:
                                confidence_score = val.get("confidence_score", 0.0)
                                confidence_reasoning = val.get("reasoning", "")
                            
                            agent_data = {
                                "id": agent_id,
                                "role": val.get("agent_type", "Unknown"),
                                "status": "review_required",
                                "output": val.get("current_output", ""),
                                "confidence_score": val.get("confidence_score", 0.0),
                                "confidence_reasoning": val.get("reasoning", ""),
                                "depth": state.get("depth", 0)
                            }
                            
                            # Add instruction from nodes list
                            for n in nodes:
                                if n["id"] == agent_id:
                                    agent_data["instruction"] = n["instruction"]
                                    break
                            
                            # Update or Add the agent
                            found = False
                            for agent in agg_agents:
                                if agent["id"] == agent_id:
                                    agent.update(agent_data)
                                    found = True
                                    break
                            if not found:
                                agg_agents.append(agent_data)


            interrupt_data = {
                "type": "inner_graph_interrupt",
                "paused_at": list(inner_state.next),
                "inner_interrupts": inner_interrupts,
                "all_agents": agg_agents,
                "all_edges": agg_edges,
                "confidence_score": confidence_score,
                "confidence_reasoning": confidence_reasoning,
                "inner_thread_id": inner_thread_id  # Include for reference
            }
            
            # 2. INTERRUPT - This suspends execution and bubbles up to outer graph
            resume_value = interrupt(interrupt_data)
            
            # === AFTER RESUME: Outer graph called us again with the resume value ===
            # This code executes when the outer graph resumes and calls graph_executor again
            print(f"🔍 [Interrupt Debug] Inner Graph Resume value received:")
            print(f"   - Type: {type(resume_value)}")
            print(f"   - Value: {resume_value}")
            print(f"✅ Outer graph resumed with: {resume_value}")
            
            # 3. RESUME INNER GRAPH with the resume value
            resume_payload = resume_value
            all_interrupt_objs = []
            if inner_interrupts:
                for i_tuple in inner_interrupts:
                    for i_obj in i_tuple:
                        all_interrupt_objs.append(i_obj)
            
            if all_interrupt_objs:
                 resume_payload = {i.id: resume_value for i in all_interrupt_objs}
            
            try:
                await app.ainvoke(Command(resume=resume_payload), config=inner_config)
            except Exception as e:
                from langgraph.errors import GraphBubbleUp
                if isinstance(e, GraphBubbleUp) or "Interrupt" in type(e).__name__:
                    print(f"⏸️ Inner graph raised Interrupt during resumed execution.")
                else:
                    raise e
            
            # Continue loop to check for more interrupts after inner graph processes resume
            continue
        
        elif not inner_state.values:
            # --- START PATH: Inner graph hasn't started yet ---
            print("▶️ Starting new Dynamic Graph Execution...")
            initial_dynamic_state = {
                "results": {},
                "depth": state.get("depth", 0),
                "subject": state.get("subject", ""),
                "metadata": {},
                # Add horizontal edges to the initial state
                "all_agents": [],
                "all_edges": [
                    # Dynamic edges
                    {"source": e.source, "target": e.target, "depth": state.get("depth", 0)} for e in blueprint_edges
                ] + [
                    # Connect Supervisor to Roots (Nodes with no dependencies in the plan)
                    {"source": "supervisor", "target": node["id"], "depth": state.get("depth", 0)}
                     for node in nodes if not node.get("dependencies")
                ],
                # Pass budget config and usage stats for enforcement
                "usage_stats": {}, # Start empty to return only the delta
                "budget_config": {
                    **(state.get("budget_config") or {}),
                    "external_cost": (state.get("usage_stats") or {}).get("cost", 0.0)
                },
                "root_task_id": state.get("root_task_id")
            }
            try:
                await app.ainvoke(initial_dynamic_state, config=inner_config)
            except Exception as e:
                from langgraph.errors import GraphBubbleUp
                if isinstance(e, GraphBubbleUp) or "Interrupt" in type(e).__name__:
                    print(f"⏸️ Inner graph raised Initial Interrupt.")
                else:
                    raise e
            
            # Continue loop to check state after initial execution
            continue
        
        else:
            # --- COMPLETION PATH: Inner graph is done ---
            print("✅ Dynamic Graph Execution Complete.")
            combined_agents, combined_edges = _aggregate_graph_data(inner_state.values)
            
            return {
                "results": inner_state.values.get("results", {}), 
                "metadata": inner_state.values.get("metadata", {}),
                "all_agents": combined_agents,
                "all_edges": combined_edges,
                "inner_thread_id": inner_thread_id,
                "usage_stats": inner_state.values.get("usage_stats", {}),
                "global_signal": inner_state.values.get("global_signal", "")
            }

