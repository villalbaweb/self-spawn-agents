from typing import Dict, Any, Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from agents.state import AgentState
from agents.workers.generic import generic_worker_node

def merge_dicts(a: Dict, b: Dict) -> Dict:
    return {**a, **b}

def replace(a: Any, b: Any) -> Any:
    return b

class DynamicState(TypedDict):
    # Use a reducer to allow parallel updates to merge
    results: Annotated[Dict[str, str], merge_dicts]
    depth: Annotated[int, replace]

async def graph_compiler_node(state: AgentState) -> Dict[str, Any]:
    """
    Compiles and executes a dynamic LangGraph based on the graph_plan.
    Injects parent node results into dependent node instructions for context continuity.
    """
    plan = state.get("graph_plan", {})
    nodes = plan.get("nodes", [])
    
    if not nodes:
        print("⚠️ No nodes in plan to execute.")
        return {}
        
    print(f"🏗️ Compiling Dynamic Graph with {len(nodes)} nodes...")

    # Build a lookup for node dependencies
    node_dependencies = {node["id"]: node.get("dependencies", []) for node in nodes}

    workflow = StateGraph(DynamicState)

    # Add Nodes with context injection
    for node in nodes:
        node_id = node["id"]
        instruction = node["instruction"]
        agent_type = node["agent_type"]
        dependencies = node.get("dependencies", [])
        
        async def _node_fn(
            s: DynamicState, 
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
            if context_parts:
                context_block = "\n".join(context_parts)
                enriched_instruction = f"{context_block}\n\n<task>\n{_instr}\n</task>"
                print(f"📎 [Context] Injecting {len(_deps)} parent result(s) into '{_id}'")
            else:
                enriched_instruction = _instr
            
            current_depth = s.get("depth", 0)
            result = await generic_worker_node(s, enriched_instruction, _type)
            
            return {"results": {_id: result["output"]}}
            
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
        "depth": state.get("depth", 0)
    } 
    
    final_dynamic_state = await app.ainvoke(initial_dynamic_state)
    
    print("✅ Dynamic Graph Execution Complete.")
    
    return {"results": final_dynamic_state.get("results", {})}
