# Self-Spawn Agents: High Level Architecture Design Document

**Version:** 1.0
**Date:** 2026-02-08
**Status:** Living Document

## 1. Executive Summary

The **Self-Spawn Agents** system is a production-ready agentic orchestration platform designed to handle complex, multi-step tasks through recursive decomposition and dynamic execution. It leverages a graph-based architecture to break down high-level user goals into atomic subtasks, executes them in parallel or sequentially, and synthesizes the results into a coherent output.

Key capabilities include:
-   **Dynamic Graph Generation:** Compiles custom execution graphs at runtime based on task requirements.
-   **Recursive Decomposition:** Spawns lightweight "Native Worker Subgraphs" for complex sub-problems, supporting multi-level hierarchy (Depth 0 → 1 → 2 → 3).
-   **Self-Healing & Safety:** Implements "Zombie Branch Pruning" to stop failed parallel branches and "Budget Caps" to control costs.
-   **Time Travel & Human-in-the-Loop:** Allows users to rewind, fork, and replay execution threads from any state.
-   **Secure Execution:** Runs Python code in isolated E2B sandboxes.

## 2. System Architecture

The system follows a modular, graph-based architecture powered by **LangGraph**. The core orchestrator manages the flow of data between specialized agents, while a native worker subgraph handles recursive execution.

```mermaid
graph TB
    subgraph "Orchestrator Level (Root)"
        User[User Input] --> Splitter[Semantic Splitter]
        Splitter --> Supervisor[Supervisor Agent]
        Supervisor --> Compiler[Dynamic Graph Compiler]
        Compiler --> Synthesizer[Synthesizer Agent]
        Synthesizer --> Output[Final Output]
    end

    subgraph "Dynamic Execution (Compiler)"
        Compiler -->|Compiles & Runs| Nodes[Execution Nodes]
        Nodes -->|Simple Task| Worker[Generic Worker]
        Nodes -->|Complex Task| Subgraph[Worker Subgraph]
    end

    subgraph "Native Worker Subgraph"
        Subgraph --> Analyze[Complexity Analysis]
        Analyze -->|Simple| Direct[Direct Execution]
        Analyze -->|Complex| MiniPlan[Mini-Orchestrator]
        MiniPlan -->|Parallel| Workers[Parallel Workers]
        Workers -->|Recursive| RecursiveSubgraph[Recursive Subgraph]
        Direct --> Validate[Validator]
        Workers --> Validate
    end

    subgraph "Safety & Persistence"
        State[Postgres State Store]
        Pruner[Zombie Pruner]
        Budget[Budget Enforcer]
    end

    Nodes -.->|Checkpoints| State
    Nodes -.->|Signal| Pruner
    Nodes -.->|Usage| Budget
```

## 3. Core Modules

The system is composed of several distinct modules, each responsible for a specific phase of the agentic lifecycle.

### Module 1: Semantic Intent Analysis
-   **Component:** `SemanticSplitter`
-   **Role:** Decomposes user prompts into structured `SubtaskList` objects.
-   **Function:**
    -   Analyzes user intent.
    -   Breaks down abstract goals into concrete steps.
    -   Optimizes subtasks for search retrieval.

### Module 2: Supervisor & Graph Planning
-   **Component:** `SupervisorAgent`
-   **Role:** Plans the execution strategy.
-   **Function:**
    -   Maps subtasks to specific agent roles (Researcher, Coder, Orchestrator).
    -   Generates a dependency graph (Blueprint).
    -   Identifies parallel vs. sequential tasks.

### Module 3: Dynamic Graph Compiler
-   **Component:** `GraphCompiler`
-   **Role:** Builds and executes the runtime graph.
-   **Function:**
    -   Translates the Blueprint into an executable `StateGraph`.
    -   Manages node execution and state transitions.
    -   Enforces safety checks (Zombie Pruning, Global Signals).

### Module 4: Native Worker Subgraph
-   **Component:** `WorkerSubgraph`
-   **Role:** Efficiently executes subtasks.
-   **Function:**
    -   **Smart Complexity Detection:** Uses heuristics and LLM to decide if a task needs decomposition.
    -   **Mini-Orchestration:** Creates mini-plans for complex tasks (2-4 parallel workers).
    -   **Recursive Spawning:** Spawns child subgraphs for deeply nested tasks.
    -   **Context Compression:** Automatically compresses results using density-aware summarization before returning to parent.
    -   **Direct Execution:** Handles simple tasks with minimal overhead.

### Module 5: Synthesis & Delivery
-   **Component:** `SynthesizerAgent`
-   **Role:** Aggregates results.
-   **Function:**
    -   Combines outputs from all nodes.
    -   Generates the final markdown report.
    -   Ensures the response answers the original user prompt.

### Module 6: Safety & Escalation
-   **Components:** Logic for Pruning, Budgets, and Persistence.
-   **Function:**
    -   **Zombie Branch Pruning:** Kills sibling branches if one fails critically.
    -   **Budget Caps:** Enforces `max_cost` and `max_steps` limits.
    -   **Atomic Persistence:** Saves state after every node using Postgres (`AsyncPostgresSaver`).

## 4. Data Flow & State Management

The system uses a shared `AgentState` to maintain context across the graph.

