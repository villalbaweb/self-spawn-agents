"""
Blueprint Schemas.

Defines the visualization and execution blueprint structures.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class AgentInfo(BaseModel):
    """Information about a single agent for visualization."""
    id: str = Field(..., description="Unique identifier for the agent instance")
    role: str = Field(..., description="The role of the agent (e.g., Researcher, Coder)")
    system_prompt: str = Field(default="", description="The dynamic system prompt generated for this agent")
    tools: List[str] = Field(default_factory=list, description="List of tools available to this agent")
    instruction: str = Field(..., description="The specific instruction given to this agent")
    parent: Optional[str] = Field(None, description="ID of the parent orchestrator node")


class EdgeInfo(BaseModel):
    """Edge connection between nodes for visualization."""
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")


class AppBlueprint(BaseModel):
    """
    Complete execution blueprint for visualization.
    
    Captures the full structure of an execution run including
    all agents, their connections, and execution metadata.
    """
    run_id: str = Field(..., description="Unique run identifier")
    task: str = Field(..., description="High-level user task")
    agents: List[AgentInfo] = Field(default_factory=list, description="List of agents involved")
    edges: List[EdgeInfo] = Field(default_factory=list, description="Graph connections")
    execution_flow: List[str] = Field(default_factory=list, description="Execution order")
    timestamp: str = Field(..., description="Creation timestamp")
    depth: int = Field(default=0, description="Recursion depth of this graph")
