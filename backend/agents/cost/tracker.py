"""
Universal Cost Tracker for multi-agent orchestration.

Provides centralized cost tracking across LLM calls, tool executions,
embeddings, and external API calls. Designed for extensibility.
"""
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
from contextlib import contextmanager
import threading
import json

from agents.cost.models import CostRecord, CostType, CostSummary
from agents.cost.pricing import ModelPricing


class CostTracker:
    """
    Centralized cost tracking service for multi-agent workflows.
    
    Thread-safe singleton pattern for cross-agent cost aggregation.
    Supports both synchronous recording and context-based scoping.
    
    Usage:
        tracker = CostTracker.get_instance()
        
        # Record LLM cost
        tracker.record_llm(
            task_id="task-123",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
        )
        
        # Record tool cost
        tracker.record_tool(
            task_id="task-123", 
            tool_name="web_search",
            cost=0.001,
        )
        
        # Get summary
        print(tracker.get_summary())
    """
    
    _instance: Optional["CostTracker"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._records: List[CostRecord] = []
        self._record_lock = threading.Lock()
        self._listeners: List[Callable[[CostRecord], None]] = []
    
    @classmethod
    def get_instance(cls) -> "CostTracker":
        """Get or create singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None
    
    def record_llm(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        node_name: Optional[str] = None,
        cached_tokens: int = 0,
        provider: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CostRecord:
        """
        Record an LLM call with automatic cost calculation.
        
        Args:
            model: Model identifier (e.g., "gpt-4o")
            input_tokens: Prompt token count
            output_tokens: Completion token count
            task_id: Parent task/workflow ID
            agent_id: Agent that made the call
            node_name: LangGraph node name
            cached_tokens: Cached prompt tokens (for prompt caching)
            provider: Optional provider hint
            metadata: Additional metadata
            
        Returns:
            Created CostRecord
        """
        cost = ModelPricing.calculate_cost(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_tokens,
            provider=provider,
        )
        
        record = CostRecord(
            type=CostType.LLM,
            cost_usd=cost,
            timestamp=datetime.now(timezone.utc),
            task_id=task_id,
            agent_id=agent_id,
            node_name=node_name,
            model=model,
            provider=provider or ModelPricing._resolve_provider(model, None).value,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            metadata=metadata or {},
        )
        
        self._add_record(record)
        return record
    
    def record_tool(
        self,
        tool_name: str,
        cost: float,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        node_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CostRecord:
        """
        Record a tool execution cost.
        
        Args:
            tool_name: Name of the tool (e.g., "web_search", "python_repl")
            cost: Cost in USD
            task_id: Parent task/workflow ID
            agent_id: Agent that invoked the tool
            node_name: LangGraph node name
            metadata: Additional metadata (e.g., query, execution time)
            
        Returns:
            Created CostRecord
        """
        record = CostRecord(
            type=CostType.TOOL,
            cost_usd=cost,
            timestamp=datetime.now(timezone.utc),
            task_id=task_id,
            agent_id=agent_id,
            node_name=node_name,
            tool_name=tool_name,
            metadata=metadata or {},
        )
        
        self._add_record(record)
        return record
    
    def record_embedding(
        self,
        model: str,
        tokens: int,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CostRecord:
        """
        Record an embedding call cost.
        
        Args:
            model: Embedding model (e.g., "text-embedding-3-small")
            tokens: Token count
            task_id: Parent task/workflow ID
            metadata: Additional metadata
            
        Returns:
            Created CostRecord
        """
        # Embedding pricing (per 1M tokens)
        embedding_prices = {
            "text-embedding-3-small": 0.02,
            "text-embedding-3-large": 0.13,
            "text-embedding-ada-002": 0.10,
        }
        price_per_million = embedding_prices.get(model, 0.02)
        cost = tokens * price_per_million / 1_000_000
        
        record = CostRecord(
            type=CostType.EMBEDDING,
            cost_usd=cost,
            timestamp=datetime.now(timezone.utc),
            task_id=task_id,
            model=model,
            input_tokens=tokens,
            metadata=metadata or {},
        )
        
        self._add_record(record)
        return record
    
    def record_external_api(
        self,
        api_name: str,
        cost: float,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CostRecord:
        """
        Record an external API call cost.
        
        Args:
            api_name: Name of the API (e.g., "serper", "e2b")
            cost: Cost in USD
            task_id: Parent task/workflow ID
            agent_id: Agent that made the call
            metadata: Additional metadata
            
        Returns:
            Created CostRecord
        """
        record = CostRecord(
            type=CostType.EXTERNAL_API,
            cost_usd=cost,
            timestamp=datetime.now(timezone.utc),
            task_id=task_id,
            agent_id=agent_id,
            tool_name=api_name,
            metadata=metadata or {},
        )
        
        self._add_record(record)
        return record
    
    def _add_record(self, record: CostRecord) -> None:
        """Thread-safe record addition with listener notification."""
        with self._record_lock:
            self._records.append(record)
        
        # Notify listeners (outside lock to prevent deadlocks)
        for listener in self._listeners:
            try:
                listener(record)
            except Exception:
                pass  # Don't let listener errors break tracking
    
    def add_listener(self, callback: Callable[[CostRecord], None]) -> None:
        """
        Register a callback for real-time cost notifications.
        
        Useful for streaming cost updates to clients or enforcing budgets.
        """
        self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable[[CostRecord], None]) -> None:
        """Remove a registered listener."""
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass
    
    @property
    def records(self) -> List[CostRecord]:
        """Thread-safe access to all records."""
        with self._record_lock:
            return list(self._records)
    
    def get_records_for_task(self, task_id: str) -> List[CostRecord]:
        """Get all cost records for a specific task."""
        with self._record_lock:
            return [r for r in self._records if r.task_id == task_id]
    
    def get_total_cost(self, task_id: Optional[str] = None) -> float:
        """Get total cost, optionally filtered by task."""
        records = self.get_records_for_task(task_id) if task_id else self.records
        return sum(r.cost_usd for r in records)
    
    def get_cost_by_type(self, task_id: Optional[str] = None) -> Dict[str, float]:
        """Aggregate costs by type."""
        records = self.get_records_for_task(task_id) if task_id else self.records
        breakdown: Dict[str, float] = {}
        for record in records:
            key = record.type.value
            breakdown[key] = breakdown.get(key, 0.0) + record.cost_usd
        return breakdown
    
    def get_cost_by_agent(self, task_id: Optional[str] = None) -> Dict[str, float]:
        """Aggregate costs by agent (falls back to task_id if no agent_id)."""
        records = self.get_records_for_task(task_id) if task_id else self.records
        breakdown: Dict[str, float] = {}
        for record in records:
            key = record.agent_id or record.task_id or "unattributed"
            breakdown[key] = breakdown.get(key, 0.0) + record.cost_usd
        return breakdown
    
    def get_cost_by_model(self, task_id: Optional[str] = None) -> Dict[str, float]:
        """Aggregate costs by model."""
        records = self.get_records_for_task(task_id) if task_id else self.records
        breakdown: Dict[str, float] = {}
        for record in records:
            if record.model:
                breakdown[record.model] = breakdown.get(record.model, 0.0) + record.cost_usd
        return breakdown
    
    def get_summary(self, task_id: Optional[str] = None) -> CostSummary:
        """
        Generate comprehensive cost summary.
        
        Args:
            task_id: Optional filter for specific task
            
        Returns:
            CostSummary with breakdowns by type, model, agent, and node
        """
        records = self.get_records_for_task(task_id) if task_id else self.records
        
        summary = CostSummary(
            total_cost_usd=sum(r.cost_usd for r in records),
            total_input_tokens=sum(r.input_tokens for r in records),
            total_output_tokens=sum(r.output_tokens for r in records),
            total_cached_tokens=sum(r.cached_tokens for r in records),
            call_count=len(records),
        )
        
        for record in records:
            # By type
            type_key = record.type.value
            summary.by_type[type_key] = summary.by_type.get(type_key, 0.0) + record.cost_usd
            
            # By model
            if record.model:
                summary.by_model[record.model] = summary.by_model.get(record.model, 0.0) + record.cost_usd
            
            # By agent (fall back to task_id if no agent_id)
            agent_key = record.agent_id or record.task_id or "unattributed"
            summary.by_agent[agent_key] = summary.by_agent.get(agent_key, 0.0) + record.cost_usd
            
            # By node
            if record.node_name:
                summary.by_node[record.node_name] = summary.by_node.get(record.node_name, 0.0) + record.cost_usd
        
        return summary
    
    def to_usage_stats(self, task_id: Optional[str] = None) -> Dict[str, float]:
        """
        Convert to format compatible with AgentState.usage_stats.
        """
        records = self.get_records_for_task(task_id) if task_id else self.records
        
        llm_records = [r for r in records if r.type == CostType.LLM]
        tool_records = [r for r in records if r.type == CostType.TOOL]
        
        return {
            "cost": sum(r.cost_usd for r in records),
            "input_tokens": float(sum(r.input_tokens for r in llm_records)),
            "output_tokens": float(sum(r.output_tokens for r in llm_records)),
            "cached_tokens": float(sum(r.cached_tokens for r in llm_records)),
            "llm_calls": float(len(llm_records)),
            "tool_calls": float(len(tool_records)),
        }
    
    def export_records(self, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Export records as JSON-serializable list."""
        records = self.get_records_for_task(task_id) if task_id else self.records
        return [r.to_dict() for r in records]
    
    def reset(self, task_id: Optional[str] = None) -> None:
        """
        Clear recorded costs.
        
        Args:
            task_id: If provided, only clear records for this task.
                     Otherwise, clears all records.
        """
        with self._record_lock:
            if task_id:
                self._records = [r for r in self._records if r.task_id != task_id]
            else:
                self._records.clear()
    
    @contextmanager
    def task_scope(self, task_id: str):
        """
        Context manager for task-scoped cost tracking.
        
        Usage:
            with tracker.task_scope("my-task") as scope:
                # ... run workflow ...
                print(f"Task cost: ${scope.get_cost():.4f}")
        """
        yield TaskScope(self, task_id)


class TaskScope:
    """Scoped cost accessor for a specific task."""
    
    def __init__(self, tracker: CostTracker, task_id: str):
        self._tracker = tracker
        self._task_id = task_id
    
    def get_cost(self) -> float:
        return self._tracker.get_total_cost(self._task_id)
    
    def get_summary(self) -> CostSummary:
        return self._tracker.get_summary(self._task_id)
    
    def get_records(self) -> List[CostRecord]:
        return self._tracker.get_records_for_task(self._task_id)
