"""
State definitions for the Worker Subgraph.
Lightweight state focused on task execution only.
"""
from typing import TypedDict, Dict, Any, Annotated, List
import operator


def replace(a: Any, b: Any) -> Any:
    """Reducer that replaces the old value with the new one."""
    return b


def sum_usage(a: Dict[str, float], b: Dict[str, float]) -> Dict[str, float]:
    """Reducer to accumulate usage stats (cost, tokens, steps)."""
    result = dict(a) if a else {}
    for key, value in (b or {}).items():
        result[key] = result.get(key, 0.0) + value
    return result


def merge_lists(a: List, b: List) -> List:
    """Reducer to concatenate lists."""
    return (a or []) + (b or [])


class WorkerState(TypedDict):
    """
    Lightweight state for the Worker Subgraph.
    Does NOT include semantic_splitter or supervisor fields.
    
    This state is designed for direct task execution, bypassing
    the full orchestration pipeline (semantic_splitter → supervisor → ...).
    """
    # Core execution context
    task: str                                           # The specific instruction for this worker
    subject: str                                        # Subject context (for drift prevention)
    parent_node_id: str                                 # ID of the parent node that spawned this
    root_task_id: str # Primary task ID for cost attribution
    
    # Execution tracking
    depth: Annotated[int, replace]                      # Current recursion depth
    results: Annotated[Dict[str, str], operator.ior]    # Execution results keyed by node ID
    
    # Agent visualization (unified with parent graph)
    all_agents: Annotated[List[Dict], merge_lists]      # Agents spawned during execution
    all_edges: Annotated[List[Dict], merge_lists]       # Edges created during execution
    
    # Safety & Budget (inherited from parent)
    global_signal: Annotated[str, replace]              # "INTERRUPT" to stop execution
    usage_stats: Annotated[Dict[str, float], sum_usage] # Accumulated cost/tokens/steps
    budget_config: Dict[str, float]                     # Limits: {"max_cost": 2.0, "max_steps": 50}
    
    # Quality metrics
    confidence_score: float                             # Output confidence (0.0 - 1.0)
    confidence_reasoning: str                           # Explanation for confidence score
