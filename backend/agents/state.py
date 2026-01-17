from typing import TypedDict, List, Dict, Any, Annotated

def replace(a: Any, b: Any) -> Any:
    return b

def merge_lists(a: List, b: List) -> List:
    return a + b

class AgentState(TypedDict):
    task: str # High-level user prompt
    subject: str # Primary subject/product extracted from task (for drift prevention)
    subtasks: List[str] # Decomposed subtasks
    deliverables: List[str] # Expected outputs (e.g., "Marketing Roadmap", "PDF")
    graph_plan: Dict[str, Any] # Planned LangGraph nodes and edges
    results: Dict[str, str] # Results from executed nodes
    depth: Annotated[int, replace] # Current recursion depth (starts at 0)
    blueprint_id: str # ID of the generated blueprint, if any
    # Aggregated data for unified graph rendering
    all_agents: Annotated[List[Dict], merge_lists] # All agents across all subgraphs
    all_edges: Annotated[List[Dict], merge_lists] # All edges across all subgraphs
    # Synthesis and HITL
    synthesis: str # Final synthesized report markdown
    confidence_score: float # Aggregate confidence score (0.0 - 1.0)
    review_required: bool # If True, HITL pause is triggered before synthesis
    inner_thread_id: Annotated[str, replace] # Persisted ID for the inner graph execution thread