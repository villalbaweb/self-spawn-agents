import json
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from agents.dependencies import llm
from agents.state import AgentState
from agents.cost import CostTrackingCallback, CostTracker

# Define the structured output model
class SubtaskList(BaseModel):
    subject: str = Field(..., description="The primary subject/product mentioned in the task (e.g., 'luxury e-bikes', 'cooking blog')")
    subtasks: List[str] = Field(..., description="A list of atomic subtasks (max 5) starting with a verb.")
    deliverables: List[str] = Field(default_factory=list, description="Explicit outputs requested (e.g., 'Marketing Roadmap', 'Executive Summary PDF', 'Python script')")

async def semantic_splitter_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Decompose a high-level task into atomic subtasks using LLM semantics.
    Also extracts the primary subject and required deliverables.
    """
    task = state.get("task", "") or state.get("query", "")
    print(f"🧠 Decomposing: {task}")
    
    # Cost tracking setup
    task_id = config.get("configurable", {}).get("thread_id") if config else None
    cost_callback = CostTrackingCallback(task_id=task_id, node_name="semantic_splitter")
    llm_config: RunnableConfig = {"callbacks": [cost_callback]}
    
    # Improved prompt with subject and deliverables extraction + search optimization
    sys_prompt = """<role>Expert Task Decomposer</role>
<objective>Analyze the user's task, extract the primary subject, required deliverables, and break it down into atomic subtasks optimized for information retrieval.</objective>
<constraints>
- Output a JSON object with "subject", "subtasks", and "deliverables".
- CRITICAL: Extract the SPECIFIC subject mentioned in the task (preserve exact terminology).
- Extract EXPLICIT deliverables mentioned in the task (e.g., "PDF", "script", "roadmap", "summary").
- Each subtask should start with a verb.
- Max 5 subtasks.
- SEARCH OPTIMIZATION: Subtasks may be used as search queries. Make them specific and actionable:
  - Include the subject and relevant context (location, industry, etc.) when mentioned in the task
  - Prefer concrete terms (companies, products, examples) over abstract terms (regulations, frameworks)
  - Format as natural questions or search phrases that would return useful results
</constraints>
<task>Decompose the input into actionable subtasks while preserving the specific subject and identifying deliverables.</task>"""

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
            "usage_stats": cost_callback.to_usage_stats()
        }
    except Exception as e:
        print(f"❌ Error in semantic_splitter_node: {e}")
        return {"subtasks": [], "subject": "", "deliverables": [], "usage_stats": {}}
