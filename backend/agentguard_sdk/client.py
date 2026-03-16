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
        timeout: float = 30.0
    ):
        self.base_url = (base_url or os.getenv("AGENTGUARD_URL", "http://localhost:8000")).rstrip("/")
        self.timeout = timeout
        self.headers = {"Content-Type": "application/json"}
        self.token = None
        
        # Legacy API Key support
        if api_key or os.getenv("AGENTGUARD_API_KEY"):
            self.headers["Authorization"] = f"Bearer {api_key or os.getenv('AGENTGUARD_API_KEY')}"
    
    async def authenticate(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        Authenticates with the AgentGuard API and stores the access token.
        """
        user = username or os.getenv("ADMIN_USERNAME", "admin")
        pwd = password or os.getenv("ADMIN_PASSWORD", "agentguard123")
        
        url = f"{self.base_url}/api/auth/token"
        # OAuth2PasswordRequestForm expects form-data
        data = {"username": user, "password": pwd}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, data=data)
                response.raise_for_status()
                token_data = response.json()
                self.token = token_data["access_token"]
                self.headers["Authorization"] = f"Bearer {self.token}"
                return True
        except Exception as e:
            print(f"⚠️ [AgentGuard SDK] Authentication failed: {e}")
            return False

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
        except httpx.RequestError as exc:
            print(f"⚠️ Error connecting to AgentGuard at {url}: {exc}")
            return {
                "outcome": "ALLOW",
                "reason": "AgentGuard service unreachable - failing open",
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
        except httpx.RequestError as exc:
            print(f"⚠️ Error connecting to AgentGuard at {url}: {exc}")
            return {"status": "ALLOWED", "reason": "AgentGuard unreachable", "usage": {}}
    
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
        except httpx.RequestError as exc:
            print(f"⚠️ Error tracking thought to AgentGuard: {exc}")
            return {"status": "Error", "reason": str(exc)}

    async def clear_run_history(self, run_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/gatekeeper/clear-history/{run_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as exc:
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
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    client = get_agentguard_client()
    return await client.verify(agent_id, input_text, context)

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
        if "api.openai.com" in str(request.url) or "anthropic" in str(request.url):
            try:
                # Attempt to extract some context from the request body
                body = json.loads(request.read())
                input_text = str(body.get("messages", body.get("prompt", "outbound-request")))
                
                # 2. Synchronous Governance Check
                client = get_agentguard_client()
                # Note: This is a simplified async-within-async pattern
                decision = await client.verify(
                    agent_id=agent_id,
                    input_text=input_text,
                    context={"run_id": default_run_id, "interceptor": "http-shield"}
                )

                if decision.get("outcome") == "BLOCK":
                    print(f"🚫 [AgentGuard Shield] BLOCKING Outbound Request: {decision.get('reason')}")
                    raise GovernanceException(
                        f"Blocked by AgentGuard Shield: {decision.get('reason')}",
                        decision=decision
                    )
            except Exception as e:
                if isinstance(e, GovernanceException): raise
                # Fail open on parsing errors to avoid bricking the agent
                print(f"⚠️ [AgentGuard Shield] Parsing error in interceptor: {e}")

        return await original_send(self, request, **kwargs)

    httpx.AsyncClient.send = protected_send
    print(f"🛡️ [AgentGuard] Strong Shield installed (Agent: {agent_id})")

