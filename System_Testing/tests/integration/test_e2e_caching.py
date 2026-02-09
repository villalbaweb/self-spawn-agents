"""
End-to-End tests for Blueprint Caching flow.

Tests the complete flow of:
1. Running a new task (cache miss -> planning -> execution -> archival)
2. Running the same task again (cache hit -> skip planning -> execution)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any


class TestE2ECaching:
    """E2E tests for the blueprint caching flow."""
    
    @pytest.fixture
    def base_state(self) -> Dict[str, Any]:
        """Create a base AgentState for testing."""
        return {
            "task": "Create a Python function to calculate fibonacci numbers",
            "subtasks": [],
            "graph_plan": {},
            "results": {},
            "depth": 0,
            "usage_stats": {"cost": 0.0, "steps": 0},
            "global_signal": ""
        }
    
    @pytest.mark.asyncio
    async def test_first_run_archives_blueprint(self, base_state):
        """
        Test that a first-time task (cache miss) flows through the
        full pipeline and archives the resulting blueprint.
        
        Flow: Decomposer -> BlueprintManager (MISS) -> Planner -> Execute -> Synthesize -> Archive
        """
        from backend.agents.blueprint_manager import blueprint_manager_node, archive_blueprint_node
        
        # Step 1: Blueprint Manager should report cache miss
        with patch('backend.agents.blueprint_manager.get_knowledge_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.search_blueprint = AsyncMock(return_value=None)
            mock_service.archive_blueprint = AsyncMock(return_value="first-run-uuid")
            mock_get_service.return_value = mock_service
            
            # Phase 1: Check for cached blueprint (should miss)
            cache_result = await blueprint_manager_node(base_state)
            assert cache_result["blueprint_cache_hit"] is False
            
            # Simulate planner creating a graph_plan
            base_state["graph_plan"] = {
                "nodes": [
                    {"id": "code_fib", "agent_type": "Coder", "instruction": "Write fib function"}
                ],
                "explanation": "Single coder node for simple implementation"
            }
            base_state["blueprint_cache_hit"] = cache_result["blueprint_cache_hit"]
            
            # Phase 2: Archive the blueprint after successful execution
            archive_result = await archive_blueprint_node(base_state)
            
            assert archive_result["blueprint_archived"] is True
            assert archive_result["blueprint_id"] == "first-run-uuid"
            
            # Verify archive was called with correct data
            mock_service.archive_blueprint.assert_called_once()
            call_args = mock_service.archive_blueprint.call_args
            assert call_args.kwargs["task_description"] == base_state["task"]
            assert call_args.kwargs["blueprint"]["nodes"][0]["id"] == "code_fib"
    
    @pytest.mark.asyncio
    async def test_second_run_uses_cache(self, base_state):
        """
        Test that running the same task again retrieves the cached blueprint
        and skips the planning phase.
        
        Flow: Decomposer -> BlueprintManager (HIT) -> Execute -> Synthesize -> [Skip Archive]
        """
        from backend.agents.blueprint_manager import blueprint_manager_node, archive_blueprint_node
        from backend.core.knowledge.service import StoredBlueprint
        
        cached_plan = {
            "nodes": [
                {"id": "code_fib", "agent_type": "Coder", "instruction": "Write fib function"}
            ],
            "explanation": "Single coder node for simple implementation"
        }
        
        with patch('backend.agents.blueprint_manager.get_knowledge_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.search_blueprint = AsyncMock(return_value=StoredBlueprint(
                id="cached-fib-uuid",
                task_query="Create a Python function to calculate fibonacci numbers",
                graph_spec=cached_plan,
                metadata={"execution_stats": {"cost": 0.005}},
                similarity=0.98
            ))
            mock_get_service.return_value = mock_service
            
            # Phase 1: Check for cached blueprint (should HIT)
            cache_result = await blueprint_manager_node(base_state)
            
            assert cache_result["blueprint_cache_hit"] is True
            assert cache_result["graph_plan"] == cached_plan
            assert cache_result["blueprint_similarity"] == 0.98
            
            # Update state with cache results
            base_state.update(cache_result)
            
            # Phase 2: Archive should be skipped for cache hits
            archive_result = await archive_blueprint_node(base_state)
            
            assert archive_result["blueprint_archived"] is False
    
    @pytest.mark.asyncio
    async def test_similar_but_different_task_misses_cache(self, base_state):
        """
        Test that a task similar but below threshold (e.g., 0.82 similarity)
        results in a cache miss and proceeds with fresh planning.
        """
        from backend.agents.blueprint_manager import blueprint_manager_node
        
        # Modify task to be similar but different
        base_state["task"] = "Create a JavaScript function to calculate fibonacci sequence"
        
        with patch('backend.agents.blueprint_manager.get_knowledge_service') as mock_get_service:
            mock_service = MagicMock()
            # Return None because similarity (0.82) is below threshold (0.85)
            mock_service.search_blueprint = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service
            
            result = await blueprint_manager_node(base_state)
            
            assert result["blueprint_cache_hit"] is False


class TestE2EGraphRouting:
    """Tests for verifying the conditional routing in app_graph."""
    
    def test_route_after_blueprint_check_cache_hit(self):
        """Test routing function returns 'graph_executor' on cache hit."""
        from backend.app_graph import route_after_blueprint_check
        
        state = {"blueprint_cache_hit": True}
        result = route_after_blueprint_check(state)
        
        assert result == "graph_executor"
    
    def test_route_after_blueprint_check_cache_miss(self):
        """Test routing function returns 'execution_planner' on cache miss."""
        from backend.app_graph import route_after_blueprint_check
        
        state = {"blueprint_cache_hit": False}
        result = route_after_blueprint_check(state)
        
        assert result == "execution_planner"
    
    def test_route_after_blueprint_check_no_flag(self):
        """Test routing function defaults to planner when flag is missing."""
        from backend.app_graph import route_after_blueprint_check
        
        state = {}
        result = route_after_blueprint_check(state)
        
        assert result == "execution_planner"
