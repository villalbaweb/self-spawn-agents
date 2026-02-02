import pytest
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os


import sys
from agents.graph_compiler import graph_compiler_node
graph_compiler_module = sys.modules["agents.graph_compiler"]

class TestDepthPropagation(unittest.IsolatedAsyncioTestCase):
    
    @patch("agents.graph_compiler.interrupt")
    @patch.object(graph_compiler_module, "StateGraph")
    @pytest.mark.asyncio
    async def test_depth_passed_to_dynamic_graph(self, mock_state_graph_cls, mock_interrupt):
        """Verify that graph_compiler_node initializes dynamic graph with depth from parent state."""
        print("\n🧪 Testing Depth Propagation in Graph Compiler...")
        
        # Setup Mocks
        mock_workflow = MagicMock()
        mock_state_graph_cls.return_value = mock_workflow
        
        mock_app = AsyncMock()
        mock_workflow.compile.return_value = mock_app
        mock_app = AsyncMock()
        mock_workflow.compile.return_value = mock_app
        mock_app.ainvoke.return_value = {"results": {}}
        
        # Mock aget_state to return clean state (no resume needed)
        mock_state_snapshot = MagicMock()
        mock_state_snapshot.next = None # Prop 'next' is None
        mock_state_snapshot.values = {} # Start with empty values so it triggers START path
        mock_app.aget_state.return_value = mock_state_snapshot
        
        # Input State with specific depth
        parent_state = {
            "graph_plan": {
                "nodes": [{"id": "node1", "instruction": "do work", "agent_type": "Worker"}]
            },
            "depth": 5 # Arbitrary non-zero depth
        }
        
        # Run compiler node
        await graph_compiler_node(parent_state)
        
        # Verify app.ainvoke was called with initial state containing depth=5
        mock_app.ainvoke.assert_called_once()
        call_args = mock_app.ainvoke.call_args[0][0]
        
        print(f"Initial Dynamic State: {call_args}")
        self.assertEqual(call_args.get("depth"), 5)
        self.assertEqual(call_args.get("results"), {})

if __name__ == "__main__":
    unittest.main()
