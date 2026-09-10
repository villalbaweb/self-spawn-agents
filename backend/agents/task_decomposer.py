import json
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from config.llm_providers import llm
from core.state.orchestrator_state import AgentState
from core.cost import CostTrackingCallback, CostTracker

from agentguard_sdk.client import verify_with_governance, track_consumption

# Define the structured output model
class SubtaskList(BaseModel):
    subject: str = Field(..., description="The primary subject/product mentioned in the task (e.g., 'luxury e-bikes', 'cooking blog')")
    subtasks: List[str] = Field(..., description="A list of atomic subtasks (max 5) starting with a verb.")
    deliverables: List[str] = Field(default_factory=list, description="Explicit outputs requested (e.g., 'Marketing Roadmap', 'Executive Summary PDF', 'Python script')")
    reasoning: str = Field(..., description="Brief explanation of the decomposition strategy.")

async def task_decomposer_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Decompose a high-level task into atomic subtasks using LLM semantics.
    Also extracts the primary subject and required deliverables.
    """
    task = state.get("task", "") or state.get("query", "")
    print(f"🧠 Decomposing: {task}")

    task_id = config.get("configurable", {}).get("thread_id") if config else None

    # --- AGENTGUARD GOVERNANCE: Semantic Firewall ---
    # Proactively verify intent. The SDK now raises GovernanceException natively on BLOCK.
    await verify_with_governance(
        agent_id="task_decomposer",
        input_text=task,
        context={"task_id": task_id, "depth": state.get("depth", 0)}
    )

    # --- AGENTGUARD GOVERNANCE: Identity Propagation ---
    from utils.governance_utils import governance_context
    with governance_context(agent_id="task_decomposer", run_id=task_id or "default-run"):
        # Cost tracking setup
        cost_callback = CostTrackingCallback(task_id=task_id, node_name="task_decomposer")
        llm_config: RunnableConfig = {"callbacks": [cost_callback]}

        # Enhanced prompt for semantic alignment
        parent_task = state.get("parent_task", "Root Task")
        sys_prompt = f"""<role>Expert Task Decomposer</role>
<objective>Analyze the user's task to extract the primary subject and decompose it into ATOMIC, SEARCH-OPTIMIZED subtasks.</objective>

<context>
- **Parent Task**: {parent_task}
- **Alignment Rule**: Produce subtasks that are semantically distinct from the parent task. Avoid repeating the same high-level objective.
</context>

<constraints>
- **Subject**: Extract the SPECIFIC core subject. Keep it concise but exact.
- **Subtasks**:
    - Maximum 5 subtasks.
    - Each must start with an actionable verb.
    - SEARCH OPTIMIZATION: Include relevant context (industry, location).
    - PREVENT LOOPS: Subtasks must represent concrete progress steps, not just a restatement of the parent task.
- **Deliverables**: Identify explicit outputs requested.
- **Reasoning**: Provide a brief justification.
- **Output Format**: Return a valid JSON object.
</constraints>"""

        messages = [
            SystemMessage(content=sys_prompt),
            HumanMessage(content=f"[RUN_ID: {task_id or 'unknown'}][AGENT: task_decomposer]\n<input_data>{task}</input_data>")
        ]

        try:
            # Use structured output for reliability
            structured_llm = llm.with_structured_output(SubtaskList)
            response = await structured_llm.ainvoke(messages, config=llm_config)
            print(f"📌 Extracted Subject: {response.subject}")
            print(f"📦 Expected Deliverables: {response.deliverables}")

            # Record costs to global tracker
            tracker = CostTracker.get_instance()
            for record in cost_callback.records:
                tracker._add_record(record)
            print(f"💰 [semantic_splitter] Cost: ${cost_callback.get_total_cost():.6f}")

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

            return {
                "subtasks": response.subtasks,
                "subject": response.subject,
                "deliverables": response.deliverables,
                "root_task_id": task_id,
                "usage_stats": cost_callback.to_usage_stats()
            }
        except Exception as e:
            # Re-raise GovernanceException (or wrapped version) for hard stop
            from utils.governance_utils import is_governance_block
            if is_governance_block(e):
                raise e
            print(f"❌ Error in semantic_splitter_node: {e}")
            return {"subtasks": [], "subject": "", "deliverables": [], "usage_stats": {}}
