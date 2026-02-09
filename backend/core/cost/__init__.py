"""
Cost Tracking Module for Multi-Agent Orchestration.

Provides LLM token cost tracking with extensibility for tool/embedding costs.
Integrates with LangGraph state for per-agent/task attribution.
"""
from core.cost.callback import CostTrackingCallback
from core.cost.tracker import CostTracker
from core.cost.pricing import ModelPricing, TokenPricing, Provider
from core.cost.models import CostRecord, CostType, CostSummary, UsageStatsUpdate
from core.cost.budget_guard import BudgetGuard, BudgetExceededError, check_budget
from core.cost.integration import (
    CostTrackingMiddleware,
    with_cost_tracking,
    inject_cost_tracking,
    get_cost_callbacks,
    extract_cost_from_callbacks,
    create_cost_aware_config,
)

__all__ = [
    # Core
    "CostTrackingCallback",
    "CostTracker",
    "ModelPricing",
    "TokenPricing",
    "Provider",
    # Models
    "CostRecord",
    "CostType",
    "CostSummary",
    "UsageStatsUpdate",
    # Budget
    "BudgetGuard",
    "BudgetExceededError",
    "check_budget",
    # Integration
    "CostTrackingMiddleware",
    "with_cost_tracking",
    "inject_cost_tracking",
    "get_cost_callbacks",
    "extract_cost_from_callbacks",
    "create_cost_aware_config",
]
