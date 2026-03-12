import functools
import time
import asyncio
import json
import os
import threading
from typing import Callable, Any, Dict, Optional, Union
from concurrent.futures import Future

# Late import to prevent circular dependency issues during SDK load
from .client import (
    verify_with_governance, 
    track_thought_telemetry, 
    track_consumption,
    get_agentguard_client
)

def _get_input_from_args(args: Any, kwargs: Any) -> str:
    """Helper to extract a searchable string from function arguments."""
    try:
        # If there's only one argument, use it as the main input
        if len(args) == 1 and isinstance(args[0], str):
            return args[0]
        # Otherwise, serialize the whole context
        return json.dumps({"args": args, "kwargs": kwargs})
    except Exception:
        return str(args) + str(kwargs)

def protected_tool(
    agent_id: str = "tool-agent",
    policy_id: Optional[str] = None,
    risk_level: str = "medium",
    cost_per_call: float = 0.0,
    enforce: bool = True
):
    """
    Production-ready decorator for standalone tools (CrewAI, AutoGen, custom functions).
    
    Provides:
    1. Semantic Firewall (verify_action)
    2. Circuit Breaker (record_consumption)
    3. Audit Telemetry (track_thought)
    
    Supports both sync and async functions.
    """
    def decorator(func):
        is_async = asyncio.iscoroutinefunction(func)

        async def _run_governance_logic(*args, **kwargs):
            node_name = func.__name__
            full_agent_id = f"{agent_id}.{node_name}"
            input_text = _get_input_from_args(args, kwargs)
            
            # 1. PRE-EXECUTION: Semantic Firewall
            print(f"🛡️ [AgentGuard] Protecting tool '{node_name}'...")
            
            # Attempt to extract run_id/task_id from kwargs if present (common in agents)
            run_id = kwargs.get("run_id") or kwargs.get("task_id") or "standalone-tool-run"
            
            context = {
                "node": node_name,
                "risk_level": risk_level,
                "policy_id": policy_id,
                "run_id": run_id
            }
            
            decision = await verify_with_governance(
                agent_id=full_agent_id,
                input_text=input_text,
                context=context
            )
            
            if decision.get("outcome") == "BLOCK":
                print(f"🚫 [AgentGuard] BLOCKED Tool Execution: {decision.get('reason')}")
                return {"outcome": "BLOCK", "reason": decision.get("reason"), "run_id": run_id}

            return {"outcome": "ALLOW", "run_id": run_id}

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            node_name = func.__name__
            
            # 1. PRE-EXECUTION
            governance_result = await _run_governance_logic(*args, **kwargs)
            if governance_result["outcome"] == "BLOCK":
                if enforce:
                    raise PermissionError(f"AgentGuard Policy Violation: {governance_result.get('reason')}")
                return {"outcome": "BLOCKED", "reason": governance_result.get("reason")}

            run_id = governance_result["run_id"]

            # 2. EXECUTION PHASE
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                # 3. POST-EXECUTION: Telemetry & Consumption
                # We do this as fire-and-forget to avoid blocking tool return
                asyncio.create_task(track_thought_telemetry(run_id, node_name, str(result)))
                if cost_per_call > 0:
                    asyncio.create_task(track_consumption(run_id=run_id, cost=cost_per_call))
                
                print(f"🔧 [AgentGuard] Tool '{node_name}' Finished ({duration_ms:.2f}ms).")
                return result
                
            except Exception as e:
                print(f"❌ [AgentGuard] Tool '{node_name}' Failed: {e}")
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            node_name = func.__name__
            
            def run_async_in_new_loop(coro):
                """Runs a coroutine in a completely fresh event loop in a new thread."""
                result_future = Future()

                def thread_target():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        res = loop.run_until_complete(coro)
                        result_future.set_result(res)
                    except Exception as e:
                        result_future.set_exception(e)
                    finally:
                        loop.close()

                thread = threading.Thread(target=thread_target)
                thread.start()
                return result_future.result()

            # 1. PRE-EXECUTION
            governance_result = run_async_in_new_loop(_run_governance_logic(*args, **kwargs))
            
            if governance_result["outcome"] == "BLOCK":
                if enforce:
                    raise PermissionError(f"AgentGuard Policy Violation: {governance_result.get('reason')}")
                return {"outcome": "BLOCKED", "reason": governance_result.get("reason")}

            run_id = governance_result["run_id"]

            # 2. EXECUTION PHASE
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                # 3. POST-EXECUTION: Telemetry & Consumption (Fire and forget)
                def track_telemetry_bg():
                    run_async_in_new_loop(track_thought_telemetry(run_id, node_name, str(result)))
                    if cost_per_call > 0:
                        run_async_in_new_loop(track_consumption(run_id=run_id, cost=cost_per_call))

                threading.Thread(target=track_telemetry_bg, daemon=True).start()
                
                print(f"🔧 [AgentGuard] Tool '{node_name}' Finished ({duration_ms:.2f}ms).")
                return result
                
            except Exception as e:
                print(f"❌ [AgentGuard] Tool '{node_name}' Failed: {e}")
                raise

        return async_wrapper if is_async else sync_wrapper

    return decorator

