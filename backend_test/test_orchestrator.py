import asyncio
import sys
import os
import json
import httpx

# Add backend directory to sys.path so we can import from it
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../backend'))

from agent import app_graph
from agents.state import AgentState

async def test_graph_direct():
    print("🚀 Testing Orchestrator Graph Direct Execution...")
    
    initial_state = AgentState(
        task="Direct Graph Test: Build invoice extraction",
        subtasks=[],
    )

    try:
        final_state = await app_graph.ainvoke(initial_state)
        print("✅ Graph Execution Complete.")
        print(f"Subtasks: {len(final_state.get('subtasks', []))}")
            
    except Exception as e:
        print(f"❌ Error executing graph: {e}")
        sys.exit(1)

# Note: Testing API requires running server, so we'll skip that in this unit test script
# and stick to direct graph testing which verifies logic.

if __name__ == "__main__":
    asyncio.run(test_graph_direct())
