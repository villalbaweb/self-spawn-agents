"""
Integration tests for BlueprintManager node.

Tests the blueprint_manager_node behavior within the LangGraph workflow context.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any


class TestBlueprintManagerNode:
    """Integration tests for blueprint_manager_node."""
    
    @pytest.fixture
    def mock_state_with_task(self) -> Dict[str, Any]:
        """Create a mock AgentState with a task."""
        return {
            "task": "Research best practices for caching strategies",
            "subtasks": ["Identify caching patterns", "Compare Redis vs Memcached"],
            "graph_plan": {},
            "results": {},
            "depth": 0,
            "usage_stats": {"cost": 0.0, "steps": 0},
            "global_signal": ""
        }
    
    @pytest.fixture
    def mock_state_without_task(self) -> Dict[str, Any]:
        """Create a mock AgentState without a task."""
        return {
            "task": "",
            "subtasks": [],
            "graph_plan": {},
            "results": {},
            "depth": 0,
            "usage_stats": {},
            "global_signal": ""
        }
    
    @pytest.mark.asyncio
    async def test_blueprint_manager_cache_hit(self, mock_state_with_task):
        """Test blueprint_manager returns cached blueprint on hit."""
        from backend.agents.blueprint_manager import blueprint_manager_node
        from backend.core.knowledge.service import StoredBlueprint
        
        with patch('backend.agents.blueprint_manager.get_knowledge_service') as mock_get_service:
            # Setup mock service
            mock_service = MagicMock()
            mock_service.search_blueprint = AsyncMock(return_value=StoredBlueprint(
                id="cached-uuid",
                task_query="Research caching strategies",
                graph_spec={"nodes": [{"id": "research_node"}]},
                metadata={},
                similarity=0.91
            ))
            mock_get_service.return_value = mock_service
            
            result = await blueprint_manager_node(mock_state_with_task)
            
            assert result["blueprint_cache_hit"] is True
            assert result["graph_plan"] == {"nodes": [{"id": "research_node"}]}
            assert result["blueprint_id"] == "cached-uuid"
            assert result["blueprint_similarity"] == 0.91
    
    @pytest.mark.asyncio
    async def test_blueprint_manager_cache_miss(self, mock_state_with_task):
        """Test blueprint_manager returns empty result on miss."""
        from backend.agents.blueprint_manager import blueprint_manager_node
        
        with patch('backend.agents.blueprint_manager.get_knowledge_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.search_blueprint = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service
            
            result = await blueprint_manager_node(mock_state_with_task)
            
            assert result["blueprint_cache_hit"] is False
            assert "graph_plan" not in result
    
    @pytest.mark.asyncio
    async def test_blueprint_manager_no_task(self, mock_state_without_task):
        """Test blueprint_manager handles missing task gracefully."""
        from backend.agents.blueprint_manager import blueprint_manager_node
        
        result = await blueprint_manager_node(mock_state_without_task)
        
        assert result["blueprint_cache_hit"] is False
    
    @pytest.mark.asyncio
    async def test_blueprint_manager_error_handling(self, mock_state_with_task):
        """Test blueprint_manager degrades gracefully on error."""
        from backend.agents.blueprint_manager import blueprint_manager_node
        
        with patch('backend.agents.blueprint_manager.get_knowledge_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.search_blueprint = AsyncMock(side_effect=Exception("DB connection fail"))
            mock_get_service.return_value = mock_service
            
            result = await blueprint_manager_node(mock_state_with_task)
            
            # Should gracefully degrade, not crash
            assert result["blueprint_cache_hit"] is False


class TestArchiveBlueprintNode:
    """Integration tests for archive_blueprint_node."""
    
    @pytest.fixture
    def mock_state_for_archive(self) -> Dict[str, Any]:
        """Create a state ready for archival."""
        return {
            "task": "Research caching strategies",
            "subtasks": ["Identify patterns"],
            "graph_plan": {"nodes": [{"id": "node1"}]},
            "results": {"node1": "Completed research"},
            "depth": 0,
            "usage_stats": {"cost": 0.01, "steps": 3},
            "blueprint_cache_hit": False,
            "global_signal": ""
        }
    
    @pytest.mark.asyncio
    async def test_archive_blueprint_success(self, mock_state_for_archive):
        """Test successful blueprint archival."""
        from backend.agents.blueprint_manager import archive_blueprint_node
        
        with patch('backend.agents.blueprint_manager.get_knowledge_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.archive_blueprint = AsyncMock(return_value="new-archived-uuid")
            mock_get_service.return_value = mock_service
            
            result = await archive_blueprint_node(mock_state_for_archive)
            
            assert result["blueprint_archived"] is True
            assert result["blueprint_id"] == "new-archived-uuid"
    
    @pytest.mark.asyncio
    async def test_archive_blueprint_skips_cache_hit(self, mock_state_for_archive):
        """Test that cache hits are not re-archived."""
        from backend.agents.blueprint_manager import archive_blueprint_node
        
        mock_state_for_archive["blueprint_cache_hit"] = True
        
        result = await archive_blueprint_node(mock_state_for_archive)
        
        assert result["blueprint_archived"] is False
