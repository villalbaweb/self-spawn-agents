import asyncio
from typing import TypedDict, Annotated, Dict
import operator
from langgraph.graph import StateGraph, START, END

def merge_dicts(a: Dict, b: Dict) -> Dict:
    return {**a, **b}

class DynamicState(TypedDict):
    results: Annotated[Dict[str, str], merge_dicts]
    depth: int

async def worker_node(state: DynamicState):
    print(f"Worker Node State: {state}")
    current_depth = state.get("depth", "MISSING")
    print(f"Depth in worker: {current_depth}")
    return {"results": {"foo": "bar"}}

async def debug_flow():
    workflow = StateGraph(DynamicState)
    workflow.add_node("worker", worker_node)
    workflow.add_edge(START, "worker")
    workflow.add_edge("worker", END)
    
    app = workflow.compile()
    
    initial_state = {
        "results": {},
        "depth": 5
    }
    
    print("Starting execution with depth=5...")
    final_state = await app.ainvoke(initial_state)
    print(f"Final State: {final_state}")

if __name__ == "__main__":
    asyncio.run(debug_flow())
