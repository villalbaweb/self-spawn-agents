from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.search_agent import search_market_node
from agents.consolidator_agent import search_consolidator_node
from agents.analyst_agent import market_price_analyst_node
from agents.compiler_agent import report_compiler_node

# --- GRAPH ---
workflow = StateGraph(AgentState)

workflow.add_node("search_market", search_market_node)
workflow.add_node("search_consolidator", search_consolidator_node)
workflow.add_node("market_analyst", market_price_analyst_node)
#workflow.add_node("opportunity_detector", opportunity_detector_node)
workflow.add_node("report_compiler", report_compiler_node)

workflow.set_entry_point("search_market")

workflow.add_edge("search_market", "search_consolidator")
workflow.add_edge("search_consolidator", "market_analyst")
workflow.add_edge("market_analyst", "report_compiler")
#workflow.add_edge("opportunity_detector", "report_compiler")
workflow.add_edge("report_compiler", END)

app_graph = workflow.compile()
