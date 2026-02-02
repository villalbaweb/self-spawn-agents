
import pytest
from agents.state import AgentState
from tests.utils.mocks import MockLLM

# --- Example Node for Testing ---
# in a real scenario, you'd import this from agents.nodes...
async def simple_researcher_node(state: AgentState):
    """
    A simple node that takes a query and returns a result.
    """
    query = state.get("task", "")
    
    # Logic: simple string manipulation or check
    if not query:
        return {"results": {"error": "No query provided"}}
        
    return {"results": {"research": f"Analysis of: {query}"}}

@pytest.mark.asyncio
async def test_simple_researcher_node():
    """
    Test the researcher node in isolation.
    """
    # 1. Arrange
    start_state = {
        "task": "LangGraph Unit Testing",
        "results": {},
        "depth": 0
    }
    
    # 2. Act
    output = await simple_researcher_node(start_state)
    
    # 3. Assert
    assert "research" in output["results"]
    assert output["results"]["research"] == "Analysis of: LangGraph Unit Testing"

@pytest.mark.asyncio
async def test_node_handles_empty_state(mock_agent_state):
    """
    Test edge case with empty task using fixture.
    """
    # 1. Arrange
    mock_agent_state["task"] = ""
    
    # 2. Act
    output = await simple_researcher_node(mock_agent_state)
    
    # 3. Assert
    assert "error" in output["results"]
    assert output["results"]["error"] == "No query provided"
