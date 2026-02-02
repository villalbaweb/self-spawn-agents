import pytest
import asyncio
import sys
import os
import json

# Add backend directory to sys.path

from agents.execution_planner import execution_planner_node

@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_supervisor():
    print("🚀 Testing Execution Planner Node...")
    
    # Mock input state
    subtasks = [
        "Search for LangGraph documentation",
        "Write a python script using LangGraph",
        "Review the script for errors"
    ]
    
    state = {
        "task": "Create a LangGraph example",
        "subtasks": subtasks
    }

    try:
        result = await execution_planner_node(state)
        graph_plan = result.get("graph_plan", {})
        
        print("\\n✅ Execution Planner Output:")
        print(json.dumps(graph_plan, indent=2))
        
        if not graph_plan.get("nodes"):
            print("❌ No nodes in graph plan.")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_supervisor())
