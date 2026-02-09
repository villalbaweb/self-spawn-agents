"""
Knowledge Service - Semantic Long-Term Memory for Blueprint Caching.

This module provides vector-based storage and retrieval of successful
execution blueprints using pgvector in PostgreSQL.
"""
import os
import json
import asyncio
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime, timezone

from langchain_openai import OpenAIEmbeddings


@dataclass
class StoredBlueprint:
    """Represents a cached blueprint stored in the vector database."""
    id: str
    task_query: str
    graph_spec: Dict[str, Any]
    metadata: Dict[str, Any]
    similarity: float = 0.0
    created_at: Optional[datetime] = None


class KnowledgeService:
    """
    Manages semantic long-term memory for the agentic system.
    
    Uses pgvector (PostgreSQL) to store and retrieve execution blueprints
    based on semantic similarity of task descriptions.
    
    Attributes:
        db_url: PostgreSQL connection string
        embeddings: OpenAI embeddings model for vectorization
        similarity_threshold: Minimum similarity score for cache hits (default 0.85)
    """
    
    def __init__(
        self,
        db_url: Optional[str] = None,
        similarity_threshold: float = 0.85,
        embedding_model: str = "text-embedding-3-small"
    ):
        """
        Initialize the KnowledgeService.
        
        Args:
            db_url: PostgreSQL connection string. Defaults to DATABASE_URL env var.
            similarity_threshold: Minimum cosine similarity for cache hits.
            embedding_model: OpenAI embedding model to use.
        """
        self.db_url = db_url or os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable not set")
        
        self.similarity_threshold = similarity_threshold
        self.embeddings = OpenAIEmbeddings(model=embedding_model)
        self._pool = None
    
    async def _get_pool(self):
        """Get or create the connection pool."""
        if self._pool is None:
            from psycopg_pool import AsyncConnectionPool
            self._pool = AsyncConnectionPool(conninfo=self.db_url)
            await self._pool.open()
        return self._pool
    
    async def close(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
    
    async def search_blueprint(
        self,
        task_description: str,
        threshold: Optional[float] = None
    ) -> Optional[StoredBlueprint]:
        """
        Search for a cached blueprint matching the task description.
        
        Uses cosine similarity to find the most relevant blueprint.
        Returns None if no blueprint exceeds the similarity threshold.
        
        Args:
            task_description: The user's task/query to match against.
            threshold: Override the default similarity threshold.
            
        Returns:
            StoredBlueprint if a match is found, None otherwise.
        """
        threshold = threshold or self.similarity_threshold
        
        # Generate embedding for the query
        query_embedding = await self.embeddings.aembed_query(task_description)
        
        pool = await self._get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # Use pgvector's cosine distance operator (<=>)
                # 1 - distance = similarity
                await cur.execute(
                    """
                    SELECT 
                        id::text,
                        task_query,
                        graph_spec,
                        metadata,
                        1 - (embedding <=> %s::vector) as similarity,
                        created_at
                    FROM blueprints
                    WHERE 1 - (embedding <=> %s::vector) > %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT 1
                    """,
                    (query_embedding, query_embedding, threshold, query_embedding)
                )
                
                row = await cur.fetchone()
                
                if row:
                    return StoredBlueprint(
                        id=row[0],
                        task_query=row[1],
                        graph_spec=row[2],
                        metadata=row[3] or {},
                        similarity=float(row[4]),
                        created_at=row[5]
                    )
        
        return None
    
    async def archive_blueprint(
        self,
        task_description: str,
        blueprint: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Archive a successful blueprint for future retrieval.
        
        Args:
            task_description: The original task/query.
            blueprint: The execution graph specification (JSON-serializable).
            metadata: Optional metadata (execution stats, user feedback, etc.).
            
        Returns:
            The UUID of the newly created blueprint record.
        """
        # Generate embedding for the task
        task_embedding = await self.embeddings.aembed_query(task_description)
        
        pool = await self._get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO blueprints (task_query, graph_spec, embedding, metadata)
                    VALUES (%s, %s, %s::vector, %s)
                    RETURNING id::text
                    """,
                    (
                        task_description,
                        json.dumps(blueprint),
                        task_embedding,
                        json.dumps(metadata or {})
                    )
                )
                
                result = await cur.fetchone()
                await conn.commit()
                
                return result[0] if result else ""
    
    async def delete_blueprint(self, blueprint_id: str) -> bool:
        """
        Delete a blueprint by ID.
        
        Args:
            blueprint_id: UUID of the blueprint to delete.
            
        Returns:
            True if deleted, False if not found.
        """
        pool = await self._get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM blueprints WHERE id = %s::uuid",
                    (blueprint_id,)
                )
                await conn.commit()
                return cur.rowcount > 0


# Singleton instance for global access
_knowledge_service: Optional[KnowledgeService] = None


def get_knowledge_service() -> KnowledgeService:
    """Get the global KnowledgeService instance."""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service


async def init_knowledge_service() -> KnowledgeService:
    """Initialize and return the global KnowledgeService instance."""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service
