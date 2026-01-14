from typing import TypedDict, List, Dict, Any, Annotated

def replace(a: Any, b: Any) -> Any:
    return b

class AgentState(TypedDict):
    task: str # High-level user prompt
    subject: str # Primary subject/product extracted from task (for drift prevention)
    subtasks: List[str] # Decomposed subtasks
    deliverables: List[str] # Expected outputs (e.g., "Marketing Roadmap", "PDF")
    graph_plan: Dict[str, Any] # Planned LangGraph nodes and edges
    results: Dict[str, str] # Results from executed nodes
    depth: Annotated[int, replace] # Current recursion depth (starts at 0)
    blueprint_id: str # ID of the generated blueprint, if any