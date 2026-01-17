from typing import Dict, Any, Annotated, TypedDict, List
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from agents.state import AgentState
from agents.workers.generic import generic_worker_node
from agents.blueprint import AppBlueprint, AgentInfo, EdgeInfo
from agents.shared_memory import memory
from langgraph.types import interrupt, Command
import json
import uuid
import os
from datetime import datetime

def merge_dicts(a: Dict, b: Dict) -> Dict:
    return {**a, **b}

def merge_lists(a: list, b: list) -> list:
    return a + b

def replace(a: Any, b: Any) -> Any:
    return b

class DynamicState(TypedDict):
    # Use a reducer to allow parallel updates to merge
    results: Annotated[Dict[str, str], merge_dicts]
    depth: Annotated[int, replace]
    subject: str  # Primary subject for drift prevention
    metadata: Annotated[Dict[str, Dict], merge_dicts] # Capture agent metadata
    all_agents: Annotated[list, merge_lists] # Aggregated agents from all subgraphs
    all_edges: Annotated[list, merge_lists] # Aggregated edges from all subgraphs
    inner_thread_id: Annotated[str, replace] # Persist inner graph thread ID

async def graph_compiler_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Compiles and executes a dynamic LangGraph based on the graph_plan.
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
    # The state is stored in the checkpointer.
    workflow = StateGraph(DynamicState)
    blueprint_edges = []

    # Add Nodes
    for node in nodes:
        node_id = node["id"]
        instruction = node["instruction"]
        agent_type = node["agent_type"]
        dependencies = node.get("dependencies", [])
        is_recursive = node.get("recursive", False)
        
        if is_recursive:
            # RECURSIVE NODE: Spawn full sub-orchestration
            async def _recursive_node_fn(s: DynamicState, config: RunnableConfig, _instr=instruction, _id=node_id, _deps=dependencies):
                from agent import app_graph
                from agents.dependencies import MAX_RECURSION_DEPTH
                current_depth = s.get("depth", 0)
                print(f"🔄 [RecursiveNode] Spawning sub-orchestration for: {_instr[:50]}... (Depth: {current_depth})")
                
                if current_depth >= MAX_RECURSION_DEPTH:
                    return {
                        "results": {_id: f"[Depth limit reached]"},
                        "metadata": {_id: {"agent_role": "Skipped"}},
                        "all_agents": [], "all_edges": []
                    }
                
                context_parts = []
                results = s.get("results", {})
                if _deps:
                    for dep_id in _deps:
                        if dep_id in results:
                            dep_output = results[dep_id]
                            truncated = dep_output[:2000] + "..." if len(dep_output) > 2000 else dep_output
                            context_parts.append(f"<input_data source=\"{dep_id}\">\n{truncated}\n</input_data>")
                
                sub_state = {
                    "task": _instr + ("\n\nContext:\n" + "\n".join(context_parts) if context_parts else ""),
                    "subtasks": [], "graph_plan": {}, "results": {},
                    "depth": current_depth + 1,
                    "subject": s.get("subject", ""),
                    "all_agents": [], "all_edges": []
                }
                
                if config:
                    final_sub_state = await app_graph.ainvoke(sub_state, config=config)
                else:
                    final_sub_state = await app_graph.ainvoke(sub_state)
                
                sub_results = final_sub_state.get("results", {})
                sub_agents = final_sub_state.get("all_agents", [])
                sub_edges = final_sub_state.get("all_edges", [])
                synthesis = final_sub_state.get("synthesis", "")
                result_summary = synthesis if synthesis else str(sub_results)
                
                hierarchy_edges = []
                sub_depth = current_depth + 1
                root_sub_agents = [a for a in sub_agents if a.get("depth") == sub_depth]
                for root_agent in root_sub_agents:
                    hierarchy_edges.append({
                        "source": _id, "target": root_agent["id"],
                        "depth": current_depth, "type": "hierarchy"
                    })

                parent_agent = {
                    "id": _id, "role": "SubOrchestrator",
                    "instruction": _instr, "output": result_summary,
                    "tools": [], "depth": current_depth
                }
                
                return {
                    "results": {_id: result_summary},
                    "metadata": {_id: {"agent_role": "SubOrchestrator"}},
                    "all_agents": [parent_agent] + sub_agents,
                    "all_edges": hierarchy_edges + sub_edges
                }
            
            workflow.add_node(node_id, _recursive_node_fn)
        else:
            # NORMAL NODE
            async def _node_fn(s: DynamicState, config: RunnableConfig, _instr=instruction, _type=agent_type, _id=node_id, _deps=dependencies):
                context_parts = []
                results = s.get("results", {})
                if _deps:
                    for dep_id in _deps:
                        if dep_id in results:
                            dep_output = results[dep_id]
                            truncated = dep_output[:2000] + "..." if len(dep_output) > 2000 else dep_output
                            context_parts.append(f"<input_data source=\"{dep_id}\">\n{truncated}\n</input_data>")
                            
                subject = s.get("subject", "")
                subject_block = f"<subject>{subject}</subject>\n" if subject else ""
                enriched_instruction = f"{subject_block}" + "\n".join(context_parts) + f"\n\n<task>\n{_instr}\n</task>"
                
                result = await generic_worker_node(s, enriched_instruction, _type, config)
                return {
                    "results": {_id: result["output"]},
                    "metadata": {_id: result.get("metadata", {})},
                    "all_agents": result.get("nested_agents", []),
                    "all_edges": result.get("nested_edges", [])
                }
                
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
            
    # Compile with SHARED memory
    app = workflow.compile(checkpointer=memory)
    
    # --- 2. MANAGE INNER STATE ---
    # Retrieve or Create Persistent Thread ID
    inner_thread_id = state.get("inner_thread_id")
    if not inner_thread_id:
        inner_thread_id = str(uuid.uuid4())
        print(f"🆕 Initializing new inner graph thread: {inner_thread_id}")
    else:
        print(f"🔄 Resuming existing inner graph thread: {inner_thread_id}")
        
    inner_config = {"configurable": {"thread_id": inner_thread_id}}
    
    # helper for aggregation (same as before)
    def _aggregate_graph_data(inner_state_data: Dict[str, Any]):
        current_depth = state.get("depth", 0)
        execution_metadata = inner_state_data.get("metadata", {})
        new_agents = []
        for node in nodes:
            nid = node["id"]
            if nid in execution_metadata:
                meta = execution_metadata[nid]
                agent_data = {
                    "id": nid,
                    "role": meta.get("agent_role", node["agent_type"]),
                    "system_prompt": meta.get("system_prompt", ""),
                    "instruction": node["instruction"],
                    "output": inner_state_data.get("results", {}).get(nid, ""),
                    "tools": meta.get("tools", []),
                    "depth": current_depth
                }
                for key in ["status", "execution_time_seconds", "tool_used", "tools_available", "error_message", "confidence_score", "confidence_reasoning"]:
                    if key in meta:
                        agent_data[key] = meta[key]
                new_agents.append(agent_data)
        new_edges = [{"source": e.source, "target": e.target, "depth": current_depth} for e in blueprint_edges]
        return new_agents + inner_state_data.get("all_agents", []), new_edges + inner_state_data.get("all_edges", [])

    # --- 3. CHECK FOR RESUME or START ---
    # Check if we are resuming from a pause
    inner_state = await app.aget_state(inner_config)
    
    if inner_state.next:
        # --- RESUME PATH ---
        print(f"⏸️ Inner graph paused at: {inner_state.next}. Bubbling up interrupt...")
        
        # 1. Aggregate State
        agg_agents, agg_edges = _aggregate_graph_data(inner_state.values)
        inner_interrupts = [t.interrupts for t in inner_state.tasks if t.interrupts] if inner_state.tasks else []
        
        confidence_score = 0.0
        confidence_reasoning = ""
        current_agent_data = None
        
        if inner_interrupts:
            for i_list in inner_interrupts:
                for i in i_list:
                    val = i.value if hasattr(i, "value") else i
                    if isinstance(val, dict) and val.get("type") == "tier3_interrupt":
                        confidence_score = val.get("confidence_score", 0.0)
                        confidence_reasoning = val.get("reasoning", "")
                        current_agent_data = {
                            "id": list(inner_state.next)[0] if inner_state.next else "unknown",
                            "role": val.get("agent_type", "Unknown"),
                            "status": "review_required",
                            "output": val.get("current_output", ""),
                            "confidence_score": confidence_score,
                            "confidence_reasoning": confidence_reasoning
                        }
                        # Add prompt info if possible
                        for n in nodes:
                            if n["id"] == current_agent_data["id"]:
                                current_agent_data["instruction"] = n["instruction"]
                                break
                        current_agent_data["depth"] = state.get("depth", 0)
                        break
        
        if current_agent_data:
            # Merge into agg_agents
            found = False
            for agent in agg_agents:
                if agent["id"] == current_agent_data["id"]:
                    agent.update(current_agent_data)
                    found = True
                    break
            if not found:
                agg_agents.append(current_agent_data)

        interrupt_data = {
            "type": "inner_graph_interrupt",
            "paused_at": list(inner_state.next),
            "inner_interrupts": inner_interrupts,
            "all_agents": agg_agents,
            "all_edges": agg_edges,
            "confidence_score": confidence_score,
            "confidence_reasoning": confidence_reasoning
        }
        
        # 2. INTERRUPT (Suspend Outer Graph)
        resume_value = interrupt(interrupt_data)
        
        print(f"✅ Outer graph resumed with: {resume_value}")
        
        # 3. RESUME INNER GRAPH
        resume_payload = resume_value
        all_interrupt_objs = []
        if inner_interrupts:
            for i_tuple in inner_interrupts:
                for i_obj in i_tuple:
                    all_interrupt_objs.append(i_obj)
        
        if all_interrupt_objs:
             # Map decisions to all interrupts
             resume_payload = {i.id: resume_value for i in all_interrupt_objs}
        
        try:
            await app.ainvoke(Command(resume=resume_payload), config=inner_config)
        except Exception as e:
            from langgraph.errors import GraphBubbleUp
            if isinstance(e, GraphBubbleUp) or "Interrupt" in type(e).__name__:
                print(f"⏸️ Inner graph raised Interrupt during resumed execution.")
            else:
                raise e
    
    else:
        # --- START PATH ---
        # If no next state and no values, it's a new run
        if not inner_state.values:
             print("▶️ Starting new Dynamic Graph Execution...")
             initial_dynamic_state = {
                "results": {},
                "depth": state.get("depth", 0),
                "subject": state.get("subject", ""),
                "metadata": {},
                "all_agents": [],
                "all_edges": []
            }
             try:
                await app.ainvoke(initial_dynamic_state, config=inner_config)
             except Exception as e:
                from langgraph.errors import GraphBubbleUp
                if isinstance(e, GraphBubbleUp) or "Interrupt" in type(e).__name__:
                    print(f"⏸️ Inner graph raised Initial Interrupt.")
                else:
                    raise e
        else:
            print("✅ Inner graph already completed (no next state).")

    # --- 4. CHECK LOOP CONDITION ---
    # Check if we are paused AGAIN
    inner_state = await app.aget_state(inner_config)
    
    if inner_state.next:
        print(f"� More interrupts pending. Returning self-loop Command.")
        # Return Command to re-execute THIS node.
        # This exits the current step, clearing the 'interrupt' context, so the next run can block again.
        return Command(
            goto="graph_compiler", 
            update={"inner_thread_id": inner_thread_id} 
        )
    
    # --- 5. FINISH ---
    print("✅ Dynamic Graph Execution Complete.")
    combined_agents, combined_edges = _aggregate_graph_data(inner_state.values)
    
    return {
        "results": inner_state.values.get("results", {}), 
        "metadata": inner_state.values.get("metadata", {}),
        "all_agents": combined_agents,
        "all_edges": combined_edges,
        "inner_thread_id": inner_thread_id
    }
