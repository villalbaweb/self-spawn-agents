from typing import Dict, Any, Annotated, TypedDict, List
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from agents.state import AgentState
from agents.workers.generic import generic_worker_node
from agents.blueprint import AppBlueprint, AgentInfo, EdgeInfo
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
        
    print(f"🏗️ Compiling Dynamic Graph with {len(nodes)} nodes...")

    workflow = StateGraph(DynamicState)
    
    # Track edges for blueprint
    blueprint_edges = []

    # Add Nodes with context injection
    for node in nodes:
        node_id = node["id"]
        instruction = node["instruction"]
        agent_type = node["agent_type"]
        dependencies = node.get("dependencies", [])
        is_recursive = node.get("recursive", False)
        
        if is_recursive:
            # RECURSIVE NODE: Spawn full sub-orchestration
            async def _recursive_node_fn(
                s: DynamicState, 
                config: RunnableConfig,
                _instr=instruction, 
                _id=node_id,
                _deps=dependencies
            ):
                from agent import app_graph  # Import here to avoid circular deps
                from agents.dependencies import MAX_RECURSION_DEPTH
                
                current_depth = s.get("depth", 0)
                print(f"🔄 [RecursiveNode] Spawning sub-orchestration for: {_instr[:50]}... (Depth: {current_depth})")
                
                # Depth limit check
                if current_depth >= MAX_RECURSION_DEPTH:
                    print(f"⛔ Depth limit reached ({current_depth}/{MAX_RECURSION_DEPTH}). Skipping recursive node.")
                    return {
                        "results": {_id: f"[Depth limit reached - task skipped: {_instr[:100]}]"},
                        "metadata": {_id: {"agent_role": "Skipped", "system_prompt": "Depth limit reached"}},
                        "all_agents": [],
                        "all_edges": []
                    }
                
                # Build context from parent nodes
                context_parts = []
                results = s.get("results", {})
                if _deps:
                    for dep_id in _deps:
                        if dep_id in results:
                            dep_output = results[dep_id]
                            truncated = dep_output[:2000] + "..." if len(dep_output) > 2000 else dep_output
                            context_parts.append(f"<input_data source=\"{dep_id}\">\n{truncated}\n</input_data>")
                
                # Prepare sub-orchestration state (inherits subject to prevent drift)
                sub_state = {
                    "task": _instr + ("\n\nContext:\n" + "\n".join(context_parts) if context_parts else ""),
                    "subtasks": [],
                    "graph_plan": {},
                    "results": {},
                    "depth": current_depth + 1,
                    "subject": s.get("subject", ""),  # CRITICAL: Inherit subject for drift prevention
                    "all_agents": [],
                    "all_edges": []
                }
                
                # Execute full sub-orchestration
                if config:
                    final_sub_state = await app_graph.ainvoke(sub_state, config=config)
                else:
                    final_sub_state = await app_graph.ainvoke(sub_state)
                
                # Extract results and nested graph data
                sub_results = final_sub_state.get("results", {})
                sub_agents = final_sub_state.get("all_agents", [])
                sub_edges = final_sub_state.get("all_edges", [])
                synthesis = final_sub_state.get("synthesis", "")
                
                # Create parent node entry for visualization
                parent_agent = {
                    "id": _id,
                    "role": "SubOrchestrator",
                    "system_prompt": f"Recursive orchestration for: {_instr[:200]}",
                    "instruction": _instr,
                    "output": result_summary,
                    "tools": [],
                    "depth": current_depth
                }
                
                # Create edges from this parent to root nodes of sub-orchestration
                # (Root nodes are those at depth = current_depth + 1 with no incoming edges from same depth)
                hierarchy_edges = []
                sub_depth = current_depth + 1
                root_sub_agents = [a for a in sub_agents if a.get("depth") == sub_depth]
                for root_agent in root_sub_agents:
                    hierarchy_edges.append({
                        "source": _id,
                        "target": root_agent["id"],
                        "depth": current_depth,
                        "type": "hierarchy"  # Mark as hierarchy edge for visualization
                    })
                
                # Combine sub-results into a summary
                result_summary = synthesis if synthesis else str(sub_results)
                
                print(f"✅ [RecursiveNode] Sub-orchestration complete. {len(sub_agents)} agents, {len(sub_edges) + len(hierarchy_edges)} edges (incl. {len(hierarchy_edges)} hierarchy).")
                
                return {
                    "results": {_id: result_summary},
                    "metadata": {_id: {"agent_role": "SubOrchestrator", "system_prompt": f"Recursive orchestration for: {_instr[:100]}"}},
                    "all_agents": [parent_agent] + sub_agents,  # Include parent + children
                    "all_edges": hierarchy_edges + sub_edges  # Include hierarchy + sub edges
                }
            
            workflow.add_node(node_id, _recursive_node_fn)
        else:
            # NORMAL NODE: Call generic_worker_node
            async def _node_fn(
                s: DynamicState, 
                config: RunnableConfig,
                _instr=instruction, 
                _type=agent_type, 
                _id=node_id,
                _deps=dependencies
            ):
                # BUILD CONTEXT FROM PARENT NODES
                context_parts = []
                results = s.get("results", {})
                
                if _deps:
                    for dep_id in _deps:
                        if dep_id in results:
                            dep_output = results[dep_id]
                            truncated = dep_output[:2000] + "..." if len(dep_output) > 2000 else dep_output
                            context_parts.append(f"<input_data source=\"{dep_id}\">\n{truncated}\n</input_data>")
                            
                # Inject context into instruction
                subject = s.get("subject", "")
                subject_block = f"<subject>{subject}</subject>\n" if subject else ""
                
                enriched_instruction = f"{subject_block}" + "\n".join(context_parts) + f"\n\n<task>\n{_instr}\n</task>"
                
                # Pass config to worker node for tracing
                result = await generic_worker_node(s, enriched_instruction, _type, config)
                
                # Extract nested agents/edges from spawn_subgraph calls (legacy support)
                nested_agents = result.get("nested_agents", [])
                nested_edges = result.get("nested_edges", [])
                
                # Return result AND metadata AND nested graph data
                return {
                    "results": {_id: result["output"]},
                    "metadata": {_id: result.get("metadata", {})},
                    "all_agents": nested_agents,
                    "all_edges": nested_edges
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
                    # Track for blueprint
                    blueprint_edges.append(EdgeInfo(source=parent_id, target=node_id))
        
    # Connect Start Nodes
    for node in nodes:
        if node["id"] not in nodes_with_parents:
            workflow.add_edge(START, node["id"])
            
    # Connect Leaf Nodes to END
    parent_ids = set()
    for node in nodes:
        for dep in node.get("dependencies", []):
            parent_ids.add(dep)
            
    for node in nodes:
        if node["id"] not in parent_ids:
            workflow.add_edge(node["id"], END)
            
    # Compile
    app = workflow.compile()
    
    # Execute
    print("▶️ Executing Dynamic Graph...")
    initial_dynamic_state = {
        "results": {},
        "depth": state.get("depth", 0),
        "subject": state.get("subject", ""),
        "metadata": {},
        "all_agents": [],
        "all_edges": []
    } 
    
    # Pass config to inner graph execution
    if config:
        final_dynamic_state = await app.ainvoke(initial_dynamic_state, config=config)
    else:
        final_dynamic_state = await app.ainvoke(initial_dynamic_state)
    
    print("✅ Dynamic Graph Execution Complete.")
    
    # --- AGGREGATE AGENTS AND EDGES FOR UNIFIED GRAPH ---
    current_depth = state.get("depth", 0)
    execution_metadata = final_dynamic_state.get("metadata", {})
    
    # Build agent info dicts (not Pydantic models, for state merging)
    new_agents = []
    for node in nodes:
        nid = node["id"]
        if nid in execution_metadata:
            meta = execution_metadata[nid]
            # Build agent info with ALL metadata fields
            agent_data = {
                "id": nid,
                "role": meta.get("agent_role", node["agent_type"]),
                "system_prompt": meta.get("system_prompt", ""),
                "instruction": node["instruction"],
                "output": final_dynamic_state.get("results", {}).get(nid, ""),
                "tools": meta.get("tools", []),
                "depth": current_depth
            }
            # Spread standard metadata keys if they exist
            for key in ["status", "execution_time_seconds", "tool_used", "tools_available", "error_message"]:
                if key in meta:
                    agent_data[key] = meta[key]
            
            new_agents.append(agent_data)
    
    # Build edge dicts
    new_edges = [{"source": e.source, "target": e.target, "depth": current_depth} for e in blueprint_edges]
    
    # --- BLUEPRINT GENERATION (for backwards compatibility/debugging) ---
    try:
        run_id = str(uuid.uuid4())
        
        agent_infos = [AgentInfo(**a) for a in new_agents]
        
        blueprint = AppBlueprint(
            run_id=run_id,
            task=task,
            agents=agent_infos,
            edges=blueprint_edges,
            execution_flow=[n["id"] for n in nodes],
            timestamp=datetime.now().isoformat(),
            depth=current_depth
        )
        
        # Save Blueprint
        blueprint_dir = os.path.join(os.getcwd(), "blueprints")
        os.makedirs(blueprint_dir, exist_ok=True)
        blueprint_path = os.path.join(blueprint_dir, f"{run_id}.json")
        
        with open(blueprint_path, "w") as f:
            f.write(blueprint.model_dump_json(indent=2))
            
        print(f"📐 Saved App Blueprint to: {blueprint_path}")
        
    except Exception as e:
        print(f"❌ Error generating blueprint: {e}")
        run_id = None
    
    # Combine local agents with nested agents from subgraph calls
    nested_agents = final_dynamic_state.get("all_agents", [])
    nested_edges = final_dynamic_state.get("all_edges", [])
    
    combined_agents = new_agents + nested_agents
    combined_edges = new_edges + nested_edges
    
    print(f"📊 graph_compiler returning {len(combined_agents)} total agents ({len(new_agents)} local + {len(nested_agents)} nested)")
    
    return {
        "results": final_dynamic_state.get("results", {}), 
        "blueprint_id": run_id,
        "all_agents": combined_agents,
        "all_edges": combined_edges
    }
