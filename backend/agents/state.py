from typing import TypedDict, List, Dict, Any, Annotated

def replace(a: Any, b: Any) -> Any:
    return b

class AgentState(TypedDict):
    task: str # High-level user prompt
    subtasks: List[str] # Decomposed subtasks
    graph_plan: Dict[str, Any] # Planned LangGraph nodes and edges
    results: Dict[str, str] # Results from executed nodes
    depth: Annotated[int, replace] # Current recursion depth (starts at 0)