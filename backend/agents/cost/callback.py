"""
LangChain Callback Handler for automatic LLM cost tracking.

Captures token usage from LLM calls and integrates with CostTracker.
"""
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
from uuid import UUID
import threading

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from agents.cost.models import CostRecord, CostType
from agents.cost.pricing import ModelPricing


class CostTrackingCallback(BaseCallbackHandler):
    """
    Callback handler that captures LLM token usage and calculates costs.
    
    Thread-safe implementation for concurrent agent execution.
    Integrates with LangGraph state through context metadata.
    
    Usage:
        callback = CostTrackingCallback(task_id="my-task")
        result = llm.invoke(prompt, config={"callbacks": [callback]})
        print(f"Cost: ${callback.get_total_cost():.6f}")
    """
    
    def __init__(
        self,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        node_name: Optional[str] = None,
    ):
        super().__init__()
        self._lock = threading.Lock()
        self._records: List[CostRecord] = []
        
        # Default attribution (can be overridden per-call via run metadata)
        self.task_id = task_id
        self.agent_id = agent_id
        self.node_name = node_name
    
    @property
    def records(self) -> List[CostRecord]:
        """Thread-safe access to cost records."""
        with self._lock:
            return list(self._records)
    
    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """
        Called when LLM call completes. Extracts token usage and calculates cost.
        """
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0
        model = "unknown"
        
        # Primary extraction: from llm_output (works for most cases)
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            if not usage:
                usage = response.llm_output.get("usage", {})
            
            input_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
            cached_tokens = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0) if isinstance(usage.get("prompt_tokens_details"), dict) else 0
            
            model = response.llm_output.get("model_name", "unknown")
            if model == "unknown":
                model = response.llm_output.get("model", "unknown")
        
        # Fallback: Check generations for usage_metadata (newer LangChain/tool-calling flows)
        if input_tokens == 0 and output_tokens == 0 and response.generations:
            try:
                for gen_list in response.generations:
                    for gen in gen_list:
                        # Check for usage_metadata on the message (AIMessage)
                        if hasattr(gen, 'message') and hasattr(gen.message, 'usage_metadata'):
                            usage_meta = gen.message.usage_metadata
                            if usage_meta:
                                if isinstance(usage_meta, dict):
                                    input_tokens = usage_meta.get('input_tokens', 0) or 0
                                    output_tokens = usage_meta.get('output_tokens', 0) or 0
                                else:
                                    input_tokens = getattr(usage_meta, 'input_tokens', 0) or 0
                                    output_tokens = getattr(usage_meta, 'output_tokens', 0) or 0
                                    
                                # Get model from response_metadata
                                if hasattr(gen.message, 'response_metadata') and gen.message.response_metadata:
                                    model = gen.message.response_metadata.get('model_name', model)
                                break
                    if input_tokens > 0 or output_tokens > 0:
                        break
            except Exception as e:
                print(f"⚠️ [CostTrackingCallback] Fallback 1 failed: {e}")
        
        # Fallback 2: Check response_metadata on the first generation (common for certain providers)
        if input_tokens == 0 and output_tokens == 0 and response.generations:
            try:
                first_gen = response.generations[0][0]
                meta = first_gen.message.response_metadata if hasattr(first_gen, 'message') and hasattr(first_gen.message, 'response_metadata') else {}
                if not meta and hasattr(first_gen, 'generation_info'):
                    meta = first_gen.generation_info or {}
                
                usage = meta.get("token_usage") or meta.get("usage") or {}
                if usage:
                    input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
                    output_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
                    model = meta.get("model_name") or model
            except Exception:
                pass

        if input_tokens == 0 and output_tokens == 0:
            print(f"⚠️ [CostTrackingCallback] No usage data found for run {run_id}. response.llm_output={response.llm_output}")
            return  # No usage data found
        
        # Detect provider from model
        provider = self._detect_provider(model, response.llm_output or {})
        
        # Calculate cost
        cost = ModelPricing.calculate_cost(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_tokens,
            provider=provider,
        )
        
        # Get attribution from run metadata or fall back to defaults
        run_metadata = kwargs.get("metadata", {}) or {}
        
        record = CostRecord(
            type=CostType.LLM,
            cost_usd=cost,
            timestamp=datetime.now(timezone.utc),
            task_id=run_metadata.get("task_id", self.task_id),
            agent_id=run_metadata.get("agent_id", self.agent_id),
            node_name=run_metadata.get("node_name", self.node_name),
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            metadata={
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
            },
        )
        
        with self._lock:
            self._records.append(record)
    
    def _detect_provider(self, model: str, llm_output: Dict) -> str:
        """Detect provider from model name or response metadata."""
        # Check explicit provider in output
        if "provider" in llm_output:
            return llm_output["provider"]
        
        # Infer from model name
        model_lower = model.lower()
        if model_lower.startswith(("gpt-", "o1", "o3")):
            return "openai"
        if model_lower.startswith("claude"):
            return "anthropic"
        if model_lower.startswith("deepseek"):
            return "deepseek"
        
        return "unknown"

    def get_total_cost(self) -> float:
        """Get total cost across all recorded LLM calls."""
        with self._lock:
            return sum(r.cost_usd for r in self._records)
    
    def get_total_tokens(self) -> Dict[str, int]:
        """Get total token counts."""
        with self._lock:
            return {
                "input": sum(r.input_tokens for r in self._records),
                "output": sum(r.output_tokens for r in self._records),
                "cached": sum(r.cached_tokens for r in self._records),
                "total": sum(r.input_tokens + r.output_tokens for r in self._records),
            }
    
    def get_cost_by_agent(self) -> Dict[str, float]:
        """Aggregate costs by agent_id."""
        with self._lock:
            costs: Dict[str, float] = {}
            for record in self._records:
                key = record.agent_id or "unattributed"
                costs[key] = costs.get(key, 0.0) + record.cost_usd
            return costs
    
    def get_cost_by_model(self) -> Dict[str, float]:
        """Aggregate costs by model."""
        with self._lock:
            costs: Dict[str, float] = {}
            for record in self._records:
                key = record.model or "unknown"
                costs[key] = costs.get(key, 0.0) + record.cost_usd
            return costs
    
    def get_cost_by_node(self) -> Dict[str, float]:
        """Aggregate costs by node_name."""
        with self._lock:
            costs: Dict[str, float] = {}
            for record in self._records:
                key = record.node_name or "unattributed"
                costs[key] = costs.get(key, 0.0) + record.cost_usd
            return costs
    
    def to_usage_stats(self) -> Dict[str, float]:
        """
        Convert to format compatible with AgentState.usage_stats.
        Returns dict that can be merged with existing usage_stats via reducer.
        """
        tokens = self.get_total_tokens()
        return {
            "cost": self.get_total_cost(),
            "input_tokens": float(tokens["input"]),
            "output_tokens": float(tokens["output"]),
            "llm_calls": float(len(self._records)),
        }
    
    def reset(self) -> None:
        """Clear all recorded costs. Useful for per-request tracking."""
        with self._lock:
            self._records.clear()
