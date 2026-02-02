"""
Graph Plan Schema.

Defines the structured output from the Supervisor agent.
"""
from typing import List
from pydantic import BaseModel, Field


class NodeSchema(BaseModel):
    """Schema for a single node in the execution graph."""
    id: str = Field(..., description="Unique identifier for the node (e.g., 'research_step_1').")
    agent_type: str = Field(..., description="The type of agent needed (e.g., 'Researcher', 'Coder', 'Reviewer').")
    instruction: str = Field(..., description="Specific instruction for this node.")
    dependencies: List[str] = Field(default_factory=list, description="IDs of nodes that must complete before this one starts.")
    recursive: bool = Field(default=False, description="If true, this node spawns a full sub-orchestration pipeline for complex multi-step tasks.")


class GraphPlan(BaseModel):
    """
    Structured execution plan from the Supervisor.
    
    Contains a list of nodes with their dependencies and a brief explanation
    of the planning rationale.
    """
    nodes: List[NodeSchema] = Field(..., description="List of nodes in the execution graph.")
    explanation: str = Field(..., description="Brief reasoning for this graph structure.")
