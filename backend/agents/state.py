from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    task: str # High-level user prompt
    subtasks: List[str] # Decomposed subtasks