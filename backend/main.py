from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from agent import app_graph
import json
from agents.semantic_splitter import semantic_splitter_node

import os

app = FastAPI(title="Multi-Agent Orchestrator Backend")

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

class DecomposeRequest(BaseModel):
    task: str

@app.post("/api/decompose")
async def decompose_handler(request: DecomposeRequest):
    """
    Decompose a high-level task into subtasks using Module 1 (Semantic Splitter).
    """
    print(f"Received decompose request for: {request.task}")
    # Construct minimal state for the node
    result = await semantic_splitter_node({"task": request.task, "subtasks": []})
    return {"status": "success", "subtasks": result.get("subtasks", [])}

class OrchestratorRequest(BaseModel):
    task: str

@app.post("/api/run")
async def run_orchestrator(request: OrchestratorRequest):
    """
    Execute the Orchestrator Graph for a given task.
    """
    print(f"Received orchestrator run request for: {request.task}")

    async def event_generator():
        try:
            initial_state = {
                "task": request.task, 
                "subtasks": []
            }
            
            # Use astream_events to track node transitions
            async for event in app_graph.astream_events(initial_state, version="v2"):
                kind = event.get("event")
                name = event.get("name")
                
                # Yield progress updates for nodes
                if kind == "on_chain_start" and name == "semantic_splitter":
                    msg = "Decomposing task into subtasks..."
                    yield f"data: {json.dumps({'type': 'progress', 'message': msg})}\n\n"

                # Yield final results
                elif kind == "on_chain_end" and name == "LangGraph":
                    final_output = event.get("data", {}).get("output", {})
                    subtasks = final_output.get("subtasks", [])
                    
                    if subtasks:
                         yield f"data: {json.dumps({'type': 'result', 'subtasks': subtasks})}\n\n"

        except Exception as e:
            print(f"Error in event_generator: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")