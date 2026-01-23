# LangGraph Unit Testing Strategy & Guide

## Overview
This guide defines the strategy for implementing a robust unit testing system for our LangGraph application. We prioritize isolating nodes, mocking external dependencies (LLMs, Tools), and validating state transitions.

## Testing Layers

| Testing Layer | Objective | Tools/Methods |
| :--- | :--- | :--- |
| **Unit (Nodes)** | Validate logic within a single node function | Mock input `State`, assert return dict |
| **Mocks (Tools)** | Replace real API calls with fixed responses | `unittest.mock.AsyncMock`, `pytest-mock` |
| **State Invariants** | Ensure graph state stays within valid bounds | Pydantic validation, Property checks |
| **CI/CD** | Automate quality checks for every code change | GitHub Actions, Pytest |

---

## 1. Mock Node Test (Unit Layer)
Testing a node in isolation involves passing a manufactured `State` dictionary and asserting the output.

### Example: Testing a "Researcher" Node
```python
import pytest
from unittest.mock import AsyncMock, patch
from agents.state import AgentState

# Assume this is the node function we are testing
async def researcher_node(state: AgentState):
    query = state.get("query")
    # Simulation of calling a tool
    results = f"Results for {query}" 
    return {"results": { "researcher": results }}

@pytest.mark.asyncio
async def test_researcher_node_logic():
    # 1. Arrange: Create Mock State
    start_state = {
        "query": "LangGraph Testing",
        "results": {},
        "messages": []
    }
    
    # 2. Act: Call the node directly (no graph overhead)
    output = await researcher_node(start_state)
    
    # 3. Assert: Check the return value updates the state as expected
    assert "researcher" in output["results"]
    assert output["results"]["researcher"] == "Results for LangGraph Testing"
```

---

## 2. Tool Mocking Utility
We discourage making real LLM calls during unit tests. We use a centralized mocking utility to intercept `ChatOpenAI` and other tool calls.

### Mock Utility (`tests/utils/mocks.py`)
```python
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage

class MockLLM:
    """Helper to create a mock LLM that returns fixed responses."""
    
    @staticmethod
    def create_mock_llm(response_text: str = "Mocked Response"):
        """Returns an AsyncMock that pretends to be a ChatOpenAI model."""
        mock_llm = AsyncMock()
        
        # Mock ainvoke() to return an AIMessage
        mock_llm.ainvoke.return_value = AIMessage(content=response_text)
        
        # Mock invoke() for synchronous calls
        mock_llm.invoke.return_value = AIMessage(content=response_text)
        
        return mock_llm

def mock_tool_response(tool_name: str, return_value: str):
    """Factory for tool mocks."""
    mock_tool = AsyncMock()
    mock_tool.name = tool_name
    mock_tool.ainvoke.return_value = return_value
    return mock_tool
```

### Usage in Test
```python
from tests.utils.mocks import MockLLM
from agents.nodes.writer import writer_node

@pytest.mark.asyncio
async def test_writer_node_with_mock_llm(mocker):
    # Mock the LLM inside the node's module
    mock_llm = MockLLM.create_mock_llm("Generated Article Content")
    
    # Patch the LLM used in the node
    mocker.patch("agents.nodes.writer.llm", mock_llm)
    
    state = {"topic": "AI"}
    result = await writer_node(state)
    
    assert result["params"]["content"] == "Generated Article Content"
```

---

## 3. GitHub Actions Configuration
Automate tests on every push.

### `.github/workflows/test.yml`
```yaml
name: Run Unit Tests

on:
  push:
    branches: [ "main", "develop" ]
  pull_request:
    branches: [ "main" ]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python 3.11
      uses: actions/setup-python@v4
      with:
        python-version: "3.11"
        
    - name: Install Dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r backend/requirements.txt
        pip install pytest pytest-asyncio pytest-mock
        
    - name: Run Tests
      # Assuming tests are in backend/tests
      run: |
        export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
        pytest backend/tests
```

---

## Best Practices
- **Decouple Logic**: Keep business logic in pure functions where possible, separate from LangGraph node wrappers.
- **Deterministic Tests**: Never rely on "live" LLM calls for unit tests.
- **State Validation**: Use Pydantic models for `AgentState` to enforce types at runtime if possible, or verify keys in tests.
