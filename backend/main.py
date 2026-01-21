from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from agent import app_graph
import json
from agents.semantic_splitter import semantic_splitter_node
from agents.shared_memory import init_checkpointer, close_checkpointer

import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup and clean up on shutdown."""
    await init_checkpointer()
    yield
    await close_checkpointer()

app = FastAPI(title="Multi-Agent Orchestrator Backend", lifespan=lifespan)

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
                
                # Extract extended interrupt data if available (from inner_graph_interrupt)
                interrupt_payload = {}
                if graph_state.tasks and len(graph_state.tasks) > 0:
                    task_interrupts = graph_state.tasks[0].interrupts
                    if task_interrupts and len(task_interrupts) > 0:
                        interrupt_payload = task_interrupts[0] if isinstance(task_interrupts[0], dict) else {}
                
                # Yield interrupt event with all metadata
                yield "data: " + json.dumps({
                    'type': 'interrupt', 
                    'next': list(graph_state.next), 
                    'confidence_score': interrupt_payload.get('confidence_score', latest_state.get('confidence_score', 0.0)),
                    'confidence_reasoning': interrupt_payload.get('confidence_reasoning', latest_state.get('confidence_reasoning', '')),
                    'review_required': True
                }) + "\n\n"
                
                # Also yield the unified graph state captured during interrupt if it exists
                if interrupt_payload.get("all_agents"):
                    print(f"📡 Emitting partial unified_graph from interrupt: {len(interrupt_payload['all_agents'])} agents")
                    yield "data: " + json.dumps({
                        'type': 'unified_graph', 
                        'agents': interrupt_payload['all_agents'], 
                        'edges': interrupt_payload.get('all_edges', [])
                    }) + "\n\n"

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
        if os.path.exists(blueprint_path):
            with open(blueprint_path, "r") as f:
                return json.load(f)
        return {"error": "Blueprint not found"}
    except Exception as e:
        return {"error": f"Error retrieving blueprint: {str(e)}"}

class HydrateRequest(BaseModel):
    source_thread_id: Optional[str] = None
    checkpoint_id: Optional[str] = None
    blueprint: Optional[Dict[str, Any]] = None

@app.get("/api/run/{run_id}/state")
async def get_run_state(run_id: str):
    """
    Stream the current state of a run (agents, edges, synthesis) without executing it.
    """
    async def state_generator():
        config = {"configurable": {"thread_id": run_id}}
        try:
            state = await app_graph.aget_state(config)
            if not state or not state.values:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Run state not found or empty'})}\n\n"
                return

            values = state.values
            all_agents = values.get("all_agents", [])
            all_edges = values.get("all_edges", [])
            synthesis = values.get("synthesis", "")
            
            # Emit run loaded event
            yield f"data: {json.dumps({'type': 'start', 'run_id': run_id})}\n\n"

            if all_agents:
                print(f"📡 Replaying unified_graph: {len(all_agents)} agents")
                yield f"data: {json.dumps({'type': 'unified_graph', 'agents': all_agents, 'edges': all_edges})}\n\n"
            
            if synthesis:
                yield f"data: {json.dumps({'type': 'synthesis', 'markdown': synthesis})}\n\n"
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            print(f"Error fetching state: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(state_generator(), media_type="text/event-stream")

@app.post("/api/hydrate")
async def hydrate_state(request: HydrateRequest):
    """
    Hydrate a new execution thread from an existing thread (Fork) 
    OR from a raw JSON blueprint (State Hydration).
    Returns: { "run_id": "new-uuid" }
    """
    print(f"💧 Hydrate request: source={request.source_thread_id}, has_blueprint={bool(request.blueprint)}")
    
    new_run_id = str(uuid4())
    config = {"configurable": {"thread_id": new_run_id}}

    try:
        if request.source_thread_id:
            # Fork from existing run
            from history import fork_run
            # fork_run creates a NEW thread ID internally, but we want to control it or get it back.
            # actually fork_run generates a uuid return it.
            # let's just use fork_run directly if source provided
            new_run_id = await fork_run(request.source_thread_id, request.checkpoint_id)
            print(f"✅ Forked run {request.source_thread_id} -> {new_run_id}")
            
        elif request.blueprint:
            # Hydrate from JSON Blueprint
            # We assume blueprint contains "task", "subtasks", "graph_plan", etc.
            initial_state = request.blueprint
            
            # Ensure essential fields are present
            if "task" not in initial_state:
                initial_state["task"] = "Hydrated Task"
            
            # Use aupdate_state to persist this state as the latest checkpoint for the new thread
            # as_node="start" is not needed, we just update state.
            await app_graph.aupdate_state(config, initial_state)
            print(f"✅ Hydrated new thread {new_run_id} from blueprint")
            
        else:
            raise HTTPException(status_code=400, detail="Must provide either source_thread_id or blueprint")

        return {"run_id": new_run_id}

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

from history import list_runs, fork_run, find_checkpoint_for_rewind

@app.get("/api/runs")
async def get_runs_handler():
    """List all available runs."""
    return await list_runs()

class ForkRequest(BaseModel):
    checkpoint_id: Optional[str] = None
    node_id: Optional[str] = None
    modifications: Optional[Dict[str, Any]] = None

@app.post("/api/run/{run_id}/fork")
async def fork_run_handler(run_id: str, request: ForkRequest):
    """
    Fork a run (Rewind). 
    If node_id is provided, finds the checkpoint before that node.
    Creates a new thread, applies modifications, and resumes execution.
    
    For inner agent nodes, we rewind to before graph_compiler and invalidate
    the target node's results (and all dependent nodes) to force re-execution.
    """
    print(f"🍴 Fork request for {run_id}. Node: {request.node_id}, Ckpt: {request.checkpoint_id}")
    
    target_checkpoint_id = request.checkpoint_id
    is_inner_node_rewind = False
    nodes_to_invalidate = []
    
    if request.node_id and not target_checkpoint_id:
        target_checkpoint_id = await find_checkpoint_for_rewind(run_id, request.node_id)
        if not target_checkpoint_id:
             print(f"❌ Could not find checkpoint for node {request.node_id}")
             async def error_generator():
                 yield f"data: {json.dumps({'type': 'error', 'message': f'Could not find checkpoint for node {request.node_id}'})}\n\n"
             return StreamingResponse(error_generator(), media_type="text/event-stream")
        
        # Check if this is an inner node rewind (we rewound to graph_compiler start)
        # by checking if the node is in the graph_plan
        from history import get_nodes_to_invalidate
        nodes_to_invalidate = await get_nodes_to_invalidate(run_id, request.node_id)
        if len(nodes_to_invalidate) > 0:
            is_inner_node_rewind = True
            print(f"🔄 Inner node rewind detected. Will invalidate: {nodes_to_invalidate}")

    try:
        new_run_id = await fork_run(run_id, target_checkpoint_id)
        
        # Apply modifications if any
        new_config = {"configurable": {"thread_id": new_run_id}}
        
        # For inner node rewinds, we need to:
        # 1. Clear the inner_thread_id so graph_compiler creates a fresh inner graph
        # 2. Remove the target node's results (and dependents) so they get re-executed
        if is_inner_node_rewind and nodes_to_invalidate:
            print(f"✏️ Invalidating results for inner node rewind: {nodes_to_invalidate}")
            
            # Get current state to modify
            current_state = await app_graph.aget_state(new_config)
            if current_state and current_state.values:
                results = dict(current_state.values.get("results", {}))
                metadata = dict(current_state.values.get("metadata", {}))
                all_agents = list(current_state.values.get("all_agents", []))
                
                # Remove invalidated nodes from results
                for node_id in nodes_to_invalidate:
                    if node_id in results:
                        del results[node_id]
                        print(f"  🗑️ Removed result for: {node_id}")
                    if node_id in metadata:
                        del metadata[node_id]
                
                # Remove invalidated agents from all_agents
                all_agents = [a for a in all_agents if a.get("id") not in nodes_to_invalidate]
                
                # Apply the state update - also clear inner_thread_id to force new inner graph
                await app_graph.aupdate_state(new_config, {
                    "results": results,
                    "metadata": metadata,
                    "all_agents": all_agents,
                    "inner_thread_id": None  # Force new inner graph
                })
        
        if request.modifications:
            print(f"✏️ Applying user modifications to {new_run_id}: {request.modifications}")
            await app_graph.aupdate_state(new_config, request.modifications)
            
        # Stream the new run
        async def event_generator():
            yield f"data: {json.dumps({'type': 'start', 'run_id': new_run_id, 'forked_from': run_id})}\n\n"
            
            # Resume execution
            try:
                # We interpret 'resume' here as 'continue execution from current state'
                # Pass None as input to resume normal graph flow
                async for event in app_graph.astream_events(None, config=new_config, version="v2"):
                    kind = event.get("event")
                    name = event.get("name")
                    
                    if kind in ["on_chain_end", "on_node_end"]:
                        output = event.get("data", {}).get("output")
                        if output and isinstance(output, dict):
                            # Emit partial updates if needed
                            pass

                    if kind == "on_chain_start" and name in ["graph_compiler", "confidence_check", "synthesizer"]:
                        display_names = {
                            "graph_compiler": "Resuming execution graph...",
                            "confidence_check": "Evaluating results confidence...",
                            "synthesizer": "Synthesizing final report...",
                        }
                        msg = display_names.get(name, f"Executing {name}...")
                        yield f"data: {json.dumps({'type': 'progress', 'message': msg})}\n\n"

                # Check for interrupts again (copy-pasted logic from run/resume)
                graph_state = await app_graph.aget_state(new_config)
                if graph_state.next:
                     # ... Handle interrupt (same logic as main run)
                     # For brevity, reusing the standard interrupt emission
                    interrupt_payload = {}
                    if graph_state.tasks and len(graph_state.tasks) > 0:
                        task_interrupts = graph_state.tasks[0].interrupts
                        if task_interrupts and len(task_interrupts) > 0:
                            interrupt_payload = task_interrupts[0] if isinstance(task_interrupts[0], dict) else {}
                    
                    yield "data: " + json.dumps({
                        'type': 'interrupt', 
                        'next': list(graph_state.next), 
                        'confidence_score': interrupt_payload.get('confidence_score', 0.0),
                        'confidence_reasoning': interrupt_payload.get('confidence_reasoning', ''),
                        'review_required': True
                    }) + "\n\n"
                    
                    if interrupt_payload.get("all_agents"):
                         yield "data: " + json.dumps({
                            'type': 'unified_graph', 
                            'agents': interrupt_payload['all_agents'], 
                            'edges': interrupt_payload.get('all_edges', [])
                        }) + "\n\n"
                else:
                    # Final results
                    full_state = await app_graph.aget_state(new_config)
                    synthesis = full_state.values.get("synthesis", "")
                    all_agents = full_state.values.get("all_agents", [])
                    all_edges = full_state.values.get("all_edges", [])
                    
                    if all_agents:
                        yield f"data: {json.dumps({'type': 'unified_graph', 'agents': all_agents, 'edges': all_edges})}\n\n"
                    if synthesis:
                        yield f"data: {json.dumps({'type': 'synthesis', 'markdown': synthesis})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"

            except Exception as e:
                print(f"Error in fork generator: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
        
        # Build the resume value to pass to the interrupted node
        if request.action == "refine" and request.overrides:
            # User provided a manual fix
            resume_value = {"output": request.overrides.get("output", "")}
        else:
            # User said "proceed" - just continue with the original output
            resume_value = {"action": "proceed"}
        
        print(f"📝 Resume value: {resume_value}")

        latest_state = {}
        
        try:
            # Use Command(resume=value) to pass the user's decision to the interrupted node
            from langgraph.types import Command
            resume_command = Command(resume=resume_value)
            
            # Resume the graph by streaming with the Command as input
            async for event in app_graph.astream_events(resume_command, config=config, version="v2"):
                kind = event.get("event")
                name = event.get("name")
                
                if kind in ["on_chain_end", "on_node_end"]:
                    output = event.get("data", {}).get("output")
                    if output and isinstance(output, dict):
                        latest_state.update(output)

                if kind == "on_chain_start" and name in ["graph_compiler", "confidence_check", "synthesizer"]:
                    display_names = {
                        "graph_compiler": "Resuming execution graph...",
                        "confidence_check": "Evaluating results confidence...",
                        "synthesizer": "Synthesizing final report...",
                    }
                    msg = display_names.get(name, f"Executing {name}...")
                    yield f"data: {json.dumps({'type': 'progress', 'message': msg})}\n\n"

            # Check if interrupted again
            graph_state = await app_graph.aget_state(config)
            if graph_state.next:
                print(f"⏸️ Graph interrupted again at: {graph_state.next}")
                
                # Extract extended interrupt data if available
                interrupt_payload = {}
                if graph_state.tasks and len(graph_state.tasks) > 0:
                    task_interrupts = graph_state.tasks[0].interrupts
                    if task_interrupts and len(task_interrupts) > 0:
                        interrupt_payload = task_interrupts[0] if isinstance(task_interrupts[0], dict) else {}
                
                # Yield interrupt event
                yield "data: " + json.dumps({
                    'type': 'interrupt', 
                    'next': list(graph_state.next), 
                    'confidence_score': interrupt_payload.get('confidence_score', latest_state.get('confidence_score', 0.0)),
                    'confidence_reasoning': interrupt_payload.get('confidence_reasoning', latest_state.get('confidence_reasoning', '')),
                    'review_required': True
                }) + "\n\n"
                
                # Also yield the unified graph state captured during interrupt if it exists
                if interrupt_payload.get("all_agents"):
                    print(f"📡 Emitting partial unified_graph from resume-interrupt: {len(interrupt_payload['all_agents'])} agents")
                    yield "data: " + json.dumps({
                        'type': 'unified_graph', 
                        'agents': interrupt_payload['all_agents'], 
                        'edges': interrupt_payload.get('all_edges', [])
                    }) + "\n\n"
            else:
                # Execution finished, emit final results
                full_state = await app_graph.aget_state(config)
                synthesis = full_state.values.get("synthesis", "")
                all_agents = full_state.values.get("all_agents", [])
                all_edges = full_state.values.get("all_edges", [])
                
                if all_agents:
                    print(f"📡 Emitting unified_graph: {len(all_agents)} agents")
                    yield f"data: {json.dumps({'type': 'unified_graph', 'agents': all_agents, 'edges': all_edges})}\n\n"
                    
                if synthesis:
                    print(f"📡 Emitting synthesis report ({len(synthesis)} chars)")
                    yield f"data: {json.dumps({'type': 'synthesis', 'markdown': synthesis})}\n\n"
                    
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            print(f"Error in resume_generator: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")