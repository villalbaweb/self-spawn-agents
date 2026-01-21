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
- [ ] **2.2 Node-Specific Invalidation** <!-- id: 4 -->
    - [ ] Add backend method to clear/invalidate specific node outputs in state.
    - [ ] Expose "Re-run Node" action in the React Visualizer.

## Epic 3: User Optics & Polish
Focus: Trust and Transparency.
- [ ] **3.1 Visual Warning Indicators** <!-- id: 5 -->
    - [ ] Update Backend to emit "Tier 2 Warnings" in SSE events.
    - [ ] Update Frontend Node component to display Yellow Warning badges.
- [ ] **3.2 real-time Cost Badge** <!-- id: 6 -->
    - [ ] calculate estimated cost during execution.
    - [ ] streaming update to UI Header.

## Epic 4: Maintenance & Optimization
- [ ] **4.1 Refactor Subgraph to Native LangGraph** <!-- id: 7 -->
    - [ ] (Carried over) Complete existing refactor of `spawn_subgraph` to native integration.
