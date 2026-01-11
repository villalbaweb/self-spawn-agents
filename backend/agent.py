from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.semantic_splitter import semantic_splitter_node

# --- GRAPH ---
workflow = StateGraph(AgentState)

# Orchestrator Nodes
workflow.add_node("semantic_splitter", semantic_splitter_node)

workflow.set_entry_point("semantic_splitter")

# For now, end after splitting
workflow.add_edge("semantic_splitter", END)

app_graph = workflow.compile()
