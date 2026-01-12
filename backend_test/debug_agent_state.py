import sys
import os
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.agents.state import AgentState
from langgraph.graph import StateGraph

def test_agent_state_keys():
    print(f"AgentState keys: {AgentState.__annotations__.keys()}")
    
    workflow = StateGraph(AgentState)
    print("StateGraph created.")
    
    # Check if we can compile and run with depth
    workflow.add_node("test", lambda s: {"task": "done"})
    workflow.set_entry_point("test")
    workflow.add_edge("test", "__end__")
    
    app = workflow.compile()
    
    res = app.invoke({"task": "start", "depth": 10, "subtasks": [], "graph_plan": {}, "results": {}})
    print(f"Result State: {res}")
    
    if res.get("depth") == 10:
        print("✅ Success: Depth preserved.")
    else:
        print("❌ Failure: Depth lost.")

if __name__ == "__main__":
    test_agent_state_keys()
