import pytest
import asyncio
import sys
import os
import json

# Add backend directory to sys.path

from agent import app_graph
from agents.state import AgentState

@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_graph_direct():
    print("🚀 Testing Full Orchestrator (Modules 1 + 2 + 3)...")
    
    # We use a simple task to avoid expensive LLM calls if possible, 
    # but semantic splitter prompts are hardcoded to real models.
    initial_state = AgentState(
        task="Create a hello world python script",
        subtasks=[],
        graph_plan={},
        results={}
    )

    try:
        print("▶️ Invoking Graph...")
        final_state = await app_graph.ainvoke(initial_state)
        
        subtasks = final_state.get("subtasks", [])
        graph_plan = final_state.get("graph_plan", {})
        results = final_state.get("results", {})
        
        print(f"\n✅ Execution Complete.")
        print(f"Subtasks: {len(subtasks)}")
        print(f"Plan Nodes: {len(graph_plan.get('nodes', []))}")
        print(f"Results: {len(results)}")
        
        if results:
            print(json.dumps(results, indent=2))
        else:
            print("❌ No Results generated.")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error executing graph: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_graph_direct())
