import pytest
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os
import asyncio


# Import the actual graph
from app_graph import app_graph
from agents.workers.generic_worker import generic_worker_node

class TestFullChainDepth(unittest.IsolatedAsyncioTestCase):
    
    @pytest.mark.skip(reason="Legacy test: spawn_subgraph is no longer used in generic_worker (refactored to graph recursion)")
    @patch("config.llm_providers.llm")
    @patch("agents.tools.subgraph.spawn_subgraph") # Mock the tool execution to capture args
    @pytest.mark.asyncio
    async def test_depth_propagation_in_full_chain(self, mock_spawn_subgraph, mock_llm):
        """
        Verify that passing depth=10 to app_graph results in spawn_subgraph being called with depth=10.
        """
        print("\n🧪 Testing Full Chain Depth Propagation...")
        
        # 1. Mock Semantic Splitter (LLM structured output)
        # It's called first.
        mock_splitter_resp = MagicMock()
        mock_splitter_resp.subtasks = ["subtask1"]
        
        # 2. Mock Supervisor (LLM structured output)
        mock_plan_resp = MagicMock()
        mock_plan_resp.model_dump.return_value = {
            "nodes": [
                {"id": "node1", "agent_type": "Researcher", "instruction": "research", "dependencies": []}
            ],
            "explanation": "plan"
        }
        
        # 3. Mock Generic Worker (LLM tool call)
        # The worker calls bind_tools, then ainvoke.
        mock_bound_llm = AsyncMock()
        mock_bound_llm.ainvoke.return_value = MagicMock(
            tool_calls=[{"name": "spawn_subgraph", "args": {"task": "recursive_task"}}],
            content="Spawning..."
        )
        
        # Setup the side_effect for llm.with_structured_output to return different mocks for splitter vs supervisor
        # Splitter runs first, then Supervisor.
        # But generic worker uses llm.bind_tools().
        
        # We need to handle the calls carefully.
        # agent.py -> semantic_splitter -> llm.with_structured_output(SubtaskList)
        # agent.py -> supervisor -> llm.with_structured_output(GraphPlan)
        # graph_compiler -> generic -> llm.bind_tools(...)
        
        async def mock_structured_ainvoke(messages):
            # Hacky way to distinguish: look at system prompt or just sequence?
            # Splitter prompt has "Expert Task Decomposer"
            # Supervisor prompt has "System Architect"
            content = messages[0].content
            if "Decomposer" in content:
                print("   -> Mocking Splitter Output")
                return mock_splitter_resp
            else:
                print("   -> Mocking Supervisor Output")
                return mock_plan_resp

        mock_structured_llm = MagicMock()
        mock_structured_llm.ainvoke = AsyncMock(side_effect=mock_structured_ainvoke)
        
        mock_llm.with_structured_output.return_value = mock_structured_llm
        mock_llm.bind_tools.return_value = mock_bound_llm
        
        # Mock spawn_subgraph to return a string
        mock_spawn_subgraph.ainvoke = AsyncMock(return_value="Recursion Done")
        mock_spawn_subgraph.name = "spawn_subgraph"

        # EXECUTE
        print("▶️ running app_graph with depth=10")
        inputs = {
            "task": "Test Root",
            "depth": 10,
            "subtasks": [],
            "graph_plan": {},
            "results": {}
        }
        
        await app_graph.ainvoke(inputs)
        
        # ASSERT
        # Verify spawn_subgraph called
        mock_spawn_subgraph.ainvoke.assert_called()
        
        # Check args
        args = mock_spawn_subgraph.ainvoke.call_args[0][0]
        print(f"args passed to spawn_subgraph: {args}")
        
        self.assertEqual(args.get("depth"), 10, f"Expected depth 10, got {args.get('depth')}")

if __name__ == "__main__":
    unittest.main()
