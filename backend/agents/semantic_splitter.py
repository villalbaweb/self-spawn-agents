import json
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from agents.dependencies import llm
from agents.state import AgentState

# Define the structured output model
class SubtaskList(BaseModel):
    subject: str = Field(..., description="The primary subject/product mentioned in the task (e.g., 'luxury e-bikes', 'cooking blog')")
    subtasks: List[str] = Field(..., description="A list of atomic subtasks (max 5) starting with a verb.")

async def semantic_splitter_node(state: AgentState) -> Dict[str, Any]:
    """
    Decompose a high-level task into atomic subtasks using LLM semantics.
    Also extracts the primary subject for drift prevention.
    """
    task = state.get("task", "") or state.get("query", "")
    print(f"🧠 Decomposing: {task}")
    
    # Improved prompt with subject extraction
    sys_prompt = """<role>Expert Task Decomposer</role>
<objective>Analyze the user's task, extract the primary subject, and break it down into atomic subtasks.</objective>
<constraints>
- Output a JSON object with "subject" (the main product/topic) and "subtasks" (list of strings).
- CRITICAL: Extract the SPECIFIC subject (e.g., "luxury e-bikes" NOT "vehicles", "cooking blog" NOT "websites").
- Each subtask should start with a verb.
- Max 5 subtasks.
- Keep subtasks concise and clear.
</constraints>
<task>Decompose the input into subtasks while preserving the specific subject.</task>"""

    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=f"<input_data>{task}</input_data>")
    ]

    try:
        # Use structured output for reliability
        structured_llm = llm.with_structured_output(SubtaskList)
        response = await structured_llm.ainvoke(messages)
        print(f"📌 Extracted Subject: {response.subject}")
        return {"subtasks": response.subtasks, "subject": response.subject}
    except Exception as e:
        print(f"❌ Error in semantic_splitter_node: {e}")
        return {"subtasks": [], "subject": ""}
