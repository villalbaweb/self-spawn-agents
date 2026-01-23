import pytest
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import os

# Set ENV for testing before imports
os.environ["MAX_RECURSION_DEPTH"] = "3"

import sys

from agents.tools.subgraph import spawn_subgraph
from agents.workers.generic import generic_worker_node
from agents.state import AgentState

class TestInceptionFix(unittest.IsolatedAsyncioTestCase):
    
    @patch("agent.app_graph") # Patch the actual source where subgraph imports from
    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_max_recursion_depth(self, mock_app_graph):
        """Verify that spawn_subgraph blocks recursion when depth >= MAX_RECURSION_DEPTH."""
        print("\n🧪 Testing Max Recursion Limit...")
        
        # Setup mock return for success case
        mock_app_graph.ainvoke = AsyncMock(return_value={"subtasks": [], "results": {}})
        
        # Test Case 1: Depth Limit Reached
        result = await spawn_subgraph.ainvoke({"task": "test", "depth": 3})
        print(f"Result at depth 3: {result}")
        self.assertIn("DEPTH LIMIT REACHED", result)
        
        # Verify app_graph was NOT called
        mock_app_graph.ainvoke.assert_not_called()
        
        # Test Case 2: Depth Limit OK
        result_ok = await spawn_subgraph.ainvoke({"task": "test", "depth": 2})
        print(f"Result at depth 2: {result_ok}")
        
        # Verify app_graph WAS called
        mock_app_graph.ainvoke.assert_called_once()
        # Verify it was called with incremented depth
        call_args = mock_app_graph.ainvoke.call_args[0][0]
        self.assertEqual(call_args["depth"], 3)
        self.assertNotIn("DEPTH LIMIT REACHED", result_ok)


    @patch("agents.workers.generic.spawn_subgraph")
    @patch("agents.workers.generic.web_search") 
    @patch("agents.workers.generic.llm")
    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_tool_binding_and_depth_injection(self, mock_llm, mock_web_search, mock_spawn_subgraph):
        """Verify Researcher tools and proper depth injection."""
        print("\n🧪 Testing Tool Binding & Depth Injection...")
        
        # Setup Mocks
        mock_llm.bind_tools = MagicMock()
        mock_bound_llm = AsyncMock()
        mock_llm.bind_tools.return_value = mock_bound_llm
        
        # Configure tool mocks to have names (so .name access works)
        mock_web_search.name = "web_search"
        mock_spawn_subgraph.name = "spawn_subgraph"
        
        # Mock LLM causing a spawning tool call
        
        # Mock LLM causing a spawning tool call
        mock_bound_llm.ainvoke.return_value = MagicMock(
            tool_calls=[{"name": "spawn_subgraph", "args": {"task": "subtask"}}],
            content="Spawning..."
        )
        
        # Mock the tool execution return
        mock_spawn_subgraph.ainvoke = AsyncMock(return_value="Mocked Recursion Result")

        # 1. Run generic worker with a depth of 2
        test_state = {"depth": 2}
        await generic_worker_node(test_state, "Research something", "Researcher")
        
        # Check if spawn_subgraph was called with depth=2
        # generic_worker calls: await spawn_subgraph.ainvoke(tool_args)
        # where tool_args should have "depth": 2 added.
        args, _ = mock_spawn_subgraph.ainvoke.call_args
        called_tool_args = args[0]
        
        print(f"Spawn Tool Args: {called_tool_args}")
        self.assertEqual(called_tool_args.get("depth"), 2)
        
        # 2. Verify Researcher got web_search bound
        bind_args, _ = mock_llm.bind_tools.call_args
        tools_list = bind_args[0]
        tool_names = [t.name for t in tools_list]
        print(f"Researcher Tools: {tool_names}")
        self.assertIn("web_search", tool_names)

if __name__ == "__main__":
    unittest.main()
