import pytest
import asyncio
import sys
import os
import json
from unittest.mock import MagicMock
from langgraph.checkpoint.memory import MemorySaver

# --- AGENTGUARD ALIGNMENT TEST MOCKS ---
# These mocks MUST be applied before importing app_graph or any agent modules
# to ensure the pre-compiled subgraphs use the mocked versions.

# 1. Mock Checkpointer
import core.persistence.checkpointer as cp_mod
memory_checkpointer = MemorySaver()
cp_mod.get_checkpointer = lambda: memory_checkpointer
cp_mod.init_checkpointer = MagicMock(return_value=None)
cp_mod.close_checkpointer = MagicMock(return_value=None)

# 2. Mock KnowledgeService (pgvector)
import core.knowledge.service as ks_mod
class MockKnowledgeService:
    async def search_blueprint(self, *args, **kwargs): return None
    async def archive_blueprint(self, *args, **kwargs): return "mock-id"
    async def close(self): pass
    @property
    def similarity_threshold(self): return 0.85

mock_ks = MockKnowledgeService()
ks_mod.get_knowledge_service = lambda: mock_ks
ks_mod.init_knowledge_service = MagicMock(return_value=mock_ks)

# --- END MOCKS ---

from app_graph import app_graph

@pytest.mark.asyncio
async def test_natural_recursion():
    """
    Test with a NATURAL, non-technical user request.
    The system should autonomously decide when to spawn subgraphs.
    """
    print("🚀 Testing NATURAL Recursive Subgraph Triggering...")
    print("="*60)
    
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
    config = {"configurable": {"thread_id": "test_natural_recursion"}}
    
    from agentguard_sdk.client import get_agentguard_client
    ag_client = get_agentguard_client()
    print("🛡️ Authenticating with Agent Guard...")
    success = await ag_client.authenticate()
    if not success:
        print("❌ Failed to authenticate with Agent Guard. Verification might fail.")
    else:
        print("✅ Authenticated with Agent Guard.")

    try:
        print("\n▶️ Starting execution...\n")
        
        # Stream events
        async for event in app_graph.astream_events(initial_state, config=config, version="v2"):
            kind = event.get("event")
            name = event.get("name", "")
            
            if kind == "on_chain_start" and ("MiniOrchestrator" in name or "worker_subgraph" in name.lower()):
                 print(f"🔄 NATIVE SUBGRAPH TRIGGERED - {name}!")
                 recursion_detected = True

            if kind == "on_chain_start" and name in ["task_decomposer", "execution_planner", "graph_executor", "human_review_trigger", "synthesizer"]:
                print(f"▶️ {name}...")
                
        final_state = await app_graph.aget_state(config)
        state_values = final_state.values
        
        print("\n" + "="*60)
        print("📊 FINAL RESULTS:")
        print("="*60)
        
        subtasks = state_values.get("subtasks", [])
        graph_plan = state_values.get("graph_plan", {})
        all_agents = state_values.get("all_agents", [])
        
        print(f"\n🔹 Subtasks ({len(subtasks)}):")
        for s in subtasks[:5]:
            print(f"   - {s}")
            
        print(f"\n🔹 Graph Plan Nodes ({len(graph_plan.get('nodes', []))}):")
        for node in graph_plan.get("nodes", []):
            print(f"   - [{node['agent_type']}] {node['id']}: {node['instruction'][:60]}... (Recursive: {node.get('recursive', False)})")
            
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
