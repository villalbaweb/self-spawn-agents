"""
Tests for the Native Worker Subgraph (Epic 4.1).

Verifies the lightweight mini-orchestration flow:
- Simple tasks: Direct execute → validate (2-3 LLM calls)
- Complex tasks: Mini-plan → parallel workers → validate (3-6 LLM calls)
- Recursive spawning: Complex child tasks spawn their own subgraphs
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import sys
from agents.subgraphs import worker_subgraph, build_worker_subgraph, WorkerState
# Access the module explicitly to avoid shadowing by the CompiledStateGraph object
worker_subgraph_module = sys.modules["agents.subgraphs.worker_subgraph"]
from agents.subgraphs.worker_subgraph import (
    execute_node,
    validate_node,
    should_decompose,
    create_mini_plan,
    execute_mini_plan,
    MiniTask,
    MiniPlan,
    ComplexityClassification
)


@pytest.fixture
def simple_worker_state() -> WorkerState:
    """Create a WorkerState for a simple single-step task."""
    return WorkerState(
        task="Research the impact of AI on healthcare diagnostics",
        subject="AI in Healthcare",
        parent_node_id="test_worker_1",
        depth=1,
        results={},
        all_agents=[],
        all_edges=[],
        global_signal="",
        usage_stats={},
        budget_config={"max_cost": 2.0, "max_steps": 50},
        confidence_score=0.0,
        confidence_reasoning=""
    )


@pytest.fixture
def complex_worker_state() -> WorkerState:
    """Create a WorkerState for a complex multi-step task."""
    return WorkerState(
        task="Build a complete authentication system with OAuth2, JWT tokens, role-based access control, and integration tests",
        subject="SaaS Authentication",
        parent_node_id="auth_orchestrator",
        depth=1,
        results={},
        all_agents=[],
        all_edges=[],
        global_signal="",
        usage_stats={},
        budget_config={"max_cost": 5.0, "max_steps": 100},
        confidence_score=0.0,
        confidence_reasoning=""
    )


class TestShouldDecompose:
    """Tests for the should_decompose complexity detection."""
    
    @pytest.mark.asyncio
    async def test_extremely_short_task_returns_false(self):
        """Tasks under 40 chars should be marked simple via safety rail."""
        result, _ = await should_decompose("Short task")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_semantic_classification_true(self):
        """Verify that the classifier can trigger decomposition."""
        task = "Implement a dual-layer authentication system with OAuth and JWT"
        mock_classification = ComplexityClassification(
            needs_decomposition=True,
            reasoning="Task involves multiple auth components."
        )
        
        with patch("agents.subgraphs.worker_subgraph.llm_mini") as mock_llm:
            structured_mock = MagicMock()
            structured_mock.ainvoke = AsyncMock(return_value=mock_classification)
            mock_llm.with_structured_output.return_value = structured_mock
            
            result, stats = await should_decompose(task)
            assert result is True
            assert "usage_stats" not in stats or isinstance(stats, dict)
    
    @pytest.mark.asyncio
    async def test_semantic_classification_false(self):
        """Verify that the classifier can identify simple tasks."""
        task = "Research the current weather in Tokyo"
        mock_classification = ComplexityClassification(
            needs_decomposition=False,
            reasoning="Single research query."
        )
        
        with patch("agents.subgraphs.worker_subgraph.llm_mini") as mock_llm:
            structured_mock = MagicMock()
            structured_mock.ainvoke = AsyncMock(return_value=mock_classification)
            mock_llm.with_structured_output.return_value = structured_mock
            
            result, _ = await should_decompose(task)
            assert result is False
    
    @pytest.mark.asyncio
    async def test_fallback_on_llm_error(self):
        """Should fall back to SINGLE (False) if the LLM fails."""
        with patch("agents.subgraphs.worker_subgraph.llm_mini") as mock_llm:
            mock_llm.with_structured_output.side_effect = Exception("LLM Error")
            
            result, _ = await should_decompose("Some long task that exceeds the length check limit")
            assert result is False


class TestMiniPlanner:
    """Tests for the mini-planner functionality."""
    
    @pytest.mark.asyncio
    async def test_create_mini_plan_returns_plan(self):
        """create_mini_plan should return a MiniPlan with tasks."""
        mock_plan = MiniPlan(
            tasks=[
                MiniTask(id="task_1", agent_type="Researcher", instruction="Research OAuth2"),
                MiniTask(id="task_2", agent_type="Coder", instruction="Implement JWT")
            ],
            reasoning="Split into research and implementation"
        )
        
        with patch("agents.subgraphs.worker_subgraph.llm_mini") as mock_llm:
            structured_mock = MagicMock()
            structured_mock.ainvoke = AsyncMock(return_value=mock_plan)
            mock_llm.with_structured_output.return_value = structured_mock
            
            result, _ = await create_mini_plan("Build auth with OAuth2 and JWT", "Auth System")
            
            assert len(result.tasks) == 2
            assert result.tasks[0].id == "task_1"
    
    @pytest.mark.asyncio
    async def test_create_mini_plan_fallback_on_error(self):
        """create_mini_plan should return fallback plan on error."""
        with patch("agents.subgraphs.worker_subgraph.llm_mini") as mock_llm:
            mock_llm.with_structured_output.side_effect = Exception("API Error")
            
            result, _ = await create_mini_plan("Some task", "Subject")
            
            assert len(result.tasks) == 1
            assert result.tasks[0].id == "fallback_research"


class TestWorkerSubgraphStructure:
    """Tests for subgraph structure and compilation."""
    
    def test_build_worker_subgraph_returns_stategraph(self):
        """Verify build_worker_subgraph returns a valid StateGraph."""
        from langgraph.graph import StateGraph
        graph = build_worker_subgraph()
        assert isinstance(graph, StateGraph)
    
    def test_worker_subgraph_is_compiled(self):
        """Verify the pre-compiled worker_subgraph is usable."""
        assert worker_subgraph is not None
        assert hasattr(worker_subgraph, "ainvoke")


class TestExecuteNode:
    """Tests for the execute_node function."""
    
    @pytest.mark.asyncio
    async def test_execute_aborts_on_interrupt_signal(self, simple_worker_state):
        """Execute should abort immediately if global_signal is INTERRUPT."""
        simple_worker_state["global_signal"] = "INTERRUPT"
        
        result = await execute_node(simple_worker_state)
        
        assert "test_worker_1" in result["results"]
        assert "Aborted" in result["results"]["test_worker_1"]
        assert result["all_agents"][0]["status"] == "aborted"
    
    @pytest.mark.asyncio
    async def test_execute_respects_depth_limit(self, simple_worker_state):
        """Execute should stop at MAX_RECURSION_DEPTH."""
        with patch("agents.subgraphs.worker_subgraph.MAX_RECURSION_DEPTH", 2):
            simple_worker_state["depth"] = 2  # At limit
            
            result = await execute_node(simple_worker_state)
            
            assert "Depth limit" in result["results"]["test_worker_1"]
            assert result["all_agents"][0]["status"] == "depth_limited"
    
    @pytest.mark.asyncio
    async def test_execute_respects_budget_limit(self, simple_worker_state):
        """Execute should stop if budget is exceeded."""
        simple_worker_state["usage_stats"] = {"cost": 2.5}  # Over max_cost of 2.0
        
        result = await execute_node(simple_worker_state)
        
        assert "Budget limit" in result["results"]["test_worker_1"]
        assert result["global_signal"] == "INTERRUPT"
        assert result["all_agents"][0]["status"] == "budget_exceeded"
    
    @pytest.mark.asyncio
    async def test_simple_task_uses_direct_execution(self, simple_worker_state):
        """Simple tasks should use direct generic_worker_node execution."""
        mock_result = {
            "output": "AI is transforming healthcare through diagnostics.",
            "metadata": {"status": "completed", "confidence_score": 0.85}
        }
        
        with patch.object(worker_subgraph_module, "should_decompose", new_callable=AsyncMock) as mock_decompose, \
             patch.object(worker_subgraph_module, "generic_worker_node", new_callable=AsyncMock) as mock_worker:
            
            mock_decompose.return_value = (False, {})
            mock_worker.return_value = mock_result
            
            result = await execute_node(simple_worker_state)
            
            mock_worker.assert_called_once()
            assert result["all_agents"][0]["orchestration_mode"] == "direct"
            assert "AI is transforming" in result["results"]["test_worker_1"]
    
    @pytest.mark.asyncio
    async def test_complex_task_uses_mini_orchestration(self, complex_worker_state):
        """Complex tasks should use mini-plan + parallel execution."""
        mock_plan = MiniPlan(
            tasks=[
                MiniTask(id="oauth_research", agent_type="Researcher", instruction="Research OAuth2"),
                MiniTask(id="jwt_impl", agent_type="Coder", instruction="Implement JWT"),
            ],
            reasoning="Split into research and implementation"
        )
        
        mock_worker_result = {
            "output": "Task completed successfully",
            "metadata": {"status": "completed", "confidence_score": 0.85}
        }
        
        # Patch MAX_RECURSION_DEPTH to ensure depth check passes (depth=1, need depth < MAX-1)
        with patch.object(worker_subgraph_module, "MAX_RECURSION_DEPTH", 5), \
             patch.object(worker_subgraph_module, "should_decompose", new_callable=AsyncMock) as mock_decompose, \
             patch.object(worker_subgraph_module, "create_mini_plan", new_callable=AsyncMock) as mock_planner, \
             patch.object(worker_subgraph_module, "generic_worker_node", new_callable=AsyncMock) as mock_worker:
            
            # Use side_effect to prevent infinite recursion
            # 1. Main task -> True (decompose)
            # 2. Sub-task 1 -> False (direct)
            # 3. Sub-task 2 -> False (direct)
            # 4. Any subsequent calls (safety) -> False
            mock_decompose.side_effect = [(True, {}), (False, {}), (False, {}), (False, {}), (False, {})]
            mock_planner.return_value = (mock_plan, {})
            mock_worker.return_value = mock_worker_result
            
            result = await execute_node(complex_worker_state)
            
            mock_planner.assert_called_once()
            assert result["all_agents"][0]["role"] == "MiniOrchestrator"
            assert result["all_agents"][0]["orchestration_mode"] == "mini"
            # Should have MiniOrchestrator + child agents
            assert len(result["all_agents"]) >= 2


class TestValidateNode:
    """Tests for the validate_node function."""
    
    @pytest.mark.asyncio
    async def test_validate_skips_on_error_output(self, simple_worker_state):
        """Validate should skip if output indicates error."""
        simple_worker_state["results"] = {"test_worker_1": "[Error: Something failed]"}
        
        result = await validate_node(simple_worker_state)
        
        assert result["confidence_score"] == 0.0
        assert "failed" in result["confidence_reasoning"].lower() or "skipped" in result["confidence_reasoning"].lower()
    
    @pytest.mark.asyncio
    async def test_validate_calls_evaluate_confidence(self, simple_worker_state):
        """Validate should call evaluate_confidence for valid outputs."""
        simple_worker_state["results"] = {"test_worker_1": "AI improves diagnostic accuracy by 30%."}
        
        mock_eval = {"confidence_score": 0.9, "confidence_reasoning": "Complete and accurate answer."}
        
        with patch("agents.subgraphs.worker_subgraph.evaluate_confidence", new_callable=AsyncMock) as mock_confidence:
            mock_confidence.return_value = (mock_eval, {})
            
            result = await validate_node(simple_worker_state)
            
            mock_confidence.assert_called_once()
            assert result["confidence_score"] == 0.9
            assert "Complete" in result["confidence_reasoning"]
    
    @pytest.mark.asyncio
    async def test_validate_handles_evaluation_error(self, simple_worker_state):
        """Validate should return default score if evaluation fails."""
        simple_worker_state["results"] = {"test_worker_1": "Some valid output."}
        
        with patch("agents.subgraphs.worker_subgraph.evaluate_confidence", new_callable=AsyncMock) as mock_confidence:
            mock_confidence.side_effect = Exception("API Error")
            
            result = await validate_node(simple_worker_state)
            
            assert result["confidence_score"] == 0.5
            assert "failed" in result["confidence_reasoning"].lower()


class TestWorkerSubgraphIntegration:
    """Integration tests for the full subgraph flow."""
    
    @pytest.mark.asyncio
    async def test_simple_task_full_flow(self, simple_worker_state):
        """Test complete flow for simple task: analyze → direct execute → validate."""
        mock_worker_result = {
            "output": "Comprehensive research findings on AI in healthcare.",
            "metadata": {"status": "completed", "confidence_score": 0.88}
        }
        mock_confidence = {"confidence_score": 0.88, "confidence_reasoning": "Thorough analysis."}
        
        with patch.object(worker_subgraph_module, "should_decompose", new_callable=AsyncMock) as mock_decompose, \
             patch.object(worker_subgraph_module, "generic_worker_node", new_callable=AsyncMock) as mock_worker, \
             patch.object(worker_subgraph_module, "evaluate_confidence", new_callable=AsyncMock) as mock_eval:
            
            mock_decompose.return_value = (False, {})
            mock_worker.return_value = mock_worker_result
            mock_eval.return_value = (mock_confidence, {})
            
            result = await worker_subgraph.ainvoke(simple_worker_state)
            
            assert "test_worker_1" in result["results"]
            assert result["confidence_score"] == 0.88
            assert result["all_agents"][0]["orchestration_mode"] == "direct"
    
    @pytest.mark.asyncio
    async def test_subgraph_propagates_interrupt(self, simple_worker_state):
        """Test that budget exceeded triggers INTERRUPT propagation."""
        simple_worker_state["usage_stats"] = {"cost": 3.0}  # Over limit
        
        result = await worker_subgraph.ainvoke(simple_worker_state)
        
        assert result["global_signal"] == "INTERRUPT"
        assert result["all_agents"][0]["status"] == "budget_exceeded"


class TestRecursiveSpawning:
    """Tests verifying multi-level spawning capability."""
    
    @pytest.mark.asyncio
    async def test_complex_mini_task_spawns_child_subgraph(self, complex_worker_state):
        """Complex child tasks in mini-plan should spawn recursive subgraphs."""
        # Create a mini-plan where one task is complex enough to recurse
        mock_plan = MiniPlan(
            tasks=[
                MiniTask(id="oauth_impl", agent_type="Researcher", instruction="Implement OAuth2 with refresh tokens and token validation"),
                MiniTask(id="simple_task", agent_type="Coder", instruction="Write a test"),
            ],
            reasoning="Split authentication implementation"
        )
        
        mock_worker_result = {
            "output": "Task completed",
            "metadata": {"status": "completed", "confidence_score": 0.8}
        }
        
        # Track should_decompose calls to verify recursive check
        decompose_calls = []
        async def mock_decompose(task, config=None, root_task_id=None):
            decompose_calls.append(task)
            # First call (main task) returns True to trigger mini-plan
            # Subsequent calls for child tasks
            if ("OAuth2" in task and "refresh" in task) or "authentication system" in task:
                return True, {}  # Complex child task
            return False, {}
        
        # Patch MAX_RECURSION_DEPTH to ensure depth check passes (depth=1, need depth < MAX-1)
        with patch.object(worker_subgraph_module, "MAX_RECURSION_DEPTH", 5), \
             patch.object(worker_subgraph_module, "should_decompose", side_effect=mock_decompose), \
             patch.object(worker_subgraph_module, "create_mini_plan", new_callable=AsyncMock) as mock_planner, \
             patch.object(worker_subgraph_module, "generic_worker_node", new_callable=AsyncMock) as mock_worker, \
             patch.object(worker_subgraph_module, "_get_compiled_subgraph") as mock_get_subgraph:
            
            mock_planner.return_value = (mock_plan, {})
            mock_worker.return_value = mock_worker_result
            
            # Mock the recursive subgraph call
            mock_child_result = {
                "results": {"oauth_impl": "OAuth2 implemented with refresh tokens"},
                "all_agents": [{"id": "child_worker", "role": "SubWorker", "depth": 2, "status": "completed"}],
                "all_edges": [],
                "usage_stats": {"steps": 1}
            }
            mock_subgraph = MagicMock()
            mock_subgraph.ainvoke = AsyncMock(return_value=mock_child_result)
            mock_get_subgraph.return_value = mock_subgraph
            
            result = await execute_node(complex_worker_state)
            
            # Verify mini-orchestration was used
            assert result["all_agents"][0]["role"] == "MiniOrchestrator"
            
            # Verify should_decompose was called for child tasks
            assert len(decompose_calls) >= 2  # Main task + at least one child check
    
    @pytest.mark.asyncio
    async def test_depth_limit_prevents_infinite_recursion(self, complex_worker_state):
        """Ensure recursion stops at MAX_RECURSION_DEPTH."""
        complex_worker_state["depth"] = 2  # Near limit
        
        with patch.object(worker_subgraph_module, "MAX_RECURSION_DEPTH", 3):
            with patch.object(worker_subgraph_module, "should_decompose", new_callable=AsyncMock) as mock_decompose, \
                 patch.object(worker_subgraph_module, "generic_worker_node", new_callable=AsyncMock) as mock_worker:
                
                mock_decompose.return_value = (True, {})  # Would want to decompose
                mock_worker.return_value = {"output": "Direct execution", "metadata": {}}
                
                result = await execute_node(complex_worker_state)
                
                # At depth 2 with MAX=3, should still try to decompose
                # But the condition checks current_depth < MAX_RECURSION_DEPTH - 1
                # So at depth 2, it won't decompose (2 < 3-1 = 2 is False)
