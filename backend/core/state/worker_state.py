"""
Worker State Definition.

Defines the WorkerState TypedDict used by the worker subgraph.
Lightweight state focused on task execution only (no semantic splitter/supervisor fields).
"""
from typing import TypedDict, Dict, Any, Annotated, List
import operator


def replace(a: Any, b: Any) -> Any:
    """Reducer that replaces value a with value b."""
    return b


def sum_usage(a: Dict[str, float], b: Dict[str, float]) -> Dict[str, float]:
    """Reducer to accumulate usage stats."""
    result = dict(a) if a else {}
    for key, value in (b or {}).items():
        result[key] = result.get(key, 0.0) + value
    return result


class WorkerState(TypedDict):
    """
    Lightweight state for the Worker Subgraph.
    Does NOT include semantic_splitter or supervisor fields.
    
    Fields:
        task: The specific instruction for this worker
        subject: Subject context (for drift prevention)
        parent_node_id: ID of the parent node that spawned this
        root_task_id: Root task ID for cost attribution
        depth: Current recursion depth
        results: Execution results (merged via operator.ior)
        all_agents: Agents for visualization
        all_edges: Edges for visualization
        global_signal: Interrupt signal from siblings
        usage_stats: Cost/token tracking
        budget_config: Budget limits
        confidence_score: Quality score (0.0 - 1.0)
        confidence_reasoning: Explanation for confidence score
    """
    # Core execution context
    task: str
    subject: str
    parent_node_id: str
    root_task_id: str
    
    # Execution tracking
    depth: Annotated[int, replace]
    results: Annotated[Dict[str, str], operator.ior]
    
    # Agent visualization
    all_agents: Annotated[List[Dict], lambda a, b: a + b]
    all_edges: Annotated[List[Dict], lambda a, b: a + b]
    
    # Safety & Budget
    global_signal: Annotated[str, replace]
    usage_stats: Annotated[Dict[str, float], sum_usage]
    budget_config: Dict[str, float]
    
    # Quality
    confidence_score: float
    confidence_reasoning: str
