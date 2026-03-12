from fastapi import FastAPI, HTTPException
print("🚀 [Backend] main.py loaded!")
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from app_graph import app_graph
import json
from agents.task_decomposer import task_decomposer_node
from core.persistence.checkpointer import init_checkpointer, close_checkpointer
from core.cost import CostTracker, CostTrackingCallback, BudgetExceededError

import os
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup and clean up on shutdown."""
    print("🚀 [Lifespan] Starting up...")
    await init_checkpointer()

    # --- AGENTGUARD AUTHENTICATION ---
    from agentguard_sdk.client import get_agentguard_client
    print("🛡️ [Lifespan] Initiating connection to AgentGuard...")
    ag_client = get_agentguard_client()
    # Uses ADMIN_USERNAME and ADMIN_PASSWORD env vars, or defaults to admin/agentguard123
    success = await ag_client.authenticate()
    if success:
        print("✅ [Lifespan] Successfully authenticated with AgentGuard!")
    else:
        print("❌ [Lifespan] Failed to authenticate with AgentGuard.")
    
    # Start interrupt cleanup background task (Recommendation #3)
    from config.settings import INTERRUPT_TIMEOUT_SECONDS
    if INTERRUPT_TIMEOUT_SECONDS > 0:
        asyncio.create_task(cleanup_stale_interrupts())
        print(f"🚀 Started interrupt cleanup task (timeout: {INTERRUPT_TIMEOUT_SECONDS}s)")
    
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
    Decompose a high-level task into subtasks using the Task Decomposer.
    """
    print(f"Received decompose request for: {request.task}")
    # Construct minimal state for the node
    result = await task_decomposer_node({"task": request.task, "subtasks": []})
    return {"status": "success", "subtasks": result.get("subtasks", [])}

import asyncio
from typing import Dict
from uuid import uuid4
import time
from config.settings import INTERRUPT_TIMEOUT_SECONDS

# Global registry for running tasks
running_tasks: Dict[str, asyncio.Task] = {}

# Global registry for interrupt state tracking (Recommendation #3)
interrupt_registry: Dict[str, Dict[str, Any]] = {}
# Structure: {run_id: {"timestamp": float, "interrupt_type": str, "confidence_score": float}}

# Global registry for cumulative usage stats tracking (Cost Tracking Fix)
cumulative_usage_registry: Dict[str, Dict[str, float]] = {}
# Structure: {run_id: {"cost": float, "input_tokens": int, "output_tokens": int, "llm_calls": int, "tool_calls": int, "steps": int}}


