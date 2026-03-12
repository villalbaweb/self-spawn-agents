"""
Checkpointer management for LangGraph state persistence.

PostgreSQL-based checkpointing with connection pooling for concurrent-safe operations.
Requires DATABASE_URL environment variable.
"""
import os
import sys
from typing import Optional

# Fix for Windows: psycopg requires SelectorEventLoop on Windows
if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool


# Environment-based configuration
DATABASE_URL = os.getenv("DATABASE_URL")
CHECKPOINT_DB_PATH = os.getenv("CHECKPOINT_DB_PATH", "checkpoints.db")  # Legacy, not used

# Global checkpointer instance - managed via context manager
_checkpointer: Optional[AsyncPostgresSaver] = None
_context_manager = None
_connection_pool: Optional[AsyncConnectionPool] = None


def get_checkpointer() -> Optional[AsyncPostgresSaver]:
    """
    Get the current PostgreSQL checkpointer instance.
    
    Returns:
        AsyncPostgresSaver if initialized, None otherwise.
    
    Usage:
        checkpointer = get_checkpointer()
    """
    return _checkpointer


async def init_checkpointer():
    """
    Initialize the PostgreSQL checkpointer with connection pooling.
    
    Requires DATABASE_URL environment variable to be set.
    Raises RuntimeError if DATABASE_URL is not configured.
    
    Call this on app startup.
    """
    global _checkpointer, _context_manager, _connection_pool
    
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable is required for PostgreSQL checkpointer. "
            "Please set DATABASE_URL to your PostgreSQL connection string. "
            "Example: postgresql://user:password@host:port/database"
        )
    
    print(f"🔗 Initializing PostgreSQL checkpointer...")
    
    try:
        # Create connection pool for concurrency
        _connection_pool = AsyncConnectionPool(
            conninfo=DATABASE_URL,
            min_size=2,
            max_size=10,
            timeout=30,
        )
        
        # Open the pool
        await _connection_pool.open()
        
        # Create checkpointer with the pool instead of a new connection string
        _checkpointer = AsyncPostgresSaver(_connection_pool)
        
        # setup() is handled by init_db.py, but we can call it here too if needed
        # await _checkpointer.setup()
        
        print(f"✅ PostgreSQL checkpointer initialized")
        print(f"   Connection pool: 2-10 connections")
        print(f"   Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'configured'}")
        
    except Exception as e:
        print(f"❌ PostgreSQL initialization failed: {e}")
        raise RuntimeError(f"Failed to initialize PostgreSQL checkpointer: {e}") from e


async def close_checkpointer():
    """
    Close the checkpointer connection and connection pool.
    
    Call this on app shutdown.
    """
    global _connection_pool
    
    if _connection_pool:
        await _connection_pool.close()
        print("🔒 Connection pool closed.")
