from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
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

# Use MemorySaver for HITL (Human-in-the-Loop) support
from agents.shared_memory import memory
app_graph = workflow.compile(checkpointer=memory)

