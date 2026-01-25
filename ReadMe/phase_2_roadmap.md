# Self-Spawn Agents - Phase 2: Robustness & Productization

**Status:** Phase 1 (Core Engine) Complete. Moving to Phase 2 (Safety, Control, Efficiency).
**Objective:** Transform the "Self-Spawn" engine from a functional Alpha into a commercially viable, cost-safe Product.

## Epic 1: Safety Logic (The "Circuit Breakers")
## Epic 1: Safety Logic (The Brakes)
- [x] Atomic State Persistence (SQLite/Postgres)
- [x] Zombie Branch Pruning (Global Interrupt Signal)
- [x] Budget Caps & Limits (Prevent infinite spends)

## Epic 2: The Time Machine (Advanced HITL)
Focus: Allowing users to "Rewind", "Fork", and "Replay".
- [x] **2.1 State Hydrator (Blueprint -> State)** <!-- id: 3 -->
    - [x] Create `POST /hydrate` endpoint.
    - [x] Implement mapping logic: `GraphBlueprint` JSON -> LangGraph `StateSnapshot`.
    - [x] Verify "Forking" a run from a historical blueprint via UI and API.
- [x] **2.2 Node-Specific Invalidation** <!-- id: 4 -->
    - [x] Backend method to clear/invalidate specific node outputs on rewind.
    - [x] "⏪ Rewind" action available in the React Visualizer Inspector Panel.

## Epic 3: User Optics & Polish
Focus: Trust and Transparency.
- [x] **3.1 Visual Warning Indicators** <!-- id: 5 -->
    - [x] Update Backend to emit "Tier 2 Warnings" in SSE events.
    - [x] Update Frontend Node component to display Yellow Warning badges.
- [ ] **3.2 real-time Cost Badge** <!-- id: 6 -->
    - [ ] calculate estimated cost during execution.
    - [ ] streaming update to UI Header.

## Epic 4: Maintenance & Optimization
- [x] **4.1 Refactor Subgraph to Native LangGraph** <!-- id: 7 -->
    - [x] Created `backend/agents/subgraphs/` package with `WorkerState` and `worker_subgraph`.
    - [x] Replaced `app_graph.ainvoke()` recursion with native subgraph invocation.
    - [x] ~70% latency reduction per recursion level (2 LLM calls vs 4-5).
    - [x] Full state visibility and unified tracing.
