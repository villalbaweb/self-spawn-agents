import pytest
import asyncio
import sys
import os
import json

# Add backend directory to sys.path

from agents.graph_compiler import graph_compiler_node

@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_forced_subgraph():
    """
    This test FORCES a subgraph spawn by:
    1. Manually constructing a graph_plan with an "Orchestrator" agent type
    2. Giving it an explicitly complex task that encourages using spawn_subgraph
    """
    print("🚀 Testing FORCED Recursive Subgraph...")
    
    # Manually create a plan with an Orchestrator node
    # The Orchestrator is the ONLY agent type that has access to spawn_subgraph
    mock_plan = {
        "nodes": [
            {
                "id": "orchestrate_complex_task",
                "agent_type": "Orchestrator",  # <-- This agent type CAN spawn subgraphs
                "instruction": """You are given a complex multi-step task that CANNOT be completed in a single response.

TASK: Build a complete Python REST API project structure with the following components:
1. Database models for User and Product
2. CRUD endpoints for each model  
3. Authentication middleware
4. Unit tests for all endpoints

This task is too complex for one agent. You MUST use the 'spawn_subgraph' tool to delegate this work.
Call spawn_subgraph with a clear sub-task like: "Create Python SQLAlchemy models for User and Product entities"

DO NOT attempt to complete this yourself. USE THE TOOL.""",
                "dependencies": []
            }
        ]
    }
    
    # Create mock state
    state = {
        "task": "Build complex API",
        "subtasks": [],
        "graph_plan": mock_plan,
        "results": {},
        "depth": 0
    }

    try:
        print("▶️ Executing graph with Orchestrator node...")
        result = await graph_compiler_node(state)
        
        results = result.get("results", {})
        
        print("\n" + "="*50)
        print("📊 EXECUTION RESULTS:")
        print("="*50)
        
        for node_id, output in results.items():
            print(f"\n🔹 Node: {node_id}")
            print("-" * 40)
            
            # Check if recursion was triggered
            if "Recursion Result:" in output:
                print("✅ RECURSION TRIGGERED!")
                print(output[:1500] + "..." if len(output) > 1500 else output)
            elif "DEPTH LIMIT REACHED" in output:
                print("⚠️ Depth limit was reached")
                print(output[:500])
            else:
                print("❌ No recursion detected in output")
                print(output[:500] + "..." if len(output) > 500 else output)
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_forced_subgraph())
