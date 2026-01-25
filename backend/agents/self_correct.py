from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from agents.dependencies import llm, TIER1_THRESHOLD
from agents.cost import CostTrackingCallback, CostTracker

async def simple_self_correct(instruction: str, output: str, previous_reasoning: str, agent_type: str, config: RunnableConfig = None, root_task_id: str = None) -> Dict[str, str]:
    """
    Tier 1: Autonomous Self-Correction.
    Asks the agent to critique and refine its own output based on low confidence.
    
    Args:
        instruction: The original instruction
        output: The previous output that had low confidence
        previous_reasoning: The reasoning for the low confidence
        agent_type: Type of agent (Researcher, Coder, etc.)
        config: Optional RunnableConfig
        root_task_id: Optional root task ID for cost attribution
    """
    print(f"🔄 [AITL] Tier 1 Self-Correction triggered for {agent_type}")
    
    correction_prompt = f"""You previously attempted to answer the following instruction but evaluated your own confidence as LOW (< {TIER1_THRESHOLD}).
    
<instruction>
{instruction}
</instruction>

<previous_output>
{output}
</previous_output>

<previous_critique>
{previous_reasoning}
</previous_critique>

Your task:
1. Critically analyze why the previous output was insufficient.
2. Generate a significantly improved response that addresses the instruction completely.
3. If you lack information, clearly state what is missing instead of hallucinating.

Output ONLY the improved response content.
"""
    try:
        messages = [
            SystemMessage(content=f"You are an expert {agent_type} refining your previous work."),
            HumanMessage(content=correction_prompt)
        ]
        
        # Cost tracking setup - prefer root_task_id for consistent attribution
        task_id = root_task_id or (config.get("configurable", {}).get("thread_id") if config else None)
        cost_callback = CostTrackingCallback(task_id=task_id, node_name="self_correct")
        llm_config: RunnableConfig = {"callbacks": [cost_callback]}
        
        # Use the main LLM for correction to ensure high quality
        response = await llm.ainvoke(messages, config=llm_config)
        
        # Record costs to global tracker
        tracker = CostTracker.get_instance()
        for record in cost_callback.records:
            tracker._add_record(record)
            
        return {"output": response.content}
    except Exception as e:
        print(f"⚠️ Self-correction failed: {e}")
        return {"output": output} # Fallback to original
