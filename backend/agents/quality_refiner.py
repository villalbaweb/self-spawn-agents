from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from config.llm_providers import llm
from config.settings import TIER1_THRESHOLD
from core.cost import CostTrackingCallback, CostTracker

async def quality_refiner_node(instruction: str, output: str, previous_reasoning: str, agent_type: str, config: RunnableConfig = None, root_task_id: str = None) -> Dict[str, str]:
    """
    Tier 1: Autonomous Quality Refinement.
    Asks the agent to critique and refine its own output based on low confidence.
    
    Args:
        instruction: The original instruction
        output: The previous output that had low confidence
        previous_reasoning: The reasoning for the low confidence
        agent_type: Type of agent (Researcher, Coder, etc.)
        config: Optional RunnableConfig
        root_task_id: Optional root task ID for cost attribution
    """
    print(f"🔄 [AITL] Tier 1 Quality Refinement triggered for {agent_type}")
    
    correction_prompt = f"""<role>Expert Self-Correction Agent</role>
<objective>Critically refine your previous output to reach high confidence and mission success.</objective>

<input_data>
    <original_instruction>
    {instruction}
    </original_instruction>
    <failed_attempt>
    {output}
    </failed_attempt>
    <failure_diagnosis>
    {previous_reasoning}
    </failure_diagnosis>
</input_data>

<constraints>
- **Analysis**: Identify exactly where the previous attempt failed (misinterpretation, missing info, format error).
- **Refinement**: Generate an improved response that fully addresses the instruction.
- **Honesty**: If information is genuinely unavailable, state the limitation instead of guessing.
- **Threshold**: The goal is to surpass a confidence of {TIER1_THRESHOLD}.
- **Output Format**: Return ONLY the improved content text (no preamble).
</constraints>

<task>Generate the improved response based on the diagnosis.</task>"""

    messages = [
        SystemMessage(content=correction_prompt),
        HumanMessage(content="Analyze the failed attempt and generate the improved response as instructed.")
    ]
    try:
        # Cost tracking setup - prefer root_task_id for consistent attribution
        task_id = root_task_id or (config.get("configurable", {}).get("thread_id") if config else None)
        cost_callback = CostTrackingCallback(task_id=task_id, node_name="quality_refiner")
        llm_config: RunnableConfig = {"callbacks": [cost_callback]}
        
        # Use the main LLM for correction to ensure high quality
        response = await llm.ainvoke(messages, config=llm_config)
        
        # Record costs to global tracker
        tracker = CostTracker.get_instance()
        for record in cost_callback.records:
            tracker._add_record(record)
            
        return {"output": response.content, "usage_stats": cost_callback.to_usage_stats()}
    except Exception as e:
        from utils.governance_utils import is_governance_block
        if is_governance_block(e):
            raise e
        print(f"⚠️ Quality refinement failed: {e}")
        return {"output": output, "usage_stats": {}} # Fallback to original
