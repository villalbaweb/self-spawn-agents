from typing import Dict, Any, List, Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from agents.state import AgentState
from agents.workers.generic import generic_worker_node

async def graph_compiler_node(state: AgentState) -> Dict[str, Any]:
    """
    Compiles and executes a dynamic LangGraph based on the graph_plan.
    """
    plan = state.get("graph_plan", {})
    nodes = plan.get("nodes", [])
    
    if not nodes:
        print("⚠️ No nodes in plan to execute.")
        return {}
        
    print(f"🏗️ Compiling Dynamic Graph with {len(nodes)} nodes...")
    
from typing import Dict, Any, Annotated, TypedDict
import operator

def merge_dicts(a: Dict, b: Dict) -> Dict:
    return {**a, **b}

class DynamicState(TypedDict):
    # Use a reducer to allow parallel updates to merge
    results: Annotated[Dict[str, str], merge_dicts]

async def graph_compiler_node(state: AgentState) -> Dict[str, Any]:
    """
    Compiles and executes a dynamic LangGraph based on the graph_plan.
    """
    plan = state.get("graph_plan", {})
    nodes = plan.get("nodes", [])
    
    if not nodes:
        print("⚠️ No nodes in plan to execute.")
        return {}
        
    print(f"🏗️ Compiling Dynamic Graph with {len(nodes)} nodes...")

    workflow = StateGraph(DynamicState)

    # 2. Add Nodes
    for node in nodes:
        node_id = node["id"]
        instruction = node["instruction"]
        agent_type = node["agent_type"]
        
        async def _node_fn(s: DynamicState, _instr=instruction, _type=agent_type, _id=node_id):
            # Execute the generic worker
            # Note: s contains "results" so we can access prior results if needed
            # context = s.get("results", {}) (for dependency passing in future)
            
            result = await generic_worker_node(s, _instr, _type)
            
            # Return ONLY the update for the results channel
            return {"results": {_id: result["output"]}}
            
        workflow.add_node(node_id, _node_fn)
    
    # 3. Add Edges
    nodes_with_parents = set()
    
    for node in nodes:
        node_id = node["id"]
        dependencies = node.get("dependencies", [])
        
        if dependencies:
            for parent_id in dependencies:
                if any(n["id"] == parent_id for n in nodes):
                    workflow.add_edge(parent_id, node_id)
                    nodes_with_parents.add(node_id)
        
    # 4. Connect Start Nodes
    for node in nodes:
        if node["id"] not in nodes_with_parents:
            workflow.add_edge(START, node["id"])
            
    # 5. Connect Leaf Nodes to END
    parent_ids = set()
    for node in nodes:
        for dep in node.get("dependencies", []):
            parent_ids.add(dep)
            
    for node in nodes:
        if node["id"] not in parent_ids:
            workflow.add_edge(node["id"], END)
            
    # 6. Compile
    app = workflow.compile()
    
    # 7. Execute
    print("▶️ Executing Dynamic Graph...")
    # Initialize with empty results
    initial_dynamic_state = {"results": {}} 
    
    final_dynamic_state = await app.ainvoke(initial_dynamic_state)
    
    print("✅ Dynamic Graph Execution Complete.")
    
    # 8. Return results
    return {"results": final_dynamic_state.get("results", {})}
