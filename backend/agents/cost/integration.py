"""
LangGraph integration utilities for cost tracking.

Provides helper functions to wire cost tracking into existing graph nodes
with minimal code changes.
"""
from typing import Dict, Any, Optional, List, Callable
from functools import wraps

from langchain_core.runnables import RunnableConfig
from langchain_core.callbacks import BaseCallbackHandler

from agents.cost.callback import CostTrackingCallback
from agents.cost.tracker import CostTracker
from agents.cost.budget_guard import BudgetGuard, BudgetExceededError, check_budget


def get_cost_callbacks(
    config: Optional[RunnableConfig] = None,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    node_name: Optional[str] = None,
) -> List[BaseCallbackHandler]:
    """
    Extract or create cost tracking callbacks from config.
    
    Usage in nodes:
        callbacks = get_cost_callbacks(config, node_name="semantic_splitter")
        result = await llm.ainvoke(messages, config={"callbacks": callbacks})
    """
    existing_callbacks = []
    if config and "callbacks" in config:
        existing_callbacks = config["callbacks"] or []
    
    # Check if CostTrackingCallback already exists
    for cb in existing_callbacks:
        if isinstance(cb, CostTrackingCallback):
            return existing_callbacks
    
    # Create new callback
    cost_callback = CostTrackingCallback(
        task_id=task_id,
        agent_id=agent_id,
        node_name=node_name,
    )
    
    return existing_callbacks + [cost_callback]


def inject_cost_tracking(config: Optional[RunnableConfig], node_name: str, state: Dict[str, Any]) -> RunnableConfig:
    """
    Inject cost tracking callback into config, preserving existing callbacks.
    
    Args:
        config: Existing RunnableConfig (may be None)
        node_name: Current graph node name
        state: Current state (used to extract task_id from thread config)
        
    Returns:
        Updated RunnableConfig with cost tracking callback
    """
    task_id = None
    if config and "configurable" in config:
        task_id = config["configurable"].get("thread_id")
    
    callbacks = get_cost_callbacks(
        config=config,
        task_id=task_id,
        node_name=node_name,
    )
    
    new_config = dict(config) if config else {}
    new_config["callbacks"] = callbacks
    
    return new_config


def extract_cost_from_callbacks(config: Optional[RunnableConfig]) -> Dict[str, float]:
    """
    Extract accumulated cost stats from callbacks in config.
    
    Returns dict compatible with AgentState.usage_stats reducer.
    """
    if not config or "callbacks" not in config:
        return {}
    
    for cb in config.get("callbacks", []):
        if isinstance(cb, CostTrackingCallback):
            return cb.to_usage_stats()
    
    return {}


def with_cost_tracking(node_name: str):
    """
    Decorator to add cost tracking to async graph nodes.
    
    Automatically:
    - Injects cost tracking callback into LLM calls
    - Merges cost stats into returned state
    - Enforces budget limits from state.budget_config
    
    Usage:
        @with_cost_tracking("semantic_splitter")
        async def semantic_splitter_node(state: AgentState) -> Dict[str, Any]:
            # ... node logic ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(state: Dict[str, Any], config: RunnableConfig = None, **kwargs):
            # Create scoped callback for this node
            task_id = None
            if config and "configurable" in config:
                task_id = config["configurable"].get("thread_id")
            
            callback = CostTrackingCallback(
                task_id=task_id,
                node_name=node_name,
            )
            
            # Inject callback into config
            enhanced_config = dict(config) if config else {}
            existing_callbacks = enhanced_config.get("callbacks", []) or []
            enhanced_config["callbacks"] = existing_callbacks + [callback]
            
            # Check budget before execution
            budget_config = state.get("budget_config", {})
            if budget_config.get("max_cost"):
                check_budget(state)
            
            # Execute node
            result = await func(state, enhanced_config, **kwargs)
            
            # Merge cost stats into result
            if isinstance(result, dict):
                cost_stats = callback.to_usage_stats()
                if cost_stats:
                    result["usage_stats"] = cost_stats
            
            return result
        
        return wrapper
    return decorator


def create_cost_aware_config(
    thread_id: str,
    budget_config: Optional[Dict[str, float]] = None,
) -> RunnableConfig:
    """
    Create a RunnableConfig with cost tracking pre-configured.
    
    Args:
        thread_id: Unique identifier for this workflow execution
        budget_config: Optional budget limits {"max_cost": 10.0, "warn_cost": 5.0}
        
    Returns:
        RunnableConfig ready for graph invocation
    """
    callback = CostTrackingCallback(task_id=thread_id)
    
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [callback],
    }
    
    return config


class CostTrackingMiddleware:
    """
    Middleware for tracking costs across a complete workflow execution.
    
    Usage:
        middleware = CostTrackingMiddleware(thread_id="my-run")
        
        config = middleware.get_config()
        result = await graph.ainvoke(initial_state, config=config)
        
        print(f"Total cost: ${middleware.get_total_cost():.4f}")
    """
    
    def __init__(
        self,
        thread_id: str,
        budget_config: Optional[Dict[str, float]] = None,
    ):
        self.thread_id = thread_id
        self.budget_config = budget_config or {}
        self.callback = CostTrackingCallback(task_id=thread_id)
        self.guard: Optional[BudgetGuard] = None
        
        if budget_config:
            self.guard = BudgetGuard.from_config(budget_config)
    
    def get_config(self) -> RunnableConfig:
        """Get RunnableConfig for graph invocation."""
        return {
            "configurable": {"thread_id": self.thread_id},
            "callbacks": [self.callback],
        }
    
    def get_total_cost(self) -> float:
        """Get accumulated cost."""
        return self.callback.get_total_cost()
    
    def get_usage_stats(self) -> Dict[str, float]:
        """Get usage stats for state merge."""
        return self.callback.to_usage_stats()
    
    def get_cost_by_model(self) -> Dict[str, float]:
        """Get cost breakdown by model."""
        return self.callback.get_cost_by_model()
    
    def check_budget(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check budget and return updated state if limits exceeded.
        
        Raises BudgetExceededError for hard limit violations.
        """
        if not self.guard:
            return state
        
        current_cost = self.get_total_cost()
        return self.guard.check(current_cost, self.thread_id, state)
