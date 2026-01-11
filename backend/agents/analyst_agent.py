import json
import asyncio
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState
from agents.dependencies import llm
from tools.market_research import get_neighborhood_market_data

# 1. Pydantic Schema for individual analysis results
class AnalysisResult(BaseModel):
    address: str
    neighborhood: str
    price: str
    estimated_market_price: str = Field(..., description="Calculated FMV (e.g. $3,500,000 MXN)")
    size: Optional[str] = Field(None, description="Property size")
    contact: Optional[str] = Field(None, description="Contact info")
    link: str
    imageUrl: Optional[str]
    justification: str = Field(..., description="Reasoning including % vs market in SPANISH.")
    opportunity_score: int = Field(..., description="Integer score 1-10", ge=1, le=10)

SYSTEM_PROMPT_ANALYST = """<role>Expert Real Estate Valuation Analyst: Guadalajara, Jalisco.</role>
<objective>Compare <property_data> against <market_context> to calculate Fair Market Value (FMV) and Opportunity Score.</objective>
<constraints>
- MATH: Calculate Price/m2 for the property vs. the Median Price/m2 of the zone.
- PRICE VALIDATION: If the price seems too low for a total house price (e.g., < $100,000 MXN), it is likely 'Price per m2'. Flag this in the 'justification' and try to calculate the total price if 'size' is available.
- SCORING: 
    - 8-10: Price is >15% BELOW FMV (High Opportunity).
    - 4-7: Price is +/- 10% of FMV (Fair Value).
    - 1-3: Price is >15% ABOVE FMV (Overvalued).
- LANGUAGE: The 'justification' MUST be in SPANISH.
</constraints>"""

async def analyze_single_property(item: dict, market_context: str):
    """Analyzes a single property using the LLM."""
    property_data = item.get('property_data', {})
    
    # We use the consolidated, clean property_data object
    property_data_block = f"""
    <property_data>
    {json.dumps(property_data, ensure_ascii=False, indent=2)}
    </property_data>
    """
    
    prompt = f"""
    {market_context}
    {property_data_block}
    <task>Analyze the property and generate a structured report in SPANISH.</task>
    """
    
    messages = [
        SystemMessage(content=SYSTEM_PROMPT_ANALYST),
        HumanMessage(content=prompt)
    ]
    
    try:
        structured_llm = llm.with_structured_output(AnalysisResult)
        result = await structured_llm.ainvoke(messages)
        return result.dict()
    except Exception as e:
        print(f"Error analyzing property {item['url']}: {e}")
        return None

async def market_price_analyst_node(state: AgentState):
    print("--- [MARKET ANALYST] Analyzing properties individually ---")
    detailed = state.get('detailed_content', [])
    if not detailed:
        return {"analyzed_properties": []}
        
    # 0. Fetch unique market context and cache it to avoid redundant calls
    neighborhood_cache = {}
    tasks = []
    
    for item in detailed:
        nb = item.get('property_data', {}).get('neighborhood')
        if nb and nb not in neighborhood_cache:
            # Await the async market research data
            data = await get_neighborhood_market_data(nb)
            neighborhood_cache[nb] = f"<market_data zone='{nb}'>{data}</market_data>"
            
    for item in detailed:
        nb = item.get('property_data', {}).get('neighborhood')
        m_context = neighborhood_cache.get(nb, "No market data available for this zone.")
        full_context = f"<market_context>{m_context}</market_context>"
        tasks.append(analyze_single_property(item, full_context))
        
    # 2. Run analysis in parallel
    results = await asyncio.gather(*tasks)
    analyzed_list = [r for r in results if r is not None]
    
    return {"analyzed_properties": analyzed_list}
