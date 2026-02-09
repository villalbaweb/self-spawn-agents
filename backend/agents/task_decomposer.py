import json
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from config.llm_providers import llm
from core.state.orchestrator_state import AgentState
from core.cost import CostTrackingCallback, CostTracker

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
    
    # Cost tracking setup
    task_id = config.get("configurable", {}).get("thread_id") if config else None
    cost_callback = CostTrackingCallback(task_id=task_id, node_name="task_decomposer")
    llm_config: RunnableConfig = {"callbacks": [cost_callback]}
    
    # Improved prompt with subject and deliverables extraction + search optimization
    sys_prompt = """<role>Expert Task Decomposer</role>
<objective>Analyze the user's task to extract the primary subject, identify explicit deliverables, and decompose it into atomic, search-optimized subtasks.</objective>

<constraints>
- **Subject**: Extract the SPECIFIC core subject (brand, company, technology, niche). Keep it concise but exact.
- **Subtasks**:
    - Maximum 5 subtasks.
    - Each must start with an actionable verb.
    - SEARCH OPTIMIZATION: Subtasks will be used as search queries. Include relevant context (industry, location) if present.
    - Prefer concrete identifiers over vague instructions.
- **Deliverables**: Identify explicit outputs requested (e.g., "Table", "Python Script", "300-word summary").
- **Reasoning**: Provide a brief justification (Reasoning-to-Result).
- **Output Format**: Return a valid JSON object with this structure:
  {
    "reasoning": "Brief justification...",
    "subject": "Core subject",
    "deliverables": ["List", "of", "items"],
    "subtasks": ["Subtask 1", "Subtask 2"]
  }
</constraints>

<task>Decompose the provided input_data into the structured JSON format.</task>"""


    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=f"<input_data>{task}</input_data>")
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
        
        return {
            "subtasks": response.subtasks, 
            "subject": response.subject, 
            "deliverables": response.deliverables,
            "root_task_id": task_id,
            "usage_stats": cost_callback.to_usage_stats()
        }
    except Exception as e:
        print(f"❌ Error in semantic_splitter_node: {e}")
        return {"subtasks": [], "subject": "", "deliverables": [], "usage_stats": {}}
