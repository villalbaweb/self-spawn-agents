from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from config.llm_providers import llm
from core.state.orchestrator_state import AgentState
from core.cost import CostTrackingCallback, CostTracker

from agentguard_sdk.client import verify_with_governance, track_consumption

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

# --- 2. Execution Planner Node Logic ---

async def execution_planner_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Takes atomic subtasks and generates a structured LangGraph execution plan.
    """
    subtasks = state.get("subtasks", [])
    task = state.get("task", "")

    print(f"📋 Planning execution for {len(subtasks)} subtasks...")

    if not subtasks:
        print("⚠️ No subtasks found to plan.")
        return {"graph_plan": {}}

    task_id = config.get("configurable", {}).get("thread_id") if config else None

    # --- AGENTGUARD GOVERNANCE: Semantic Firewall ---
    try:
        print(f"🛡️ [AgentGuard] Verifying intent for execution_planner...")
        verification = await verify_with_governance(
            agent_id="execution_planner",
            input_text="\n".join(subtasks),
            context={"task_id": task_id, "depth": state.get("depth", 0)}
        )
        if verification.get("outcome") == "BLOCK":
            print(f"🛑 [AgentGuard] Blocked by Semantic Firewall: {verification.get('reason')}")
            return {"graph_plan": {}}
    except Exception as e:
        print(f"⚠️ AgentGuard verification failed ({e}). Proceeding without firewall.")

    # Cost tracking setup
    cost_callback = CostTrackingCallback(task_id=task_id, node_name="execution_planner")
    llm_config: RunnableConfig = {"callbacks": [cost_callback]}

    sys_prompt = """<role>System Architect & Orchestrator</role>
<objective>Decompose the provided subtasks into a structured, executable LangGraph plan while maximizing efficiency and adhering to safety constraints.</objective>

<context>
Available Agent Types:
- **Researcher**: Optimized for information retrieval and documentation analysis.
- **Coder**: Specialized in writing, editing, and debugging code.
- **Reviewer**: Provides critical feedback on code quality and logic.
- **Sub-Orchestrator**: Coordinates complex, multi-step tasks via a specialized sub-orchestration pipeline.
</context>

<constraints>
- **Node Limit**: MAXIMUM 3 nodes per plan. Consolidate if necessary.
- **Recursion Limit**: MAX 1 recursive node (`recursive: true`) per plan.
- **Recursion Rule**: Use ONLY for complex features; never for atomic tasks.
- **Output Format**: Return a JSON object with this structure:
  {
    "explanation": "Detailed justification for the graph structure...",
    "nodes": [
      { "id": "node_1", "agent_type": "Coder", "instruction": "...", "dependencies": [], "recursive": false }
    ]
  }
</constraints>

<task>Create a structured GraphPlan for the input_data.</task>"""


    user_content = f"Original Task: {task}\n\nSubtasks:\n" + "\n".join(f"- {s}" for s in subtasks)

    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=f"<input_data>{user_content}</input_data>")
    ]

    try:
        structured_llm = llm.with_structured_output(GraphPlan)
        plan: GraphPlan = await structured_llm.ainvoke(messages, config=llm_config)

        # Record costs to global tracker
        tracker = CostTracker.get_instance()
        for record in cost_callback.records:
            tracker._add_record(record)
        print(f"💰 [supervisor] Cost: ${cost_callback.get_total_cost():.6f}")

        # --- AGENTGUARD GOVERNANCE: Circuit Breaker ---
        try:
            print(f"⚡ [AgentGuard] Recording consumption for task {task_id}...")
            await track_consumption(
                run_id=task_id or "default-run",
                cost=cost_callback.get_total_cost(),
                steps=1,
                depth=state.get("depth", 0)
            )
        except Exception as e:
            print(f"⚠️ AgentGuard consumption tracking failed ({e}). Proceeding.")

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
