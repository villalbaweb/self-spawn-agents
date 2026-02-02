"""
Data models for cost tracking.

Provides both Pydantic models (for API/state) and dataclasses (for in-memory tracking).
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field
from dataclasses import dataclass, field


class CostType(str, Enum):
    """Type of cost being tracked."""
    LLM = "llm"
    TOOL = "tool"
    EMBEDDING = "embedding"
    EXTERNAL_API = "external_api"


def _utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass
class CostRecord:
    """
    Immutable record of a single cost event.
    Used for in-memory tracking and serialization.
    """
    type: CostType
    cost_usd: float
    timestamp: datetime = field(default_factory=_utc_now)
    
    # Attribution
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    node_name: Optional[str] = None
    
    # LLM-specific
    model: Optional[str] = None
    provider: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    
    # Tool-specific
    tool_name: Optional[str] = None
    
    # Extensibility
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON/state storage."""
        # Sanitize metadata to ensure all values are JSON-serializable
        safe_metadata = {}
        for k, v in (self.metadata or {}).items():
            if v is None or isinstance(v, (str, int, float, bool)):
                safe_metadata[k] = v
            elif isinstance(v, (list, dict)):
                try:
                    import json
                    json.dumps(v)  # Test if serializable
                    safe_metadata[k] = v
                except (TypeError, ValueError):
                    safe_metadata[k] = str(v)
            else:
                safe_metadata[k] = str(v)
        
        return {
            "type": self.type.value,
            "cost_usd": self.cost_usd,
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "node_name": self.node_name,
            "model": self.model,
            "provider": self.provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "tool_name": self.tool_name,
            "metadata": safe_metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CostRecord":
        """Deserialize from dictionary."""
        return cls(
            type=CostType(data["type"]),
            cost_usd=data["cost_usd"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            task_id=data.get("task_id"),
            agent_id=data.get("agent_id"),
            node_name=data.get("node_name"),
            model=data.get("model"),
            provider=data.get("provider"),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cached_tokens=data.get("cached_tokens", 0),
            tool_name=data.get("tool_name"),
            metadata=data.get("metadata", {}),
        )


class CostSummary(BaseModel):
    """Aggregated cost summary for API responses."""
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cached_tokens: int = 0
    call_count: int = 0
    
    by_type: Dict[str, float] = Field(default_factory=dict)
    by_model: Dict[str, float] = Field(default_factory=dict)
    by_agent: Dict[str, float] = Field(default_factory=dict)
    by_node: Dict[str, float] = Field(default_factory=dict)


class UsageStatsUpdate(BaseModel):
    """
    Pydantic model for streaming usage stats updates.
    Compatible with existing AgentState.usage_stats reducer.
    """
    cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    
    def to_usage_stats(self) -> Dict[str, float]:
        """Convert to format compatible with AgentState.usage_stats."""
        return {
            "cost": self.cost,
            "input_tokens": float(self.input_tokens),
            "output_tokens": float(self.output_tokens),
            "cached_tokens": float(self.cached_tokens),
            "llm_calls": float(self.llm_calls),
            "tool_calls": float(self.tool_calls),
        }
