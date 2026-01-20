import asyncio
import uuid
import json
import aiosqlite
from typing import List, Dict, Optional, Any
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

async def find_checkpoint_for_rewind(run_id: str, node_id: str) -> Optional[str]:
    """
    Find the checkpoint ID representing the state *before* the specified node executed.
    This effectively allows rewinding to the moment before 'node_id' started.
    
    Strategy:
    - Inner nodes (like research_xxx) run within graph_compiler
    - graph_compiler creates an inner_thread_id when it starts
    - We find the checkpoint BEFORE inner_thread_id appeared (before graph_compiler ran)
    - Then validate that node_id is actually an inner node in the final state
    """
    if not shared_memory.memory:
        print("❌ find_checkpoint_for_rewind: memory not initialized")
        return None
        
    config = {"configurable": {"thread_id": run_id, "checkpoint_ns": ""}}
    
    print(f"\n{'='*60}")
    print(f"🔍 CHECKPOINT LOOKUP: Searching for node '{node_id}' in run '{run_id}'")
    print(f"{'='*60}")
    
    # Collect all checkpoints with their channel_values info
    checkpoints = []
    
    async for checkpoint_tuple in shared_memory.memory.alist(config):
        ct_metadata = checkpoint_tuple.metadata or {}
        ct_config = checkpoint_tuple.config or {}
        checkpoint_id = ct_config.get("configurable", {}).get("checkpoint_id", "")
        step = ct_metadata.get("step", 0)
        
        # Get channel_values to check for inner_thread_id
        channel_values = {}
        if hasattr(checkpoint_tuple, 'checkpoint') and checkpoint_tuple.checkpoint:
            channel_values = checkpoint_tuple.checkpoint.get('channel_values', {})
        
        has_inner_thread_id = bool(channel_values.get("inner_thread_id"))
        
        checkpoints.append({
            "checkpoint_id": checkpoint_id,
            "step": step,
            "has_inner_thread_id": has_inner_thread_id,
            "parent_config": checkpoint_tuple.parent_config,
            "channel_values": channel_values,
        })
        
        # Debug: print first few checkpoints
        if len(checkpoints) <= 5:
            print(f"   Checkpoint #{len(checkpoints)}: step={step}, id={checkpoint_id[:16]}...")
            print(f"      has_inner_thread_id: {has_inner_thread_id}")
            if has_inner_thread_id:
                print(f"      inner_thread_id: {channel_values.get('inner_thread_id')}")
    
    print(f"\n📋 Total checkpoints: {len(checkpoints)}")
    
    # Checkpoints are in newest-first order. Reverse to go oldest-first
    checkpoints.reverse()
    
    # Find the checkpoint just before inner_thread_id first appeared
    graph_compiler_start_ckpt = None
    for i, ckpt in enumerate(checkpoints):
        if ckpt["has_inner_thread_id"]:
            # inner_thread_id appeared at this checkpoint
            # The checkpoint before this is when graph_compiler was about to start
            if i > 0:
                prev_ckpt = checkpoints[i - 1]
                graph_compiler_start_ckpt = prev_ckpt["checkpoint_id"]
                print(f"📝 inner_thread_id first appeared at step {ckpt['step']}")
                print(f"   graph_compiler start checkpoint (step before): {graph_compiler_start_ckpt}")
            else:
                # inner_thread_id already present in first checkpoint, use that checkpoint's parent
                if ckpt["parent_config"]:
                    graph_compiler_start_ckpt = ckpt["parent_config"].get("configurable", {}).get("checkpoint_id")
                    print(f"📝 inner_thread_id present from step {ckpt['step']}, using parent")
            break
    
    if not graph_compiler_start_ckpt:
        print(f"❌ Could not find checkpoint before graph_compiler started")
        print(f"{'='*60}\n")
        return None
    
    # Now verify that node_id is actually an inner node
    # Check the latest checkpoint for all_agents and graph_plan
    latest = checkpoints[-1] if checkpoints else None
    if latest and latest["channel_values"]:
        channel_vals = latest["channel_values"]
        
        # Check graph_plan.nodes
        graph_plan = channel_vals.get("graph_plan", {})
        plan_nodes = graph_plan.get("nodes", [])
        plan_node_ids = [n.get("id") for n in plan_nodes]
        print(f"   graph_plan node IDs: {plan_node_ids}")
        
        if node_id in plan_node_ids:
            print(f"✅ FOUND: '{node_id}' is in graph_plan")
            print(f"   Returning checkpoint: {graph_compiler_start_ckpt}")
            print(f"{'='*60}\n")
            return graph_compiler_start_ckpt
        
        # Check all_agents (for nodes from recursive sub-orchestrators)
        all_agents = channel_vals.get("all_agents", [])
        agent_ids = [a.get("id") for a in all_agents]
        print(f"   all_agents IDs: {agent_ids}")
        
        if node_id in agent_ids:
            print(f"✅ FOUND: '{node_id}' is in all_agents")
            print(f"   Returning checkpoint: {graph_compiler_start_ckpt}")
            print(f"{'='*60}\n")
            return graph_compiler_start_ckpt
        
        print(f"❌ Node '{node_id}' NOT found in graph_plan or all_agents")
    else:
        print(f"❌ No latest checkpoint or channel_values available")
    
    print(f"{'='*60}\n")
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

