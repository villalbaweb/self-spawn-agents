"""
Confidence Evaluation Agent

This module provides an LLM-based evaluator that assesses the quality
and confidence of an agent's output, implementing heuristic guardrails
to detect "null result" failures (the "Phantom Protocol" fix).
"""

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from config.llm_providers import llm_mini
from utils.rate_limiter import safe_ainvoke
from core.cost import CostTrackingCallback, CostTracker
import re
import json


async def evaluate_confidence(instruction: str, output: str, config: RunnableConfig = None, root_task_id: str = None) -> dict:
    """
    Uses the LLM to evaluate the quality and confidence of an agent's output.
    Returns a dict with 'confidence_score' (0.0-1.0) and 'confidence_reasoning'.
    
    Args:
        instruction: The original instruction given to the agent
        output: The agent's output to evaluate
        config: Optional RunnableConfig with thread_id
        root_task_id: Optional root task ID for cost attribution (overrides config thread_id)
    """
    evaluation_prompt = f"""<role>Precision Quality Evaluator</role>
<objective>Assess the fidelity and completeness of the agent's output relative to the original instruction.</objective>

<input_data>
    <user_instruction>
    {instruction}
    </user_instruction>
    <candidate_output>
    {output[:2000]}
    </candidate_output>
</input_data>

<constraints>
- Rate the output on a scale from 0.0 to 1.0.
- **Criteria**:
    1. **Goal Achievement**: Did the agent fulfill the core mission? If it says "not found" or "cannot find", the score must be <= 0.2.
    2. **Completeness**: Are all parts of the instruction addressed?
    3. **Accuracy**: Is the info reliable and non-vague?
- **Workflow**: Perform a critical analysis of the output (Reasoning) BEFORE providing the final score.
- **Output Format**: Return ONLY a JSON object.
</constraints>

<task>
Analyze the <candidate_output> against the <user_instruction> and produce the JSON response:
{{
  "reasoning": "Detailed justification...",
  "confidence_score": 0.X
}}
</task>"""

    messages = [
        SystemMessage(content=evaluation_prompt),
        HumanMessage(content="Evaluate the candidate output against the user instruction and providing the required JSON response.")
    ]
    try:
        task_id = root_task_id or (config.get("configurable", {}).get("thread_id") if config else None)
        cost_callback = CostTrackingCallback(task_id=task_id, node_name="evaluate_confidence")
        llm_config: RunnableConfig = {"callbacks": [cost_callback]}
        
        response = await safe_ainvoke(llm_mini, messages, config=llm_config)
        
        # Record costs to global tracker
        tracker = CostTracker.get_instance()
        for record in cost_callback.records:
            tracker._add_record(record)
        
        # Parse JSON from response
        content = response.content.strip()
        # Handle potential markdown code blocks
        if "```" in content:
            content = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
            content = content.group(1) if content else "{}"
        
        result = json.loads(content)
        score = float(result.get("confidence_score", 0.5))
        reasoning = result.get("reasoning", "Unable to evaluate")

        # --- HEURISTIC SAFETY NET (The "Phantom Protocol" Fix) ---
        # If the agent verbally admits defeat, we MUST score it as a failure,
        # even if it assigns itself a high score for "being honest".
        failure_phrases = [
            r"does not exist",
            r"unable to find",
            r"no information available",
            r"cannot (provide|confirm|verify)",
            r"no consensus algorithm",
            r"unclear",
            r"not found"
        ]
        
        # Check against the first 500 chars (usually where the summary is)
        lower_output = output[:500].lower()
        if any(re.search(phrase, lower_output) for phrase in failure_phrases):
            print(f"📉 Heuristic Penalty Applied: Detected failure phrase in output.")
            score = min(score, 0.2)
            reasoning = f"[Heuristic Penalty] Output suggests task failure ('not found'). Original Score: {result.get('confidence_score')}. {reasoning}"

        return {
            "confidence_score": score,
            "confidence_reasoning": reasoning
        }, cost_callback.to_usage_stats()
    except Exception as e:
        print(f"⚠️ Confidence evaluation failed: {e}")
        return {"confidence_score": 0.5, "confidence_reasoning": f"Evaluation error: {str(e)}"}, {}
