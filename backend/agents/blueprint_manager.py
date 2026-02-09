"""
Blueprint Manager Agent - Cross-Run Blueprint Caching.

This node queries the KnowledgeService for existing blueprints before
the Execution Planner is invoked, enabling cache hits to skip expensive
LLM planning calls.
"""
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig
from core.state.orchestrator_state import AgentState
from core.knowledge.service import get_knowledge_service


async def blueprint_manager_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Manages blueprint retrieval from semantic long-term memory.
    
    This node acts as a "recall" phase, checking if the system has
    solved a similar task before. If a high-confidence match is found,
    the cached blueprint is loaded into the state, allowing the graph
    to skip the expensive planning step.
    
    Flow:
        1. Extract task description from state
        2. Query KnowledgeService for matching blueprints
        3. If match found (>0.85 similarity):
           - Load cached graph_plan into state
           - Set blueprint_cache_hit = True
        4. If no match:
           - Set blueprint_cache_hit = False
           - Let graph flow to execution_planner
    
    Args:
        state: Current AgentState
        config: Optional RunnableConfig
        
    Returns:
        Dict with graph_plan (if found) and blueprint_cache_hit flag
    """
    task = state.get("task", "")
    
    if not task:
        print("⚠️ [blueprint_manager] No task found in state, skipping cache lookup.")
        return {"blueprint_cache_hit": False}
    
    print(f"🔍 [blueprint_manager] Searching for cached blueprint...")
    
    try:
        knowledge_service = get_knowledge_service()
        cached_blueprint = await knowledge_service.search_blueprint(task)
        
        if cached_blueprint:
            print(f"✅ [blueprint_manager] Cache HIT! Found blueprint with {cached_blueprint.similarity:.2%} similarity.")
            print(f"   Original query: \"{cached_blueprint.task_query[:50]}...\"")
            print(f"   Blueprint ID: {cached_blueprint.id}")
            
            # Load cached graph plan
            return {
                "graph_plan": cached_blueprint.graph_spec,
                "blueprint_cache_hit": True,
                "blueprint_id": cached_blueprint.id,
                "blueprint_similarity": cached_blueprint.similarity
            }
        else:
            print("❌ [blueprint_manager] Cache MISS. No matching blueprint found.")
            return {"blueprint_cache_hit": False}
            
    except Exception as e:
        # Graceful degradation: if cache fails, just proceed with normal planning
        print(f"⚠️ [blueprint_manager] Error during cache lookup: {e}")
        print("   Falling back to normal planning flow...")
        return {"blueprint_cache_hit": False}


async def archive_blueprint_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Archives a successful blueprint for future retrieval.
    
    This node should be called after successful execution to store
    the blueprint in the KnowledgeService for future cache hits.
    
    Args:
        state: Current AgentState with completed execution
        config: Optional RunnableConfig
        
    Returns:
        Dict with archive status
    """
    task = state.get("task", "")
    graph_plan = state.get("graph_plan", {})
    blueprint_cache_hit = state.get("blueprint_cache_hit", False)
    
    # Don't re-archive cached blueprints
    if blueprint_cache_hit:
        print("ℹ️ [archive_blueprint] Skipping archive - this was a cache hit.")
        return {"blueprint_archived": False}
    
    if not task or not graph_plan:
        print("⚠️ [archive_blueprint] Missing task or graph_plan, skipping archive.")
        return {"blueprint_archived": False}
    
    print(f"📦 [archive_blueprint] Archiving successful blueprint...")
    
    try:
        knowledge_service = get_knowledge_service()
        
        # Collect execution metadata
        metadata = {
            "execution_stats": state.get("usage_stats", {}),
            "depth": state.get("depth", 0),
            "subtask_count": len(state.get("subtasks", [])),
        }
        
        blueprint_id = await knowledge_service.archive_blueprint(
            task_description=task,
            blueprint=graph_plan,
            metadata=metadata
        )
        
        print(f"✅ [archive_blueprint] Blueprint archived with ID: {blueprint_id}")
        return {
            "blueprint_archived": True,
            "blueprint_id": blueprint_id
        }
        
    except Exception as e:
        print(f"⚠️ [archive_blueprint] Error archiving blueprint: {e}")
        return {"blueprint_archived": False}
