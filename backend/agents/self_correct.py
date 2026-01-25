from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from agents.dependencies import llm, TIER1_THRESHOLD

async def simple_self_correct(instruction: str, output: str, previous_reasoning: str, agent_type: str, config: RunnableConfig = None) -> Dict[str, str]:
    """
    Tier 1: Autonomous Self-Correction.
    Asks the agent to critique and refine its own output based on low confidence.
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
        
        # Use the main LLM for correction to ensure high quality
        if config:
            response = await llm.ainvoke(messages, config=config)
        else:
            response = await llm.ainvoke(messages)
            
        return {"output": response.content}
    except Exception as e:
        print(f"⚠️ Self-correction failed: {e}")
        return {"output": output} # Fallback to original
