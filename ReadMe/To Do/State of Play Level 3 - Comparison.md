# COMPARISON AUDIT: Evolution from Beta to Pre-Production

**Summary:** The architecture has successfully graduated from **"Structural Fragility"** (Tool-based hacks) to **"Logic Optimization"** (Native Graphs). The execution of Epic 4.1 (Native Subgraph Refactor) directly addressed the most critical severity flag from the previous audit, resulting in a **+10 point Synergy Score jump (78 → 88)**.

The system has traded **Architecture Risk** (it might crash/blind spots) for **Logic Risk** (it might not trigger correctly).

---

## 1. Resolved Deficiencies (The "Green" Zone)

| Component | Previous Status (Red Flag) | Current Status (Resolved) | Impact Analysis |
| :--- | :--- | :--- | :--- |
| **Recursion Mechanism** | **"The Sub-Graph Hack"**<br>Used `spawn_subgraph` tool. Created observability black boxes and blinded the Zombie Pruner. | **Native LangGraph Subgraph**<br>Implemented `WorkerSubgraph`. Full state visibility, shared traces, and correct budget propagation. | **Critical Fix.** The "Budget Enforcer" and "Zombie Pruner" now function reliably at depth 2+ because the parent graph has direct visibility into child nodes. |
| **Observability** | **Opaque (ToolError)**<br>Failures inside recursion looked like generic tool errors. | **Transparent (Unified Trace)**<br>`all_agents` and `all_edges` bubble up. | **TUE Update:** Tool Utilisation Efficacy is now high fidelity. Debugging is possible across recursive boundaries. |

---

## 2. Evolved Risks (The "Yellow" Zone)

*The solution to the previous "Native Recursive Integration" roadmap item introduced new, subtler technical debt.*

### **A. The Heuristic Trap (New SPI Risk)**
*   **Previous:** The system struggled to *execute* recursion safely.
*   **Current:** The system executes recursion safely, but struggles to *decide* when to use it.
*   **Analysis:** The shift to Native Subgraphs relies on `should_decompose` (keyword matching/conjunction counting). This is a regression in decision intelligence compared to the previous (albeit brittle) LLM-driven tool selection. The architecture is now **Structurally Sound but Semantically Brittle**.

### **B. Data Payload Bloat (New MCR Risk)**
*   **Previous:** Child threads were isolated; data return was minimal/opaque.
*   **Current:** Full state visibility means `WorkerState` aggregates *everything*.
*   **Analysis:** Solving the "Black Box" created a "Loud Speaker" issue. Without a compression step (the "Return-Trip Summarization" in the new roadmap), the context window will flood exponentially with depth.

---

## 3. Persistent Deficiencies (The "Red" Zone)

*These issues were flagged previously and remain unaddressed.*

### **Context Amnesia (MCR Failure)**
*   **Previous:** "Lack of Semantic Long-Term Memory."
*   **Current:** "Ephemeral Knowledge Silos."
*   **Status:** **UNCHANGED.** The roadmap focused entirely on *Mechanism* (how to run) and ignored *Knowledge* (what was learned). The system is still purely episodic. The "Time Travel" feature helps within a run, but not *across* runs.

### **Persistence Scalability**
*   **Previous:** "Persistence Bottleneck (SQLite)."
*   **Current:** Docs still reference `shared_memory.py` and `AsyncSqliteSaver`.
*   **Status:** **UNCHANGED.** While sufficient for single-user testing, the "Zombie Branch Pruner" (which kills parallel siblings) creates race conditions that SQLite cannot handle under load. This remains a barrier to Level 4 Production status.

---

## Final Verdict: Trajectory Check

**Progress:** **Excellent.**
The team prioritized correctly. Fixing the structural integrity of recursion (Epic 4.1) was a prerequisite for any logic optimization. You cannot tune a car with a broken engine. The engine is now fixed.

**Next Pivot:**
You must now shift focus from **"Can it run?"** to **"Can it remember?"** and **"Can it scale?"**.
1.  **Kill the Keywords:** Replace the regex/keyword heuristics with a cheap classifier.
2.  **Add the Brain:** Implement the Vector Store (long-term memory).
3.  **Upgrade the DB:** Swap SQLite for Postgres before adding more users.