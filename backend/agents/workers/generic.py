from langchain_core.messages import SystemMessage, HumanMessage
from agents.dependencies import llm, llm_mini
from langchain_core.runnables import RunnableConfig
import re
import time
import json

async def evaluate_confidence(instruction: str, output: str, config: RunnableConfig = None) -> dict:
    """
    Uses the LLM to evaluate the quality and confidence of an agent's output.
    Returns a dict with 'confidence_score' (0.0-1.0) and 'confidence_reasoning'.
    """
    evaluation_prompt = f"""Evaluate how well the following output addresses the given instruction.
    
<instruction>
{instruction}
</instruction>

<output>
{output[:2000]}  # Truncated for evaluation
</output>

Rate the output on a scale of 0.0 to 1.0 based on:
- Completeness: Does it fully address all parts of the instruction?
- Accuracy: Is the information reliable and not vague?
- Relevance: Is the content directly related to the instruction?

Respond with ONLY a JSON object, no other text:
{{"confidence_score": 0.X, "reasoning": "Brief explanation"}}
"""
    try:
        messages = [
            SystemMessage(content="You are a quality evaluator. Output ONLY valid JSON."),
            HumanMessage(content=evaluation_prompt)
        ]
        if config:
            response = await llm_mini.ainvoke(messages, config=config)
        else:
            response = await llm_mini.ainvoke(messages)
        
        # Parse JSON from response
        content = response.content.strip()
        # Handle potential markdown code blocks
        if "```" in content:
            content = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
            content = content.group(1) if content else "{}"
        
        result = json.loads(content)
        return {
            "confidence_score": float(result.get("confidence_score", 0.5)),
            "confidence_reasoning": result.get("reasoning", "Unable to evaluate")
        }
    except Exception as e:
        print(f"⚠️ Confidence evaluation failed: {e}")
        return {"confidence_score": 0.5, "confidence_reasoning": f"Evaluation error: {str(e)}"}

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

from agents.tools.web_search import web_search
from agents.tools.python_repl import python_repl
from agents.self_correct import simple_self_correct
from langgraph.types import interrupt

