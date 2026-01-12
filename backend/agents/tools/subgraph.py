from langchain_core.tools import tool
import json

@tool
async def spawn_subgraph(task: str, depth: int = 0) -> str:
    """
    Spawns a recursive instance of the Agent Orchestrator to solve a complex sub-problem.
    Use this tool when a task is too complex to solve directly and requires further decomposition.
    
    Args:
        task (str): The high-level description of the sub-problem to solve.
        depth (int): Current recursion depth. DO NOT SET THIS MANUALLY - IT IS INJECTED AUTOMATICALLY.
        
    Returns:
        str: A summary of the results from the recursive execution.
    """
    from agent import app_graph # Import here to avoid circular dependencies
    from agents.dependencies import MAX_RECURSION_DEPTH
    
    print(f"🔄 Spawning Recursive Subgraph for: {task} (Depth: {depth})")
    
    if depth >= MAX_RECURSION_DEPTH:
        msg = f"⛔ Max recursion depth of {MAX_RECURSION_DEPTH} reached. Cannot spawn new sub-agents."
        print(msg)
        return msg
    
    initial_state = {
        "task": task,
        "subtasks": [],
        "graph_plan": {},
        "results": {},
        "depth": depth + 1
    }
    
    try:
        # Run the full orchestrator recursively
        final_state = await app_graph.ainvoke(initial_state)
        
        results = final_state.get("results", {})
        subtasks = final_state.get("subtasks", [])
        
        # Summarize output
        summary = {
            "subtasks_executed": subtasks,
            "results": results
        }
        
        return json.dumps(summary, indent=2)
        
    except Exception as e:
        return f"Error in recursive subgraph: {str(e)}"
