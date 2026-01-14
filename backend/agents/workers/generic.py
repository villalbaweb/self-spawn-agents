from langchain_core.messages import SystemMessage, HumanMessage
from agents.dependencies import llm, llm_mini
from langchain_core.runnables import RunnableConfig
import re

async def generate_dynamic_system_prompt(instruction: str, agent_type: str, config: RunnableConfig = None) -> str:
    """
    Generates a personalized system prompt using a faster/cheaper LLM.
    Includes information about available tools based on agent type.
    """
    # Define tool context based on agent type
    tool_context = ""
    if agent_type.lower() == "orchestrator":
        tool_context = """
    
    IMPORTANT - You have access to the following tool:
    - spawn_subgraph(task: str): Use this tool when YOUR assigned task is too complex to complete in a single response. 
      It will spawn a separate workflow to handle that sub-problem. Only use this if the task genuinely requires 
      multiple coordinated steps that you cannot do alone."""
    elif agent_type.lower() == "researcher":
        tool_context = """
    
    IMPORTANT - You have access to the following tool:
    - web_search(query: str): Use this to search for information online."""
    elif agent_type.lower() == "coder":
        tool_context = """
    
    IMPORTANT - You have access to the following tool:
    - python_repl(code: str): Use this to execute Python code for calculations, data processing, or generating outputs.
      The code MUST print results to stdout. Always use this tool when asked to "calculate", "compute", or "write a script"."""

    meta_prompt = f"""You are an expert Prompt Engineer.
    Your goal is to create a high-quality system prompt for an AI agent acting as a "{agent_type}".
    
    The user's instruction to the agent is: "{instruction}"
    {tool_context}
    
    Create a system prompt that STRICTLY follows the "Tagged Prompt" pattern:
    1. <role>: Define the persona, expertise, and behavioral tone.
    2. <objective>: A clear, single-sentence high-level goal.
    3. <constraints>: A checklist of technical, logical, and formatting rules. If tools are available, include when to use them.
    
    You must also instruct the agent that it will receive its input in a <task> tag, and if provided, specific data in an <input_data> tag.
    
    Output ONLY the system prompt text wrapped in the XML tags.
    """
    
    messages = [
        SystemMessage(content="You are a helpful assistant that generates system prompts."),
        HumanMessage(content=meta_prompt)
    ]
    
    # Pass config if provided
    if config:
        response = await llm_mini.ainvoke(messages, config=config)
    else:
        response = await llm_mini.ainvoke(messages)
        
    return response.content

from agents.tools.subgraph import spawn_subgraph
from agents.tools.web_search import web_search
from agents.tools.python_repl import python_repl

async def generic_worker_node(state: dict, instruction: str, agent_type: str, config: RunnableConfig = None) -> dict:
    """
    A generic worker that uses the LLM to perform a task.
    Supports tool calling for recursive subgraphs.
    """
    print(f"🤖 {agent_type} working on: {instruction}")
    
    # Generate dynamic system prompt (keeping existing logic)
    try:
        sys_prompt = await generate_dynamic_system_prompt(instruction, agent_type, config)
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
        elif agent_type.lower() == "coder":
            tools = [python_repl]
            
        llm_with_tools = llm.bind_tools(tools) if tools else llm
        
        # Pass config to LLM
        if config:
            response = await llm_with_tools.ainvoke(messages, config=config)
        else:
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
                
                if config:
                    tool_output = await spawn_subgraph.ainvoke(tool_args, config=config)
                else:
                    tool_output = await spawn_subgraph.ainvoke(tool_args)
                
                # Check if depth limit was hit - if so, complete task directly
                if "DEPTH LIMIT REACHED" in tool_output:
                    print("🔄 Depth limit hit. Completing task directly without delegation...")
                    # Re-invoke LLM without tools to force direct completion
                    if config:
                        direct_response = await llm.ainvoke(messages, config=config)
                    else:
                        direct_response = await llm.ainvoke(messages)
                        
                    return {
                        "output": f"[Completed directly due to depth limit]\n{direct_response.content}",
                        "metadata": {
                            "system_prompt": sys_prompt,
                            "agent_role": agent_type,
                            "instruction": instruction
                        }
                    }
                
                return {
                    "output": f"Recursion Result:\n{tool_output}",
                    "metadata": {
                        "system_prompt": sys_prompt,
                        "agent_role": agent_type,
                        "instruction": instruction
                    }
                }
                
            elif tool_call["name"] == "web_search":
                tool_args = tool_call["args"]
                original_query = tool_args["query"]
                
                # web_search might be a Tool, lets try ainvoke with config
                # If it fails, we fall back to run, but standard tools support ainvoke
                if config:
                     tool_output = await web_search.ainvoke(original_query, config=config)
                else:
                     tool_output = await web_search.ainvoke(original_query)
                
                # OPTIMIZATION 2: Auto-refinement when Missing: metadata detected
                if "[SEARCH_METADATA]" in tool_output:
                    missing_match = re.search(r'Missing terms not found.*?:\s*([^\n]+)', tool_output)
                    if missing_match:
                        missing_terms = missing_match.group(1).strip()
                        # Extract subject from state if available
                        subject = state.get("subject", "")
                        
                        # Generate refined query with missing terms
                        refined_query = f"{subject} {missing_terms} retailers brands companies stores"
                        print(f"🔄 Auto-refining search for missing terms: {missing_terms}")
                        
                        # Execute refined search
                        if config:
                            refined_output = await web_search.ainvoke(refined_query, config=config)
                        else:
                            refined_output = await web_search.ainvoke(refined_query)
                        
                        # Append refined results
                        tool_output += f"\n\n[REFINED SEARCH for: {missing_terms}]\n{refined_output}"
                
                return {
                    "output": f"Search Results:\n{tool_output}",
                    "metadata": {
                        "system_prompt": sys_prompt,
                        "agent_role": agent_type,
                        "instruction": instruction
                    }
                }
            
            elif tool_call["name"] == "python_repl":
                tool_args = tool_call["args"]
                if config:
                    tool_output = await python_repl.ainvoke(tool_args, config=config)
                else:
                    tool_output = await python_repl.ainvoke(tool_args)

                return {
                    "output": f"Python Execution:\n{tool_output}",
                    "metadata": {
                        "system_prompt": sys_prompt,
                        "agent_role": agent_type,
                        "instruction": instruction
                    }
                }
        
        return {
            "output": response.content,
            "metadata": {
                "system_prompt": sys_prompt,
                "agent_role": agent_type,
                "instruction": instruction
            }
        }
    except Exception as e:
        return {
            "output": f"Error: {str(e)}",
            "metadata": {
                "system_prompt": "Error generating prompt",
                "agent_role": agent_type,
                "instruction": instruction
            }
        }
