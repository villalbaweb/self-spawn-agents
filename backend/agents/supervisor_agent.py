from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from agents.dependencies import llm
from agents.state import AgentState
from agents.cost import CostTrackingCallback, CostTracker

# --- 1. Graph Schema Definition ---

class NodeSchema(BaseModel):
    id: str = Field(..., description="Unique identifier for the node (e.g., 'research_step_1').")
    agent_type: str = Field(..., description="The type of agent needed (e.g., 'Researcher', 'Coder', 'Reviewer').")
    instruction: str = Field(..., description="Specific instruction for this node.")
    dependencies: List[str] = Field(default_factory=list, description="IDs of nodes that must complete before this one starts.")
    recursive: bool = Field(default=False, description="If true, this node spawns a full sub-orchestration pipeline for complex multi-step tasks.")

class GraphPlan(BaseModel):
    nodes: List[NodeSchema] = Field(..., description="List of nodes in the execution graph.")
    explanation: str = Field(..., description="Brief reasoning for this graph structure.")

# --- 2. Supervisor Node Logic ---

async def supervisor_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Takes atomic subtasks and generates a structured LangGraph plan.
    """
    subtasks = state.get("subtasks", [])
    task = state.get("task", "")
    
    print(f"👷 Supervisor Planning for {len(subtasks)} subtasks...")

    if not subtasks:
        print("⚠️ No subtasks found to plan.")
        return {"graph_plan": {}}
    
    # Cost tracking setup
    task_id = config.get("configurable", {}).get("thread_id") if config else None
    cost_callback = CostTrackingCallback(task_id=task_id, node_name="supervisor")
    llm_config: RunnableConfig = {"callbacks": [cost_callback]}

    sys_prompt = """<role>System Architect & Planner</role>
<objective>Map the provided subtasks into a structured execution graph of Agents.</objective>
<context>
You have the following Agent Types available:
- **Researcher**: searches for information, reads docs.
- **Coder**: writes, edits, or debugs code.
- **Reviewer**: critiques code or plans.
- **Sub-Orchestrator**: A specialized agent that coordinates a FULL sub-orchestration pipeline for complex multi-step tasks.

Each node in the graph can be a regular agent or a **Sub-Orchestrator** (by setting `recursive: true`).
</context>
<constraints>
- Output a JSON structure with 'nodes'.
- 'dependencies' should list node IDs that must finish first.
- Create a logical flow (e.g., Research -> Code -> Review).
- IMPORTANT: Limit the graph to a MAXIMUM of 3 nodes to prevent resource explosion.
- If more than 3 subtasks exist, consolidate them into 3 or fewer logical groups.
</constraints>
<recursive_guidance>
Use `recursive: true` (Sub-Orchestrator agent) ONLY when a subtask genuinely requires MULTI-STEP ORCHESTRATION (e.g., "build an API" needs research, coding, testing).
DO NOT use recursive for:
- Simple research tasks (use Researcher)
- Single coding tasks (use Coder)
- Reviews (use Reviewer)

SAFEGUARDS:
- Maximum 1 recursive node per plan to prevent explosion.
- The Sub-Orchestrator will stay focused on its specific subtask.
- Prefer simpler agent types unless complexity truly requires orchestration.
</recursive_guidance>
<task>Create a plan for the user's request based on the subtasks.</task>"""

    user_content = f"Original Task: {task}\n\nSubtasks:\n" + "\n".join(f"- {s}" for s in subtasks)

    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=user_content)
    ]

    try:
        structured_llm = llm.with_structured_output(GraphPlan)
        plan: GraphPlan = await structured_llm.ainvoke(messages, config=llm_config)
        
        # Record costs to global tracker
        tracker = CostTracker.get_instance()
        for record in cost_callback.records:
            tracker._add_record(record)
        print(f"💰 [supervisor] Cost: ${cost_callback.get_total_cost():.6f}")
        
        # Add Supervisor to visualization
        supervisor_agent = {
            "id": "supervisor",
            "role": "Orchestrator",
            "instruction": task,
            "output": f"Planned {len(plan.nodes)} nodes: {', '.join(n.id for n in plan.nodes)}",
            "tools": [],
            "depth": state.get("depth", 0),
            "status": "completed",
            "execution_time_seconds": 0.0 # Placeholder
        }
        
        # Convert pydantic model to dict for state storage
        return {
            "graph_plan": plan.model_dump(),
            "usage_stats": cost_callback.to_usage_stats(),
            "all_agents": [supervisor_agent]
        }
        
    except Exception as e:
        print(f"❌ Error in supervisor_node: {e}")
        return {"graph_plan": {}, "usage_stats": cost_callback.to_usage_stats()}
