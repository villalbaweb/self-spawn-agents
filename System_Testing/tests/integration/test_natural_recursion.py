import pytest
import asyncio
import sys
import os
import json

# Add backend directory to sys.path

from agent import app_graph

@pytest.mark.asyncio
async def test_natural_recursion():
    """
    Test with a NATURAL, non-technical user request.
    The system should autonomously decide when to spawn subgraphs.
    
    Epic 4.1 Update: Recursion is now handled via native LangGraph subgraphs.
    When supervisor marks a node as recursive:true, the graph_compiler
    invokes worker_subgraph which may use mini-orchestration for complex tasks.
    """
    print("🚀 Testing NATURAL Recursive Subgraph Triggering...")
    print("="*60)
    
    # Natural, non-technical user request
    # This should decompose into multiple complex steps where the supervisor
    # might mark nodes as recursive, triggering worker_subgraph
    task = "I want to start a blog about cooking. Help me build a complete website with recipes, user accounts, and a newsletter signup."
    
    print(f"📝 User Task: {task}")
    print("="*60)
    
    initial_state = {
        "task": task,
        "subtasks": [],
        "graph_plan": {},
        "results": {},
        "depth": 0
    }

    recursion_detected = False
    
    # Add thread_id to support checkpointers
    config = {"configurable": {"thread_id": "test_natural_recursion"}}
    
    try:
        print("\n▶️ Starting execution...\n")
        
        # Stream events to see what's happening in real-time
        async for event in app_graph.astream_events(initial_state, config=config, version="v2"):
            kind = event.get("event")
            name = event.get("name", "")
            
            # Look for recursion signals - now handled via native worker_subgraph
            if kind == "on_chain_start" and ("MiniOrchestrator" in name or "worker_subgraph" in name.lower()):
                 print(f"🔄 NATIVE SUBGRAPH TRIGGERED - {name}!")
                 recursion_detected = True

            # Show progress
            if kind == "on_chain_start" and name in ["semantic_splitter", "supervisor", "graph_compiler", "confidence_check", "synthesizer"]:
                print(f"▶️ {name}...")
                
        # Get final state
        final_state = await app_graph.aget_state(config)
        state_values = final_state.values
        
        print("\n" + "="*60)
        print("📊 FINAL RESULTS:")
        print("="*60)
        
        subtasks = state_values.get("subtasks", [])
        graph_plan = state_values.get("graph_plan", {})
        results = state_values.get("results", {})
        all_agents = state_values.get("all_agents", [])
        
        print(f"\n🔹 Subtasks ({len(subtasks)}):")
        for s in subtasks[:5]:
            print(f"   - {s}")
            
        print(f"\n🔹 Graph Plan Nodes ({len(graph_plan.get('nodes', []))}):")
        for node in graph_plan.get("nodes", []):
            print(f"   - [{node['agent_type']}] {node['id']}: {node['instruction'][:60]}... (Recursive: {node.get('recursive', False)})")
            
        # Check all_agents for MiniOrchestrator or SubOrchestrator (new native subgraph)
        for agent in all_agents:
            role = agent.get("role", "")
            if role in ["SubOrchestrator", "MiniOrchestrator"]:
                print(f"   ✅ Agent '{agent['id']}' is a {role} (depth {agent.get('depth')})")
                recursion_detected = True

        print(f"\n🔹 Recursion/Mini-Orchestration Detected: {'✅ YES' if recursion_detected else '❌ NO'}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_natural_recursion())
