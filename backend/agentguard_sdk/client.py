import os
import httpx
from typing import Dict, Any, Optional
import json

class GovernanceException(Exception):
    """Raised when AgentGuard blocks an action due to policy violation."""
    def __init__(self, message: str, decision: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.decision = decision or {}

class AgentGuardClient:
    """
    Standalone client for AgentGuard governance APIs.
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None
    ):
        self.base_url = (base_url or os.getenv("AGENTGUARD_URL", "http://localhost:8000")).rstrip("/")
        # A verify call waits on AgentGuard's LLM safety guard, so the ceiling
        # has to cover that model's slow tail rather than a bare HTTP round
        # trip — time out early and we fail open on exactly the calls that took
        # longest to judge. Tune with AGENTGUARD_TIMEOUT.
        self.timeout = timeout if timeout is not None else float(os.getenv("AGENTGUARD_TIMEOUT", "60"))
        self.headers = {"Content-Type": "application/json"}
        self.token = None
        
        # Static API key. This goes in X-Api-Key, NOT Authorization: AgentGuard
        # treats any Bearer value as a JWT and 401s when it fails to decode, so
        # sending a static key that way locks us out instead of authenticating.
        # Authorization is reserved for a real token from authenticate().
        static_key = api_key or os.getenv("AGENTGUARD_API_KEY")
        if static_key:
            self.headers["X-Api-Key"] = static_key
    
    async def authenticate(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        Confirms AgentGuard is reachable and accepts our credential.

        There is no password grant to call: AgentGuard authenticates with a
        static X-Api-Key (AGENTGUARD_API_KEY) or a JWT minted elsewhere, and
        keeps no user store. So instead of exchanging credentials we probe an
        endpoint that requires auth and see whether it lets us in — which is
        the thing callers actually want to know before trusting governance.

        The username/password arguments are accepted for backwards
        compatibility and ignored.
        """
        url = f"{self.base_url}/policy"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers)
        except httpx.HTTPError as e:
            print(f"⚠️ [AgentGuard SDK] Service unreachable at {self.base_url}: {e}")
            return False

        if response.status_code in (401, 403):
            print(
                f"⚠️ [AgentGuard SDK] Credential rejected ({response.status_code}). "
                "Check that AGENTGUARD_API_KEY matches the value AgentGuard is running with."
            )
            return False
        if response.status_code >= 400:
            print(f"⚠️ [AgentGuard SDK] Unexpected response probing {url}: {response.status_code}")
            return False

        if "X-Api-Key" not in self.headers and "Authorization" not in self.headers:
            print("ℹ️ [AgentGuard SDK] Connected without a credential (AgentGuard has auth disabled).")
        return True

    async def verify(
        self,
        agent_id: str,
        input_text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/gatekeeper/verify"
        payload = {
            "agent_id": agent_id,
            "input_text": input_text,
            "context": context or {}
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            # Fail open on BOTH transport errors (service down) and HTTP status
            # errors (e.g. 404 when the service on the other end does not expose
            # /api/gatekeeper/*). A governance BLOCK is carried in the response
            # body, never as an HTTP error, so no decision is lost here.
            print(f"⚠️ AgentGuard verify unavailable at {url} ({exc}) - failing open")
            return {
                "outcome": "ALLOW",
                "reason": f"AgentGuard service unavailable ({exc}) - failing open",
                "decision_id": "fallback-allow"
            }
    
    async def consume(
        self,
        run_id: str,
        cost: float,
        steps: int = 1,
        depth: int = 0,
        max_cost: Optional[float] = None,
        max_depth: Optional[int] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/gatekeeper/consume"
        payload = {
            "run_id": run_id,
            "cost": cost,
            "steps": steps,
            "depth": depth,
            "max_cost": max_cost,
            "max_depth": max_depth
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                if response.status_code == 429:
                    return {
                        "status": "BLOCKED",
                        "reason": "Circuit breaker tripped",
                        "usage": {}
                    }
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            # 429 (circuit breaker tripped) is handled above, so anything landing
            # here means the service is unavailable rather than denying us.
            print(f"⚠️ AgentGuard consume unavailable at {url} ({exc}) - failing open")
            return {"status": "ALLOWED", "reason": f"AgentGuard unavailable ({exc})", "usage": {}}
    
    async def track_thought(
        self,
        run_id: str,
        node_name: str,
        text: str
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/gatekeeper/track_thought"
        payload = {
            "run_id": run_id,
            "node_name": node_name,
            "text": text
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            print(f"⚠️ Error tracking thought to AgentGuard: {exc}")
            return {"status": "Error", "reason": str(exc)}

    async def clear_run_history(self, run_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/gatekeeper/clear-history/{run_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            print(f"⚠️ Error clearing history for run {run_id}: {exc}")
            return {"status": "Error", "reason": str(exc)}


    async def health_check(self) -> bool:
        try:
            url = f"{self.base_url}/health"
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception:
            return False

_client: Optional[AgentGuardClient] = None

def get_agentguard_client() -> AgentGuardClient:
    global _client
    if _client is None:
        _client = AgentGuardClient()
    return _client

async def verify_with_governance(
    agent_id: str,
    input_text: str,
    context: Optional[Dict[str, Any]] = None,
    enforce: bool = True
) -> Dict[str, Any]:
    """Verify a step and, by default, hard-stop the caller on BLOCK.

    Enforcing here is what makes a bare `await verify_with_governance(...)`
    meaningful: most call sites discard the return value, so a returned BLOCK
    would otherwise be silently ignored and the step would run anyway.

    Pass enforce=False when the caller inspects the decision itself — the
    decorators do, since they record it in state and handle PAUSE first.
    """
    client = get_agentguard_client()
    decision = await client.verify(agent_id, input_text, context)

    if enforce and decision.get("outcome") == "BLOCK":
        print(f"🚫 [AgentGuard] BLOCKED '{agent_id}': {decision.get('reason')}")
        raise GovernanceException(
            f"AgentGuard Policy Violation in '{agent_id}': {decision.get('reason')}",
            decision=decision
        )
    return decision

async def track_consumption(
    run_id: str, 
    cost: float, 
    steps: int = 1, 
    depth: int = 0,
    max_cost: Optional[float] = None,
    max_depth: Optional[int] = None,
    enforce: bool = True
) -> Dict[str, Any]:
    client = get_agentguard_client()
    result = await client.consume(run_id, cost, steps, depth, max_cost, max_depth)
    
    if enforce and result.get("status") == "BLOCKED":
        raise GovernanceException(
            f"AgentGuard Circuit Breaker: {result.get('reason')}",
            decision=result
        )
    return result

async def track_thought_telemetry(
    run_id: str,
    node_name: str,
    text: str
) -> Dict[str, Any]:
    client = get_agentguard_client()
    return await client.track_thought(run_id, node_name, text)

# --- 🛡️ GENERIC SHIELD (Framework-Agnostic Interceptor) ---

def install_shield(agent_id: str = "generic-agent", default_run_id: str = "shield-run"):
    """
    Installs a global interceptor that hooks into common LLM library calls (via httpx).
    Ensures 'Strong & Generic' protection regardless of agent technology.
    """
    import httpx
    
    original_send = httpx.AsyncClient.send

    async def protected_send(self, request: httpx.Request, **kwargs):
        # 1. Identify if this is an LLM/Tool outbound call (simple heuristic)
        # In a real implementation, we'd more accurately inspect the payload
        url_str = str(request.url)
        if "api.openai.com" in url_str or "anthropic" in url_str:
            try:
                # Attempt to extract some context from the request body
                body = json.loads(request.read())
                
                # Extract text for semantic analysis
                input_text = ""
                if "messages" in body:
                    # LangChain style messages
                    input_text = str(body["messages"])
                elif "prompt" in body:
                    input_text = str(body["prompt"])
                else:
                    input_text = "outbound-request"
                
                # 2. Synchronous Governance Check
                client = get_agentguard_client()
                
                decision = await client.verify(
                    agent_id=agent_id,
                    input_text=input_text,
                    context={
                        "run_id": default_run_id, 
                        "interceptor": "http-shield"
                    }
                )

                if decision.get("outcome") == "BLOCK":
                    print(f"🚫 [AgentGuard Shield] BLOCKING Outbound Request for {agent_id}: {decision.get('reason')}")
                    raise GovernanceException(
                        f"Blocked by AgentGuard Shield: {decision.get('reason')}",
                        decision=decision
                    )
            except Exception as e:
                if isinstance(e, GovernanceException): raise
                # Fail open on parsing errors to avoid bricking the agent
                print(f"⚠️ [AgentGuard Shield] Error in interceptor: {e}")

        return await original_send(self, request, **kwargs)

    httpx.AsyncClient.send = protected_send
    print(f"🛡️ [AgentGuard] Strong Shield installed (Default Agent: {agent_id})")

