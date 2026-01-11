import json
import re
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from agents.state import AgentState
from agents.dependencies import llm

# 1. Pydantic Schema (Keep this for the parser)
class Contact(BaseModel):
    email: Optional[str] = Field(None, description="Property contact email")
    phone: Optional[str] = Field(None, description="Property contact phone")

class PropertyReport(BaseModel):
    id: str = Field(..., description="Sequential ID (e.g., prop_001)")
    address: str
    neighborhood: str
    price: str
    estimated_market_price: str
    details: str
    justification: str
    contact: Contact
    link: str
    imageUrl: Optional[str]
    opportunity_score: str

class PropertyReportList(BaseModel):
    reports: List[PropertyReport]

# 2. Setup the Parser
parser = PydanticOutputParser(pydantic_object=PropertyReportList)

SYSTEM_PROMPT_COMPILER = f"""<role>Precision Data Compiler & JSON Architect.</role>
<objective>Compile <input_data> into a standardized Investment Opportunity Report.</objective>
<constraints>
- LANGUAGE: ALL generated text (specifically 'details' and 'justification') MUST be in SPANISH.
- INTEGRITY: Zero hallucinations. Retain all technical metrics.
- ID_GEN: Assign sequential IDs starting from prop_001.
- DETAILS: Synthesize a 1-2 sentence summary based on sqm/location in SPANISH.
- JUSTIFICATION: Explain why it is a good opportunity in SPANISH.
- FORMAT: Output a valid JSON array matching the schema below.
</constraints>

<schema_instructions>
{parser.get_format_instructions()}
</schema_instructions>"""

async def report_compiler_node(state: AgentState):
    analyzed_props = state.get('analyzed_properties', [])
    if not analyzed_props: return {"final_results": []}

    input_json = json.dumps(analyzed_props, separators=(',', ':'))
    user_prompt = f"""<input_data>{input_json}</input_data>
<task>Compile the final report from <input_data>. Assign sequential IDs and synthesize details for each property in SPANISH.</task>"""

    messages = [
        SystemMessage(content=SYSTEM_PROMPT_COMPILER),
        HumanMessage(content=user_prompt)
    ]
    
    try:
        # Use with_structured_output for better reliability
        structured_llm = llm.with_structured_output(PropertyReportList)
        final_data = await structured_llm.ainvoke(messages)
        
        # Convert Pydantic objects to serializable dicts
        return {"final_results": [prop.dict() for prop in final_data.reports]}
            
    except Exception as e:
        print(f"--- [REPORT COMPILER] Error: {e} ---")
        # If structured output fails, try to add missing fields manually as fallback
        formatted_props = []
        for idx, prop in enumerate(analyzed_props):
            p = prop.copy()
            if 'id' not in p:
                p['id'] = f"prop_{idx+1:03d}"
            if 'details' not in p:
                # Sintetizar un string de detalles simple si falta
                nb = p.get('neighborhood', 'Vecindario desconocido')
                price = p.get('price', 'precio no especificado')
                p['details'] = f"Propiedad en {nb} listada a {price}."
            formatted_props.append(p)
        return {"final_results": formatted_props}
