# Strategic GTM Roadmap & Implementation Plan

This plan addresses the critical deficiencies and pending items identified across the GTM Viability Assessment and State of Play reports. The system is currently at **Level 3 (High-Fidelity Pilot)**, and these changes are required to reach **Level 4 (Enterprise Production)**.

## Pending Items & Technical Breakdown

### 1. Production Persistence (Infrastructure)
**Goal:** Eliminate database lock contentions in recursive parallel executions.
*   **Item:** Migrate from SQLite to PostgreSQL.
*   **Derived from:** [GTM Viability Assessment.md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/GTM%20Viability%20Assessment.md#L47), [State of Play Level 3 (Autonomous Orchestration).md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/State%20of%20Play%20Level%203%20(Autonomous%20Orchestration).md#L20)
*   **Action:**
    *   Update [backend/agents/shared_memory.py](file:///d:/Git/self-spawn-agents/backend/agents/shared_memory.py) to support `AsyncPostgresSaver`.
    *   Provide a Docker Compose configuration for a local Postgres instance for development.

### 2. Semantic Long-Term Memory (Memory Tier)
**Goal:** Enable cross-run knowledge retrieval to reduce redundant compute.
*   **Item:** Integrate Vector Store (KnowledgeStore).
*   **Derived from:** [State of Play Level 3 (High Fidelity Pilot).md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/State%20of%20Play%20Level%203%20(High%20Fidelity%20Pilot).md#L39), [State of Play Level 3 (Autonomous Orchestration).md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/State%20of%20Play%20Level%203%20(Autonomous%20Orchestration).md#L14)
*   **Action:**
    *   Implement a `KnowledgeStore` class using a vector database (e.g., Pinecone or local Chroma).
    *   Update `Researcher` nodes to upsert findings and `Supervisor` to query the store before planning.

### 3. Cross-Run Blueprint Caching (Optimization)
**Goal:** Reduce latency and cost by reusing successful graph topologies.
*   **Item:** Implement Blueprint Caching.
*   **Derived from:** [State of Play Level 3 (Autonomous Orchestration).md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/State%20of%20Play%20Level%203%20(Autonomous%20Orchestration).md#L28)
*   **Action:**
    *   Hash `SemanticSplitter` inputs and store successful `GraphBlueprints` in the vector store.
    *   Query the store before generation; hydrate existing blueprints if a similar match is found.

### 4. Recursive Context Management (Reliability)
**Goal:** Prevent "Context Bloat" and token limit saturation at depth.
*   **Item:** "Return-Trip" Summarization.
*   **Derived from:** [State of Play Level 3 (High Fidelity Pilot).md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/State%20of%20Play%20Level%203%20(High%20Fidelity%20Pilot).md#L35)
*   **Action:**
    *   Add a `summarization` node to [worker_subgraph.py](file:///d:/Git/self-spawn-agents/backend/agents/subgraphs/worker_subgraph.py)'s return path.
    *   Ensure child results are compressed before being merged into the parent's `WorkerState`.

### 5. Context Engineering & Prompt Quality (Global)
**Goal:** Improve agent performance and reliability via best-practice prompting.
*   **Item:** Prompt Refinement.
*   **Derived from:** [User Request](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/State%20of%20Play%20Level%203%20(Autonomous%20Orchestration).md#L3)
*   **Action:**
    *   Audit all agent system prompts (`supervisor`, `workers`, `synthesizer`).
    *   Enforce structured chain-of-thought, explicit constraint adherence, and better context injection.

---

## Proposed Changes

### [Backend]

#### [MODIFY] [shared_memory.py](file:///d:/Git/self-spawn-agents/backend/agents/shared_memory.py)
*   **Belongs to:** 1. Production Persistence (Infrastructure).
*   **Description:** Implement `AsyncPostgresSaver` integration to replace SQLite, ensuring stable concurrency for parallel recursive nodes.

#### [NEW] [knowledge_store.py](file:///d:/Git/self-spawn-agents/backend/agents/memory/knowledge_store.py)
*   **Belongs to:** 2. Semantic Long-Term Memory (Memory Tier) & 3. Cross-Run Blueprint Caching (Optimization).
*   **Description:** Create a new component for vector-based retrieval, enabling both discovery of previous research and reuse of successful task blueprints.

#### [MODIFY] [semantic_splitter.py](file:///d:/Git/self-spawn-agents/backend/agents/semantic_splitter.py)
*   **Belongs to:** 3. Cross-Run Blueprint Caching (Optimization).
*   **Description:** Integrate with `KnowledgeStore` to check for cached blueprints before initiating new graph decomposition.

#### [MODIFY] [worker_subgraph.py](file:///d:/Git/self-spawn-agents/backend/agents/subgraphs/worker_subgraph.py)
*   **Belongs to:** 4. Recursive Context Management.
*   **Description:** Add a dedicated summarization node to the return path of the subgraph to compress child outputs before they reach the root supervisor.

#### [MODIFY] All Agent Prompt Definitions
*   **Belongs to:** 5. Context Engineering & Prompt Quality (Global).
*   **Description:** Systematic update of prompts across [supervisor_agent.py](file:///d:/Git/self-spawn-agents/backend/agents/supervisor_agent.py), `generic_worker.py`, and [synthesizer.py](file:///d:/Git/self-spawn-agents/backend/agents/synthesizer.py) to enforce best-practice context engineering.
