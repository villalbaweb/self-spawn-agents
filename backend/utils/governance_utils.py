import json
import httpx
from typing import Optional, Dict, Any
from agentguard_sdk.client import GovernanceException, get_agentguard_client
from contextvars import ContextVar
from contextlib import contextmanager

# Context variables for identity propagation
current_agent_id: ContextVar[Optional[str]] = ContextVar("current_agent_id", default=None)
current_run_id: ContextVar[Optional[str]] = ContextVar("current_run_id", default=None)

def install_contextual_shield(default_agent_id: str = "production-shield", default_run_id: str = "shield-run"):
    """
    Installs a global interceptor that pulls identity from the ContextVar.
    Aligns with Agent Guard by providing accurate identity signals.
    """
    original_send = httpx.AsyncClient.send

    async def protected_send(self, request: httpx.Request, **kwargs):
        url_str = str(request.url)
        # Intercept LLM calls
        if "api.openai.com" in url_str or "anthropic" in url_str:
            try:
                # 1. Determine Identity (Context-Aware)
                effective_agent_id = current_agent_id.get() or default_agent_id
                effective_run_id = current_run_id.get() or default_run_id
                
                # 2. Extract input text for verification
                body = json.loads(request.read())
                input_text = "outbound-request"
                if "messages" in body:
                    input_text = str(body["messages"])
                elif "prompt" in body:
                    input_text = str(body["prompt"])

                # 3. Align with Agent Guard Rules (Verify)
                client = get_agentguard_client()
                decision = await client.verify(
                    agent_id=effective_agent_id,
                    input_text=input_text,
                    context={
                        "run_id": effective_run_id,
                        "interceptor": "contextual-shield"
                    }
                )

                if decision.get("outcome") == "BLOCK":
                    print(f"🚫 [AgentGuard Alignment] BLOCKING {effective_agent_id}: {decision.get('reason')}")
                    raise GovernanceException(
                        f"Blocked by AgentGuard Alignment: {decision.get('reason')}",
                        decision=decision
                    )
                    
            except Exception as e:
                if isinstance(e, GovernanceException): raise
                print(f"⚠️ [AgentGuard Alignment] Shield Error: {e}")

        return await original_send(self, request, **kwargs)

    httpx.AsyncClient.send = protected_send
    print(f"🛡️ [AgentGuard] Contextual Alignment Shield installed.")

@contextmanager
def governance_context(agent_id: str, run_id: str):
    """
    Context manager to set the current agent and run ID for governance tracking.
    This allows the universal shield to attribute LLM calls correctly.
    """
    token_agent = current_agent_id.set(agent_id)
    token_run = current_run_id.set(run_id)
    try:
        yield
    finally:
        current_agent_id.reset(token_agent)
        current_run_id.reset(token_run)

def get_governance_exception(e: Exception) -> Optional[GovernanceException]:
    """
    Recursively inspects an exception and its causes to find a GovernanceException.
    This is necessary because LLM libraries (like openai) often wrap underlying
    exceptions into their own connection or API errors.
    """
    if isinstance(e, GovernanceException):
        return e
    
    # Check the cause (explicitly chained via 'from')
    if hasattr(e, "__cause__") and e.__cause__:
        res = get_governance_exception(e.__cause__)
        if res:
            return res
            
    # Check the context (implicitly caught)
    if hasattr(e, "__context__") and e.__context__:
        res = get_governance_exception(e.__context__)
        if res:
            return res
            
    return None

def is_governance_block(e: Exception) -> bool:
    """
    Returns True if the exception or any of its causes is a GovernanceException.
    """
    return get_governance_exception(e) is not None