async def cleanup_stale_interrupts():
    """Background task to clean up stale interrupts."""
    while True:
        try:
            await asyncio.sleep(60)
            current_time = time.time()
            stale_runs = [
                run_id for run_id, data in interrupt_registry.items()
                if current_time - data["timestamp"] > INTERRUPT_TIMEOUT_SECONDS
            ]
            
            for run_id in stale_runs:
                print(f"⏰ [Interrupt Cleanup] Timeout for run_id: {run_id}")
                try:
                    config = {"configurable": {"thread_id": run_id}}
                    graph_state = await app_graph.aget_state(config)
                    
                    if graph_state.next:
                        from langgraph.types import Command
                        abort_value = {"action": "abort", "reasoning": "Timeout exceeded"}
                        
                        interrupt_ids = []
                        if graph_state.tasks:
                            for task in graph_state.tasks:
                                if task.interrupts:
                                    for interrupt_obj in task.interrupts:
                                        if hasattr(interrupt_obj, 'id'):
                                            interrupt_ids.append(interrupt_obj.id)
                        
                        if len(interrupt_ids) > 1:
                            resume_payload = {iid: abort_value for iid in interrupt_ids}
                            await app_graph.ainvoke(Command(resume=resume_payload), config=config)
                        else:
                            await app_graph.ainvoke(Command(resume=abort_value), config=config)
                    
                    del interrupt_registry[run_id]
                except Exception as e:
                    print(f"❌ Cleanup error for {run_id}: {e}")
                    if run_id in interrupt_registry:
                        del interrupt_registry[run_id]
        except Exception as e:
            print(f"❌ Background task error: {e}")


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
        print(f"🚀 [event_generator] Starting for {req_id}")
        # Register current task
        current_task = asyncio.current_task()
        if current_task:
            running_tasks[req_id] = current_task
            print(f"✅ Registered task {req_id}")

        try:
            # Emit start event with Run ID immediately
            yield f"data: {json.dumps({'type': 'start', 'run_id': req_id})}\n\n"
            print(f"📡 [event_generator] Yielded start event for {req_id}")

            initial_state = {
                "task": request.task, 
                "subtasks": [],
                "subject": "",
                "deliverables": [],
                "root_task_id": req_id,
                "usage_stats": {
                    "cost": 0.0,
                    "input_tokens": 0.0,
                    "output_tokens": 0.0,
                    "cached_tokens": 0.0,
                    "llm_calls": 0.0,
                    "tool_calls": 0.0,
                    "steps": 0.0
                }
            }
            
            # Pass thread_id to support checkpointers/HITL
            config = {"configurable": {"thread_id": req_id}}

            # Use astream_events to track node transitions
            latest_state = initial_state
            async for event in app_graph.astream_events(initial_state, config=config, version="v2"):
                kind = event.get("event")
                name = event.get("name")
                print(f"DEBUG: Processing event: {kind} {name}")
                
                # Update latest_state on every end event that carries state
                if kind in ["on_chain_end", "on_node_end"]:
                    output = event.get("data", {}).get("output")
                    if output and isinstance(output, dict):
                        latest_state.update(output)
                        # FIX: Source usage_stats from global CostTracker for Monotonic updates
                        # (latest_state['usage_stats'] only contains the last node's delta)
                        tracker = CostTracker.get_instance()
                        real_stats = tracker.to_usage_stats(task_id=req_id)
                        
                        # Accumulate into cumulative registry
                        if req_id not in cumulative_usage_registry:
                            cumulative_usage_registry[req_id] = {
                                "cost": 0.0,
                                "input_tokens": 0,
                                "output_tokens": 0,
                                "llm_calls": 0,
                                "tool_calls": 0,
                                "steps": 0,
                                "cached_tokens": 0
                            }
                        
                        # Update cumulative totals (use max to handle resets)
                        cumulative_usage_registry[req_id]["cost"] = real_stats.get("cost", 0)
                        cumulative_usage_registry[req_id]["input_tokens"] = real_stats.get("input_tokens", 0)
                        cumulative_usage_registry[req_id]["output_tokens"] = real_stats.get("output_tokens", 0)
                        cumulative_usage_registry[req_id]["llm_calls"] = real_stats.get("llm_calls", 0)
                        cumulative_usage_registry[req_id]["tool_calls"] = real_stats.get("tool_calls", 0)
                        cumulative_usage_registry[req_id]["steps"] = real_stats.get("steps", 0)
                        cumulative_usage_registry[req_id]["cached_tokens"] = real_stats.get("cached_tokens", 0)
                        
                        # Emit cumulative stats instead of just current
                        yield f"data: {json.dumps({'type': 'usage_stats', 'stats': cumulative_usage_registry[req_id]})}\n\n"

                # We care about when nodes start for progress logs
                if kind == "on_chain_start" and name in ["task_decomposer", "execution_planner", "graph_executor", "synthesizer"]:
                    display_names = {
                        "task_decomposer": "Decomposing task into subtasks...",
                        "execution_planner": "Planning execution graph...",
                        "graph_executor": "Compiling and Executing Dynamic Graph...",
                        "synthesizer": "Synthesizing final report...",
                    }
                    msg = display_names.get(name, f"Executing {name}...")
                    yield f"data: {json.dumps({'type': 'progress', 'message': msg})}\n\n"

            # Check if the graph is at an interrupt point
            graph_state = await app_graph.aget_state(config)
            if graph_state.next:
                print(f"⏸️ Graph interrupted at: {graph_state.next}")
                
                # Extract extended interrupt data from ALL tasks (not just the first one)
                # When parallel nodes interrupt, there may be multiple tasks with interrupts
                interrupt_payload = {}
                all_interrupt_agents = []
                all_interrupt_edges = []
                combined_confidence_score = 0.0
                combined_confidence_reasoning = ""
                
                if graph_state.tasks:
                    for task in graph_state.tasks:
                        if task.interrupts:
                            for interrupt_obj in task.interrupts:
                                # Get the interrupt value (might be wrapped in an object)
                                val = interrupt_obj.value if hasattr(interrupt_obj, 'value') else interrupt_obj
                                if isinstance(val, dict):
                                    # Collect agents from all interrupts
                                    if val.get("all_agents"):
                                        all_interrupt_agents.extend(val["all_agents"])
                                    if val.get("all_edges"):
                                        all_interrupt_edges.extend(val["all_edges"])
                                    # Use first interrupt's confidence as primary
                                    if combined_confidence_score == 0.0:
                                        combined_confidence_score = val.get("confidence_score", 0.0)
                                        combined_confidence_reasoning = val.get("confidence_reasoning", "")
                                    # Merge other fields from first interrupt found
                                    if not interrupt_payload:
                                        interrupt_payload = val
                
                # Add combined agents/edges to payload
                if all_interrupt_agents:
                    interrupt_payload["all_agents"] = all_interrupt_agents
                if all_interrupt_edges:
                    interrupt_payload["all_edges"] = all_interrupt_edges
                
                # 🔍 [Interrupt Debug] Register interrupt in global registry
                interrupt_registry[req_id] = {
                    "timestamp": time.time(),
                    "interrupt_type": interrupt_payload.get("type", "unknown"),
                    "confidence_score": combined_confidence_score or interrupt_payload.get("confidence_score", 0.0),
                    "paused_at": list(graph_state.next)
                }
                print(f"🔍 [Interrupt Debug] Registered interrupt for run_id: {req_id}")
                print(f"   - Combined agents: {len(all_interrupt_agents)}, edges: {len(all_interrupt_edges)}")
                
                # Yield interrupt event with all metadata
                yield "data: " + json.dumps({
                    'type': 'interrupt', 
                    'next': list(graph_state.next), 
                    'confidence_score': combined_confidence_score or interrupt_payload.get('confidence_score', latest_state.get('confidence_score', 0.0)),
                    'confidence_reasoning': combined_confidence_reasoning or interrupt_payload.get('confidence_reasoning', latest_state.get('confidence_reasoning', '')),
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
            # Fetch the actual final state from the checkpointer to ensure all updates (including the last node) are captured
            final_graph_state = await app_graph.aget_state(config)
            if final_graph_state and final_graph_state.values:
                latest_state = final_graph_state.values
                print(f"🏁 Stream ended. Final state captured from checkpointer.")
            else:
                print(f"🏁 Stream ended. Falling back to latest_state accumulator.")

            print(f"📊 Final Captured Cost: ${latest_state.get('usage_stats', {}).get('cost', 0):.6f}")
            print(f"Captured state keys: {list(latest_state.keys())}")
            
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
            # Note: Do NOT delete from cumulative_usage_registry here
            # It needs to persist across interrupt/resume cycles
            # Only clean up on explicit cancel or after final completion

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/cancel/{request_id}")
async def cancel_orchestrator(request_id: str):
    """
    Cancel a running orchestrator task by its request_id.
    """
    if request_id in running_tasks:
        task = running_tasks[request_id]
        task.cancel()
        
        # Cleanup cumulative usage registry
        if request_id in cumulative_usage_registry:
            del cumulative_usage_registry[request_id]
            print(f"🧹 Cleaned up cumulative usage stats for {request_id}")
        
        return {"status": "cancelled", "message": f"Task {request_id} has been requested to cancel."}
    
    return {"status": "not_found", "message": f"Task {request_id} not found."}

# --- COST TRACKING API ---

@app.get("/api/cost/summary")
async def get_cost_summary(task_id: Optional[str] = None):
    """
    Get aggregated cost summary.
    Optional task_id filter for per-task breakdown.
    """
    tracker = CostTracker.get_instance()
    summary = tracker.get_summary(task_id)
    return summary.model_dump()

@app.get("/api/cost/records")
async def get_cost_records(task_id: Optional[str] = None, limit: int = 100):
    """
    Get detailed cost records.
    """
    tracker = CostTracker.get_instance()
    records = tracker.export_records(task_id)
    # Ensure we return plain dicts (already serialized by export_records)
    result_records = records[-limit:] if len(records) > limit else records
    return {"records": result_records, "total": len(records)}

@app.get("/api/run/{run_id}/cost")
async def get_run_cost(run_id: str):
    """
    Get cost breakdown for a specific run.
    """
    tracker = CostTracker.get_instance()
    summary = tracker.get_summary(run_id)
    
    return {
        "run_id": run_id,
        "total_cost_usd": summary.total_cost_usd,
        "total_input_tokens": summary.total_input_tokens,
        "total_output_tokens": summary.total_output_tokens,
        "call_count": summary.call_count,
        "by_type": summary.by_type,
        "by_model": summary.by_model,
        "by_node": summary.by_node,
    }

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
            
            # Emit usage stats if present
            usage_stats = values.get("usage_stats")
            if usage_stats:
                yield f"data: {json.dumps({'type': 'usage_stats', 'stats': usage_stats})}\n\n"

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
            from api.history import fork_run
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

from api.history import list_runs, fork_run, find_checkpoint_for_rewind

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
    Targeted Sub-Incision: Targets the specific sub-graph layer where the node lives.
    """
    print(f"🍴 Fork request for {run_id}. Node: {request.node_id}, Ckpt: {request.checkpoint_id}")
    
    try:
        # 1. Find the base checkpoint and the target thread
        checkpoint_id = request.checkpoint_id
        target_thread_id = run_id
        
        if request.node_id and not checkpoint_id:
            lookup = await find_checkpoint_for_rewind(run_id, request.node_id)
            if lookup:
                target_thread_id, checkpoint_id = lookup
                print(f"🎯 Targeted rewind: Node '{request.node_id}' found in thread '{target_thread_id}' at checkpoint '{checkpoint_id}'")
            else:
                async def error_generator():
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Could not find checkpoint for node {request.node_id}'})}\n\n"
                return StreamingResponse(error_generator(), media_type="text/event-stream")

        # 2. Fork the Target Lineage
        # If target_thread_id != run_id, we need to fork the target thread and link it to a forked master.
        # For our current architecture, we support 2-level surgical rewinds.
        if target_thread_id != run_id:
            print(f"🌳 Recursive Fork: Target is inner thread '{target_thread_id}'")
            new_master_id = await fork_run(run_id)
            new_target_id = await fork_run(target_thread_id, checkpoint_id)
            
            # Map the new master to the new inner thread
            master_config = {"configurable": {"thread_id": new_master_id}}
            await app_graph.aupdate_state(master_config, {"inner_thread_id": new_target_id})
            
            final_run_id = new_master_id
            target_thread_fork_id = new_target_id
        else:
            new_run_id = await fork_run(run_id, checkpoint_id)
            final_run_id = new_run_id
            target_thread_fork_id = new_run_id
            
        target_config = {"configurable": {"thread_id": target_thread_fork_id}}
        new_master_config = {"configurable": {"thread_id": final_run_id}}

        # 3. Apply Node-Specific Invalidation
        if request.node_id:
            from api.history import get_nodes_to_invalidate
            nodes_to_clear = await get_nodes_to_invalidate(target_thread_id, request.node_id)
            print(f"🔄 Invalidating {len(nodes_to_clear)} results in {target_thread_fork_id}")
            
            # Clear results in the NEW thread
            clear_vals = {"results": {node: None for node in nodes_to_clear}}
            await app_graph.aupdate_state(target_config, clear_vals)

        # 4. Apply Modifications
        if request.modifications:
            print(f"✏️ Applying modifications to {target_thread_fork_id}: {request.modifications}")
            
            if "new_instruction" in request.modifications and request.node_id:
                state = await app_graph.aget_state(target_config)
                if state and state.values:
                    graph_plan = dict(state.values.get("graph_plan", {}))
                    nodes = list(graph_plan.get("nodes", []))
                    for i, node in enumerate(nodes):
                        if node.get("id") == request.node_id:
                            nodes[i] = dict(node)
                            nodes[i]["instruction"] = request.modifications["new_instruction"]
                            print(f"🎯 SURGICAL UPDATE: Instruction for '{request.node_id}' updated")
                            break
                    graph_plan["nodes"] = nodes
                    request.modifications["graph_plan"] = graph_plan
                    del request.modifications["new_instruction"]

            await app_graph.aupdate_state(target_config, request.modifications)
            
        # 5. Helper to stream events
        async def event_generator():
            yield f"data: {json.dumps({'type': 'start', 'run_id': final_run_id, 'forked_from': run_id})}\n\n"
            
            try:
                async for event in app_graph.astream_events(None, config=new_master_config, version="v2"):
                    kind = event.get("event")
                    name = event.get("name")
                    
                    if kind == "on_chain_start" and name in ["graph_executor", "human_review_trigger", "synthesizer"]:
                        display_names = {
                            "graph_executor": "Resuming execution graph...",
                            "human_review_trigger": "Evaluating results confidence...",
                            "synthesizer": "Synthesizing final report...",
                        }
                        msg = display_names.get(name, f"Executing {name}...")
                        yield f"data: {json.dumps({'type': 'progress', 'message': msg})}\n\n"

                # Post-stream State Check
                final_state = await app_graph.aget_state(new_master_config)
                if final_state.next:
                    interrupt_payload = {}
                    if final_state.tasks:
                        task_interrupts = final_state.tasks[0].interrupts
                        if task_interrupts:
                            interrupt_payload = task_interrupts[0] if isinstance(task_interrupts[0], dict) else {}
                    
                    yield "data: " + json.dumps({
                        'type': 'interrupt', 
                        'next': list(final_state.next), 
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
                    synthesis = final_state.values.get("synthesis", "")
                    all_agents = final_state.values.get("all_agents", [])
                    all_edges = final_state.values.get("all_edges", [])
                    
                    if all_agents:
                        yield f"data: {json.dumps({'type': 'unified_graph', 'agents': all_agents, 'edges': all_edges})}\n\n"
                    if synthesis:
                        yield f"data: {json.dumps({'type': 'synthesis', 'markdown': synthesis})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"

            except Exception as e:
                print(f"Error in fork stream: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")


    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

from schemas.resume_value import ResumeValue

@app.post("/api/run/{run_id}/resume")
async def resume_run(run_id: str, request: ResumeValue):
    """
    Resume an interrupted execution using standardized ResumeValue.
    """
    print(f"🔄 Resuming task {run_id} with action: {request.action}")

    async def event_generator():
        config = {"configurable": {"thread_id": run_id}}
        
        # Build the resume value - simply dump the model
        resume_value = request.model_dump()
            # User provided a manual fix
        print(f"📝 Resume value: {resume_value}")

        latest_state = {}
        
        try:
            # Use Command(resume=value) to pass the user's decision to the interrupted node
            from langgraph.types import Command
            
            # CRITICAL FIX: When there are multiple pending interrupts (e.g., nested graphs),
            # we must provide a dict mapping interrupt IDs to resume values.
            # Query the graph state to extract all interrupt IDs.
            graph_state = await app_graph.aget_state(config)
            
            # 🔍 [Interrupt Debug] Log resume attempt details
            print(f"🔍 [Interrupt Debug] Resume attempt for run_id: {run_id}")
            print(f"   - Action: {request.action}")
            print(f"   - Resume value: {resume_value}")
            
            interrupt_ids = []
            if graph_state.tasks:
                for task in graph_state.tasks:
                    if task.interrupts:
                        for interrupt_obj in task.interrupts:
                            if hasattr(interrupt_obj, 'id'):
                                interrupt_ids.append(interrupt_obj.id)
                                print(f"   - Found interrupt ID: {interrupt_obj.id}")
            
            # Extract inner_thread_id from interrupt payload for state update
            inner_thread_id = None
            if graph_state.tasks:
                for task in graph_state.tasks:
                    if task.interrupts:
                        for interrupt_obj in task.interrupts:
                            # Get the interrupt value which contains inner_thread_id
                            if hasattr(interrupt_obj, 'value') and isinstance(interrupt_obj.value, dict):
                                inner_thread_id = interrupt_obj.value.get('inner_thread_id')
                                if inner_thread_id:
                                    print(f"   - Found inner_thread_id in interrupt: {inner_thread_id}")
                                    break
                    if inner_thread_id:
                        break
            
            # Build state update dict - include inner_thread_id if found
            state_update = {}
            if inner_thread_id:
                state_update["inner_thread_id"] = inner_thread_id
                print(f"📌 Including inner_thread_id in resume update: {inner_thread_id}")
            
            # If multiple interrupts exist, map the resume value to each interrupt ID
            if len(interrupt_ids) > 1:
                print(f"🔀 Multiple interrupts detected ({len(interrupt_ids)}). Mapping resume value to all interrupt IDs.")
                print(f"🔍 [Interrupt Debug] Interrupt IDs: {interrupt_ids}")
                resume_payload = {iid: resume_value for iid in interrupt_ids}
                resume_command = Command(resume=resume_payload, update=state_update) if state_update else Command(resume=resume_payload)
            elif len(interrupt_ids) == 1:
                # Single interrupt - can use simple resume value
                print(f"✅ Single interrupt detected. Using simple resume value.")
                print(f"🔍 [Interrupt Debug] Interrupt ID: {interrupt_ids[0]}")
                resume_command = Command(resume=resume_value, update=state_update) if state_update else Command(resume=resume_value)
            else:
                # No interrupts found - this shouldn't happen, but handle gracefully
                print(f"⚠️ No interrupts found in graph state. Attempting simple resume.")
                resume_command = Command(resume=resume_value, update=state_update) if state_update else Command(resume=resume_value)
            
            # Remove from interrupt registry on resume
            if run_id in interrupt_registry:
                del interrupt_registry[run_id]
                print(f"🔍 [Interrupt Debug] Removed run_id {run_id} from interrupt registry")
            
            # Resume the graph by streaming with the Command as input
            async for event in app_graph.astream_events(resume_command, config=config, version="v2"):
                kind = event.get("event")
                name = event.get("name")
                
                if kind in ["on_chain_end", "on_node_end"]:
                    output = event.get("data", {}).get("output")
                    if output and isinstance(output, dict):
                        latest_state.update(output)
                        
                        # Accumulate usage stats from CostTracker (same as initial run)
                        tracker = CostTracker.get_instance()
                        real_stats = tracker.to_usage_stats(task_id=run_id)
                        
                        # Initialize if not exists
                        if run_id not in cumulative_usage_registry:
                            cumulative_usage_registry[run_id] = {
                                "cost": 0.0,
                                "input_tokens": 0,
                                "output_tokens": 0,
                                "llm_calls": 0,
                                "tool_calls": 0,
                                "steps": 0,
                                "cached_tokens": 0
                            }
                        
                        # Update cumulative totals
                        cumulative_usage_registry[run_id]["cost"] = real_stats.get("cost", 0)
                        cumulative_usage_registry[run_id]["input_tokens"] = real_stats.get("input_tokens", 0)
                        cumulative_usage_registry[run_id]["output_tokens"] = real_stats.get("output_tokens", 0)
                        cumulative_usage_registry[run_id]["llm_calls"] = real_stats.get("llm_calls", 0)
                        cumulative_usage_registry[run_id]["tool_calls"] = real_stats.get("tool_calls", 0)
                        cumulative_usage_registry[run_id]["steps"] = real_stats.get("steps", 0)
                        cumulative_usage_registry[run_id]["cached_tokens"] = real_stats.get("cached_tokens", 0)
                        
                        # Emit cumulative stats
                        yield f"data: {json.dumps({'type': 'usage_stats', 'stats': cumulative_usage_registry[run_id]})}\n\n"

                if kind == "on_chain_start" and name in ["graph_executor", "synthesizer"]:
                    display_names = {
                        "graph_executor": "Resuming execution graph...",
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
                
                # CRITICAL FIX: Always emit cumulative usage stats from registry
                # This ensures UI gets the total cost even if no new nodes executed
                if run_id in cumulative_usage_registry:
                    print(f"📊 Emitting final cumulative stats: ${cumulative_usage_registry[run_id]['cost']:.6f}")
                    yield f"data: {json.dumps({'type': 'usage_stats', 'stats': cumulative_usage_registry[run_id]})}\n\n"
                
                
                if all_agents:
                    print(f"📡 Emitting unified_graph: {len(all_agents)} agents")
                    yield f"data: {json.dumps({'type': 'unified_graph', 'agents': all_agents, 'edges': all_edges})}\n\n"
                    
                if synthesis:
                    print(f"📡 Emitting synthesis report ({len(synthesis)} chars)")
                    yield f"data: {json.dumps({'type': 'synthesis', 'markdown': synthesis})}\n\n"
                    
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
                # Task completed successfully - cleanup cumulative registry
                if run_id in cumulative_usage_registry:
                    print(f"✅ Task {run_id} completed. Final cumulative cost: ${cumulative_usage_registry[run_id]['cost']:.6f}")
                    # Keep the stats for a short time in case UI needs to re-fetch
                    # Actual cleanup can happen in a background task or after a timeout

        except Exception as e:
            print(f"Error in resume_generator: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- INTERRUPT MANAGEMENT ENDPOINTS (Recommendation #3) ---

@app.post("/api/run/{run_id}/cancel")
async def cancel_interrupt(run_id: str):
    """Cancel a pending interrupt and abort execution."""
    print(f"🛑 Cancel request for run_id: {run_id}")
    
    config = {"configurable": {"thread_id": run_id}}
    
    try:
        graph_state = await app_graph.aget_state(config)
        if not graph_state.next:
            return {"status": "error", "message": "No active interrupt found"}
        
        if run_id in interrupt_registry:
            del interrupt_registry[run_id]
        
        # Also cleanup cumulative usage registry on abort
        if run_id in cumulative_usage_registry:
            del cumulative_usage_registry[run_id]
            print(f"🧹 Cleaned up cumulative usage stats for aborted run {run_id}")
        
        from langgraph.types import Command
        abort_value = {"action": "abort", "reasoning": "Cancelled by user"}
        
        interrupt_ids = []
        if graph_state.tasks:
            for task in graph_state.tasks:
                if task.interrupts:
                    for interrupt_obj in task.interrupts:
                        if hasattr(interrupt_obj, 'id'):
                            interrupt_ids.append(interrupt_obj.id)
        
        if len(interrupt_ids) > 1:
            resume_payload = {iid: abort_value for iid in interrupt_ids}
            await app_graph.ainvoke(Command(resume=resume_payload), config=config)
        else:
            await app_graph.ainvoke(Command(resume=abort_value), config=config)
        
        return {"status": "success", "message": "Interrupt cancelled"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/run/{run_id}/interrupt/status")
async def get_interrupt_status(run_id: str):
    """Query the status of an interrupt."""
    config = {"configurable": {"thread_id": run_id}}
    
    try:
        graph_state = await app_graph.aget_state(config)
        has_interrupt = bool(graph_state.next)
        interrupt_data = interrupt_registry.get(run_id)
        
        if not has_interrupt and not interrupt_data:
            return {"status": "success", "active": False}
        
        elapsed_time = 0
        timeout_remaining = None
        if interrupt_data:
            elapsed_time = time.time() - interrupt_data["timestamp"]
            timeout_remaining = max(0, INTERRUPT_TIMEOUT_SECONDS - elapsed_time)
        
        return {
            "status": "success",
            "active": has_interrupt,
            "interrupt_type": interrupt_data.get("interrupt_type", "unknown") if interrupt_data else "unknown",
            "confidence_score": interrupt_data.get("confidence_score", 0.0) if interrupt_data else 0.0,
            "paused_at": interrupt_data.get("paused_at", []) if interrupt_data else list(graph_state.next),
            "elapsed_time": elapsed_time,
            "timeout_remaining": timeout_remaining
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
