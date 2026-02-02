"""
Budget enforcement middleware for cost control.

Provides real-time budget monitoring with configurable limits and actions.
Integrates with LangGraph state and CostTracker.
"""
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from core.cost.tracker import CostTracker
from core.cost.models import CostRecord


class BudgetAction(str, Enum):
    """Action to take when budget threshold is exceeded."""
    LOG = "log"           # Log warning only
    FLAG = "flag"         # Set flag in state (for HITL)
    INTERRUPT = "interrupt"  # Hard stop via interrupt


class BudgetExceededError(Exception):
    """Raised when hard budget limit is exceeded."""
    
    def __init__(self, message: str, current_cost: float, limit: float, task_id: Optional[str] = None):
        super().__init__(message)
        self.current_cost = current_cost
        self.limit = limit
        self.task_id = task_id


@dataclass
class BudgetThreshold:
    """Configuration for a budget threshold."""
    limit: float          # Cost limit in USD
    action: BudgetAction  # Action to take when exceeded
    message: str = ""     # Custom message for logging/errors


class BudgetGuard:
    """
    Real-time budget enforcement for agent workflows.
    
    Monitors cost accumulation and takes action when thresholds are exceeded.
    Supports multiple threshold levels (warn, soft limit, hard limit).
    
    Usage:
        guard = BudgetGuard(
            soft_limit=5.0,   # Flag for review
            hard_limit=10.0,  # Hard stop
        )
        
        # Attach to tracker
        tracker = CostTracker.get_instance()
        guard.attach(tracker)
        
        # Check in workflow
        guard.check(task_id="my-task", state=current_state)
    """
    
    def __init__(
        self,
        warn_limit: Optional[float] = None,
        soft_limit: Optional[float] = None,
        hard_limit: Optional[float] = None,
        on_warn: Optional[Callable[[float, float], None]] = None,
        on_soft_exceed: Optional[Callable[[float, float, Dict], None]] = None,
    ):
        """
        Initialize budget guard with threshold levels.
        
        Args:
            warn_limit: Log warning when exceeded (default: no warning)
            soft_limit: Set review flag when exceeded (default: no soft limit)
            hard_limit: Raise BudgetExceededError when exceeded (default: no hard limit)
            on_warn: Custom callback for warn threshold (cost, limit)
            on_soft_exceed: Custom callback for soft limit (cost, limit, state)
        """
        self.thresholds: list[BudgetThreshold] = []
        
        if warn_limit is not None:
            self.thresholds.append(BudgetThreshold(
                limit=warn_limit,
                action=BudgetAction.LOG,
                message=f"Budget warning: approaching limit (${warn_limit})",
            ))
        
        if soft_limit is not None:
            self.thresholds.append(BudgetThreshold(
                limit=soft_limit,
                action=BudgetAction.FLAG,
                message=f"Budget soft limit exceeded (${soft_limit})",
            ))
        
        if hard_limit is not None:
            self.thresholds.append(BudgetThreshold(
                limit=hard_limit,
                action=BudgetAction.INTERRUPT,
                message=f"Budget hard limit exceeded (${hard_limit})",
            ))
        
        # Sort by limit ascending
        self.thresholds.sort(key=lambda t: t.limit)
        
        self._on_warn = on_warn
        self._on_soft_exceed = on_soft_exceed
        self._warned_tasks: set[str] = set()
        self._flagged_tasks: set[str] = set()
    
    @classmethod
    def from_config(cls, config: Dict[str, float]) -> "BudgetGuard":
        """
        Create from budget_config dict (as stored in AgentState).
        
        Expected keys:
            - max_cost: Hard limit (required)
            - warn_cost: Warning threshold (optional)
            - soft_cost: Soft limit for HITL (optional)
        """
        return cls(
            warn_limit=config.get("warn_cost"),
            soft_limit=config.get("soft_cost"),
            hard_limit=config.get("max_cost"),
        )
    
    def attach(self, tracker: CostTracker, task_id: Optional[str] = None) -> None:
        """
        Attach to CostTracker for real-time monitoring.
        
        Args:
            tracker: CostTracker instance to monitor
            task_id: Optional task filter (only check costs for this task)
        """
        def listener(record: CostRecord) -> None:
            if task_id and record.task_id != task_id:
                return
            
            # Calculate current total for this task
            current = tracker.get_total_cost(record.task_id)
            self._check_thresholds(current, record.task_id, state=None)
        
        tracker.add_listener(listener)
    
    def check(
        self,
        current_cost: float,
        task_id: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Check cost against thresholds and take configured actions.
        
        Args:
            current_cost: Current accumulated cost
            task_id: Task identifier
            state: Optional state dict to modify (for FLAG action)
            
        Returns:
            Updated state dict (may have review_required set)
            
        Raises:
            BudgetExceededError: If hard limit exceeded
        """
        return self._check_thresholds(current_cost, task_id, state)
    
    def _check_thresholds(
        self,
        current_cost: float,
        task_id: Optional[str],
        state: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Internal threshold checking logic."""
        result_state = dict(state) if state else {}
        task_key = task_id or "default"
        
        for threshold in self.thresholds:
            if current_cost <= threshold.limit:
                continue  # Not exceeded
            
            if threshold.action == BudgetAction.LOG:
                if task_key not in self._warned_tasks:
                    self._warned_tasks.add(task_key)
                    print(f"⚠️ {threshold.message}: ${current_cost:.4f}")
                    if self._on_warn:
                        self._on_warn(current_cost, threshold.limit)
            
            elif threshold.action == BudgetAction.FLAG:
                if task_key not in self._flagged_tasks:
                    self._flagged_tasks.add(task_key)
                    print(f"🚩 {threshold.message}: ${current_cost:.4f}")
                    result_state["review_required"] = True
                    result_state["budget_exceeded"] = True
                    if self._on_soft_exceed:
                        self._on_soft_exceed(current_cost, threshold.limit, result_state)
            
            elif threshold.action == BudgetAction.INTERRUPT:
                raise BudgetExceededError(
                    message=f"{threshold.message}: ${current_cost:.4f}",
                    current_cost=current_cost,
                    limit=threshold.limit,
                    task_id=task_id,
                )
        
        return result_state
    
    def reset(self, task_id: Optional[str] = None) -> None:
        """Clear warning/flag history for a task."""
        if task_id:
            self._warned_tasks.discard(task_id)
            self._flagged_tasks.discard(task_id)
        else:
            self._warned_tasks.clear()
            self._flagged_tasks.clear()


def check_budget(state: Dict[str, Any], max_spend: Optional[float] = None) -> None:
    """
    Standalone budget check function for use in graph nodes.
    
    Reads budget_config from state or uses max_spend parameter.
    
    Args:
        state: AgentState dict
        max_spend: Optional override for max cost limit
        
    Raises:
        BudgetExceededError: If budget exceeded
    """
    budget_config = state.get("budget_config", {})
    limit = max_spend or budget_config.get("max_cost")
    
    if limit is None:
        return  # No budget configured
    
    usage_stats = state.get("usage_stats", {})
    current_cost = usage_stats.get("cost", 0.0)
    
    if current_cost > limit:
        raise BudgetExceededError(
            message=f"Budget exceeded: ${current_cost:.4f} > ${limit:.4f}",
            current_cost=current_cost,
            limit=limit,
            task_id=state.get("task_id"),
        )
