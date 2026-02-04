"""
Result Summarizer Agent (Epic 5 - Recursive Context Management).

Implements density-aware result compression to prevent context bloat
at depth. Uses LLM-based summarization when result size exceeds threshold.

This is an AGENT that performs LLM interaction to compress verbose results
into structured, high-density summaries.

Safety Features:
- Depth-limiting safeguards to prevent infinite loops
- Token-based threshold detection
- Structured output validation to prevent hallucination
"""
from typing import Dict, Any, Tuple
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from config.llm_providers import llm_mini
from utils.rate_limiter import safe_ainvoke
from core.cost import CostTrackingCallback, CostTracker


# --- CONFIGURATION ---

SUMMARY_THRESHOLD_TOKENS = 800  # Trigger summarization if result exceeds this
SUMMARY_TARGET_TOKENS = 250     # Target length for compressed output

# Depth-based compression ratios (more aggressive at deeper levels)
COMPRESSION_RATIOS = {
    0: 1.0,    # No compression at root
    1: 0.7,    # 30% reduction at depth 1
    2: 0.5,    # 50% reduction at depth 2
    3: 0.3,    # 70% reduction at depth 3+
}


def get_compression_ratio(depth: int) -> float:
    """Get compression ratio for a given depth."""
    return COMPRESSION_RATIOS.get(depth, 0.3)


# --- PROMPT ---

RESULT_SUMMARY_PROMPT = """<role>Density-Aware Context Compressor</role>
<objective>Compress execution results to preserve INFORMATION DENSITY while reducing token count by 60-80%.</objective>

<input_data>
<task>
{task}
</task>
<execution_results>
{results}
</execution_results>
</input_data>

<compression_strategy>
**Factory-Style Structured Summarization:**
1. **Intent**: What was the core objective? (1 sentence)
2. **Changes**: What concrete artifacts/decisions were produced? (bullet list, entities only)
3. **Constraints**: What technical limitations or dependencies were discovered? (bullet list)
4. **Next Steps**: What unresolved items require parent attention? (bullet list or "None")

**Critical Rules:**
- PRESERVE: Entity names (files, functions, APIs, error codes), numerical data, technical constraints
- DISCARD: Conversational filler, redundant explanations, step-by-step narration
- NO HALLUCINATION: Do not invent tasks, files, or decisions not present in the input
- TOKEN TARGET: Aim for 150-300 tokens for typical results (500+ tokens input)
</compression_strategy>

<anti_pattern_examples>
❌ BAD (verbose): "The researcher agent successfully completed an in-depth analysis of the OAuth 2.0 authentication flow, examining multiple industry-standard implementations..."
✅ GOOD (dense): "Intent: Research OAuth 2.0 flow. Changes: Identified PKCE requirement, recommended `authlib` library. Constraints: None. Next: Implementation."

❌ BAD (hallucination): "Next Steps: Deploy to production, configure CI/CD pipeline" (when results only mentioned local testing)
✅ GOOD (factual): "Next Steps: None (local validation complete)"
</anti_pattern_examples>

<task>Compress the execution results using the Factory-Style format. Return ONLY the compressed summary, no preamble.</task>"""


# --- STRUCTURED OUTPUT ---

class CompressedResult(BaseModel):
    """Structured output for compressed execution results."""
    intent: str = Field(..., description="Core objective in 1 sentence")
    changes: str = Field(..., description="Concrete artifacts/decisions (bullet list)")
    constraints: str = Field(..., description="Technical limitations discovered (bullet list or 'None')")
    next_steps: str = Field(..., description="Unresolved items requiring parent attention (bullet list or 'None')")


# --- UTILITIES ---

def estimate_token_count(text: str) -> int:
    """
    Rough token estimation (1 token ≈ 4 characters for English).
    
    Args:
        text: Input text
        
    Returns:
        Estimated token count
    """
    return len(text) // 4


# --- AGENT LOGIC ---

async def summarize_result(
    task: str,
    result: str,
    depth: int,
    root_task_id: str = None,
    config: RunnableConfig = None
) -> Tuple[str, Dict[str, float]]:
    """
    Compress a single execution result using density-aware summarization.
    
    This is the core AGENT function that performs LLM interaction.
    
    Args:
        task: Original task instruction
        result: Execution result to compress
        depth: Current recursion depth
        root_task_id: Task ID for cost attribution
        config: RunnableConfig for LLM calls
        
    Returns:
        Tuple of (compressed_result, usage_stats)
    """
    try:
        prompt = RESULT_SUMMARY_PROMPT.format(task=task, results=result)
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="Compress the execution results.")
        ]
        
        # Cost tracking
        cost_callback = CostTrackingCallback(
            task_id=root_task_id,
            node_name=f"result_summarizer_d{depth}"
        )
        llm_config: RunnableConfig = {"callbacks": [cost_callback]}
        
        structured_llm = llm_mini.with_structured_output(CompressedResult)
        compressed = await safe_ainvoke(structured_llm, messages, config=llm_config)
        
        # Record costs
        tracker = CostTracker.get_instance()
        for record in cost_callback.records:
            tracker._add_record(record)
        
        # Format as factory-style output
        formatted = f"""Intent: {compressed.intent}
Changes: {compressed.changes}
Constraints: {compressed.constraints}
Next Steps: {compressed.next_steps}"""
        
        original_tokens = estimate_token_count(result)
        compressed_tokens = estimate_token_count(formatted)
        reduction_pct = ((original_tokens - compressed_tokens) / original_tokens * 100) if original_tokens > 0 else 0
        
        print(f"   📉 [ResultSummarizer] Compressed {original_tokens} → {compressed_tokens} tokens ({reduction_pct:.1f}% reduction)")
        
        return formatted, cost_callback.to_usage_stats()
        
    except Exception as e:
        print(f"   ⚠️ [ResultSummarizer] Compression failed: {e}, returning truncated original")
        # Fallback: Simple truncation
        max_chars = SUMMARY_THRESHOLD_TOKENS * 4
        truncated = result[:max_chars] + f"\n\n[...truncated {len(result) - max_chars} chars]" if len(result) > max_chars else result
        return truncated, {}


def should_compress_result(result: str, depth: int) -> bool:
    """
    Determine if a result should be compressed based on size and depth.
    
    Args:
        result: Result text to evaluate
        depth: Current recursion depth
        
    Returns:
        True if compression should be applied
    """
    # Skip if result is error/abort marker
    if result.startswith("["):
        return False
    
    # Estimate token count
    estimated_tokens = estimate_token_count(result)
    compression_ratio = get_compression_ratio(depth)
    adjusted_threshold = int(SUMMARY_THRESHOLD_TOKENS * compression_ratio)
    
    return estimated_tokens > adjusted_threshold
