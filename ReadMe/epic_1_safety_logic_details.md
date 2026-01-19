# Epic 1: Safety Logic - Detailed Steps & Behavior Analysis

This document details the three core components of **Epic 1: Safety Logic**, contrasting the current system behavior with the expected behavior after implementation.

---

## 1.1 Atomic State Persistence

**Objective:** Ensure zero data loss in the event of a container crash or unexpected restart.

### Current Behavior ("The Checkpoint Gap")
*   **Mechanism:** State is typically saved to the `checkpointer` (Postgres/Sqlite) at the end of the graph execution or at specific "Interrupt" boundaries (before a human review).
*   **Risk:** If the container crashes *during* a long-running graph (e.g., in step 5 of 10), but before a formal checkpoint, the system has no record of steps 1-5.
*   **Recovery:** The user must restart the entire run from the beginning.
*   **Technical Detail:** `MemorySaver` usage is currently loose or implicit in some compiled graphs.

### Expected Behavior ("The Safety Net")
*   **Mechanism:** We will configure the compiled `StateGraph` to trigger the checkpointer **after every single node transition**.
*   **Refactor:** Utilize LangGraph's native `checkpoint_on_token` (if applicable) or ensure the `compile(checkpointer=...)` is correctly wired for per-step persistence.
*   **Outcome:** If the system crashes at Step 5.5:
    1.  System restarts.
    2.  User clicks "Resume".
    3.  System loads state from the end of Step 5 and immediately begins Step 6 (or retries Step 5).
*   **Benefit:** Enterprise-grade reliability.

---

## 1.2 Zombie Branch Pruning (Critical)

**Objective:** Prevent wasted token/compute usage when a parallel sibling branch has already failed.

### Current Behavior ("The Ghost Run")
*   **Scenario:** A user asks for "Competitor Analysis". The system spawns 3 parallel Researcher Agents:
    *   Agent A: Researching Google (Fast, Success).
    *   Agent B: Researching OpenAI (Slow, **FAILS** with Tier 3 Interrupt - "Need API Key").
    *   Agent C: Researching Anthropic (Very Slow, Running).
*   **Issue:** Agent B hits a critical error and pauses the graph (Tier 3). It waits for human help.
*   **Waste:** **Agent C continues running** for another 5 minutes, burning tokens, even though the overall parent task might need to be completely restarted or changed based on Agent B's failure.
*   **Technical Detail:** Parallel nodes in LangGraph are independent threads; they don't share a "stop signal" by default.

### Expected Behavior ("The Kill Switch")
*   **Mechanism:**
    1.  Add a `global_signal` object to the shared `AgentState`.
    2.  Wrap every Node execution with a "Pre-Flight Check".
*   **Scenario:**
    *   Agent B fails (Tier 3). It sets `state.global_signal = "INTERRUPT"`.
    *   Agent C finishes its current LLM call and prepares for the next step.
    *   **Pre-Flight Check:** Agent C sees `state.global_signal == "INTERRUPT"`.
    *   **Action:** Agent C raises a `GraphInterrupt` or effectively "freezes" without executing further logic.
*   **Outcome:** The system saves money. The user is notified immediately of the block without waiting for unrelated tasks to finish.

---

## 1.3 Budget Caps & Limits

**Objective:** Prevent "Infinite Loops" or "Recursive Spirals" from draining user credits.

### Current Behavior ("The Open Tab")
*   **Risk:** A recursive agent might get stuck in a loop: "Plan" -> "Execute" -> "Error" -> "Re-Plan" -> "Execute" -> "Error"...
*   **Constraint:** The only limits are `recursion_limit` (technical stack depth) and potentially the user noticing and manually stopping it.
*   **Billing:** If the user steps away for coffee, they might come back to a $50 OpenAI bill.

### Expected Behavior ("The Circuit Breaker")
*   **Mechanism:**
    1.  **Tracking:** Every node execution updates `state.usage_stats` (token counts / estimated cost).
    2.  **Config:** The root graph accepts a `budget_config` (e.g., `{ "max_cost": 2.00, "max_steps": 50 }`).
    3.  **Enforcement:** The same "Pre-Flight Check" from Zombie Pruning also checks `current_cost > max_cost`.
*   **Outcome:**
    *   If the limit is hit, the graph performs a **Tier 3 Interrupt**.
    *   UI message: *"Budget Limit Reached ($2.00). Resume to authorize more spend?"*
*   **Benefit:** Gives users (especially Enterprise managers) confidence to let the agents run autonomously.
