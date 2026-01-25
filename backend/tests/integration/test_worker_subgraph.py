"""
Tests for the Native Worker Subgraph (Epic 4.1).

Verifies the hybrid execute flow:
- Simple tasks: Direct execute → validate (2 LLM calls)
- Complex tasks: Delegate to full orchestration for multi-level spawning
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agents.subgraphs import worker_subgraph, build_worker_subgraph, WorkerState
from agents.subgraphs.worker_subgraph import execute_node, validate_node, analyze_task_complexity


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


class TestComplexityAnalysis:
    """Tests for task complexity detection."""
    
    @pytest.mark.asyncio
    async def test_simple_task_detected_by_heuristics(self):
        """Simple short tasks should be detected without LLM call."""
        result = await analyze_task_complexity("Find the current price of Bitcoin")
        assert result["needs_orchestration"] is False
        assert "heuristics" in result["reasoning"].lower()
    
    @pytest.mark.asyncio
    async def test_complex_task_triggers_llm_analysis(self):
        """Complex tasks with multiple keywords should trigger LLM analysis."""
        complex_task = "Build a complete REST API with authentication, database integration, and automated testing"
        
        mock_response = MagicMock()
        mock_response.content = '{"needs_orchestration": true, "reasoning": "Multiple deliverables"}'
        
        with patch("agents.subgraphs.worker_subgraph.llm_mini") as mock_llm:
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            result = await analyze_task_complexity(complex_task)
            
            assert result["needs_orchestration"] is True


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
        # CompiledGraph should have ainvoke method
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
        
        with patch("agents.subgraphs.worker_subgraph.analyze_task_complexity", new_callable=AsyncMock) as mock_analyze, \
             patch("agents.subgraphs.worker_subgraph.generic_worker_node", new_callable=AsyncMock) as mock_worker:
            
            mock_analyze.return_value = {"needs_orchestration": False, "reasoning": "Simple task"}
            mock_worker.return_value = mock_result
            
            result = await execute_node(simple_worker_state)
            
            mock_worker.assert_called_once()
            assert result["all_agents"][0]["orchestration_mode"] == "direct"
            assert "AI is transforming" in result["results"]["test_worker_1"]
    
    @pytest.mark.asyncio
    async def test_complex_task_uses_full_orchestration(self, complex_worker_state):
        """Complex tasks should delegate to full app_graph orchestration."""
        mock_orchestration_result = {
            "synthesis": "Complete auth system implemented with OAuth2, JWT, and RBAC.",
            "results": {"auth_module": "JWT middleware", "rbac_module": "Permission system"},
            "all_agents": [
                {"id": "researcher_1", "role": "Researcher", "depth": 2},
                {"id": "coder_1", "role": "Coder", "depth": 2}
            ],
            "all_edges": [],
            "usage_stats": {"steps": 5, "cost": 0.15}
        }
        
        with patch("agents.subgraphs.worker_subgraph.analyze_task_complexity", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = {"needs_orchestration": True, "reasoning": "Multiple deliverables"}
            
            with patch("agent.app_graph") as mock_app_graph:
                mock_app_graph.ainvoke = AsyncMock(return_value=mock_orchestration_result)
                
                result = await execute_node(complex_worker_state)
                
                mock_app_graph.ainvoke.assert_called_once()
                assert result["all_agents"][0]["orchestration_mode"] == "full"
                assert result["all_agents"][0]["role"] == "SubOrchestrator"
                # Should include child agents
                assert len(result["all_agents"]) == 3  # orchestrator + 2 children


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
            mock_confidence.return_value = mock_eval
            
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
        
        with patch("agents.subgraphs.worker_subgraph.analyze_task_complexity", new_callable=AsyncMock) as mock_analyze, \
             patch("agents.subgraphs.worker_subgraph.generic_worker_node", new_callable=AsyncMock) as mock_worker, \
             patch("agents.subgraphs.worker_subgraph.evaluate_confidence", new_callable=AsyncMock) as mock_eval:
            
            mock_analyze.return_value = {"needs_orchestration": False, "reasoning": "Simple task"}
            mock_worker.return_value = mock_worker_result
            mock_eval.return_value = mock_confidence
            
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


class TestDeepOrchestration:
    """Tests verifying multi-level spawning capability is preserved."""
    
    @pytest.mark.asyncio
    async def test_complex_task_spawns_child_graph(self, complex_worker_state):
        """Complex task should spawn full orchestration with child agents."""
        # Simulate a 3-level deep orchestration result
        mock_orchestration = {
            "synthesis": "Full auth system built",
            "results": {
                "oauth_module": "OAuth2 implementation",
                "jwt_module": "JWT token service", 
                "rbac_module": "Role-based access control"
            },
            "all_agents": [
                {"id": "oauth_researcher", "role": "Researcher", "depth": 2, "instruction": "OAuth2 best practices"},
                {"id": "jwt_coder", "role": "Coder", "depth": 2, "instruction": "Implement JWT"},
                {"id": "rbac_orchestrator", "role": "SubOrchestrator", "depth": 2, "instruction": "Build RBAC"},
                {"id": "rbac_researcher", "role": "Researcher", "depth": 3, "instruction": "RBAC patterns"},
                {"id": "rbac_coder", "role": "Coder", "depth": 3, "instruction": "Permission decorators"}
            ],
            "all_edges": [
                {"source": "rbac_orchestrator", "target": "rbac_researcher"},
                {"source": "rbac_orchestrator", "target": "rbac_coder"}
            ],
            "usage_stats": {"steps": 8, "cost": 0.25}
        }
        
        with patch("agents.subgraphs.worker_subgraph.analyze_task_complexity", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = {"needs_orchestration": True, "reasoning": "Multi-step build"}
            
            with patch("agent.app_graph") as mock_app:
                mock_app.ainvoke = AsyncMock(return_value=mock_orchestration)
                
                result = await execute_node(complex_worker_state)
                
                # Verify multi-level agents are present
                agent_depths = [a["depth"] for a in result["all_agents"]]
                assert 1 in agent_depths  # Parent orchestrator
                assert 2 in agent_depths  # Level 2 agents
                assert 3 in agent_depths  # Level 3 agents (deep spawning works!)
                
                # Verify hierarchy edges created
                assert len(result["all_edges"]) > 0
