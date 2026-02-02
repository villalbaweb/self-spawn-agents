
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langgraph.checkpoint.memory import MemorySaver
from agents.graph_compiler import graph_compiler_node
from core.state.orchestrator_state import AgentState

@pytest.mark.asyncio
async def test_compiler_node_logic(mock_agent_state):
    """
    Test the graph compiler node with a mock plan.
    Mocking the generic_worker_node to avoid real LLM calls.
    """
    # 1. Arrange
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
    
    mock_agent_state["graph_plan"] = mock_plan
    
    # Mock generic_worker_node to return immediately
    async def mock_worker(state, instruction, role, config):
        return {
            "output": f"Mocked Output for {role}",
            "metadata": {"agent_role": role, "status": "completed"}
        }

    with patch("agents.graph_compiler.generic_worker_node", side_effect=mock_worker), \
         patch("agents.graph_compiler.checkpointer.memory", MemorySaver()):
        # 2. Act
        result = await graph_compiler_node(mock_agent_state)
    
    # 3. Assert
    # The compiler aggregates inner results.
    # Check structure of result
    results = result.get("results", {})
    assert "step_1" in results
    assert "step_2" in results
    assert results["step_1"] == "Mocked Output for Researcher"
    assert results["step_2"] == "Mocked Output for Coder"
