# AgentGuard SDK

This SDK provides a decoupled interface for any agent (LangChain, CrewAI, AutoGen, or custom) to integrate with the AgentGuard Governance Control Plane.

## Installation

Add the `sdk/` directory to your Python path, or copy it into your project.

## Quick Start

### 1. Framework-Agnostic Integration

For custom agents, use the `AgentGuardClient` to verify intents and track consumption.

```python
from sdk import get_agentguard_client

client = get_agentguard_client()

# 1. Verify Intent (Semantic Firewall)
decision = await client.verify(
    agent_id="my-agent-001",
    input_text="Generate a investment strategy for crypto",
    context={"task_id": "run-xyz-123"}
)

if decision["outcome"] == "BLOCK":
    print(f"Action blocked: {decision['reason']}")

# 2. Track Consumption (Circuit Breaker)
usage = await client.consume(
    run_id="run-xyz-123",
    cost=0.002,
    steps=1
)

if usage.get("status") == "BLOCKED":
    print("Circuit breaker tripped!")
```

### 2. LangChain / LangGraph Integration

The SDK provides a built-in callback handler for automated telemetry in LangChain.

```python
from sdk import AgentGuardCallbackHandler
from langgraph.graph import StateGraph

# Initialize the handler with a specific run_id
# This ID allows the CLI to monitor this specific run
config = {"callbacks": [AgentGuardCallbackHandler(run_id="my-task-001")]}

# Invoke your graph with the config
await workflow.ainvoke(state, config=config)
```

### 3. Monitoring any Python Function

Use the `@monitor_tool` decorator for simple tool monitoring in CrewAI or AutoGen.

```python
from sdk import monitor_tool

@monitor_tool
def fetch_sensitive_data(query: str):
    # Tool logic here
    pass
```

## CLI Monitoring

Once your agent is pushing telemetry using the SDK, you can monitor it in real-time:

```bash
python backend/cli.py watch <run_id>
```
