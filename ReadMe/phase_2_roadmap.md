# Self-Spawn Agents - Phase 2: Robustness & Productization

**Status:** Phase 1 (Core Engine) Complete. Moving to Phase 2 (Safety, Control, Efficiency).
**Objective:** Transform the "Self-Spawn" engine from a functional Alpha into a commercially viable, cost-safe Product.

## Epic 1: Safety Logic (The "Circuit Breakers")
Focus: Preventing token waste and ensuring crash recovery.
- [ ] **1.1 Atomic State Persistence** <!-- id: 0 -->
    - [ ] Refactor `MemorySaver` usage to `post_node_hook` logic.
    - [ ] Verify `AgentState` is saved after *every* node execution, not just graph end.
- [ ] **1.2 Zombie Branch Pruning (Critical)** <!-- id: 1 -->
    - [ ] Add `global_signal` / `interrupt_active` flag to `DynamicState`.
    - [ ] Implement short-circuit checks at the start of every node execution.
    - [ ] Test parallel execution where one branch fails and the other stops.
- [ ] **1.3 Budget Caps & Limits** <!-- id: 2 -->
    - [ ] Implement global token tracking in `AgentState`.
    - [ ] Add `max_cost` or `max_steps` config to root graph.
    - [ ] Implement `BudgetExceededError` handling (Graceful Pause).

## Epic 2: The Time Machine (Advanced HITL)
Focus: Allowing users to "Rewind", "Fork", and "Replay".
- [ ] **2.1 State Hydrator (Blueprint -> State)** <!-- id: 3 -->
    - [ ] Create `POST /hydrate` endpoint.
    - [ ] Implement mapping logic: `GraphBlueprint` JSON -> LangGraph `StateSnapshot`.
    - [ ] Verify "Forking" a run from a historical blueprint.
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
