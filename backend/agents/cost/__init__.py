"""
Cost Tracking Module for Multi-Agent Orchestration.

Provides LLM token cost tracking with extensibility for tool/embedding costs.
Integrates with LangGraph state for per-agent/task attribution.
"""
from agents.cost.callback import CostTrackingCallback
from agents.cost.tracker import CostTracker
from agents.cost.pricing import ModelPricing
from agents.cost.budget_guard import BudgetGuard, BudgetExceededError, check_budget
from agents.cost.integration import (
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
