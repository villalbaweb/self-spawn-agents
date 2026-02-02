import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from langgraph.checkpoint.memory import MemorySaver
import sys
import os
import json

# Add backend directory to sys.path
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../backend')))
from agent import app_graph
from agents.state import AgentState
from agents.supervisor_agent import GraphPlan, NodeSchema

@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_graph_direct():
    print("🚀 Testing Full Orchestrator (Modules 1 + 2 + 3)...")
    
    # We use a simple task to avoid expensive LLM calls if possible, 
    # but semantic splitter prompts are hardcoded to real models.
    initial_state = AgentState(
        task="Create a hello world python script",
        subtasks=[],
        graph_plan={},
        results={}
    )

    try:
        print("▶️ Invoking Graph...")
        # Mock shared_memory to avoid "no active connection" error
        # We need to patch where get_app_graph looks for it (agent.shared_memory.memory)
        # But app_graph is already imported.
        # Actually, get_app_graph imports internally: from agents.shared_memory import memory
        # So we patch agents.shared_memory.memory
        # Mock shared_memory to avoid "no active connection" error
        # Use MemorySaver instead of MagicMock
        # Also RESET the cached local graph to force re-compilation with our mock memory
        # Create Mock Instances for return values
        mock_splitter_llm_instance = MagicMock()
        mock_splitter_llm_instance.ainvoke = AsyncMock(return_value=MagicMock(
            subtasks=["write_script"],
            subject="Python",
            deliverables=["script.py"],
            reasoning="Test reasoning"
        ))
        
        mock_supervisor_llm_instance = MagicMock()
        mock_plan = GraphPlan(
            nodes=[NodeSchema(id="node1", agent_type="Coder", instruction="Write hello world", dependencies=[])],
            explanation="Test plan"
        )
        mock_supervisor_llm_instance.ainvoke = AsyncMock(return_value=mock_plan)
        
        mock_synthesizer_llm_instance = MagicMock()
        mock_synthesizer_llm_instance.ainvoke = AsyncMock(return_value=MagicMock(
            content="Final Report: Completed."
        ))

        mock_worker_result = {
            "output": "print('Hello World')",
            "metadata": {"status": "completed", "agent_role": "Coder"},
            "usage_stats": {"cost": 0.01}
        }

        with patch("agents.shared_memory.memory", MemorySaver()), \
             patch("agents.semantic_splitter.llm") as mock_splitter_llm, \
             patch("agents.supervisor_agent.llm") as mock_supervisor_llm, \
             patch("agents.synthesizer.llm") as mock_synthesizer_llm, \
             patch("agents.confidence_check.interrupt") as mock_interrupt, \
             patch("agents.graph_compiler.generic_worker_node", new_callable=AsyncMock) as mock_worker:
            
            # Setup mocks
            mock_splitter_llm.with_structured_output.return_value = mock_splitter_llm_instance
            mock_supervisor_llm.with_structured_output.return_value = mock_supervisor_llm_instance
            mock_synthesizer_llm.ainvoke = mock_synthesizer_llm_instance.ainvoke # Link ainvoke directly if needed
            
            mock_worker.return_value = mock_worker_result

            # Reset cached graph to force recompile with patched MemorySaver checkpointer
            import agent
            agent._compiled_graph = None

            final_state = await app_graph.ainvoke(initial_state, config={"configurable": {"thread_id": "test_thread"}})
        
        subtasks = final_state.get("subtasks", [])
        graph_plan = final_state.get("graph_plan", {})
        results = final_state.get("results", {})
        
        print(f"\n✅ Execution Complete.")
        print(f"Subtasks: {len(subtasks)}")
        print(f"Plan Nodes: {len(graph_plan.get('nodes', []))}")
        print(f"Results: {len(results)}")
        
        if results:
            print(json.dumps(results, indent=2))
        else:
            print("❌ No Results generated.")
            pytest.fail("No Results generated.")
            
    except Exception as e:
        print(f"❌ Error executing graph: {e}")
        pytest.fail(f"Error executing graph: {e}")

if __name__ == "__main__":
    asyncio.run(test_graph_direct())
