"""
Configuration package for Self-Spawn Agents.

This package contains:
- settings: Environment variables and application settings
- llm_providers: LLM initialization (OpenAI, DeepSeek, etc.)
"""
from config.settings import (
    MAX_RECURSION_DEPTH,
    TIER1_THRESHOLD,
    TIER2_THRESHOLD,
    TIER3_THRESHOLD,
    MAX_CONCURRENCY,
)
from config.llm_providers import llm, llm_mini, search

__all__ = [
    "MAX_RECURSION_DEPTH",
    "TIER1_THRESHOLD",
    "TIER2_THRESHOLD",
    "TIER3_THRESHOLD",
    "MAX_CONCURRENCY",
    "llm",
    "llm_mini",
    "search",
]
