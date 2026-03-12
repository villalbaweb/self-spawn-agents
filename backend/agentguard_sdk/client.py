import os
import httpx
from typing import Dict, Any, Optional

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
    max_depth: Optional[int] = None
) -> Dict[str, Any]:
    client = get_agentguard_client()
    return await client.consume(run_id, cost, steps, depth, max_cost, max_depth)
async def track_thought_telemetry(
    run_id: str,
    node_name: str,
    text: str
) -> Dict[str, Any]:
    client = get_agentguard_client()
    return await client.track_thought(run_id, node_name, text)

