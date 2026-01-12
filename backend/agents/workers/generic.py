from langchain_core.messages import SystemMessage, HumanMessage
from agents.dependencies import llm

async def generic_worker_node(state: dict, instruction: str, agent_type: str) -> dict:
    """
    A generic worker that uses the LLM to perform a task.
    """
    print(f"🤖 {agent_type} working on: {instruction}")
    
    sys_prompt = f"""<role>Expert {agent_type}</role>
<objective>Execute the user's instruction with high precision and expertise.</objective>
<constraints>
- Output the result directly.
- Maintain a professional and technical tone.
- Do not include fluff or unnecessary conversational filler.
</constraints>"""

    user_content = f"""<task>
{instruction}
</task>"""
    
    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=user_content)
    ]
    
    try:
        response = await llm.ainvoke(messages)
        return {"output": response.content}
    except Exception as e:
        return {"output": f"Error: {str(e)}"}