def monitor_tool(func):
    """
    Legacy wrapper upgraded to use the protected_tool infrastructure with enforcement disabled.
    Syncs telemetry and performs checks without raising exceptions.
    """
    return protected_tool(enforce=False)(func)

def langgraph_node_guard(
    agent_id_prefix: str = "agent", 
    extract_input: Optional[Callable[[Dict], str]] = None,
    depth_increment: int = 0
):
    """
    Enhanced decorator for LangGraph nodes to automatically enforce Semantic Firewall policies.
    Supports PAUSE outcomes (Human-in-the-Loop) and updates the common WorkflowState structure.
    """
    def default_extractor(state: Dict) -> str:
        # Prioritize specific semantic fields to avoid dynamic state noise (IDs, timestamps)
        if "current_research_query" in state and state["current_research_query"]:
            return str(state["current_research_query"])
        if "messages" in state and state["messages"]:
            last_msg = state["messages"][-1]
            if hasattr(last_msg, "content"):
                return str(last_msg.content)
            return str(last_msg)
        if "original_query" in state and state["original_query"]:
            return str(state["original_query"])
        if "prompt" in state and state["prompt"]:
            return str(state["prompt"])
        
        # If we must use the whole state, try to exclude known dynamic fields
        clean_state = {k: v for k, v in state.items() if k not in ["task_id", "workflow_trace_id", "governance_decisions", "thought_records", "accumulated_cost"]}
        return str(clean_state)

    extractor = extract_input or default_extractor

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(state: Dict[str, Any], *args, **kwargs):
            node_name = func.__name__
            agent_id = f"{agent_id_prefix}-{node_name}"
            input_text = extractor(state)
            
            # --- 🚀 STICKY HINT INJECTION ---
            # If we have a persistent hint from a previous rescue, we force it!
            if state.get("sticky_human_hint"):
                hint = state["sticky_human_hint"]
                # Greedy Injection
                greedy_keys = ["prompt", "query", "input", "text", "task", "current_research_query"]
                for key in greedy_keys:
                    if key in state and isinstance(state[key], str) and "PRIORITY HUMAN FEEDBACK" not in state[key]:
                        state[key] = f"### PRIORITY HUMAN FEEDBACK (Persistent): {hint}\n\nSTRICT INSTRUCTION: {state[key]}"
                
                if "messages" in state and isinstance(state["messages"], list):
                    from langchain_core.messages import SystemMessage
                    # Check if we already injected this exact hint
                    if not any(isinstance(m, SystemMessage) and hint in str(m.content) for m in state["messages"]):
                        state["messages"].append(SystemMessage(content=f"### PERSISTENT HUMAN OVERRIDE: {hint}\nContinue strictly following this instruction."))

            # 1. Verification Phase
            print(f"🛡️ [AgentGuard] Verifying node '{node_name}' intent...")
            
            # Check for ANY pending CLI interjections (Asynchronous Nudge)
            has_new_hint = False
            import redis
            try:
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
                r = redis.from_url(redis_url, decode_responses=True)
                control_list = f"agentguard:run:{state.get('task_id')}:control"
                interjection = r.lpop(control_list)
                if interjection:
                    data = json.loads(interjection)
                    if data.get("type") == "INTERJECT":
                        hint = data.get("content")
                        if "human_interjections" not in state:
                            state["human_interjections"] = []
                        state["human_interjections"].append(hint)
                        print(f"🟢 [AgentGuard] ASYNC Human hint received: {hint}")
                        has_new_hint = True
                        
                        # Make it STICKY
                        state["sticky_human_hint"] = hint
                        
                        # Reset history
                        try:
                            client = get_agentguard_client()
                            await client.clear_run_history(state.get("task_id"))
                        except Exception: pass
            except Exception:
                pass

            if has_new_hint:
                # If we just received a human override, we ALLOW this step 
                # so the agent logic can actually process the hint.
                decision = {
                    "outcome": "ALLOW",
                    "reason": "Human override received via CLI",
                    "decision_id": "human-override"
                }
            else:
                context = {
                    "node": node_name,
                    "task_id": state.get("task_id"),
                    "depth": state.get("current_depth", 0),
                    "accumulated_cost": state.get("accumulated_cost", 0.0),
                    "max_cost": state.get("max_cost"),
                    "max_depth": state.get("max_depth")
                }
                
                decision = await verify_with_governance(
                    agent_id=agent_id,
                    input_text=input_text,
                    context=context
                )

            # Handle PAUSE Outcomes (Synchronous Rescue)
            if decision.get("outcome") == "PAUSE":
                import redis
                print(f"🟡 [AgentGuard] PAUSED node '{node_name}': {decision.get('reason')}")
                print(f"🟡 [AgentGuard] Waiting for human hint via CLI/UI (run_id: {state.get('task_id')})...")

                try:
                    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
                    r = redis.from_url(redis_url, decode_responses=True)
                    control_list = f"agentguard:run:{state.get('task_id')}:control"
                    while True:
                        interjection = r.lpop(control_list)
                        if interjection:
                            data = json.loads(interjection)
                            if data.get("type") == "INTERJECT":
                                hint = data.get("content")
                                chosen_outcome = data.get("outcome", "CONTINUE").upper()
                                
                                if "human_interjections" not in state:
                                    state["human_interjections"] = []
                                state["human_interjections"].append(hint)
                                print(f"🟢 [AgentGuard] Human hint received: RESUMING EXECUTION (Outcome: {chosen_outcome})")
                                
                                # Make it STICKY
                                state["sticky_human_hint"] = hint
                                
                                # History Reset
                                try:
                                    client = get_agentguard_client()
                                    await client.clear_run_history(state.get("task_id"))
                                except Exception: pass

                                # --- 🚀 ENFORCEMENT OF 3 STATES ---
                                
                                if chosen_outcome == "ABORT":
                                    print(f"🛑 [AgentGuard] User aborted the run.")
                                    if "workflow_status" in state: state["workflow_status"] = "blocked"
                                    if "blocked_at_node" in state: state["blocked_at_node"] = node_name
                                    await track_thought_telemetry(state["task_id"], node_name, f"RUN ABORTED BY HUMAN: {hint}")
                                    return state

                                if chosen_outcome == "OVERRIDE":
                                    print(f"🛡️ [AgentGuard] USER OVERRIDE: Forcing ALLOW for this step.")
                                    # We bypass logic and return ALLOWED
                                    # If it's a LangGraph node, we might want to continue execution 
                                    # but skip the firewall for JUST THIS STEP.
                                    # Let's proceed to func execution but mark as ALLOWED.
                                    decision = {"outcome": "ALLOW", "reason": f"Human Override: {hint}", "decision_id": "human-override"}
                                    break # Exit the PAUSE loop and continue to func()

                                # DEFAULT: CONTINUE (Nudge)
                                # 1. LangChain/LangGraph Pattern (Messages List)
                                if "messages" in state and isinstance(state["messages"], list):
                                    try:
                                        from langchain_core.messages import SystemMessage
                                        priority_msg = SystemMessage(content=f"### CRITICAL HUMAN OVERRIDE: {hint}\nInstructions: Ignore your previous thoughts and strictly follow the human instruction above.")
                                        state["messages"].append(priority_msg)
                                    except ImportError:
                                        state["messages"].append({"role": "system", "content": f"### HUMAN OVERRIDE: {hint}"})

                                # 2. Custom String Patterns (prompt, query, input, task)
                                greedy_keys = ["prompt", "query", "input", "text", "task", "current_research_query"]
                                for key in greedy_keys:
                                    if key in state and isinstance(state[key], str):
                                        state[key] = f"### PRIORITY HUMAN FEEDBACK: {hint}\n\nSTRICT INSTRUCTION: {state[key]}"
                                
                                break
                        await asyncio.sleep(1)
                except Exception as e:
                    print(f"⚠️ [AgentGuard] Error in PAUSE loop: {e}")

            # Record decision in state if it's the standard WorkflowState structure
            if "governance_decisions" in state:
                state["governance_decisions"].append({
                    "node": node_name,
                    "outcome": decision.get("outcome"),
                    "reason": decision.get("reason"),
                    "decision_id": decision.get("decision_id"),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                })

            if decision.get("outcome") == "BLOCK":
                print(f"🚫 [AgentGuard] BLOCKED node '{node_name}': {decision.get('reason')}")
                if "blocked_at_node" in state:
                    state["blocked_at_node"] = node_name
                if "workflow_status" in state:
                    state["workflow_status"] = "blocked"
                return state
            
            # Update depth
            if "current_depth" in state:
                state["current_depth"] += depth_increment
            
            # 2. Execution Phase
            start_time = time.time()
            result = await func(state, *args, **kwargs)
            duration_ms = (time.time() - start_time) * 1000
            
            # 3. Thought Tracking (Automated if result has content)
            if "task_id" in state:
                # Try to extract the core response to track it as a thought
                thought_text = ""
                if isinstance(result, dict):
                    if "analysis_results" in result: thought_text = result["analysis_results"]
                    elif "draft_content" in result: thought_text = result["draft_content"]
                    elif "research_results" in result and result["research_results"]: thought_text = result["research_results"][-1]
                
                if thought_text:
                    await track_thought_telemetry(state["task_id"], node_name, str(thought_text))

            return result

        return async_wrapper
    return decorator
