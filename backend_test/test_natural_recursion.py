import asyncio
import sys
import os
import json

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../backend'))

from agent import app_graph

async def test_natural_recursion():
    """
    Test with a NATURAL, non-technical user request.
    The system should autonomously decide when to spawn subgraphs.
    """
    print("🚀 Testing NATURAL Recursive Subgraph Triggering...")
    print("="*60)
    
    # Natural, non-technical user request
    # This should decompose into multiple complex steps where an Orchestrator
    # might decide to use spawn_subgraph
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
            
            # Look for recursion signals - now handled via recursive nodes in graph_compiler
            if kind == "on_chain_start" and name.startswith("SubOrchestrator"):
                 print(f"🔄 RECURSION TRIGGERED - {name} agent starting!")
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
            
        # Check all_agents for Sub-Orchestrator
        for agent in all_agents:
            if agent.get("role") == "SubOrchestrator":
                print(f"   ✅ Agent '{agent['id']}' is a Sub-Orchestrator")
                recursion_detected = True

        print(f"\n🔹 Recursion Detected: {'✅ YES' if recursion_detected else '❌ NO'}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_natural_recursion())
