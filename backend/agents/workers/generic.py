from langchain_core.messages import SystemMessage, HumanMessage
from agents.dependencies import llm, llm_mini, TIER1_THRESHOLD, TIER2_THRESHOLD, TIER3_THRESHOLD
from agents.evaluate_confidence import evaluate_confidence
from langchain_core.runnables import RunnableConfig
from agents.cost import CostTrackingCallback, CostTracker
import re
import time

async def generate_dynamic_system_prompt(instruction: str, agent_type: str, config: RunnableConfig = None, root_task_id: str = None) -> str:
    """
    Generates a personalized system prompt using a faster/cheaper LLM.
    Includes information about available tools based on agent type.
    
    Args:
        instruction: The task instruction to generate a prompt for
        agent_type: Type of agent (orchestrator, researcher, coder)
        config: Optional RunnableConfig with thread_id
        root_task_id: Optional root task ID for cost attribution (overrides config thread_id)
    """
    # Define tool context based on agent type
    tool_context = ""
    if agent_type.lower() == "orchestrator":
        tool_context = """
    
    IMPORTANT - You are a Sub-Orchestrator. Your role is to coordinate a complex sub-task using the full capabilities of the system.
    Break down the task into logical steps and communicate clearly with your parent orchestrator."""
    elif agent_type.lower() == "researcher":
        tool_context = """
    
    IMPORTANT - You have access to the following tool:
    - web_search(query: str): Use this to search for information online."""
    elif agent_type.lower() == "coder":
        tool_context = """
    
    IMPORTANT - You have access to the following tool:
    - python_repl(code: str): Use this to execute Python code for calculations, data processing, or generating outputs.
      The code MUST print results to stdout. Always use this tool when asked to "calculate", "compute", or "write a script"."""

    meta_prompt = f"""<role>Expert Prompt Engineer</role>
<objective>Generate a high-quality system prompt for an AI agent specialized as a "{agent_type}".</objective>

<input_data>
    <target_role_name>
    {agent_type}
    </target_role_name>
    <primary_instruction_content>
    {instruction}
    </primary_instruction_content>
    <available_tools_context>
    {tool_context}
    </available_tools_context>
</input_data>

<constraints>
- **Pattern Compliance**: The output prompt MUST strictly follow the "Tagged Prompt" pattern:
    1. <role>: Define persona/expertise.
    2. <objective>: Single-sentence goal.
    3. <constraints>: Technical/logical rules.
    4. <task>: The trigger for action.
- **Input Handling**: The generated prompt must expect its specific mission in a <task> tag and context in an <input_data> tag.
- **Tool Integration**: If <available_tools_context> is not empty, you MUST write specific constraints on when and how to use those tools.
- **Output Format**: Return the result wrapped in a code block or specific tag for easy extraction.
</constraints>

<task>Analyze the requirements and write the specialized system prompt.</task>"""

    
    messages = [
        SystemMessage(content="You are a helpful assistant that generates system prompts."),
        HumanMessage(content=meta_prompt)
    ]
    
    # Cost tracking for prompt generation
    # Prefer root_task_id for consistent attribution, fall back to config thread_id
    task_id = root_task_id or (config.get("configurable", {}).get("thread_id") if config else None)
    cost_callback = CostTrackingCallback(task_id=task_id, node_name="prompt_generation")
    llm_config: RunnableConfig = {"callbacks": [cost_callback]}
    
    response = await llm_mini.ainvoke(messages, config=llm_config)
    
    # Record to global tracker
    tracker = CostTracker.get_instance()
    for record in cost_callback.records:
        tracker._add_record(record)
        
    return response.content, cost_callback.to_usage_stats()

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
    
    # Extract task_id early for consistent cost attribution across all LLM calls
    # Prefer root_task_id from state (for subgraph attribution), fall back to config thread_id
    task_id = state.get("root_task_id") or (config.get("configurable", {}).get("thread_id") if config else None)
    
    # Initialize usage_stats_update early to avoid UnboundLocalError
    usage_stats_update = {"cost": 0.0, "input_tokens": 0, "output_tokens": 0, "llm_calls": 0}
    
    # Generate dynamic system prompt (keeping existing logic)
    try:
        sys_prompt, prompt_usage = await generate_dynamic_system_prompt(instruction, agent_type, config, root_task_id=task_id)
        if not sys_prompt: raise ValueError("Empty system prompt")
        # Merge prompt generation usage
        for k, v in prompt_usage.items():
            usage_stats_update[k] = usage_stats_update.get(k, 0) + v
    except Exception as e:
        print(f"⚠️ Failed to generate dynamic prompt ({e}). Using fallback.")
        sys_prompt = f"""<role>Expert {agent_type}</role>
<objective>Execute the provided task with maximum precision, adhering to all technical and professional standards.</objective>
<constraints>
- Deliver the result directly without unnecessary conversational filler.
- Maintain a professional and technical tone.
- If the task is unclear, state exactly what information is missing.
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
    
    # Cost tracking setup - reuse task_id extracted earlier for consistent attribution
    cost_callback = CostTrackingCallback(task_id=task_id, node_name=f"worker_{agent_type.lower()}")
    llm_config: RunnableConfig = {"callbacks": [cost_callback]}

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
        
        # Pass cost tracking config to LLM
        response = await llm_with_tools.ainvoke(messages, config=llm_config)
        
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
        # Pass task_id for consistent cost attribution
        confidence_res, val_usage = await evaluate_confidence(instruction, final_output, config, root_task_id=task_id)
        confidence_score = confidence_res["confidence_score"]
        confidence_reasoning = confidence_res["confidence_reasoning"]
        
        # Update usage_stats_update from the primary callback
        primary_usage = cost_callback.to_usage_stats()
        for k, v in primary_usage.items():
            usage_stats_update[k] = usage_stats_update.get(k, 0) + v
        
        # Merge evaluation usage
        for k, v in val_usage.items():
            usage_stats_update[k] = usage_stats_update.get(k, 0) + v
        
        if confidence_score < TIER1_THRESHOLD:
             # Trigger self-correction (Tier 1)
             correction_res = await simple_self_correct(instruction, final_output, confidence_reasoning, agent_type, config, root_task_id=task_id)
             final_output = correction_res["output"]
             
             # Merge correction usage
             for k, v in correction_res.get("usage_stats", {}).items():
                 usage_stats_update[k] = usage_stats_update.get(k, 0) + v
             
             # Re-evaluate confidence
             confidence_res, val_usage2 = await evaluate_confidence(instruction, final_output, config, root_task_id=task_id)
             confidence_score = confidence_res["confidence_score"]
             confidence_reasoning = f"[Self-Corrected] {confidence_res['confidence_reasoning']}"
             
             # Merge usage from second evaluation
             for k, v in val_usage2.items():
                 usage_stats_update[k] = usage_stats_update.get(k, 0) + v

        # --- TIER 3: HARD STOP (HITL) ---
        if confidence_score < TIER3_THRESHOLD:
            print(f"🛑 [HITL] Tier 3 Hard Stop triggered (Confidence: {confidence_score:.2f}, Threshold: {TIER3_THRESHOLD})")
            
            interrupt_payload = {
                "type": "tier3_interrupt",
                "agent_type": agent_type,
                "confidence_score": confidence_score,
                "current_output": final_output,
                "reasoning": confidence_reasoning,
                "message": f"Critical failure in {agent_type}: Confidence {confidence_score:.2f} is below safety threshold ({TIER3_THRESHOLD})."
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
        low_confidence_flag = confidence_score < TIER2_THRESHOLD
        
        # Build warning message if Tier 2 triggered
        warning = None
        if low_confidence_flag:
            warning = f"Low Confidence Warning: {(confidence_score * 100):.0f}% - {confidence_reasoning}"

        # Record costs to global tracker
        tracker = CostTracker.get_instance()
        records = cost_callback.records
        print(f"💰 [worker_{agent_type.lower()}] Callback has {len(records)} records to merge")
        for record in records:
            # Ensure task_id is set before merging
            if not record.task_id:
                record.task_id = task_id
            tracker._add_record(record)
            print(f"💰 [worker_{agent_type.lower()}] Merged record: task_id={record.task_id}, node={record.node_name}, cost=${record.cost_usd:.6f}")
        
        worker_cost = cost_callback.get_total_cost()
        print(f"💰 [worker_{agent_type.lower()}] Total Cost: ${worker_cost:.6f}, Tracker now has {len(tracker.records)} records")

        result_dict = {
            "output": final_output,
            "usage_stats": usage_stats_update,
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
                "low_confidence_flag": low_confidence_flag,
                "cost_usd": worker_cost
            }
        }
        
        if warning:
            result_dict["metadata"]["warning"] = warning
            
        return result_dict

    except (Exception) as e:
        # Check if it's any kind of LangGraph interrupt (which shouldn't be caught)
        from langgraph.errors import GraphBubbleUp
        if isinstance(e, GraphBubbleUp) or "Interrupt" in type(e).__name__:
            raise e
            
        execution_time = time.time() - start_time if 'start_time' in locals() else 0
        
        # Recover partial usage stats even on failure
        final_usage = usage_stats_update if 'usage_stats_update' in locals() else {}
        if 'cost_callback' in locals():
            try:
                cb_usage = cost_callback.to_usage_stats()
                for k, v in cb_usage.items():
                    final_usage[k] = final_usage.get(k, 0) + v
            except:
                pass

        return {
            "output": f"Error: {str(e)}",
            "usage_stats": final_usage,
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

