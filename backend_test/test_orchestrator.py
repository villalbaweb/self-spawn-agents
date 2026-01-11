import asyncio
import sys
import os
import json

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../backend'))

from agent import app_graph
from agents.state import AgentState

async def test_graph_direct():
    print("🚀 Testing Orchestrator Graph Direct Execution (Module 2)...")
    
    initial_state = AgentState(
        task="Direct Graph Test: Build invoice extraction",
        subtasks=[],
        graph_plan={}
    )

    try:
        final_state = await app_graph.ainvoke(initial_state)
        
        subtasks = final_state.get("subtasks", [])
        graph_plan = final_state.get("graph_plan", {})
        
        print(f"✅ Executed. Subtasks: {len(subtasks)}")
        
        if graph_plan:
            print(f"✅ Graph Plan Generated: {len(graph_plan.get('nodes', []))} nodes")
            print(json.dumps(graph_plan, indent=2))
        else:
            print("❌ No Graph Plan generated.")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error executing graph: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_graph_direct())
