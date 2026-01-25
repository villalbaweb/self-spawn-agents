import pytest
import asyncio
import sys
import os
import json

# Add backend directory to sys.path

from agents.graph_compiler import graph_compiler_node

@pytest.mark.asyncio
async def test_forced_subgraph():
    """
    This test FORCES a subgraph spawn by:
    1. Manually constructing a graph_plan with a "Sub-Orchestrator" agent type
    2. Setting recursive: true to trigger the native WorkerSubgraph
    
    Epic 4.1 Update: Recursion is now handled via native LangGraph subgraphs,
    not the legacy spawn_subgraph tool. Recursive nodes use worker_subgraph
    which implements lightweight mini-orchestration.
    """
    print("🚀 Testing FORCED Recursive Subgraph (Native LangGraph)...")
    
    # Manually create a plan with a recursive Sub-Orchestrator node
    # The recursive flag triggers worker_subgraph invocation
    mock_plan = {
        "nodes": [
            {
                "id": "orchestrate_complex_task",
                "agent_type": "Sub-Orchestrator",  # Recursive orchestrator type
                "instruction": """Build a complete Python REST API project structure with the following components:
1. Database models for User and Product with SQLAlchemy
2. CRUD endpoints for each model with FastAPI
3. Authentication middleware with JWT tokens
4. Unit tests for all endpoints with pytest

Provide implementation details for each component.""",
                "dependencies": [],
                "recursive": True  # This triggers native worker_subgraph
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
            
            # Check if mini-orchestration was triggered (new native subgraph)
            all_agents = result.get("all_agents", [])
            mini_orchestrators = [a for a in all_agents if a.get("role") == "MiniOrchestrator"]
            
            if mini_orchestrators:
                print("✅ NATIVE SUBGRAPH TRIGGERED (MiniOrchestrator)!")
                print(f"   Child agents spawned: {len(all_agents)}")
                for agent in all_agents[:5]:  # Show first 5
                    print(f"   - {agent.get('id')}: {agent.get('role')} (depth {agent.get('depth')})")
            elif "DEPTH LIMIT REACHED" in str(output) or "Depth limit" in str(output):
                print("⚠️ Depth limit was reached")
                print(str(output)[:500])
            else:
                print("❌ No mini-orchestration detected")
                print(str(output)[:500] + "..." if len(str(output)) > 500 else str(output))
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_forced_subgraph())
