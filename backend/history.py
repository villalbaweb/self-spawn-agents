import asyncio
import uuid
import json
import aiosqlite
from typing import List, Dict, Optional, Any, Tuple
from agents import shared_memory 
from agents.shared_memory import CHECKPOINT_DB_PATH

async def list_runs() -> List[Dict[str, Any]]:
    """
    List all available runs (threads) from the checkpoints database.
    Returns specific metadata if available in the latest checkpoint.
    """
    if not CHECKPOINT_DB_PATH:
        return []

    runs = []
    try:
        async with aiosqlite.connect(CHECKPOINT_DB_PATH) as db:
            # Query distinct thread_ids. 
            # Note: This schema assumption is based on standard LangGraph AsyncSqliteSaver
            # It usually has table 'checkpoints' with column 'thread_id'
            try:
                # Get all unique thread_ids and their latest checkpoint_id
                query = """
                SELECT thread_id, MAX(checkpoint_id) as last_active 
                FROM checkpoints 
                GROUP BY thread_id 
                ORDER BY last_active DESC
                """
                async with db.execute(query) as cursor:
                    async for row in cursor:
                        runs.append({
                            "run_id": row[0],
                            "last_active": row[1]
                        })
            except Exception as e:
                print(f"Error querying checkpoints table: {e}")
                # Fallback or empty if table doesn't exist yet
                pass
    except Exception as e:
        print(f"Error connecting to history DB: {e}")
    
    return runs

async def get_run_details(run_id: str) -> Optional[Dict[str, Any]]:
    """Get details for a specific run including its graph state snapshot."""
    if not shared_memory.memory:
        return None
        
    config = {"configurable": {"thread_id": run_id}}
    # Retrieve the latest state
    try:
        # We need to access the internal storage to get the checkpoint
        # But langgraph's memory.aget returns a Checkpoint tuple, not the high level state directly usually
        # To get high level state we usually use graph.aget_state, but we don't have the graph here easily?
        # Actually we can use memory.aget(config)
        
        checkpoint = await shared_memory.memory.aget(config)
        if not checkpoint:
            return None
            
        return {
            "run_id": run_id,
            "metadata": checkpoint.get("metadata", {}),
            # "channel_values": checkpoint.get("channel_values", {}) # This might be raw
        }
    except Exception as e:
        print(f"Error reading run details: {e}")
        return None

async def fork_run(source_run_id: str, checkpoint_id: str = None) -> str:
    """
    Fork a run from a specific point to a new thread.
    Returns the new run_id.
    """
    if not shared_memory.memory:
        raise RuntimeError("Checkpointer not initialized")

    new_run_id = str(uuid.uuid4())
    
    # Configuration for source and destination
    source_config = {"configurable": {"thread_id": source_run_id, "checkpoint_ns": ""}}
    if checkpoint_id:
        source_config["configurable"]["checkpoint_id"] = checkpoint_id
        
    dest_config = {"configurable": {"thread_id": new_run_id, "checkpoint_ns": ""}}

    # 1. Get the source checkpoint
    # Use memory.aget_tuple if available or aget
    # memory.aget returns specific checkpoint data if found
    checkpoint_tuple = await shared_memory.memory.aget_tuple(source_config)
    
    if not checkpoint_tuple or not checkpoint_tuple.checkpoint:
        raise ValueError(f"No checkpoint found for {source_run_id}")

    current_checkpoint = checkpoint_tuple.checkpoint
    current_metadata = checkpoint_tuple.metadata or {}
    
    # 2. Update metadata to link lineage
    new_metadata = current_metadata.copy()
    new_metadata["parent_run_id"] = source_run_id
    new_metadata["forked_from_checkpoint_id"] = checkpoint_tuple.config.get("checkpoint_id")
    
    # 3. Save to new thread
    # We use aput to save the checkpoint to the new thread
    # Note: langgraph checkpoints are immutable, so we write the *same* checkpoint data 
    # but keyed to the new thread.
    
    # For a clean fork, we might want to just rely on the fact that we can start a run with 
    # a specific state. But to make it "resumable" immediately as if it was there, 
    # we inject the state.
    
    await shared_memory.memory.aput(dest_config, current_checkpoint, new_metadata, {})
    
    print(f"🍴 Forked run {source_run_id} -> {new_run_id}")
    return new_run_id