async def generic_worker_node(state: dict, instruction: str, agent_type: str, config: RunnableConfig = None) -> dict:
    """
    A generic worker that uses the LLM to perform a task.
    Supports tool calling for recursive subgraphs.
    Includes 3-Tier Escalation Protocol:
    - Tier 1: Autonomous Self-Correction (Retry).
    - Tier 2: Soft Flag (Metadata).
    - Tier 3: Hard Stop (Interrupt).
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
        # Note: Orchestrator no longer uses spawn_subgraph - recursion is now via supervisor planning
        tools = []
        start_time = time.time()
        tool_used = None
        
        if agent_type.lower() == "researcher":
            tools = [web_search]
        elif agent_type.lower() == "coder":
            tools = [python_repl]
        # Orchestrator has no tools - recursion is handled via recursive nodes in graph_compiler
            
        llm_with_tools = llm.bind_tools(tools) if tools else llm
        
        # Pass config to LLM
        if config:
            response = await llm_with_tools.ainvoke(messages, config=config)
        else:
            response = await llm_with_tools.ainvoke(messages)
        
        final_output = ""
        tools_available = []
        
        # Check for tool calls
        if response.tool_calls:
            tool_call = response.tool_calls[0]
            tool_name = tool_call["name"]
            print(f"🛠️ Tool Call Detected: {tool_name}")
            tool_used = tool_name
            tools_available = [tool_name]
            
            if tool_name == "web_search":
                tool_args = tool_call["args"]
                original_query = tool_args["query"]
                
                if config:
                     tool_output = await web_search.ainvoke(original_query, config=config)
                else:
                     tool_output = await web_search.ainvoke(original_query)
                
                # Auto-refinement when Missing: metadata detected
                if "[SEARCH_METADATA]" in tool_output:
                    missing_match = re.search(r'Missing terms not found.*?:\s*([^\n]+)', tool_output)
                    if missing_match:
                        missing_terms = missing_match.group(1).strip()
                        subject = state.get("subject", "")
                        refined_query = f"{subject} {missing_terms} retailers brands companies stores"
                        print(f"🔄 Auto-refining search for missing terms: {missing_terms}")
                        
                        if config:
                            refined_output = await web_search.ainvoke(refined_query, config=config)
                        else:
                            refined_output = await web_search.ainvoke(refined_query)
                        
                        tool_output += f"\n\n[REFINED SEARCH for: {missing_terms}]\n{refined_output}"
                
                final_output = f"Search Results:\n{tool_output}"
            
            elif tool_name == "python_repl":
                tool_args = tool_call["args"]
                if config:
                    tool_output = await python_repl.ainvoke(tool_args, config=config)
                else:
                    tool_output = await python_repl.ainvoke(tool_args)

                final_output = f"Python Execution:\n{tool_output}"

        else:
            # No tool call - direct LLM response
            if agent_type.lower() == "researcher":
                tools_available = ["web_search"]
            elif agent_type.lower() == "coder":
                tools_available = ["python_repl"]
            final_output = response.content

        execution_time = time.time() - start_time
        
        # --- TIER 1: CONFIDENCE CHECK & SELF-CORRECTION ---
        confidence_eval = await evaluate_confidence(instruction, final_output, config)
        confidence_score = confidence_eval["confidence_score"]
        confidence_reasoning = confidence_eval["confidence_reasoning"]
        
        if confidence_score < 0.5:
             # Trigger self-correction
             correction_result = await simple_self_correct(instruction, final_output, confidence_reasoning, agent_type, config)
             final_output = correction_result["output"]
             
             # Re-evaluate confidence
             confidence_eval = await evaluate_confidence(instruction, final_output, config)
             confidence_score = confidence_eval["confidence_score"]
             confidence_reasoning = f"[Self-Corrected] {confidence_eval['confidence_reasoning']}"

        # --- TIER 3: HARD STOP (HITL) ---
        if confidence_score < 0.3:
            print(f"🛑 [HITL] Tier 3 Hard Stop triggered (Confidence: {confidence_score:.2f})")
            
            interrupt_payload = {
                "type": "tier3_interrupt",
                "agent_type": agent_type,
                "confidence_score": confidence_score,
                "current_output": final_output,
                "reasoning": confidence_reasoning,
                "message": f"Critical failure in {agent_type}: Confidence {confidence_score:.2f} is below safety threshold (0.3)."
            }
            
            # ⏸️ PAUSE EXECUTION HERE ⏸️
            # The function will suspend. When resumed, resume_value will contain the user's input.
            resume_value = interrupt(interrupt_payload)
            
            print(f"✅ [HITL] Tier 3 Resumed with: {resume_value}")
            
            # Handle Resume Logic
            if resume_value and isinstance(resume_value, dict):
                # Scenario A: User provided a manual fix
                if "output" in resume_value:
                    final_output = resume_value["output"]
                    confidence_score = 1.0
                    confidence_reasoning = "Manually corrected by user."
                # Scenario B: User said "proceed" (resume_value might be simple action flag) - we keep original output
                
        # --- TIER 2: SOFT FLAG ---
        low_confidence_flag = confidence_score < 0.5

        return {
            "output": final_output,
            "metadata": {
                "system_prompt": sys_prompt,
                "agent_role": agent_type,
                "instruction": instruction,
                "tool_used": tool_used,
                "execution_time_seconds": round(execution_time, 2),
                "depth": current_depth,
                "status": "completed",
                "tools_available": tools_available,
                "confidence_score": confidence_score,
                "confidence_reasoning": confidence_reasoning,
                "low_confidence_flag": low_confidence_flag
            }
        }

    except Exception as e:
        execution_time = time.time() - start_time if 'start_time' in locals() else 0
        return {
            "output": f"Error: {str(e)}",
            "metadata": {
                "system_prompt": sys_prompt if 'sys_prompt' in locals() else "Error generating prompt",
                "agent_role": agent_type,
                "instruction": instruction,
                "tool_used": None,
                "execution_time_seconds": round(execution_time, 2),
                "depth": current_depth if 'current_depth' in locals() else 0,
                "status": "error",
                "error_message": str(e),
                "tools_available": [],
                "confidence_score": 0.0,
                "confidence_reasoning": f"Error during execution: {str(e)}"
            }
        }

