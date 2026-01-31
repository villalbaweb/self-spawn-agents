# Strategic GTM Roadmap & Implementation Plan

This plan addresses the critical deficiencies and pending items identified across the GTM Viability Assessment and State of Play reports. The system is currently at **Level 3 (High-Fidelity Pilot)**, and these changes are required to reach **Level 4 (Enterprise Production)**.

## Pending Item List (Level 4 Implementation)

- [ ] **1. Deterministic Heuristic Fragility (SPI Risk)**
    *   **Goal:** Replace brittle Regex/Keyword logic with Semantic Classification.
    *   **Risk:** Users phrasing complex tasks simply might fail to trigger decomposition.
    *   **Action:** Deploy a distilled, ultra-fast classifier to classify task complexity based on semantic intent.
    *   **Derived from:** [Critical Efficiency Feedback]

- [ ] **2. Production Persistence (Infrastructure)**
    *   **Goal:** Eliminate database lock contentions in recursive parallel executions.
    *   **Action:** Migrate from SQLite to PostgreSQL in [shared_memory.py](file:///d:/Git/self-spawn-agents/backend/agents/shared_memory.py).
    *   **Derived from:** [GTM Viability Assessment.md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/GTM%20Viability%20Assessment.md#L47)

- [ ] **3. Semantic Long-Term Memory (Memory Tier)**
    *   **Goal:** Enable cross-run knowledge retrieval to reduce redundant compute.
    *   **Action:** Implement `KnowledgeStore` class using a vector database (e.g., Pinecone or local Chroma).
    *   **Derived from:** [State of Play Level 3 (High Fidelity Pilot).md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/State%20of%20Play%20Level%203%20(High%20Fidelity%20Pilot).md#L39)

- [ ] **4. Cross-Run Blueprint Caching (Optimization)**
    *   **Goal:** Reduce latency and cost by reusing successful graph topologies.
    *   **Action:** Hash `SemanticSplitter` inputs and store successful `GraphBlueprints` in the vector store.
    *   **Derived from:** [State of Play Level 3 (Autonomous Orchestration).md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/State%20of%20Play%20Level%203%20(Autonomous%20Orchestration).md#L28)

- [ ] **5. Recursive Context Management (Reliability)**
    *   **Goal:** Prevent "Context Bloat" and token limit saturation at depth.
    *   **Action:** Add a `summarization` node to `worker_subgraph.py` return path to compress child results.
    *   **Derived from:** [State of Play Level 3 (High Fidelity Pilot).md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/State%20of%20Play%20Level%203%20(High%20Fidelity%20Pilot).md#L35)

- [x] **6. Context Engineering & Prompt Quality (Global)**
    *   **Goal:** Improve agent performance and reliability via best-practice prompting.
    *   **Action:** Deployed "Tagged Prompt" pattern and "Instructional Architecture" across all agents; enforced Forced CoT and standardized context injection in graph compiler.
    *   **Derived from:** [User Request]



---

## Proposed Changes

### [Backend]

#### [MODIFY] [shared_memory.py](file:///d:/Git/self-spawn-agents/backend/agents/shared_memory.py)
*   **Belongs to:** 2. Production Persistence (Infrastructure).
*   **Description:** Implement `AsyncPostgresSaver` integration to replace SQLite, ensuring stable concurrency for parallel recursive nodes.

#### [NEW] [knowledge_store.py](file:///d:/Git/self-spawn-agents/backend/agents/memory/knowledge_store.py)
*   **Belongs to:** 3. Semantic Long-Term Memory & 4. Cross-Run Blueprint Caching.
*   **Description:** Create a new component for vector-based retrieval, enabling both discovery of previous research and reuse of successful task blueprints.

#### [MODIFY] [semantic_splitter.py](file:///d:/Git/self-spawn-agents/backend/agents/semantic_splitter.py)
*   **Belongs to:** 4. Cross-Run Blueprint Caching (Optimization).
*   **Description:** Integrate with `KnowledgeStore` to check for cached blueprints before initiating new graph decomposition.

#### [MODIFY] [worker_subgraph.py](file:///d:/Git/self-spawn-agents/backend/agents/subgraphs/worker_subgraph.py)
*   **Belongs to:** 5. Recursive Context Management & 1. Deterministic Heuristic Fragility.
*   **Description:** 
    *   Add a dedicated summarization node to the return path of the subgraph.
    *   **Fix:** Replace regex-based `should_decompose` logic with a semantic classifier to improve reliability.

#### [MODIFY] All Agent Prompt Definitions
*   **Belongs to:** 6. Context Engineering & Prompt Quality (Global).
*   **Description:** Systematic upgrade of all prompts to adhere to the `context_engineering_strategy.md`. Implemented XML tagging, isolated static instructions in `SystemMessage`, and dynamic task data in `HumanMessage`. Verified 100% compliance across orchestration and reliability nodes.


