# Self-Spawn Agents: System Architecture & Module Status

**Date:** 2026-01-22
**Overall Status:** Phase 2 Backend Logic Complete.
**Current Focus:** Phase 2 UI/Optics (User Warning Badges & Cost Visualization).

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

### Module 4: Recursive Subgraph Architecture
*   **Status:** ✅ **Operational**
*   **Core Component:** `spawn_subgraph` tool / Recursive Orchestrator.
*   **Function:** Allows any node to become a "parent" and spawn a child graph for sub-problems.
*   **Current Capabilities:**
    *   Multi-level depth handling (Root -> Backend -> Auth Service).
    *   **New:** Inherits budget configs and safety signals from parent.

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
    *   Tier 2 (Soft Warning): Internally logs `low_confidence_flag`. UI badge pending.
    *   Tier 3 (Hard Interrupt): Pauses execution on Critical failure.
    *   **Zombie Branch Pruning:** Active. Fails in one branch immediately auto-stop parallel siblings to save tokens.
    *   **Budget Caps:** Active. Graphs respect `max_cost` and `max_steps` configs.

### Module 7: Blueprinting & Visualization
*   **Status:** ✅ **Operational**
*   **Core Component:** React Visualizer + SSE.
*   **Function:** Renders the live agent graph to the user.
*   **Current Capabilities:**
    *   Standardized `GraphBlueprint` JSON emission.
    *   Live node status updates (Running, Success, Error).
    *   **Pending Phase 2b:** Tier 2 Warning Badges (Yellow "!" for low confidence).
    *   **Pending Phase 2b:** Real-time Cost Badge ($) in Header.

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
- **Safety:** Atomic persistence, Zombie Pruning, and Budget caps are enforced in the core graph loop.
- **Time Travel:** Users can Fork, Hydrate, and surgically Rewind execution threads.
**Next Steps:** Implement the UI overlays (Modules 6 & 8 Visuals) to expose these powerful backend features to the end user.
