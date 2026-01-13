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

import asyncio
from typing import Dict
from uuid import uuid4

# Global registry for running tasks
running_tasks: Dict[str, asyncio.Task] = {}

class OrchestratorRequest(BaseModel):
    task: str
    request_id: Optional[str] = None

@app.post("/api/run")
async def run_orchestrator(request: OrchestratorRequest):
    """
    Execute the Orchestrator Graph for a given task.
    """
    print(f"Received orchestrator run request for: {request.task}")

    # Use provided ID or generate one
    req_id = request.request_id or str(uuid4())
    print(f"🆔 Request ID: {req_id}")

    async def event_generator():
        # Register current task
        current_task = asyncio.current_task()
        if current_task:
            running_tasks[req_id] = current_task
            print(f"✅ Registered task {req_id}")

        try:
            initial_state = {
                "task": request.task, 
                "subtasks": [],
                "subject": "",
                "deliverables": []
            }
            
            # Use astream_events to track node transitions
            async for event in app_graph.astream_events(initial_state, version="v2"):
                kind = event.get("event")
                name = event.get("name")
                
                # We care about when nodes start
                if kind == "on_chain_start" and name in ["semantic_splitter", "supervisor", "graph_compiler", "synthesizer"]:
                    display_names = {
                        "semantic_splitter": "Decomposing task into subtasks...",
                        "supervisor": "Planning execution graph with Supervisor...",
                        "graph_compiler": "Compiling and Executing Dynamic Graph...",
                        "synthesizer": "Synthesizing final report...",
                    }
                    msg = display_names.get(name, f"Executing {name}...")
                    yield f"data: {json.dumps({'type': 'progress', 'message': msg})}\n\n"

                # Yield final results
                elif kind == "on_chain_end" and name == "LangGraph":
                    final_output = event.get("data", {}).get("output", {})
                    subtasks = final_output.get("subtasks", [])
                    graph_plan = final_output.get("graph_plan", {})
                    results = final_output.get("results", {})
                    synthesis = final_output.get("synthesis", "")
                    
                    if subtasks:
                         yield f"data: {json.dumps({'type': 'result', 'subtasks': subtasks})}\n\n"
                    
                    if graph_plan:
                         yield f"data: {json.dumps({'type': 'result', 'graph_plan': graph_plan})}\n\n"

                    if results:
                         yield f"data: {json.dumps({'type': 'result', 'results': results})}\n\n"
                    
                    if synthesis:
                         yield f"data: {json.dumps({'type': 'synthesis', 'markdown': synthesis})}\n\n"

        except asyncio.CancelledError:
            print(f"🚫 Task {req_id} was cancelled.")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Task was cancelled/interrupted.'})}\n\n"
            # Re-raise to ensure proper task cancellation propagation if needed, 
            # though usually yielding stops the generator consumption.
            raise 

        except Exception as e:
            print(f"Error in event_generator: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            
        finally:
            # Cleanup
            if req_id in running_tasks:
                del running_tasks[req_id]
                print(f"🧹 Unregistered task {req_id}")

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/cancel/{request_id}")
async def cancel_orchestrator(request_id: str):
    """
    Cancel a running orchestrator task by its request_id.
    """
    if request_id in running_tasks:
        task = running_tasks[request_id]
        task.cancel()
        return {"status": "cancelled", "message": f"Task {request_id} has been requested to cancel."}
    
    raise HTTPException(status_code=404, detail=f"Task {request_id} not found or not running.")