from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.semantic_splitter import semantic_splitter_node
from agents.supervisor_agent import supervisor_node
from agents.graph_compiler import graph_compiler_node
from agents.synthesizer import synthesizer_node
from agents.confidence_check import confidence_check_node

# --- GRAPH ---
workflow = StateGraph(AgentState)

# Orchestrator Nodes
workflow.add_node("semantic_splitter", semantic_splitter_node)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("graph_compiler", graph_compiler_node)
workflow.add_node("confidence_check", confidence_check_node)
workflow.add_node("synthesizer", synthesizer_node)

workflow.set_entry_point("semantic_splitter")

# Flow: Splitter -> Supervisor -> Compiler -> Confidence Check -> Synthesizer -> END
workflow.add_edge("semantic_splitter", "supervisor")
workflow.add_edge("supervisor", "graph_compiler")
workflow.add_edge("graph_compiler", "confidence_check")
workflow.add_edge("confidence_check", "synthesizer")
workflow.add_edge("synthesizer", END)

# Lazy compilation - app_graph is compiled after checkpointer is initialized
_compiled_graph = None

def get_app_graph():
    """Get the compiled graph. Must be called after init_checkpointer()."""
    global _compiled_graph
    if _compiled_graph is None:
        from agents.shared_memory import memory
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
