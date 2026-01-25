"""
Confidence Evaluation Agent

This module provides an LLM-based evaluator that assesses the quality
and confidence of an agent's output, implementing heuristic guardrails
to detect "null result" failures (the "Phantom Protocol" fix).
"""

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from agents.dependencies import llm_mini
from agents.cost import CostTrackingCallback, CostTracker
import re
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
1. **Goal Achievement (CRITICAL):** Did the agent actually FIND what was asked for?
   - If the user asked for X, and the agent says "X does not exist" or "I cannot find X", the score MUST be low (< 0.2).
   - We rate based on "Mission Success", not just "Fact Correctness".

2. **Completeness:** Does it fully address all parts of the instruction?
3. **Accuracy:** Is the information reliable and not vague?

**Scoring Guide:**
- 0.9-1.0: Perfect, complete answer found.
- 0.7-0.8: Good answer, minor details missing.
- 0.5-0.6: Partial answer found.
- 0.1-0.2: "Not found", "Does not exist", or refusal to answer.
- 0.0: Hallucination or complete failure.

Respond with ONLY a JSON object, no other text:
{{"confidence_score": 0.X, "reasoning": "Brief explanation"}}
"""
    try:
        messages = [
            SystemMessage(content="You are a quality evaluator. Output ONLY valid JSON."),
            HumanMessage(content=evaluation_prompt)
        ]
        
        # Cost tracking setup
        task_id = config.get("configurable", {}).get("thread_id") if config else None
        cost_callback = CostTrackingCallback(task_id=task_id, node_name="evaluate_confidence")
        llm_config: RunnableConfig = {"callbacks": [cost_callback]}
        
        response = await llm_mini.ainvoke(messages, config=llm_config)
        
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
        }
    except Exception as e:
        print(f"⚠️ Confidence evaluation failed: {e}")
        return {"confidence_score": 0.5, "confidence_reasoning": f"Evaluation error: {str(e)}"}
