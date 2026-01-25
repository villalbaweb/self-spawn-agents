"""
Data models for cost tracking.

Provides both Pydantic models (for API/state) and SQLAlchemy models (for persistence).
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
            "metadata": self.metadata,
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
    llm_calls: int = 0
    tool_calls: int = 0
    
    def to_usage_stats(self) -> Dict[str, float]:
        """Convert to format compatible with AgentState.usage_stats."""
        return {
            "cost": self.cost,
            "input_tokens": float(self.input_tokens),
            "output_tokens": float(self.output_tokens),
            "llm_calls": float(self.llm_calls),
            "tool_calls": float(self.tool_calls),
        }


# --- SQLAlchemy Models (for Phase 2 persistence) ---
# Conditionally import to avoid hard dependency

try:
    from sqlalchemy import Column, String, Float, DateTime, Integer, Text, Index
    from sqlalchemy.orm import declarative_base
    
    Base = declarative_base()
    
    class CostRecordDB(Base):
        """SQLAlchemy model for persistent cost storage."""
        __tablename__ = "cost_records"
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        type = Column(String(20), nullable=False, index=True)
        cost_usd = Column(Float, nullable=False)
        timestamp = Column(DateTime, default=datetime.utcnow, index=True)
        
        # Attribution
        task_id = Column(String(64), index=True)
        agent_id = Column(String(64), index=True)
        node_name = Column(String(128))
        
        # LLM fields
        model = Column(String(64), index=True)
        provider = Column(String(32))
        input_tokens = Column(Integer, default=0)
        output_tokens = Column(Integer, default=0)
        cached_tokens = Column(Integer, default=0)
        
        # Tool fields
        tool_name = Column(String(64))
        
        # Extensibility
        metadata_json = Column(Text)  # JSON string
        
        # Composite indexes for common queries
        __table_args__ = (
            Index("ix_cost_task_timestamp", "task_id", "timestamp"),
            Index("ix_cost_type_timestamp", "type", "timestamp"),
        )
        
        @classmethod
        def from_record(cls, record: CostRecord) -> "CostRecordDB":
            """Create DB model from CostRecord dataclass."""
            import json
            return cls(
                type=record.type.value,
                cost_usd=record.cost_usd,
                timestamp=record.timestamp,
                task_id=record.task_id,
                agent_id=record.agent_id,
                node_name=record.node_name,
                model=record.model,
                provider=record.provider,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                cached_tokens=record.cached_tokens,
                tool_name=record.tool_name,
                metadata_json=json.dumps(record.metadata) if record.metadata else None,
            )

except ImportError:
    # SQLAlchemy not installed - DB models unavailable
    Base = None
    CostRecordDB = None
