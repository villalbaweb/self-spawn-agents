from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from agent import app_graph
import json
from agents.semantic_splitter import semantic_splitter_node

import os

app = FastAPI(title="Multi-Agent Orchestrator Backend")

# Read allowed origins from environment variable, fallback to defaults
env_origins = os.getenv("ALLOWED_ORIGINS", "")
origins = [origin.strip() for origin in env_origins.split(",") if origin.strip()] or [
    "https://www.agent_forge_studio.villalbai.com",
    "https://agent_forge_studio.villalbai.com",
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
            # Emit start event with Run ID immediately
            yield f"data: {json.dumps({'type': 'start', 'run_id': req_id})}\n\n"

            initial_state = {
                "task": request.task, 
                "subtasks": [],
                "subject": "",
                "deliverables": []
            }
            
            # Pass thread_id to support checkpointers/HITL
            config = {"configurable": {"thread_id": req_id}}

            # Use astream_events to track node transitions
            latest_state = initial_state
            async for event in app_graph.astream_events(initial_state, config=config, version="v2"):
                kind = event.get("event")
                name = event.get("name")
                
                # Update latest_state on every end event that carries state
                if kind in ["on_chain_end", "on_node_end"]:
                    output = event.get("data", {}).get("output")
                    if output and isinstance(output, dict):
                        latest_state.update(output)

                # We care about when nodes start for progress logs
                if kind == "on_chain_start" and name in ["semantic_splitter", "supervisor", "graph_compiler", "confidence_check", "synthesizer"]:
                    display_names = {
                        "semantic_splitter": "Decomposing task into subtasks...",
                        "supervisor": "Planning execution graph with Supervisor...",
                        "graph_compiler": "Compiling and Executing Dynamic Graph...",
                        "confidence_check": "Evaluating results confidence...",
                        "synthesizer": "Synthesizing final report...",
                    }
                    msg = display_names.get(name, f"Executing {name}...")
                    yield f"data: {json.dumps({'type': 'progress', 'message': msg})}\n\n"

            # Check if the graph is at an interrupt point
            graph_state = await app_graph.aget_state(config)
            if graph_state.next:
                print(f"⏸️ Graph interrupted at: {graph_state.next}")
                yield f"data: {json.dumps({'type': 'interrupt', 'next': list(graph_state.next), 'confidence_score': latest_state.get('confidence_score', 0.0), 'review_required': True})}\n\n"

            # --- STREAM ENDED ---
            # Emit final results from the total accumulated state
            print(f"🏁 Stream ended. Captured state keys: {list(latest_state.keys())}")
            
            subtasks = latest_state.get("subtasks", [])
            graph_plan = latest_state.get("graph_plan", {})
            results = latest_state.get("results", {})
            synthesis = latest_state.get("synthesis", "")
            all_agents = latest_state.get("all_agents", [])
            all_edges = latest_state.get("all_edges", [])
            
            if subtasks:
                yield f"data: {json.dumps({'type': 'result', 'subtasks': subtasks})}\n\n"
            if graph_plan:
                yield f"data: {json.dumps({'type': 'result', 'graph_plan': graph_plan})}\n\n"
            if results:
                yield f"data: {json.dumps({'type': 'result', 'results': results})}\n\n"
            
            blueprint_id = latest_state.get("blueprint_id")
            if blueprint_id:
                yield f"data: {json.dumps({'type': 'blueprint', 'id': blueprint_id})}\n\n"

            if all_agents:
                print(f"📡 Emitting unified_graph: {len(all_agents)} agents")
                yield f"data: {json.dumps({'type': 'unified_graph', 'agents': all_agents, 'edges': all_edges})}\n\n"

            if synthesis:
                print(f"📡 Emitting synthesis report ({len(synthesis)} chars)")
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
    
    return {"status": "not_found", "message": f"Task {request_id} not found."}

@app.get("/api/run/{run_id}/blueprint")
async def get_blueprint(run_id: str):
    """
    Retrieve the blueprint for a specific run.
    """
    try:
        blueprint_path = f"blueprints/{run_id}.json"
        with open(blueprint_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"error": "Blueprint not found for this run ID"}
    except Exception as e:
        return {"error": f"Error retrieving blueprint: {str(e)}"}

class ResumeRequest(BaseModel):
    action: str # "proceed" or "refine"
    overrides: Optional[Dict[str, Any]] = None

@app.post("/api/run/{run_id}/resume")
async def resume_run(run_id: str, request: ResumeRequest):
    """
    Resume an interrupted execution.
    """
    print(f"🔄 Resuming task {run_id} with action: {request.action}")

    async def event_generator():
        config = {"configurable": {"thread_id": run_id}}
        
        # If refinement provided, update the state before resuming
        if request.overrides:
            print(f"📝 Applying state overrides: {list(request.overrides.keys())}")
            await app_graph.aupdate_state(config, request.overrides)

        latest_state = {}
        
        try:
            # Resuming by passing None as the first argument to astream_events
            async for event in app_graph.astream_events(None, config=config, version="v2"):
                kind = event.get("event")
                name = event.get("name")
                
                if kind in ["on_chain_end", "on_node_end"]:
                    output = event.get("data", {}).get("output")
                    if output and isinstance(output, dict):
                        latest_state.update(output)

                if kind == "on_chain_start" and name in ["confidence_check", "synthesizer"]:
                    display_names = {
                        "confidence_check": "Evaluating results confidence...",
                        "synthesizer": "Synthesizing final report...",
                    }
                    msg = display_names.get(name, f"Executing {name}...")
                    yield f"data: {json.dumps({'type': 'progress', 'message': msg})}\n\n"

            # Check if interrupted again
            graph_state = await app_graph.aget_state(config)
            if graph_state.next:
                yield f"data: {json.dumps({'type': 'interrupt', 'next': list(graph_state.next), 'review_required': True})}\n\n"
            else:
                # Execution finished, emit final synthesis
                # We need to fetch the full state since latest_state only has delta from resume
                full_state = await app_graph.aget_state(config)
                synthesis = full_state.values.get("synthesis", "")
                if synthesis:
                    yield f"data: {json.dumps({'type': 'synthesis', 'markdown': synthesis})}\n\n"

        except Exception as e:
            print(f"Error in resume_generator: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")