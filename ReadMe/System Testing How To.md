# System Testing How-To Guide

This guide describes how to use and extend the centralized test suite for the Self-Spawn Agents project.

## 🛠️ Setup the Test Suite

The test suite is isolated in the `System_Testing` directory and uses `uv` for environment management to ensure compatibility and speed.

1.  **Run the Setup Script**:
    Open a PowerShell terminal in the project root and execute:
    ```powershell
    ./System_Testing/setup_tests.ps1
    ```
    This script will:
    - Install `uv` if it's not present.
    - Create a dedicated virtual environment in `System_Testing/.venv`.
    - Install backend dependencies and test-specific libraries (`pytest`, `pytest-asyncio`, etc.).

## 🚀 Execute the Test Suite

Always run tests from the **root directory** of the project.

1.  **Activate the Environment**:
    ```powershell
    System_Testing\.venv\Scripts\activate
    ```
2.  **Run All Tests**:
    ```powershell
    pytest
    ```
3.  **Run Specific Categories**:
    ```powershell
    pytest System_Testing/tests/integration
    pytest System_Testing/tests/unit
    ```
4.  **Useful Flags**:
    - `-s`: Show stdout (print statements).
    - `-v`: Verbose output.
    - `-k "test_name"`: Run tests matching a specific name.

## 📊 Test Coverage

The test suite is divided into Unit and Integration tests.

### Integration Tests
- **`test_orchestrator.py`**: Validates the end-to-end flow of the main `app_graph`. It mocks LLM nodes to verify that data correctly passes from the `semantic_splitter` to the `synthesizer`.
- **`test_worker_subgraph.py`**: Coverage for the recursive decomposition logic. It checks if complex tasks correctly spawn child subgraphs and respect recursion depth limits.
- **`test_depth_propagation.py`**: Ensures that metadata like `depth` and `root_task_id` are preserved when the `graph_compiler` spawns a dynamic graph.
- **`test_forced_subgraph.py`**: Verifies that specific agent types (like `Sub-Orchestrator`) successfully trigger the sub-orchestration pipeline.
- **`test_warnings.py`**: Tests the "Three-Tier Escalation Protocol" for budget limits and low confidence scores.

### Unit Tests
- **`test_compiler.py`**: Unit tests for the `graph_compiler_node` logic.
- **`test_cost_tracking.py`**: Verifies that the `CostTracker` accurately accumulates tokens and USD costs across different nodes.
- **`test_nodes.py`**: Tests individual nodes (like `validate_node`) in total isolation with mock states.

## ➕ Adding New Tests

When adding new functionality, follow these steps to add corresponding tests:

### 1. Identify the Category
- **Unit Test**: If testing a single function/node with no dependencies.
- **Integration Test**: If testing how a node interacts with the state or other nodes in a graph.

### 2. Mocking LangGraph Dependencies
LangGraph nodes often require a checkpointer. When testing nodes that compile subgraphs:
- Use `langgraph.checkpoint.memory.MemorySaver` for mocking `agents.shared_memory.memory`.
- Avoid `MagicMock` for checkpointers as LangGraph performs instance checks.

### 3. Mocking LLMs
To keep tests fast and deterministic:
- Patch `with_structured_output` on the `llm` instance used in the module under test.
- Example:
  ```python
  with patch("agents.your_module.llm") as mock_llm:
      mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=YourPydanticModel(...))
  ```

### 4. Handling State
Use the factories in `System_Testing/tests/utils/mocks.py` or `conftest.py` to generate consistent `AgentState` objects.

### 5. Verify the Return Structure
Most nodes return a dictionary. Ensure your test asserts both the specific output AND the presence of `usage_stats` if the node tracks costs.
