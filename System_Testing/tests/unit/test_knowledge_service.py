"""
Unit tests for KnowledgeService.

Tests the core functionality of blueprint storage and retrieval
using mocked database connections.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Optional
import json


class TestStoredBlueprint:
    """Tests for the StoredBlueprint dataclass."""
    
    def test_stored_blueprint_creation(self):
        """Test basic StoredBlueprint instantiation."""
        from backend.core.knowledge.service import StoredBlueprint
        
        blueprint = StoredBlueprint(
            id="test-uuid",
            task_query="Test task",
            graph_spec={"nodes": []},
            metadata={"test": True},
            similarity=0.95
        )
        
        assert blueprint.id == "test-uuid"
        assert blueprint.task_query == "Test task"
        assert blueprint.similarity == 0.95


class TestKnowledgeServiceInit:
    """Tests for KnowledgeService initialization."""
    
    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql://test:test@localhost/test'})
    def test_init_with_env_var(self):
        """Test initialization with DATABASE_URL from environment."""
        from backend.core.knowledge.service import KnowledgeService
        
        service = KnowledgeService()
        assert service.db_url == 'postgresql://test:test@localhost/test'
        assert service.similarity_threshold == 0.85
    
    def test_init_with_explicit_url(self):
        """Test initialization with explicit database URL."""
        from backend.core.knowledge.service import KnowledgeService
        
        service = KnowledgeService(db_url='postgresql://explicit:url@localhost/db')
        assert service.db_url == 'postgresql://explicit:url@localhost/db'
    
    @patch.dict('os.environ', {}, clear=True)
    def test_init_without_url_raises(self):
        """Test that missing DATABASE_URL raises ValueError."""
        from backend.core.knowledge.service import KnowledgeService
        
        with pytest.raises(ValueError, match="DATABASE_URL"):
            KnowledgeService()


class TestKnowledgeServiceSearchBlueprint:
    """Tests for search_blueprint functionality."""
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql://test:test@localhost/test'})
    async def test_search_blueprint_cache_hit(self):
        """Test successful blueprint retrieval above threshold."""
        from backend.core.knowledge.service import KnowledgeService, StoredBlueprint
        
        service = KnowledgeService()
        
        # Mock the embeddings
        service.embeddings = MagicMock()
        service.embeddings.aembed_query = AsyncMock(return_value=[0.1] * 1536)
        
        # Mock the database pool and cursor
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=(
            "test-uuid",
            "Test query",
            {"nodes": [{"id": "node1"}]},
            {"meta": "data"},
            0.92,
            None
        ))
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        
        mock_conn = AsyncMock()
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        
        mock_pool = AsyncMock()
        mock_pool.connection = MagicMock(return_value=mock_conn)
        service._pool = mock_pool
        
        result = await service.search_blueprint("Find similar task")
        
        assert result is not None
        assert isinstance(result, StoredBlueprint)
        assert result.id == "test-uuid"
        assert result.similarity == 0.92
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql://test:test@localhost/test'})
    async def test_search_blueprint_cache_miss(self):
        """Test when no blueprint exceeds threshold."""
        from backend.core.knowledge.service import KnowledgeService
        
        service = KnowledgeService()
        
        # Mock the embeddings
        service.embeddings = MagicMock()
        service.embeddings.aembed_query = AsyncMock(return_value=[0.1] * 1536)
        
        # Mock cursor returning None (no match)
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        
        mock_conn = AsyncMock()
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        
        mock_pool = AsyncMock()
        mock_pool.connection = MagicMock(return_value=mock_conn)
        service._pool = mock_pool
        
        result = await service.search_blueprint("Completely new task")
        
        assert result is None


class TestKnowledgeServiceArchiveBlueprint:
    """Tests for archive_blueprint functionality."""
    
    @pytest.mark.asyncio
    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql://test:test@localhost/test'})
    async def test_archive_blueprint_success(self):
        """Test successful blueprint archival."""
        from backend.core.knowledge.service import KnowledgeService
        
        service = KnowledgeService()
        
        # Mock the embeddings
        service.embeddings = MagicMock()
        service.embeddings.aembed_query = AsyncMock(return_value=[0.1] * 1536)
        
        # Mock cursor
        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=("new-uuid",))
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=None)
        
        mock_conn = AsyncMock()
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        
        mock_pool = AsyncMock()
        mock_pool.connection = MagicMock(return_value=mock_conn)
        service._pool = mock_pool
        
        result = await service.archive_blueprint(
            task_description="New task to archive",
            blueprint={"nodes": [{"id": "node1"}]},
            metadata={"success": True}
        )
        
        assert result == "new-uuid"
