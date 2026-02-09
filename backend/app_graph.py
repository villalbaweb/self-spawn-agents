from langgraph.graph import StateGraph, END
from core.state.orchestrator_state import AgentState
from agents.task_decomposer import task_decomposer_node
from agents.blueprint_manager import blueprint_manager_node, archive_blueprint_node
from agents.execution_planner import execution_planner_node
from agents.graph_executor import graph_executor_node
from agents.synthesizer import synthesizer_node


# --- Conditional Edge: Route based on cache hit ---
def route_after_blueprint_check(state: AgentState) -> str:
    """
    Route to executor if cache hit, otherwise to planner.
    """
    if state.get("blueprint_cache_hit", False):
        print("🚀 [router] Cache HIT detected - skipping planner, going to executor.")
        return "graph_executor"
    else:
        print("📋 [router] Cache MISS - proceeding to execution planner.")
        return "execution_planner"


# --- GRAPH ---
workflow = StateGraph(AgentState)

# Orchestrator Nodes
workflow.add_node("task_decomposer", task_decomposer_node)
workflow.add_node("blueprint_manager", blueprint_manager_node)
workflow.add_node("execution_planner", execution_planner_node)
workflow.add_node("graph_executor", graph_executor_node)
workflow.add_node("synthesizer", synthesizer_node)
workflow.add_node("archive_blueprint", archive_blueprint_node)

workflow.set_entry_point("task_decomposer")

# Flow with Blueprint Cache Check:
# Decomposer -> Blueprint Manager -> (Cache Hit? -> Executor : Planner -> Executor)
# -> Synthesizer -> Archive Blueprint -> END
workflow.add_edge("task_decomposer", "blueprint_manager")
workflow.add_conditional_edges(
    "blueprint_manager",
    route_after_blueprint_check,
    {
        "graph_executor": "graph_executor",
        "execution_planner": "execution_planner"
    }
)
workflow.add_edge("execution_planner", "graph_executor")
workflow.add_edge("graph_executor", "synthesizer")
workflow.add_edge("synthesizer", "archive_blueprint")
workflow.add_edge("archive_blueprint", END)

# Lazy compilation - app_graph is compiled after checkpointer is initialized
_compiled_graph = None

def get_app_graph():
    """Get the compiled graph. Must be called after init_checkpointer()."""
    global _compiled_graph
    if _compiled_graph is None:
        from core.persistence.checkpointer import get_checkpointer
        checkpointer = get_checkpointer()
        if checkpointer is None:
            raise RuntimeError("Checkpointer not initialized. Call init_checkpointer() first.")
        _compiled_graph = workflow.compile(checkpointer=checkpointer)
    return _compiled_graph

# For backwards compatibility, create a proxy that lazily gets the graph
class _GraphProxy:
    """Proxy object that forwards attribute access to the lazily compiled graph."""
    def __getattr__(self, name):
        return getattr(get_app_graph(), name)

app_graph = _GraphProxy()
