from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from agents.dependencies import llm
from agents.state import AgentState

# --- 1. Graph Schema Definition ---

class NodeSchema(BaseModel):
    id: str = Field(..., description="Unique identifier for the node (e.g., 'research_step_1').")
    agent_type: str = Field(..., description="The type of agent needed (e.g., 'Researcher', 'Coder', 'Reviewer').")
    instruction: str = Field(..., description="Specific instruction for this node.")
    dependencies: List[str] = Field(default_factory=list, description="IDs of nodes that must complete before this one starts.")

class GraphPlan(BaseModel):
    nodes: List[NodeSchema] = Field(..., description="List of nodes in the execution graph.")
    explanation: str = Field(..., description="Brief reasoning for this graph structure.")

# --- 2. Supervisor Node Logic ---

async def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """
    Takes atomic subtasks and generates a structured LangGraph plan.
    """
    subtasks = state.get("subtasks", [])
    task = state.get("task", "")
    
    print(f"👷 Supervisor Planning for {len(subtasks)} subtasks...")

    if not subtasks:
        print("⚠️ No subtasks found to plan.")
        return {"graph_plan": {}}

    sys_prompt = """<role>System Architect & Planner</role>
<objective>Map the provided subtasks into a structured execution graph of Agents.</objective>
<context>
You have the following Agent Types available:
- **Researcher**: searches for information, reads docs.
- **Coder**: writes, edits, or debugs code.
- **Reviewer**: critiques code or plans.
- **Orchestrator**: coordinates complex multi-step flows.
</context>
<constraints>
- Output a JSON structure with 'nodes'.
- 'dependencies' should list node IDs that must finish first.
- Create a logical flow (e.g., Research -> Code -> Review).
</constraints>
<task>Create a plan for the user's request based on the subtasks.</task>"""

    user_content = f"Original Task: {task}\n\nSubtasks:\n" + "\n".join(f"- {s}" for s in subtasks)

    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=user_content)
    ]

    try:
        structured_llm = llm.with_structured_output(GraphPlan)
        plan: GraphPlan = await structured_llm.ainvoke(messages)
        
        # Convert pydantic model to dict for state storage
        return {"graph_plan": plan.model_dump()}
        
    except Exception as e:
        print(f"❌ Error in supervisor_node: {e}")
        return {"graph_plan": {}}
