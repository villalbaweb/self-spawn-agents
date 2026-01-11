import json
from pydantic import BaseModel, Field
from typing import List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState
from agents.dependencies import llm_mini, search

# 1. Pydantic Schema for structured output
class PropertyCandidate(BaseModel):
    address: str = Field(..., description="Property address")
    neighborhood: str = Field(..., description="Neighborhood or area")
    price: str = Field(..., description="Asking price")
    size: Optional[str] = Field(None, description="Size in square meters/feet")
    contact: Optional[str] = Field(None, description="Contact information")
    link: str = Field(..., description="Direct URL to the listing")
    imageUrl: Optional[str] = Field(None, description="Direct URL to a property image")

class PropertyCandidateList(BaseModel):
    candidates: List[PropertyCandidate]

SYSTEM_PROMPT_SEARCH = """<role>Expert Real Estate Researcher: Guadalajara, Jalisco.</role>
<objective>Extract active "For Sale" listings in [BARRIO] with 100% integrity from the provided search results.</objective>
<constraints>
- SOURCE: Full, direct URLs only.
- PII: No masking (e.g., +52...).
- FILTER: Exclude "Vendido", "Apartado", "Renta".
- PRICE: Prefer the TOTAL property price. Avoid extracting 'price per m2' if possible.
</constraints>"""

async def search_market_node(state: AgentState):
    barrio = state.get('query', 'Guadalajara')
    print(f"--- [SEARCH AGENT] Neighborhood: {barrio} ---")
    
    # 1. Advanced Serper Query
    search_query = f"{barrio} guadalajara venta -renta -vendido (inurl:propiedad OR inurl:casa)"
    try:
        results = search.results(search_query).get('organic', [])
        # Pruning fields to save tokens while keeping what's needed for analysis
        raw_results = [
            {k: v for k, v in r.items() if k in ['title', 'link', 'snippet', 'imageUrl', 'thumbnail']}
            for r in results
        ]
    except Exception as e:
        print(f"Search failed: {e}")
        raw_results = []

    # 2. Structured Output with gpt-4o-mini
    sys_msg = SYSTEM_PROMPT_SEARCH.replace("[BARRIO]", barrio)
    user_prompt = f"""<data>{json.dumps(raw_results, separators=(',', ':'))}</data>
<task>Extract listings from <data> following the role and constraints provided.</task>"""

    messages = [SystemMessage(content=sys_msg), HumanMessage(content=user_prompt)]
    
    try:
        structured_llm = llm_mini.with_structured_output(PropertyCandidateList)
        response = await structured_llm.ainvoke(messages)
        candidates = [c.dict() for c in response.candidates]
    except Exception as e:
        print(f"LLM Error in Search Agent: {e}")
        candidates = []
    
    return {"search_results": raw_results, "property_candidates": candidates}
