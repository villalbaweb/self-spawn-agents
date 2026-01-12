import asyncio
import sys
import os
import json

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../backend'))

from agents.graph_compiler import graph_compiler_node
from agents.state import AgentState

async def test_compiler():
    print("🚀 Testing Dynamic Graph Compiler...")
    
    # Mock a plan
    mock_plan = {
        "nodes": [
            {
                "id": "step_1",
                "agent_type": "Researcher",
                "instruction": "Say 'Researching Step 1'",
                "dependencies": []
            },
            {
                "id": "step_2",
                "agent_type": "Coder", 
                "instruction": "Say 'Coding Step 2'",
                "dependencies": ["step_1"]
            }
        ]
    }
    
    state = AgentState(
        task="Test Task",
        subtasks=[],
        graph_plan=mock_plan,
        results={}
    )

    try:
        result = await graph_compiler_node(state)
        results = result.get("results", {})
        
        print("\n✅ Compiler Execution Results:")
        print(json.dumps(results, indent=2))
        
        if len(results) != 2:
            print("❌ Expected 2 results.")
            sys.exit(1)
            
        print("✅ Success.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_compiler())