### AgentState Schema
```python
class AgentState(TypedDict):
    task: str           # Original user prompt
    subject: str        # Drift prevention context
    subtasks: List[str] # Decomposed steps
    graph_plan: Dict    # Execution blueprint
    results: Dict       # Key-value store of node outputs
    depth: int          # Recursion level
    synthesis: str      # Final output
    # Safety & HITL
    inner_thread_id: str
    global_signal: str  # e.g., "INTERRUPT"
    usage_stats: Dict   # Cost tracking
    budget_config: Dict # Limits
    blueprint_id: str
```

### Execution Flow
1.  **Input:** User provides a task.
2.  **Analysis:** `SemanticSplitter` creates subtasks.
3.  **Planning:** `Supervisor` creates a generic graph plan.
4.  **Compilation:** `GraphCompiler` converts the plan into a `StateGraph`.
5.  **Execution:** Nodes run, potentially spawning `WorkerSubgraph` for recursion.
6.  **Validation:** Outputs are validated and refined.
7.  **Synthesis:** Results are compiled and returned to the user.

## 5. Key Features & Capabilities

### 5.1 Recursive Decomposition (Native Subgraphs)
Instead of spawning full orchestrators, the system uses lightweight "Native Worker Subgraphs".
-   **Benefits:** Reduces latency (60-70%), lowers cost, and provides unified tracing.
-   **Mechanism:** `should_decompose` checks task complexity. If complex, `create_mini_plan` generates parallel sub-workers.

### 5.2 Time Travel & Human-in-the-Loop
-   **State Hydration:** Ability to clone past runs into new threads.
-   **Surgical Rewind:** Invalidate specific nodes and replay from that point (Fork & Rewind).
-   **Interrupt Bubbling:** Inner graph pauses propagate to the root level.

### 5.3 Safety Mechanisms
-   **Zombie Pruning:** Prevents token waste by stopping parallel branches when a sibling fails.
-   **Budget Enforcer:** Strict cost limits with 100% parity between state and cost tracker.

### 5.4 Context Engineering
-   **Instructional Architecture:** XML-tagged prompts (`<role>`, `<objective>`, `<constraints>`).
-   **Context Compression:** Pruning, Extraction, Scrubbing, and Refinement to manage token limits.

## 6. Technology Stack

-   **Backend:** Python, FastAPI
-   **Orchestration:** LangGraph, LangChain
-   **Runtime:** AsyncIO
-   **Sandboxing:** E2B Code Interpreter
-   **Persistence:** PostgreSQL (AsyncPostgresSaver)
-   **Frontend:** React (for Visualization)

## 7. Future Roadmap (Phase 3)

-   **System Stress Testing:** Validate Postgres persistence under high load.
-   **UI Refinement:** Polish the "Developer" UI for broader use.
-   **Deployment:** Finalize Docker configuration and production deployment pipeline.

## 8. Current State Assessment (Industry Standard Analysis)

**Maturity Level:** **Level 3 - High-Fidelity Pilot**
*(System is functional, reliable, and capable of complex tasks, but lacks enterprise-grade optimization and long-term memory.)*

### Architectural Quality Attributes

| Attribute | Status | Details |
| :--- | :--- | :--- |
| **Reliability** | 🟢 **High** | **Atomic Persistence** (Postgres) ensures no data loss. **Zombie Pruning** prevents runaway processes. **Isolation** via E2B sandboxes protects the host. |
| **Observability** | 🟢 **High** | **Distributed Tracing** (LangSmith) provides deep visibility. **Real-time Cost Tracking** (8-decimal precision) offers financial transparency. **Visualizer** renders live graph states. |
| **Maintainability** | 🟢 **High** | **Modular Architecture** (Graph Compiler, Native Subgraphs) allows easy extension. **TypedDict** state schemas ensure type safety. |
| **Scalability** | 🟡 **Moderate** | **AsyncPostgresSaver** enables concurrency, but **System Stress Testing** under high load is pending. Rate limiting logic is basic. |
| **Performance** | 🟡 **Moderate** | **Native Subgraphs** reduced latency by 60%, but lack of **Blueprint Caching** means redundant planning for recurring tasks. |
| **Intelligence** | 🟡 **Moderate** | Excellent procedural reasoning, but lacks **Semantic Long-Term Memory** (no cross-run learning). |

## 9. Gap Analysis & Roadmap to "Next Level" (Enterprise Production)

To achieve **Level 4 (Enterprise Production)**, the following architectural gaps must be closed.

### 9.1 The "Memory Gap" (Critical)
*   **Current State:** Agents start "fresh" every run. They cannot learn from past mistakes or reuse successful strategies.
*   **Target State:** **Semantic Long-Term Memory (Vector DB)**.
*   **Implementation:**
    *   Integrate a Vector Database (Pinecone/Weaviate).
    *   Implement `KnowledgeStore` to index successful Blueprints.
    *   Allow Supervisor to query "How did we solve this last time?" before planning.

### 9.2 The "Optimization Gap"
*   **Current State:** Every task triggers a full planning phase, even for identical requests.
*   **Target State:** **Cross-Run Blueprint Caching**.
*   **Implementation:**
    *   Hash task intents.
    *   Retrieve cached Blueprints for high-confidence matches (>0.85 similarity).
    *   Skip the expensive "Supervisor" LLM call for known tasks.


### 9.3 The "Infrastructure Gap"
*   **Current State:** Functional `docker-compose` for dev, but unverified for high-concurrency production.
*   **Target State:** **Production-Hardened Infrastructure**.
*   **Implementation:**
    *   Load testing with simulated multi-user traffic.
    *   Kubernetes (K8s) manifests for horizontal scaling of worker nodes.
    *   Secret management vault integration.
