# Strategic GTM Roadmap & Implementation Plan

This plan addresses the critical deficiencies and pending items identified across the GTM Viability Assessment and State of Play reports. The system is currently at **Level 3 (High-Fidelity Pilot)**, and these changes are required to reach **Level 4 (Enterprise Production)**.

## Pending Item List (Level 4 Implementation)

- [x] **1. Deterministic Heuristic Fragility (SPI Risk) & Rate Limit Stability**
    *   **Goal:** Replace brittle Regex/Keyword logic with Semantic Classification and fix 429 errors.
    *   **Action:** Deployed `ComplexityClassification` model using `llm_mini`. Implemented Global Semaphore and Exponential Backoff (`safe_ainvoke`) to handle increased fan-out traffic.
    *   **Derived from:** [Critical Efficiency Feedback] & [Rate Limit Analysis]

- [x] **2. Production Persistence (Infrastructure)**
    *   **Goal:** Eliminate database lock contentions in recursive parallel executions.
    *   **Action:** Migrated from SQLite to PostgreSQL with connection pooling (psycopg_pool) and standard LangGraph schema (`checkpoint_writes`). implemented in [checkpointer.py](file:///d:/Git/self-spawn-agents/backend/core/persistence/checkpointer.py) and [init_db.py](file:///d:/Git/self-spawn-agents/backend/database/init_db.py).
    *   **Derived from:** [GTM Viability Assessment.md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/GTM%20Viability%20Assessment.md#L47)

- [ ] **3. Semantic Long-Term Memory (Memory Tier)**
    *   **Goal:** Enable cross-run knowledge retrieval to reduce redundant compute.
    *   **Action:** Implement `KnowledgeStore` class in `backend/core/knowledge.py` using a vector database (Pinecone/Weaviate). Support `search_blueprint` and `archive_blueprint` methods.
    *   **Derived from:** [State of Play Level 3 (High Fidelity Pilot).md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/State%20of%20Play%20Level%203%20(High%20Fidelity%20Pilot).md#L39)

- [ ] **4. Cross-Run Blueprint Caching (Optimization)**
    *   **Goal:** Reduce latency and cost by reusing successful graph topologies.
    *   **Action:** Integrate `KnowledgeStore` into `supervisor_agent.py`. Search for existing blueprints by hashing task intent before initiating new decomposition.
    *   **Derived from:** [State of Play Level 3 (Autonomous Orchestration).md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/State%20of%20Play%20Level%203%20(Autonomous%20Orchestration).md#L28)

- [ ] **5. Recursive Context Management (Reliability)**
    *   **Goal:** Prevent "Context Bloat" and token limit saturation at depth.
    *   **Action:** Add a `summarize_execution` node to `worker_subgraph.py` return path. Create `backend/graph/prompts/summary_prompts.py` to drive density-aware result compression.
    *   **Derived from:** [State of Play Level 3 (High Fidelity Pilot).md](file:///d:/Git/self-spawn-agents/ReadMe/To%20Do/State%20of%20Play%20Level%203%20(High%20Fidelity%20Pilot).md#L35)

- [x] **6. Context Engineering & Prompt Quality (Global)**
    *   **Goal:** Improve agent performance and reliability via best-practice prompting.
    *   **Action:** Deployed "Tagged Prompt" pattern and "Instructional Architecture" across all agents; enforced Forced CoT and standardized context injection in graph compiler.
    *   **Derived from:** [User Request]



---

## Proposed Changes

### [Backend]

#### [NEW] [checkpointer.py](file:///d:/Git/self-spawn-agents/backend/core/persistence/checkpointer.py) & [init_db.py](file:///d:/Git/self-spawn-agents/backend/database/init_db.py)
*   **Belongs to:** 2. Production Persistence (Infrastructure).
*   **Description:** Implemented `AsyncPostgresSaver` with connection pooling to replace SQLite. Used official LangGraph `setup()` to initialize standard schema (checkpoints, checkpoint_writes). Ensures stable concurrency for parallel recursive nodes.

#### [NEW] [knowledge.py](file:///d:/Git/self-spawn-agents/backend/core/knowledge.py)
*   **Belongs to:** 3. Semantic Long-Term Memory & 4. Cross-Run Blueprint Caching.
*   **Description:** Centralized interface for Vector DB interactions. Implements semantic search for existing blueprints and archiving of successful execution paths. Requires `text-embedding-3-small` for task intent vectorization.

#### [NEW] [summary_prompts.py](file:///d:/Git/self-spawn-agents/backend/graph/prompts/summary_prompts.py)
*   **Belongs to:** 5. Recursive Context Management.
*   **Description:** XML-structured prompts for the "Technical Editor" persona. Defines compression rules to reduce raw tool outputs to dense, validated summaries before propagating to parent states.

#### [MODIFY] [supervisor_agent.py](file:///d:/Git/self-spawn-agents/backend/agents/supervisor_agent.py)
*   **Belongs to:** 4. Cross-Run Blueprint Caching (Optimization).
*   **Description:** Injected logic to query `KnowledgeStore` during the planning phase. If a high-confidence blueprint match (>0.85 similarity) is found, the generation step is bypassed in favor of the cached topology.

#### [MODIFY] [worker_subgraph.py](file:///d:/Git/self-spawn-agents/backend/agents/subgraphs/worker_subgraph.py)
*   **Belongs to:** 5. Recursive Context Management.
*   **Description:** Inject the `summarize_results` node as the mandatory exit point for all subgraphs. Ensures that the `results` key passed to the parent is always condensed.

#### [MODIFY] All Agent Prompt Definitions
*   **Belongs to:** 6. Context Engineering & Prompt Quality (Global).
*   **Description:** Systematic upgrade of all prompts to adhere to the `context_engineering_strategy.md`. Implemented XML tagging, isolated static instructions in `SystemMessage`, and dynamic task data in `HumanMessage`. Verified 100% compliance across orchestration and reliability nodes.



