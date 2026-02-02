from langgraph.graph import StateGraph, END
from core.state.orchestrator_state import AgentState
from agents.task_decomposer import task_decomposer_node
from agents.execution_planner import execution_planner_node
from agents.graph_executor import graph_executor_node
from agents.synthesizer import synthesizer_node
from agents.confidence_check import confidence_check_node

# --- GRAPH ---
workflow = StateGraph(AgentState)

# Orchestrator Nodes
workflow.add_node("task_decomposer", task_decomposer_node)
workflow.add_node("execution_planner", execution_planner_node)
workflow.add_node("graph_executor", graph_executor_node)
workflow.add_node("confidence_check", confidence_check_node)
workflow.add_node("synthesizer", synthesizer_node)

workflow.set_entry_point("task_decomposer")

# Flow: Decomposer -> Planner -> Executor -> Confidence Check -> Synthesizer -> END
workflow.add_edge("task_decomposer", "execution_planner")
workflow.add_edge("execution_planner", "graph_executor")
workflow.add_edge("graph_executor", "confidence_check")
workflow.add_edge("confidence_check", "synthesizer")
workflow.add_edge("synthesizer", END)

# Lazy compilation - app_graph is compiled after checkpointer is initialized
_compiled_graph = None

def get_app_graph():
    """Get the compiled graph. Must be called after init_checkpointer()."""
    global _compiled_graph
    if _compiled_graph is None:
        from core.persistence.checkpointer import memory
        if memory is None:
            raise RuntimeError("Checkpointer not initialized. Call init_checkpointer() first.")
        _compiled_graph = workflow.compile(checkpointer=memory)
    return _compiled_graph

# For backwards compatibility, create a proxy that lazily gets the graph
class _GraphProxy:
    """Proxy object that forwards attribute access to the lazily compiled graph."""
    def __getattr__(self, name):
        return getattr(get_app_graph(), name)

app_graph = _GraphProxy()
