import asyncio
import httpx
from pydantic import BaseModel, Field
from typing import Optional
from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgentState
from agents.dependencies import llm_mini
from tools.content_extractor import extract_main_article
from tools.image_extractor import extract_main_image

# 1. Pydantic Schema for Context Compression
class PropertySummary(BaseModel):
    price: str = Field(..., description="TOTAL asking price (e.g. $4,500,000 MXN). Avoid price per m2.")
    size_m2: Optional[str] = Field(None, description="Size in square meters")
    rooms: Optional[str] = Field(None, description="Number of rooms/bedrooms")
    bathrooms: Optional[str] = Field(None, description="Number of bathrooms")
    amenities: Optional[str] = Field(None, description="Key features like pool, garden, etc.")
    description: str = Field(..., description="A 1-sentence summary of the property in SPANISH.")

SYSTEM_PROMPT_REFINER = """<role>Real Estate Data Refiner</role>
<objective>Extract key property metrics from noisy scraped text into a clean JSON summary.</objective>
<constraints>
- LANGUAGE: The 'description' MUST be in SPANISH.
- PRICE: Extract the TOTAL listing price. If you only see 'price per m2', try to multiply by size or mark as Unknown. Do NOT include operators like '>=' unless it's the only way to represent the value.
- INTEGRITY: Zero hallucinations. Use 'null' or 'Unknown' for missing values.
</constraints>"""

async def fetch_property_details(client: httpx.AsyncClient, item: dict, headers: dict):
    url = item.get('link')
    if not url:
        return None
        
    print(f"Fetching: {url}")
    try:
        resp = await client.get(url, headers=headers, timeout=10.0, follow_redirects=True)
        if resp.status_code == 200:
            text_content = extract_main_article(resp.text)
            image_url = extract_main_image(resp.text, url)

            # Availability filter
            unavailability_keywords = ["vendido", "vendida", "apartado", "apartada", "fuera de mercado", "no disponible", "renta", "rentada", "rentado"]
            content_lower = text_content.lower()
            if any(kw in content_lower for kw in unavailability_keywords):
                return None
            
            # Context Compression: LLM Refinement
            summary = PropertySummary(price=item.get('price', 'Unknown'), description="No details found.")
            if text_content and text_content != "No main content found.":
                try:
                    refiner_llm = llm_mini.with_structured_output(PropertySummary)
                    user_msg = f"<scraped_text>{text_content[:4000]}</scraped_text>"
                    summary = await refiner_llm.ainvoke([
                        SystemMessage(content=SYSTEM_PROMPT_REFINER),
                        HumanMessage(content=user_msg)
                    ])
                except Exception as e:
                    print(f"Refinement error for {url}: {e}")

            # Merge initial_data and refined summary into a single clean object
            refined_data = {
                "address": item.get("address") or summary.description, # Fallback to description if missing
                "neighborhood": item.get("neighborhood") or "Unknown",
                "price": summary.price,
                "size_m2": summary.size_m2 or item.get("size"),
                "rooms": summary.rooms,
                "bathrooms": summary.bathrooms,
                "amenities": summary.amenities,
                "description": summary.description,
                "link": url,
                "imageUrl": image_url or item.get('imageUrl')
            }

            # Update image if missing
            if refined_data["imageUrl"] == "No especificada":
                refined_data["imageUrl"] = None

            # Strict price filtering: If price is unknown or invalid, discard.
            price_val = refined_data["price"].lower() if refined_data["price"] else ""
            if not price_val or price_val in ['unknown', 'null', 'no especificado', 'no especificada', 'nd']:
                print(f"Discarding {url} due to unknown or invalid price after refinement.")
                return None

            return {
                "url": url,
                "title": item.get('title', ''),
                "property_data": refined_data
            }
        else:
            print(f"Failed to fetch {url}: Status {resp.status_code}")
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None

async def search_consolidator_node(state: AgentState):
    print("--- [CONSOLIDATOR AGENT] Consolidating and Fetching Details ---")
    candidates = state.get('property_candidates', [])
    
    seen_urls = set()
    selection = []
    for cand in candidates:
        url = cand.get('link')
        if url and url not in seen_urls:
            seen_urls.add(url)
            selection.append(cand)
        if len(selection) >= 15: # Reduced slightly for performance
            break
            
    if not selection:
        return {"detailed_content": []}
            
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)) as client:
        tasks = [fetch_property_details(client, item, headers) for item in selection]
        results = await asyncio.gather(*tasks)
        
    scraped_data = [r for r in results if r is not None]
    return {"detailed_content": scraped_data}
