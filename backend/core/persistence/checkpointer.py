"""
Checkpointer management for LangGraph state persistence.

Provides async SQLite-based checkpointing with proper lifecycle management.
"""
import os
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Path to the SQLite checkpoint database
CHECKPOINT_DB_PATH = os.getenv("CHECKPOINT_DB_PATH", "checkpoints.db")

# Global checkpointer instance - managed via context manager
memory: AsyncSqliteSaver = None
_context_manager = None


def get_memory() -> AsyncSqliteSaver | None:
    """Get the current memory checkpointer instance. Use this after init_checkpointer()."""
    return memory


async def init_checkpointer():
    """Initialize the async SQLite checkpointer. Call this on app startup."""
    global memory, _context_manager
    # Use the recommended context manager approach
    _context_manager = AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB_PATH)
    memory = await _context_manager.__aenter__()
    print(f"✅ Checkpointer initialized with SQLite at: {CHECKPOINT_DB_PATH}")


async def close_checkpointer():
    """Close the checkpointer connection. Call this on app shutdown."""
    global _context_manager
    if _context_manager:
        await _context_manager.__aexit__(None, None, None)
        print("🔒 Checkpointer connection closed.")
