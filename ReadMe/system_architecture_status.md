# Self-Spawn Agents: System Architecture & Module Status

**Date:** 2026-01-19
**Overall Status:** Phase 1 Complete (Core Functionality Operational).
**Current Focus:** Phase 2 (Robustness, Safety, Productization).

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

### Module 4: Recursive Subgraph Architecture
*   **Status:** ✅ **Operational**
*   **Core Component:** `spawn_subgraph` tool / Recursive Orchestrator.
*   **Function:** Allows any node to become a "parent" and spawn a child graph for sub-problems.
*   **Current Capabilities:**
    *   Multi-level depth handling (Root -> Backend -> Auth Service).
    *   **Pending Phase 2:** Refactoring `spawn_subgraph` to a native LangGraph node for better state visibility.

### Module 5: Quality Assurance & Sandboxing (Modules 4.5 & 5.5)
*   **Status:** ✅ **Operational**
*   **Core Components:** E2B Sandbox, Validator Agents.
*   **Function:** Ensures code runs safe and outputs meet quality standards.
*   **Current Capabilities:**
    *   Safe Python execution via E2B.
    *   "Search Refinement" loop for missing information.

### Module 6: 3-Tier Escalation Protocol
*   **Status:** ⚠️ **Partially Operational**
*   **Core Component:** Confidence Scoring Logic.
*   **Function:** Handles errors based on severity (Retry, Warn, Pause).
*   **Current Capabilities:**
    *   Tier 1 (Autonomous Retry): Working.
    *   Tier 2 (Soft Warning): Internally logs, but needs UI visibility (Phase 2).
    *   Tier 3 (Hard Interrupt): Pauses execution on Critical failure.
    *   **Operational:** *Zombie Branch Pruning* (Stopping sibling branches via Global Signals implemented & verified during Budget Logic tests).
    *   🔴 **Missing for Full Operation:** Frontend UI to display Tier 2 "Soft Warnings" to the user (currently only logs internally).

### Module 7: Blueprinting & Visualization
*   **Status:** ✅ **Operational**
*   **Core Component:** React Visualizer + SSE.
*   **Function:** Renders the live agent graph to the user.
*   **Current Capabilities:**
    *   Standardized `GraphBlueprint` JSON emission.
    *   Live node status updates (Running, Success, Error).

### Module 8: Interactive Refinement (Human-in-the-Loop)
*   **Status:** ⚠️ **Partially Operational** (Alpha)
*   **Core Component:** Interrupt Bubbling & State Injection.
*   **Function:** Allows users to modify execution mid-flight.
*   **Current Capabilities:**
    *   Interrupt Bubbling: Inner graph interrupts propagate to root.
    *   Resume with verified Checkpoint Lookup (using `inner_thread_id`).
    *   🔴 **Missing for Full Operation:** *Node-Specific Invalidations* (Granular re-execution of specific nodes without full rewind) and *State Hydration* (Forking from arbitrary state).

---

## Technical Summary
The system acts as a **Recursive, Human-in-the-Loop Agentic Workflow Engine**. 
Phase 1 established the "Happy Path" and basic intervention capabilities. 
Phase 2 (Current Work) is focused on hardening Module 6 (Safety/Pruning) and expanding Module 8 (Time Travel/Forking) to make the system commercially viable and cost-efficient.
