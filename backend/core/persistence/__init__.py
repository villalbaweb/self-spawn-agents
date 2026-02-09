"""
Persistence module for Self-Spawn Agents.

Provides:
- checkpointer: PostgreSQL-based checkpointing for state persistence with connection pooling
- history: Time-travel, fork, and hydration utilities
"""
from core.persistence.checkpointer import (
    get_checkpointer,
    init_checkpointer,
    close_checkpointer,
    DATABASE_URL,
)

__all__ = [
    "get_checkpointer",
    "init_checkpointer",
    "close_checkpointer",
    "DATABASE_URL",
]
