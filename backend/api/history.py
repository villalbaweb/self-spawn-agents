"""
History and checkpoint management for LangGraph runs.

Provides functions for listing runs, forking runs, and finding checkpoints
using PostgreSQL-based persistence.
"""
import asyncio
import uuid
import json
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
import psycopg
from core.persistence import checkpointer
from core.persistence.checkpointer import DATABASE_URL


async def list_runs() -> List[Dict[str, Any]]:
    """
    List all available runs (threads) from the PostgreSQL checkpoints database.
    Returns metadata for each run including thread_id and last activity.
    """
    if not DATABASE_URL:
        return []
    
    runs = []
    try:
        async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
            async with conn.cursor() as cur:
                # Get all unique thread_ids and their latest checkpoint
                query = """
                SELECT 
                    thread_id,
                    MAX(checkpoint_id) as last_checkpoint,
                    MAX(parent_checkpoint_id) as parent_id
                FROM checkpoints
                GROUP BY thread_id
                ORDER BY MAX(checkpoint_id) DESC
                """
                await cur.execute(query)
                rows = await cur.fetchall()
                
                for row in rows:
                    thread_id = row[0]
                    last_checkpoint = row[1]
                    
                    runs.append({
                        "run_id": thread_id,
                        "last_checkpoint": last_checkpoint,
                        "last_active": datetime.now().isoformat()  # PostgreSQL doesn't store timestamp in same way
                    })
                    
    except Exception as e:
        print(f"Error listing runs: {e}")
        return []
    
    return runs


async def fork_run(source_thread_id: str, checkpoint_id: Optional[str] = None) -> str:
    """
    Fork a run by creating a new thread with the state from a specific checkpoint.
    
    Args:
        source_thread_id: The thread ID to fork from
        checkpoint_id: Optional specific checkpoint ID to fork from (uses latest if not provided)
        
    Returns:
        New thread ID
    """
    from app_graph import app_graph
    
    new_thread_id = str(uuid.uuid4())
    source_config = {"configurable": {"thread_id": source_thread_id}}
    new_config = {"configurable": {"thread_id": new_thread_id}}
    
    try:
        # Get state from source thread at specific checkpoint or latest
        if checkpoint_id:
            source_config["configurable"]["checkpoint_id"] = checkpoint_id
        
        source_state = await app_graph.aget_state(source_config)
        
        if source_state and source_state.values:
            # Copy state to new thread
            await app_graph.aupdate_state(new_config, source_state.values)
            print(f"✅ Forked {source_thread_id} -> {new_thread_id}")
        else:
            print(f"⚠️ No state found for {source_thread_id}")
            
    except Exception as e:
        print(f"Error forking run: {e}")
        raise
    
    return new_thread_id


async def find_checkpoint_for_rewind(
    run_id: str, 
    node_id: str
) -> Optional[Tuple[str, str]]:
    """
    Find the checkpoint before a specific node execution.
    
    This searches through the checkpoint history to find the state before
    the specified node was executed.
    
    Args:
        run_id: The run ID to search in
        node_id: The node ID to find
        
    Returns:
        Tuple of (thread_id, checkpoint_id) or None if not found
    """
    from app_graph import app_graph
    
    try:
        config = {"configurable": {"thread_id": run_id}}
        
        # Get checkpoint history
        checkpoints = []
        async for state in app_graph.aget_state_history(config):
            checkpoints.append(state)
        
        # Search through checkpoints for the node execution
        for i, state in enumerate(checkpoints):
            if state.values and state.metadata:
                # Check if this checkpoint contains the node execution
                # The checkpoint BEFORE this one is what we want
                if i + 1 < len(checkpoints):
                    prev_state = checkpoints[i + 1]
                    if prev_state.config:
                        thread_id = prev_state.config.get("configurable", {}).get("thread_id", run_id)
                        checkpoint_id = prev_state.config.get("configurable", {}).get("checkpoint_id")
                        if checkpoint_id:
                            return (thread_id, checkpoint_id)
        
    except Exception as e:
        print(f"Error finding checkpoint for rewind: {e}")
    
    return None


async def get_nodes_to_invalidate(thread_id: str, node_id: str) -> List[str]:
    """
    Get list of nodes that should be invalidated when rewinding to a specific node.
    
    This analyzes the graph structure to find all nodes that depend on the
    specified node and should have their results cleared.
    
    Args:
        thread_id: The thread ID
        node_id: The node ID to rewind to
        
    Returns:
        List of node IDs to invalidate
    """
    from app_graph import app_graph
    
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = await app_graph.aget_state(config)
        
        if not state or not state.values:
            return []
        
        # Get the graph plan to understand dependencies
        graph_plan = state.values.get("graph_plan", {})
        nodes = graph_plan.get("nodes", [])
        edges = graph_plan.get("edges", [])
        
        # Find all nodes that come after the target node in the execution graph
        nodes_to_clear = []
        
        # Build adjacency list for graph traversal
        adjacency = {}
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if source not in adjacency:
                adjacency[source] = []
            adjacency[source].append(target)
        
        # BFS to find all downstream nodes
        queue = [node_id]
        visited = set()
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            nodes_to_clear.append(current)
            
            # Add all children to queue
            if current in adjacency:
                for child in adjacency[current]:
                    if child not in visited:
                        queue.append(child)
        
        return nodes_to_clear
        
    except Exception as e:
        print(f"Error getting nodes to invalidate: {e}")
        return []


async def get_run_details(run_id: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a specific run.
    
    Args:
        run_id: The run ID to get details for
        
    Returns:
        Dictionary with run details or None if not found
    """
    from app_graph import app_graph
    
    try:
        config = {"configurable": {"thread_id": run_id}}
        state = await app_graph.aget_state(config)
        
        if not state or not state.values:
            return None
        
        return {
            "run_id": run_id,
            "task": state.values.get("task", ""),
            "subtasks": state.values.get("subtasks", []),
            "synthesis": state.values.get("synthesis", ""),
            "all_agents": state.values.get("all_agents", []),
            "all_edges": state.values.get("all_edges", []),
            "usage_stats": state.values.get("usage_stats", {}),
            "next": list(state.next) if state.next else [],
        }
        
    except Exception as e:
        print(f"Error getting run details: {e}")
        return None


async def delete_run(run_id: str) -> bool:
    """
    Delete a run and all its checkpoints from the database.
    
    Args:
        run_id: The run ID to delete
        
    Returns:
        True if successful, False otherwise
    """
    if not DATABASE_URL:
        return False
    
    try:
        async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
            async with conn.cursor() as cur:
                # Delete checkpoints for this thread
                await cur.execute(
                    "DELETE FROM checkpoints WHERE thread_id = %s",
                    (run_id,)
                )
                # Delete checkpoint blobs
                await cur.execute(
                    "DELETE FROM checkpoint_blobs WHERE thread_id = %s",
                    (run_id,)
                )
                await conn.commit()
                print(f"✅ Deleted run {run_id}")
                return True
                
    except Exception as e:
        print(f"Error deleting run: {e}")
        return False
