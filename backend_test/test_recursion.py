import asyncio
import sys
import os
import json

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../backend'))

from agents.tools.subgraph import spawn_subgraph

async def test_recursion_tool():
    print("🚀 Testing Recursive Subgraph Tool...")
    
    task = "Simple recursion test: List 3 colors"
    
    try:
        # Invoke the tool directly
        print(f"▶️ Invoking spawn_subgraph with: '{task}'")
        result = await spawn_subgraph.ainvoke({"task": task})
        
        print("\n✅ Recursion Result:")
        print(result)
        
        # Verify JSON
        data = json.loads(result)
        if "results" in data and len(data["results"]) > 0:
            print("✅ Subgraph executed nodes successfully.")
        else:
            print("❌ Subgraph returned no results?")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_recursion_tool())
