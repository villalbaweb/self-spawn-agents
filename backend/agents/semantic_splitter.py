import json
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from agents.dependencies import llm
from agents.state import AgentState

# Define the structured output model
class SubtaskList(BaseModel):
    subtasks: List[str] = Field(..., description="A list of atomic subtasks (max 5) starting with a verb.")

async def semantic_splitter_node(state: AgentState) -> Dict[str, Any]:
    """
    Decompose a high-level task into atomic subtasks using LLM semantics.
    """
    task = state.get("task", "") or state.get("query", "")
    print(f"🧠 Decomposing: {task}")
    
    # improved semantic_splitter agent prompt to follow context_engineering_strategy
    sys_prompt = """<role>Expert Task Decomposer</role>
<objective>Analyze the user's task and break it down into atomic, executable subtasks.</objective>
<constraints>
- Output ONLY a JSON object with a key "subtasks" containing a list of strings.
- Each subtask should start with a verb.
- Max 5 subtasks.
- Keep subtasks concise and clear.
</constraints>
<task>Decompose the input into subtasks.</task>"""

    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=f"<input_data>{task}</input_data>")
    ]

    try:
        # Use structured output for reliability
        structured_llm = llm.with_structured_output(SubtaskList)
        response = await structured_llm.ainvoke(messages)
        return {"subtasks": response.subtasks}
    except Exception as e:
        print(f"❌ Error in semantic_splitter_node: {e}")
        # Fallback or empty list on error
        return {"subtasks": []}
