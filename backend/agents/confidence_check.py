from typing import Dict, Any
from langgraph.types import interrupt
from agents.state import AgentState

async def confidence_check_node(state: AgentState) -> Dict[str, Any]:
    """
    Calculates aggregate confidence and triggers an interrupt if below threshold.
    """
    all_agents = state.get("all_agents", [])
    
    # --- AGGREGATE CONFIDENCE CALCULATION ---
    confidence_scores = [
        agent.get("confidence_score", 0.5) 
        for agent in all_agents 
        if "confidence_score" in agent
    ]
    aggregate_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.5
    
    # HITL threshold: If aggregate confidence < 0.6, flag for review
    CONFIDENCE_THRESHOLD = 0.6
    review_required = aggregate_confidence < CONFIDENCE_THRESHOLD
    
    # If review is required, trigger LangGraph interrupt
    if review_required:
        print(f"⏸️ [HITL] Pause for Human Review (Confidence: {aggregate_confidence:.2f})")
        # interrupt() will pause execution and return the value sent during resume
        try:
            user_response = interrupt({
                "type": "review_required",
                "confidence_score": aggregate_confidence,
                "message": f"Execution paused: Aggregate confidence ({aggregate_confidence:.2f}) is below threshold ({CONFIDENCE_THRESHOLD})."
            })
            print(f"✅ [HITL] Resume received: {user_response}")
        except Exception as e:
            # Handle cases where interrupt might not be supported (e.g., no checkpointer)
            print(f"⚠️ Interrupt failed: {e}")
            pass

        return {
            "confidence_score": aggregate_confidence,
            "review_required": False # Reset so we don't interrupt again
        }

    return {
        "confidence_score": aggregate_confidence,
        "review_required": False
    }
