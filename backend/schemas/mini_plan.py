"""
Mini Plan Schema.

Defines the lightweight execution plan used by the worker subgraph
for mini-orchestration of complex tasks.
"""
from typing import List
from pydantic import BaseModel, Field


class MiniTask(BaseModel):
    """A single task in the mini execution plan."""
    id: str = Field(..., description="Unique task ID (e.g., 'research_oauth')")
    agent_type: str = Field(..., description="Agent type: Researcher, Coder, or Reviewer")
    instruction: str = Field(..., description="Specific instruction for this task")


class MiniPlan(BaseModel):
    """
    Lightweight execution plan for worker subgraph.
    
    All tasks are parallel (no dependencies) to maximize throughput.
    Used when a task is too complex for single-agent execution but
    doesn't need full orchestrator overhead.
    """
    tasks: List[MiniTask] = Field(..., description="List of 2-4 parallel tasks")
    reasoning: str = Field(..., description="Brief explanation of the plan")
