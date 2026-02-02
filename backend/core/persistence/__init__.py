"""
Persistence module for Self-Spawn Agents.

Provides:
- checkpointer: SQLite-based checkpointing for state persistence
- history: Time-travel, fork, and hydration utilities
"""
from core.persistence.checkpointer import (
    memory,
    get_memory,
    init_checkpointer,
    close_checkpointer,
    CHECKPOINT_DB_PATH,
)

__all__ = [
    "memory",
    "get_memory",
    "init_checkpointer",
    "close_checkpointer",
    "CHECKPOINT_DB_PATH",
]
