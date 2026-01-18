from typing import TypedDict, List, Dict, Any, Annotated
import operator

def replace(a: Any, b: Any) -> Any:
    return b

def merge_lists(a: List, b: List) -> List:
    return a + b

def sum_usage(a: Dict[str, float], b: Dict[str, float]) -> Dict[str, float]:
    """Reducer to accumulate usage stats (cost, tokens, steps)."""
    result = dict(a) if a else {}
    for key, value in (b or {}).items():
        result[key] = result.get(key, 0.0) + value
    return result

class AgentState(TypedDict):
    task: str # High-level user prompt
    subject: str # Primary subject/product extracted from task (for drift prevention)
    subtasks: List[str] # Decomposed subtasks
    deliverables: List[str] # Expected outputs (e.g., "Marketing Roadmap", "PDF")
    graph_plan: Dict[str, Any] # Planned LangGraph nodes and edges
    results: Annotated[Dict[str, str], operator.ior] # Results from executed nodes, merge dictionaries
    depth: Annotated[int, replace] # Current recursion depth (starts at 0)
    metadata: Annotated[Dict[str, Dict], operator.ior] # Capture agent metadata (system prompts, etc.)
    blueprint_id: str # ID of the generated blueprint, if any
    # Aggregated data for unified graph rendering
    all_agents: Annotated[List[Dict], merge_lists] # All agents across all subgraphs
    all_edges: Annotated[List[Dict], merge_lists] # All edges across all subgraphs
    # Synthesis and HITL
    synthesis: str # Final synthesized report markdown
    confidence_score: float # Aggregate confidence score (0.0 - 1.0)
    review_required: bool # If True, HITL pause is triggered before synthesis
    inner_thread_id: Annotated[str, replace] # Persisted ID for the inner graph execution thread
    # Safety Logic (Epic 1)
    global_signal: Annotated[str, replace] # Global interrupt signal ("INTERRUPT" to stop siblings)
    usage_stats: Annotated[Dict[str, float], sum_usage] # Accumulated cost/tokens/steps
    budget_config: Dict[str, float] # Limits: {"max_cost": 2.0, "max_steps": 50}
