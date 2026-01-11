from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from agent import app_graph
import json

import os

app = FastAPI(title="Opportunity Finder Backend")

# Read allowed origins from environment variable, fallback to defaults
env_origins = os.getenv("ALLOWED_ORIGINS", "")
origins = [origin.strip() for origin in env_origins.split(",") if origin.strip()] or [
    "https://www.opportunityfinder.villalbai.com",
    "https://opportunityfinder.villalbai.com",
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

# Allow CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchRequest(BaseModel):
    query: str

class ContactInfo(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None

class PropertyResult(BaseModel):
    id: Optional[str] = None
    address: Optional[str] = None
    price: Optional[str] = None
    estimated_market_price: Optional[str] = None
    neighborhood: Optional[str] = None
    details: Optional[str] = None
    justification: Optional[str] = None
    imageUrl: Optional[str] = None
    link: Optional[str] = None
    source_url: Optional[str] = None
    contact: Optional[ContactInfo] = None
    opportunity_score: Optional[int] = None

class SearchResponse(BaseModel):
    status: str
    results: List[PropertyResult]

@app.get("/")
def read_root():
    return {"message": "Opportunity Finder Backend is running"}

@app.post("/api/search")
async def search_handler(request: SearchRequest):
    print(f"Received search request for: {request.query}")

    async def event_generator():
        try:
            initial_state = {"query": request.query, "raw_data": [], "final_results": []}
            
            # Use astream_events to track node transitions
            # Note: version="v2" is recommended for latest LangGraph
            async for event in app_graph.astream_events(initial_state, version="v2"):
                kind = event.get("event")
                name = event.get("name")
                
                # We care about when nodes start
                if kind == "on_chain_start" and name in ["search_market", "search_consolidator", "market_analyst", "report_compiler"]:
                    display_names = {
                        "search_market": "Buscando propiedades en el mercado...",
                        "search_consolidator": "Consolidando y extrayendo detalles...",
                        "market_analyst": "Analizando precios y oportunidades...",
                        "report_compiler": "Compilando reporte final..."
                    }
                    msg = display_names.get(name, f"Ejecutando {name}...")
                    yield f"data: {json.dumps({'type': 'progress', 'message': msg})}\n\n"

                # We care about the final result from the graph
                elif kind == "on_chain_end" and name == "LangGraph":
                    # The final output of the graph is in event["data"]["output"]
                    final_output = event.get("data", {}).get("output", {})
                    results = final_output.get("final_results", [])
                    yield f"data: {json.dumps({'type': 'result', 'results': results})}\n\n"

        except Exception as e:
            print(f"Error in event_generator: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
