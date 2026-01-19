# Implementation Plan - Phase 2: Safety Logic

## Goal Description
Enhance the reliability and cost-efficiency of the Self-Spawn Agents engine by implementing robust safety mechanisms1.  **Atomic State Persistence:** Save state after *every* node execution to enable full crash recovery.
2.  **Zombie Branch Pruning:** Immediately stop parallel branches when one fails (Tier 3 Interrupt).
3.  **Budget Caps:** Enforce hard limits on cost/steps to prevent recursive runaways.

## Epic 1 Status: Completed ✅
- [x] **Atomic State Persistence**
    - [x] Replace `MemorySaver` with `AsyncSqliteSaver` (or Postgres).
    - [x] Ensure `thread_id` is persisted and resumable.
- [x] **Zombie Branch Pruning**
    - [x] Implement "Global Interrupt Signal" in `AgentState`.
    - [x] Add pre-flight checks to all Node execution functions.
- [x] **Budget Caps & Limits**
    - [x] Add `budget_config` to state.
    - [x] Implement token/cost tracking logic.

## User Review Required
> [!IMPORTANT]
> **Breaking Change:** The `AgentState` schema will undergo significant changes to include `interrupt_signals` and `budget_tracking`. Existing checkpoints may be incompatible.

> [!WARNING]
> **Zombie Pruning Behavior:** When a branch is pruned, its partial work is discarded. This is by design to save tokens, but users should be aware that "Pause and Resume" might mean "Pause and Restart Sibling".

## Proposed Changes

### Backend Core (`backend/agents`)

#### [MODIFY] [state.py](file:///d:/Git/self-spawn-agents/backend/agents/state.py)
*   Add `GlobalSignal` class/dict to `AgentState`.
*   Add `token_usage` (dict) and `budget_config` (dict) to `AgentState`.

#### [MODIFY] [graph_compiler.py](file:///d:/Git/self-spawn-agents/backend/agents/graph_compiler.py)
*   **Atomic Persistence:**
    *   Configure the compiled `StateGraph` to use a `checkpointer` with `recursion_limit` and proper persistence settings.
    *   Verify `compile(checkpointer=memory)` usage.
*   **Zombie Pruning:**
    *   Inject a `CheckSignal` node or logic at the start of *every* node wrapper.
    *   If `state.feature_flags['global_interrupt']` is active, raise `GraphInterrupt` immediately.

#### [MODIFY] [orchestrator.py](file:///d:/Git/self-spawn-agents/backend/agents/orchestrator.py)
*   Implement `budget_check` logic before spawning new sub-agents.
*   Update `monitor_execution` to listen for Global Signals.

### Backend API (`backend/api`)

#### [MODIFY] [routes.py](file:///d:/Git/self-spawn-agents/backend/api/routes.py)
*   Update `/run` endpoint to accept `budget_limit` in the request body.

## Verification Plan

### Automated Tests
*   `test_zombie_pruning.py`:
    1.  Create a graph with 2 parallel nodes: `FastSuccess` and `SlowFail`.
    2.  `SlowFail` triggers a Tier 3 interrupt.
    3.  Verify `FastSuccess` (if not done) or a 3rd sibling `SlowSuccess` is stopped immediately.
*   `test_persistence.py`:
    1.  Run a graph 50% through.
    2.  Kill process (simulate crash).
    3.  Reload from checkpoint.
    4.  Verify execution resumes exactly at the next node.

### Manual Verification
*   **Visualizer Check:** Run a complex query, manually trigger an interrupt in a sub-agent. Watch sibling nodes turn "Gray/Paused" instead of "Green/Running".
