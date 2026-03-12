from typing import Any, Dict, List, Optional
from langchain_core.callbacks.base import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

# We use generic print/logging here to avoid internal backend dependencies
# External users can hook up their own telemetry tracers if needed.

class AgentGuardCallbackHandler(AsyncCallbackHandler):
    """
    Hooks into LangChain/LangGraph to provide telemetry and observability.
    """
    
    def __init__(self, run_id: str = "default_run"):
        super().__init__()
        self.run_id = run_id

    async def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        print(f"🧠 [AgentGuard] LLM Started: {serialized.get('name', 'Unknown Model')}")

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        print(f"🧠 [AgentGuard] LLM Finished.")

    async def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        tool_name = serialized.get('name', 'Unknown Tool')
        print(f"🔧 [AgentGuard] Tool Started: '{tool_name}' with input: {input_str}")

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        print("🔧 [AgentGuard] Tool Finished.")

    async def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
    ) -> None:
        chain_name = serialized.get('name') if serialized else "Unknown Chain"
        if "Graph" in chain_name or "Agent" in chain_name:
            print(f"🤖 [AgentGuard] Agent Flow Started: {chain_name}")

    async def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        print("🤖 [AgentGuard] Agent Flow Finished.")
