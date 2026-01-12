import asyncio
import sys
import os
import json

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../backend'))

from agent import app_graph

async def validate_complex_task():
    print("🚀 Running Complex Validation Task for Modules 1-4...")
    
    # This task is designed to be multi-step and potentially recursive
    # 1. Research frameworks (Complex -> trigger recursion?)
    # 2. Select top choice
    # 3. Write script
    task = "Research the top 3 Python web frameworks for 2024, select the best one for a microservice, and write a 'Hello World' app code for it."
    
    initial_state = {
        "task": task,
        "subtasks": [],
        "graph_plan": {},
        "results": {}
    }

    try:
        print(f"▶️ Sending Task: '{task}'")
        print("--------------------------------------------------")
        
        # We invoke the graph. The logs should show recursion if the agents decide to spawn it.
        # Note: Whether recursion happens depends on the LLM's decision in `generic.py`.
        # We can't 100% guarantee recursion unless the prompt strongly encourages it for "Research" tasks.
        final_state = await app_graph.ainvoke(initial_state)
        
        subtasks = final_state.get("subtasks", [])
        results = final_state.get("results", {})
        
        print("\n✅ Execution Complete.")
        print(f"🔹 Top Level Subtasks: {len(subtasks)}")
        for i, sub in enumerate(subtasks):
             print(f"  {i+1}. {sub}")
             
        print(f"\n🔹 Execution Results ({len(results)} steps verified):")
        for node_id, output in results.items():
            print(f"-- Node: {node_id} --")
            # Truncate output for readability
            print(output[:300] + "..." if len(output) > 300 else output)
            print("-----------------------")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(validate_complex_task())
