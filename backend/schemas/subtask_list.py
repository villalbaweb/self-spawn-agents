"""
Subtask List Schema.

Defines the structured output from the Semantic Splitter.
"""
from typing import List
from pydantic import BaseModel, Field


class SubtaskList(BaseModel):
    """
    Structured decomposition from the Semantic Splitter.
    
    Contains the extracted subject, atomic subtasks, expected deliverables,
    and reasoning for the decomposition strategy.
    """
    subject: str = Field(..., description="The primary subject/product mentioned in the task (e.g., 'luxury e-bikes', 'cooking blog')")
    subtasks: List[str] = Field(..., description="A list of atomic subtasks (max 5) starting with a verb.")
    deliverables: List[str] = Field(default_factory=list, description="Explicit outputs requested (e.g., 'Marketing Roadmap', 'Executive Summary PDF', 'Python script')")
    reasoning: str = Field(..., description="Brief explanation of the decomposition strategy.")
