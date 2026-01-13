from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.semantic_splitter import semantic_splitter_node
from agents.supervisor_agent import supervisor_node
from agents.graph_compiler import graph_compiler_node
from agents.synthesizer import synthesizer_node

# --- GRAPH ---
workflow = StateGraph(AgentState)

# Orchestrator Nodes
workflow.add_node("semantic_splitter", semantic_splitter_node)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("graph_compiler", graph_compiler_node)
workflow.add_node("synthesizer", synthesizer_node)

workflow.set_entry_point("semantic_splitter")

# Flow: Splitter -> Supervisor -> Compiler -> Synthesizer -> END
workflow.add_edge("semantic_splitter", "supervisor")
workflow.add_edge("supervisor", "graph_compiler")
workflow.add_edge("graph_compiler", "synthesizer")
workflow.add_edge("synthesizer", END)

app_graph = workflow.compile()
