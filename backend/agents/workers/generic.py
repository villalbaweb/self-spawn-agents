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

from agents.tools.subgraph import spawn_subgraph
from agents.tools.web_search import web_search

async def generic_worker_node(state: dict, instruction: str, agent_type: str) -> dict:
    """
    A generic worker that uses the LLM to perform a task.
    Supports tool calling for recursive subgraphs.
    """
    print(f"🤖 {agent_type} working on: {instruction}")
    
    # Generate dynamic system prompt (keeping existing logic)
    try:
        sys_prompt = await generate_dynamic_system_prompt(instruction, agent_type)
        if not sys_prompt: raise ValueError("Empty system prompt")
    except Exception as e:
        print(f"⚠️ Failed to generate dynamic prompt ({e}). Using fallback.")
        sys_prompt = f"""<role>Expert {agent_type}</role>
<objective>Execute the user's instruction with high precision and expertise.</objective>
<constraints>
- Output the result directly.
- If the task is too complex or requires multiple steps, call the 'spawn_subgraph' tool.
- Maintain a professional and technical tone.
</constraints>"""

    user_content = f"""<task>
{instruction}
</task>"""
    
    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=user_content)
    ]
    
    # Inject depth into tool execution logic if needed
    current_depth = state.get("depth", 0)
    print(f"🤖 [GenericWorker] Processing for {agent_type} with depth {current_depth}")

    try:
        # Bind tools based on agent type
        # STRUCTURAL LIMIT: Only Orchestrator can spawn sub-agents to prevent exponential branching
        tools = []
        
        if agent_type.lower() == "orchestrator":
            tools = [spawn_subgraph]
        elif agent_type.lower() == "researcher":
            tools = [web_search]
        # Coder and Reviewer get no tools - they must complete tasks directly
            
        llm_with_tools = llm.bind_tools(tools) if tools else llm
        
        response = await llm_with_tools.ainvoke(messages)
        
        # Check for tool calls
        if response.tool_calls:
            print(f"🛠️ Tool Call Detected: {response.tool_calls[0]['name']}")
            # Execute tool call manually (simple tool node logic)
            # In a real LangGraph agent we'd let the graph handle this, but here we do a simple linear execution 
            # since generic_worker is a single node wrapped in a function.
            
            tool_call = response.tool_calls[0]
            if tool_call["name"] == "spawn_subgraph":
                tool_args = tool_call["args"]
                
                # INJECT SAFEGUARD: Pass current depth from state to the tool
                tool_args["depth"] = state.get("depth", 0)
                
                tool_output = await spawn_subgraph.ainvoke(tool_args)
                
                # Check if depth limit was hit - if so, complete task directly
                if "DEPTH LIMIT REACHED" in tool_output:
                    print("🔄 Depth limit hit. Completing task directly without delegation...")
                    # Re-invoke LLM without tools to force direct completion
                    direct_response = await llm.ainvoke(messages)
                    return {"output": f"[Completed directly due to depth limit]\n{direct_response.content}"}
                
                return {"output": f"Recursion Result:\n{tool_output}"}
                
            elif tool_call["name"] == "web_search":
                tool_args = tool_call["args"]
                tool_output = web_search.run(tool_args["query"])
                return {"output": f"Search Results:\n{tool_output}"}
        
        return {"output": response.content}
    except Exception as e:
        return {"output": f"Error: {str(e)}"}
