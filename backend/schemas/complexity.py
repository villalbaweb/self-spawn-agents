"""
Complexity Classification Schema.

Defines the output from task complexity analysis in the worker subgraph.
"""
from pydantic import BaseModel, Field


class ComplexityClassification(BaseModel):
    """
    Result of task complexity analysis.
    
    Used by the worker subgraph to decide whether to decompose a task
    into parallel sub-tasks (mini-orchestration) or execute directly.
    """
    needs_decomposition: bool = Field(..., description="True if the task should be split into parallel sub-tasks")
    reasoning: str = Field(..., description="Brief explanation of why decomposition is or isn't needed")
