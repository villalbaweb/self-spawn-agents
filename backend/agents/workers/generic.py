from langchain_core.messages import SystemMessage, HumanMessage
from agents.dependencies import llm, llm_mini

async def generate_dynamic_system_prompt(instruction: str, agent_type: str) -> str:
    """
    Generates a personalized system prompt using a faster/cheaper LLM.
    """
    meta_prompt = f"""You are an expert Prompt Engineer.
    Your goal is to create a high-quality system prompt for an AI agent acting as a "{agent_type}".
    
    The user's instruction to the agent is: "{instruction}"
    
    Create a system prompt that STRICTLY follows the "Tagged Prompt" pattern:
    1. <role>: Define the persona, expertise, and behavioral tone.
    2. <objective>: A clear, single-sentence high-level goal.
    3. <constraints>: A checklist of technical, logical, and formatting rules.
    
    You must also instruct the agent that it will receive its input in a <task> tag, and if provided, specific data in an <input_data> tag.
    
    Output ONLY the system prompt text wrapped in the XML tags.
    """
    
    messages = [
        SystemMessage(content="You are a helpful assistant that generates system prompts."),
        HumanMessage(content=meta_prompt)
    ]
    
    response = await llm_mini.ainvoke(messages)
    return response.content

async def generic_worker_node(state: dict, instruction: str, agent_type: str) -> dict:
    """
    A generic worker that uses the LLM to perform a task.
    """
    print(f"🤖 {agent_type} working on: {instruction}")
    
    # Generate dynamic system prompt
    try:
        sys_prompt = await generate_dynamic_system_prompt(instruction, agent_type)
        # Fallback if empty
        if not sys_prompt:
             raise ValueError("Empty system prompt generated")
    except Exception as e:
        print(f"⚠️ Failed to generate dynamic prompt ({e}). Using fallback.")
        sys_prompt = f"""<role>Expert {agent_type}</role>
<objective>Execute the user's instruction with high precision and expertise.</objective>
<constraints>
- Output the result directly.
- Maintain a professional and technical tone.
- Do not include fluff or unnecessary conversational filler.
</constraints>"""

    # print(f"📝 Generated System Prompt:\n{sys_prompt}\n") # Optional: Debug print

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
