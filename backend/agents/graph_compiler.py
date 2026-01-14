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

def replace(a: Any, b: Any) -> Any:
    return b

class DynamicState(TypedDict):
    # Use a reducer to allow parallel updates to merge
    results: Annotated[Dict[str, str], merge_dicts]
    depth: Annotated[int, replace]
    subject: str  # Primary subject for drift prevention
    metadata: Annotated[Dict[str, Dict], merge_dicts] # Capture agent metadata

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
        
        async def _node_fn(
            s: DynamicState, 
            config: RunnableConfig, # LangGraph passes this automatically
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
                        # Truncate if too long to avoid context overflow
                        truncated = dep_output[:2000] + "..." if len(dep_output) > 2000 else dep_output
                        context_parts.append(f"<input_data source=\"{dep_id}\">\n{truncated}\n</input_data>")
                        
            # Inject context into instruction
            subject = s.get("subject", "")
            subject_block = f"<subject>{subject}</subject>\n" if subject else ""
            
            enriched_instruction = f"{subject_block}" + "\n".join(context_parts) + f"\n\n<task>\n{_instr}\n</task>"
            
            # Pass config to worker node for tracing
            result = await generic_worker_node(s, enriched_instruction, _type, config)
            
            # Return result AND metadata
            return {
                "results": {_id: result["output"]},
                "metadata": {_id: result.get("metadata", {})}
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
        "metadata": {}
    } 
    
    # Pass config to inner graph execution
    if config:
        final_dynamic_state = await app.ainvoke(initial_dynamic_state, config=config)
    else:
        final_dynamic_state = await app.ainvoke(initial_dynamic_state)
    
    print("✅ Dynamic Graph Execution Complete.")
    
    # --- BLUEPRINT GENERATION ---
    try:
        run_id = str(uuid.uuid4())
        execution_metadata = final_dynamic_state.get("metadata", {})
        
        agent_infos = []
        execution_flow = [] # Simple approximation
        
        for node in nodes:
            nid = node["id"]
            if nid in execution_metadata:
                meta = execution_metadata[nid]
                agent_infos.append(AgentInfo(
                    id=nid,
                    role=meta.get("agent_role", "unknown"),
                    system_prompt=meta.get("system_prompt", ""),
                    instruction=node["instruction"],
                    tools=meta.get("tools", []) # Generic worker needs to pass this if we want it
                ))
            execution_flow.append(nid) # Simplified execution flow (topological-ish)

        blueprint = AppBlueprint(
            run_id=run_id,
            task=task,
            agents=agent_infos,
            edges=blueprint_edges,
            execution_flow=execution_flow,
            timestamp=datetime.now().isoformat()
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
    
    return {"results": final_dynamic_state.get("results", {}), "blueprint_id": run_id}
