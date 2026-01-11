from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.semantic_splitter import semantic_splitter_node
from agents.supervisor_agent import supervisor_node

# --- GRAPH ---
workflow = StateGraph(AgentState)

# Orchestrator Nodes
workflow.add_node("semantic_splitter", semantic_splitter_node)
workflow.add_node("supervisor", supervisor_node)

workflow.set_entry_point("semantic_splitter")

# Flow: Splitter -> Supervisor -> END
workflow.add_edge("semantic_splitter", "supervisor")
workflow.add_edge("supervisor", END)

app_graph = workflow.compile()
