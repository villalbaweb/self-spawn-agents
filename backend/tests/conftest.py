
import pytest
import asyncio
from typing import Dict, Any, AsyncGenerator

@pytest.fixture(scope="session")
def event_loop() -> AsyncGenerator[asyncio.AbstractEventLoop, None]:
    """
    Create an instance of the default event loop for the session.
    Required for async tests in pytest-asyncio.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_agent_state() -> Dict[str, Any]:
    """
    Returns a cleaner, basic AgentState dictionary for testing nodes.
    """
    return {
        "task": "Test Task",
        "subtasks": [],
        "graph_plan": {},
        "results": {},
        "depth": 0,
        "usage_stats": {"cost": 0.0, "steps": 0},
        "global_signal": ""
    }
