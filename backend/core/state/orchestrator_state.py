"""
Orchestrator State Definition.

Defines the main AgentState TypedDict used by the orchestrator graph.
Includes all fields for task decomposition, execution, safety, and HITL.
"""
from typing import TypedDict, List, Dict, Any, Annotated
import operator


def replace(a: Any, b: Any) -> Any:
    """Reducer that replaces value a with value b."""
    return b


def merge_lists(a: List, b: List) -> List:
    """Reducer that concatenates two lists."""
    return a + b


def sum_usage(a: Dict[str, float], b: Dict[str, float]) -> Dict[str, float]:
    """Reducer to accumulate usage stats (cost, tokens, steps)."""
    result = dict(a) if a else {}
    for key, value in (b or {}).items():
        result[key] = result.get(key, 0.0) + value
    return result


class AgentState(TypedDict):
    """
    Main state for the orchestrator graph.
    
    Fields:
        task: High-level user prompt
        subject: Primary subject/product extracted from task (for drift prevention)
        subtasks: Decomposed subtasks from semantic splitter
        deliverables: Expected outputs (e.g., "Marketing Roadmap", "PDF")
        graph_plan: Planned LangGraph nodes and edges
        results: Results from executed nodes (merged via operator.ior)
        depth: Current recursion depth (starts at 0)
        metadata: Capture agent metadata (system prompts, etc.)
        blueprint_id: ID of the generated blueprint
        all_agents: All agents across all subgraphs (for visualization)
        all_edges: All edges across all subgraphs (for visualization)
        synthesis: Final synthesized report markdown
        confidence_score: Aggregate confidence score (0.0 - 1.0)
        review_required: If True, HITL pause is triggered before synthesis
        inner_thread_id: Persisted ID for the inner graph execution thread
        global_signal: Global interrupt signal ("INTERRUPT" to stop siblings)
        usage_stats: Accumulated cost/tokens/steps
        root_task_id: Primary task ID for cost attribution across subgraphs
        budget_config: Limits: {"max_cost": 2.0, "max_steps": 50}
    """
    task: str
    subject: str
    subtasks: List[str]
    deliverables: List[str]
    graph_plan: Dict[str, Any]
    results: Annotated[Dict[str, str], operator.ior]
    depth: Annotated[int, replace]
    metadata: Annotated[Dict[str, Dict], operator.ior]
    # Blueprint Caching and Knowledge
    blueprint_id: str
    blueprint_cache_hit: bool
    blueprint_similarity: float
    blueprint_archived: bool
    # Aggregated data for unified graph rendering
    all_agents: Annotated[List[Dict], merge_lists]
    all_edges: Annotated[List[Dict], merge_lists]
    # Synthesis and HITL
    synthesis: str
    confidence_score: float
    review_required: bool
    inner_thread_id: Annotated[str, replace]
    # Safety Logic
    global_signal: Annotated[str, replace]
    usage_stats: Annotated[Dict[str, float], sum_usage]
    root_task_id: str
    budget_config: Dict[str, float]
