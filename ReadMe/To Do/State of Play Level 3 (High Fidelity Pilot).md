# AUDIT: Self-Spawn Agents Architecture
**Date:** 2026-01-29 | **Status:** Phase 2 Complete (Backend)

## State of Play
**Level 3: Operational Beta (High-Fidelity Pilot)**
 The architecture is sophisticated, utilizing advanced patterns (Dynamic Graph Compilation, Recursive Native Subgraphs, Time Travel). It surpasses standard linear chains but lacks the data governance and context optimization required for Level 4 (Enterprise Production). The move from tool-based recursion to native subgraphs (Epic 4.1) significantly improved TUE and SPI, but introduced brittle heuristics.

---

> **UPDATE (2026-02-08):** Use of `recursive_executor.py` and `result_summarizer.py` (Epic 5) resolved the **Recursive Context Bloat** deficiency.

---

## Critical Deficiencies (Red Flags)

**1. Deterministic Heuristic Fragility (SPI Risk)**
The `should_decompose` logic in the Native Worker Subgraph relies on **Keyword Matching** ("oauth", "step 1") and **Conjunction Counting**.
*   **Risk:** This is brittle technical debt. Users phrasing complex tasks simply (e.g., "Build a secure login") might fail to trigger decomposition because they lack specific keywords, while verbose simple tasks trigger unnecessary, costly recursion.
*   **Impact:** Inconsistent performance; false negatives lead to capability failure, false positives drain budget.

**2. Recursive Context Bloat (MCR Risk)**
The `WorkerState` aggregates `results` and `all_agents` and passes them up the chain. At `MAX_RECURSION_DEPTH = 3`, the root parent absorbs the raw verbose outputs of every grandchild and great-grandchild.
*   **Risk:** Context window saturation. The root "Synthesizer" will suffer from "Lost in the Middle" phenomena or hit token limits on complex runs.
*   **Impact:** Degradation of final report quality; exponential cost scaling on token input.

**3. Ephemeral Knowledge Silos (MCR Risk)**
The architecture handles *State* (short-term execution) perfectly via SQLite/Time Travel but lacks *Knowledge* (long-term retrieval).
*   **Risk:** Every run starts from zero knowledge. If a user runs "Research Competitor A" and later "Compare with Competitor B", the agent cannot retrieve insights from the first run without manual manual "Forking/Hydration".
*   **Impact:** Redundant compute spend; inability to build a compounding knowledge base.

---

## GTM Roadmap (Alpha → Production)

**Step 1: Replace Regex with Semantic Classification (Fixes SPI)**
*   **Action:** Deprecate the keyword/conjunction heuristic in `should_decompose`.
*   **Implementation:** Deploy a distilled, ultra-fast classifier (e.g., fine-tuned gpt-4o-mini or a local BERT model) to classify task complexity based on semantic intent, not string length.

**Step 2: Implement "Return-Trip" Summarization (Fixes MCR)**
*   **Action:** Enforce compression on the recursive return path.
*   **Implementation:** When a Child Subgraph finishes, it must run a `summarize_execution` node. The Parent graph receives a compressed `summary` + `key_artifacts`, not the full raw `results` dictionary. Raw logs stay in persistence for debugging; only insights travel up.

**Step 3: Integrate Semantic Vector Store (Fixes MCR)**
*   **Action:** Bridge the gap between isolated threads.
*   **Implementation:** Add a `KnowledgeStore` (Pinecone/Weaviate). Successful `Researcher` nodes should upsert findings to the vector DB. The `Supervisor` should query this DB before spawning new research nodes to deduplicate work.

---

## Synergy Score (CSS)
**88/100**
*   **High Marks:** Exceptional integration of Safety (Zombie Pruning) with Logic (Dynamic Graphs). The "Delta Pattern" for cost tracking across recursive depths is architecturally elegant.
*   **Deductions:** -7 for Brittle Heuristics, -5 for Context Management risks at depth.

**GTM Viability:** **BETA** (Requires Step 1 & 2 fixes before general release).