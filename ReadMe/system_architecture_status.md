# Self-Spawn Agents: System Architecture & Module Status

**Date:** 2026-01-25
**Overall Status:** Phase 2 Complete (Backend & Optics).
**Current Focus:** Phase 3: Stabilization & GTM Polish.

## Module Breakdown

### Module 1: Semantic Intent Analysis
*   **Status:** ✅ **Operational**
*   **Core Component:** `SemanticSplitter` Agent.
*   **Function:** Decomposes wild user inputs into structured `SubtaskList` objects using LLMs.
*   **Current Capabilities:**
    *   Optimizes subtasks for search retrieval.
    *   Converts abstract goals (e.g., "Write a song") into concrete steps ("Identify genre", "Compose melody").

### Module 2: Supervisor & Graph Planning
*   **Status:** ✅ **Operational**
*   **Core Component:** `SupervisorAgent`.
*   **Function:** Maps subtasks to specific Agent Roles (Researcher, Coder, Orchestrator) and generates a dependency graph.
*   **Current Capabilities:**
    *   Produces a JSON-based **Execution Plan** (Blueprint).
    *   Defines rigid dependencies vs. parallelizable tasks.

### Module 3: Dynamic Graph Compiler
*   **Status:** ✅ **Operational**
*   **Core Component:** `GraphCompiler`.
*   **Function:** Reads the Execution Plan and constructs an executable `StateGraph` at runtime.
*   **Current Capabilities:**
    *   Supports arbitrary, non-hardcoded topologies.
    *   Handles parallel node execution based on the blueprint.
    *   **New:** Enforces Zombie Branch Pruning via Global Interrupt Signals.

### Module 4: Native Worker Subgraph Architecture
*   **Status:** ✅ **Operational (Refactored - Epic 4.1 Complete)**
*   **Core Component:** `WorkerSubgraph` (Native LangGraph Subgraph with Mini-Orchestration).
*   **Function:** Executes recursive sub-tasks with a lightweight flow, bypassing full orchestration.
*   **Current Capabilities:**
    *   Native LangGraph subgraph composition (`execute → validate`).
    *   **Smart complexity detection:** Heuristics + LLM classify task complexity via `should_decompose()`.
    *   **Mini-orchestration:** Complex tasks trigger `create_mini_plan()` → 2-4 parallel workers.
    *   **Recursive spawning:** Complex child tasks in mini-plan spawn their own subgraphs.
    *   **Multi-level hierarchy:** Supports depth 0 → 1 → 2 → 3 recursive decomposition.
    *   ~60-70% latency reduction per recursion level (2-6 LLM calls vs 5-8).
    *   Multi-level depth handling with inherited budget configs.
    *   Full state visibility in parent graph (unified tracing).
    *   **Safety preserved:** Zombie Pruning, Budget Caps, Depth Limits all enforced in subgraph.
    *   **Removed:** Legacy `spawn_subgraph` tool and `app_graph.ainvoke()` recursion.

### Module 5: Quality Assurance & Sandboxing (Modules 4.5 & 5.5)
*   **Status:** ✅ **Operational**
*   **Core Components:** E2B Sandbox, Validator Agents.
*   **Function:** Ensures code runs safe and outputs meet quality standards.
*   **Current Capabilities:**
    *   Safe Python execution via E2B.
    *   "Search Refinement" loop for missing information.

### Module 6: 3-Tier Escalation Protocol
*   **Status:** ✅ **Operational**
*   **Core Component:** Confidence Scoring Logic & Safety Enforcement.
*   **Function:** Handles errors based on severity (Retry, Warn, Pause) and enforces budgets.
*   **Current Capabilities:**
    *   Tier 1 (Autonomous Retry): Working.
    *   Tier 2 (Soft Warning): Internally logs `low_confidence_flag`. **UI badge Active.**
    *   Tier 3 (Hard Interrupt): Pauses execution on Critical failure.
    *   **Zombie Branch Pruning:** Active. Fails in one branch immediately auto-stop parallel siblings to save tokens.
    *   **Budget Caps:** ✅ **Operational (100% Parity).** Graphs respect `max_cost` and `max_steps` configs.
    *   **Persistence:** ✅ **Postgres (AsyncPostgresSaver).** Replaced SQLite for production readiness.

### Module 7: Blueprinting & Visualization
*   **Status:** ✅ **Operational**
*   **Core Component:** React Visualizer + SSE.
*   **Function:** Renders the live agent graph to the user.
*   **Current Capabilities:**
    *   Standardized `GraphBlueprint` JSON emission.
    *   Live node status updates (Running, Success, Error).
    *   **Active:** Tier 2 Warning Badges (Yellow "!" for low confidence).
    *   **Operational:** Real-time Cost Badge ($) in Header. (100% accurate live streaming with 8-decimal precision).

### Module 8: Interactive Refinement (Human-in-the-Loop)
*   **Status:** ✅ **Operational**
*   **Core Component:** Interrupt Bubbling & State Injection.
*   **Function:** Allows users to modify execution mid-flight or time-travel.
*   **Current Capabilities:**
    *   Interrupt Bubbling: Inner graph interrupts propagate to root.
    *   **State Hydration:** Fork from arbitrary state or clone existing runs via `/api/hydrate`.
    *   **Node-Specific Invalidation:** Surgical re-runs via "⏪ Rewind" (Fork & Invalidate).

---

## Technical Summary
The system acts as a **Recursive, Human-in-the-Loop Agentic Workflow Engine**.
Phase 2 Backend Logic is now **COMPLETE**.
- **Safety:** Atomic persistence (Postgres), Zombie Pruning, and Budget caps are enforced.
- **Time Travel:** Users can Fork, Hydrate, and surgically Rewind execution threads.

**Next Steps (Phase 3):**
1.  **System Stress Testing:** Verify Postgres under load.
2.  **UI Refinement:** Polish "Developer" UI for end-users.
3.  **Deployment:** Finalize Docker configuration for production.
