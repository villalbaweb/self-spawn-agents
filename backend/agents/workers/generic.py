from langchain_core.messages import SystemMessage, HumanMessage
from agents.dependencies import llm

async def generic_worker_node(state: dict, instruction: str, agent_type: str) -> dict:
    """
    A generic worker that uses the LLM to perform a task.
    """
    print(f"🤖 {agent_type} working on: {instruction}")
    
    sys_prompt = f"Role: You are an expert {agent_type}. Perform the requested task efficiently."
    
    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=instruction)
    ]
    
    try:
        response = await llm.ainvoke(messages)
        return {"output": response.content}
    except Exception as e:
        return {"output": f"Error: {str(e)}"}
