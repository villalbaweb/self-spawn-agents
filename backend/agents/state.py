from typing import TypedDict, List, Dict, Any

class AgentState(TypedDict):
    query: str
    search_results: List[Dict[str, Any]] 
    property_candidates: List[Dict[str, Any]] # Output of Search Agent
    detailed_content: List[Dict[str, Any]] # Output of Consolidator Agent
    analyzed_properties: List[Dict[str, Any]] 
    opportunities: List[Dict[str, Any]] 
    final_results: List[Dict[str, Any]] 