async def find_checkpoint_for_rewind(run_id: str, node_id: str) -> Optional[Tuple[str, str]]:
    """
    Find the (thread_id, checkpoint_id) representing the state *before* the specified node executed.
    
    Strategy:
    1. Check if node_id is in the current thread's graph_plan.
    2. If yes, find the checkpoint before it started.
    3. If no, and there is an inner_thread_id, recurse into that thread.
    """
    if not shared_memory.memory:
        return None
        
    config = {"configurable": {"thread_id": run_id, "checkpoint_ns": ""}}
    print(f"🔍 SEARCHING: Node '{node_id}' in thread '{run_id}'")
    
    # 1. Get latest state to see where we are
    latest_tuple = await shared_memory.memory.aget_tuple(config)
    if not latest_tuple or not latest_tuple.checkpoint:
        return None
        
    checkpoint_vals = latest_tuple.checkpoint.get("channel_values", {})
    graph_plan = checkpoint_vals.get("graph_plan", {})
    plan_nodes = graph_plan.get("nodes", [])
    plan_node_ids = [n.get("id") for n in plan_nodes]
    
    # CASE A: Node is in THIS thread's plan
    if node_id in plan_node_ids:
        print(f"✅ FOUND: '{node_id}' is in plan for '{run_id}'")
        # Find the checkpoint just before this node's name appeared in 'tasks' or before it finished
        # For simplicity in Dynamic Graph, nodes run sequentially in the inner thread.
        # We look for the newest checkpoint where 'node_id' is NOT yet in 'results'.
        
        checkpoints = []
        async for cp in shared_memory.memory.alist(config):
            checkpoints.append(cp)
        
        # Newest first. Find the first checkpoint where the node results don't exist yet
        for cp in checkpoints:
            vals = cp.checkpoint.get("channel_values", {})
            results = vals.get("results", {})
            if node_id not in results:
                # This is a state where the node hasn't finished.
                # Is it the state JUST BEFORE it started?
                # In LangGraph, moving from node A to node B creates a checkpoint.
                return (run_id, cp.config.get("configurable", {}).get("checkpoint_id"))

        # Fallback: earliest checkpoint
        if checkpoints:
            return (run_id, checkpoints[-1].config.get("configurable", {}).get("checkpoint_id"))
            
    # CASE B: Node might be in an INNER thread
    inner_thread_id = checkpoint_vals.get("inner_thread_id")
    if inner_thread_id:
        print(f"⏬ Node not in '{run_id}'. Recursing into inner thread '{inner_thread_id}'")
        return await find_checkpoint_for_rewind(inner_thread_id, node_id)
        
    # CASE C: Node might be a 'graph_compiler' child (Legacy/Branch approach)
    # If the user selected a top-level node but we don't see it in plan_nodes (unlikely)
    # Or if we want to support the 'Branch-Level' as a fallback.
    
    print(f"❌ '{node_id}' not found in '{run_id}' and no more inner threads.")
    return None




async def get_nodes_to_invalidate(run_id: str, target_node_id: str) -> List[str]:
    """
    Get the list of node IDs that need to be invalidated when rewinding to target_node_id.
    This includes the target node and all nodes that depend on it (directly or transitively).
    """
    if not shared_memory.memory:
        return [target_node_id]
    
    config = {"configurable": {"thread_id": run_id, "checkpoint_ns": ""}}
    
    try:
        # Get the graph plan from the latest checkpoint
        latest_state = await shared_memory.memory.aget_tuple(config)
        if not latest_state or not latest_state.checkpoint:
            return [target_node_id]
        
        checkpoint_vals = latest_state.checkpoint.get("channel_values", {})
        graph_plan = checkpoint_vals.get("graph_plan", {})
        nodes = graph_plan.get("nodes", [])
        
        # Build dependency graph
        node_deps = {}
        for node in nodes:
            node_deps[node["id"]] = set(node.get("dependencies", []))
        
        # Find all nodes that depend on target (BFS/DFS)
        to_invalidate = {target_node_id}
        changed = True
        while changed:
            changed = False
            for node_id, deps in node_deps.items():
                if node_id not in to_invalidate:
                    # If any of this node's dependencies are being invalidated, invalidate this too
                    if deps & to_invalidate:
                        to_invalidate.add(node_id)
                        changed = True
        
        result = list(to_invalidate)
        print(f"🔄 Nodes to invalidate for rewind to '{target_node_id}': {result}")
        return result
    except Exception as e:
        print(f"⚠️ Error computing nodes to invalidate: {e}")
        return [target_node_id]

