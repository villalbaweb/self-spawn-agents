# Context Engineering Strategy for Agentic Applications

This document defines the architecture and strategy for managing LLM context, prompt engineering, and data refinement. These principles are designed to be applied universally across any multi-agent or single-agent system to ensure reliability, efficiency, and structured reasoning.

## 1. Instructional Architecture (The "Tagged Prompt" Pattern)

Standardizing prompt structure through XML-based tagging maximizes model adherence and maintains a clean separation between instructions, metadata, and user-provided data.

### Standard Tags
- `<role>`: Defines the persona, expertise, and behavioral tone.
- `<objective>`: A clear, single-sentence high-level goal.
- `<constraints>`: A checklist of technical, logical, and formatting rules.
- `<input_data>`: The specific scope of information the model must process.
- `<task>`: The precise action/operation the model should perform on the data.

> [!TIP]
> Use XML tags to encapsulate dynamic content. This prevents "instruction leakage" from noisy input data and helps the LLM distinguish between developer directives and external content.

---

## 2. Multistage Context Compression

To handle high-volume or noisy input data while remaining within token limits and optimizing cost, a tiered compression pipeline is essential.

### Pipeline Stages
| Stage | Technique | Result |
| :--- | :--- | :--- |
| **Pruning** | Metadata/Field Filtering | Removes irrelevant technical attributes from raw data structures. |
| **Extraction**| Structural Cleaning | Strips boilerplate, navigation, and non-essential artifacts. |
| **Scrubbing** | Token Truncation | Applies safety limits to prevent context window overflow. |
| **Refinement**| LLM Summarization | Converts large, unstructured fragments into a dense, structured format. |

---

## 3. Just-In-Time (JIT) Context Injection

Optimize performance and minimize "noise" by injecting context only at the specific node or step where it is actionable.

- **Dynamic Injection**: Fetch and inject supplementary data (e.g., API references, external research) only when the specific agent logic requires it.
- **Node-Level Caching**: Cache contextual data within a session or loop to avoid redundant external calls for similar operations.

---

## 4. Structural Reasoning (Forced CoT)

Ensure high-quality outputs by forcing the model to perform internal reasoning before generating final results.

- **Justification Fields**: Include a mandatory field in structured output schemas (e.g., JSON/Pydantic) that requires the model to explain its reasoning.
- **Reasoning-to-Result**: The act of verbalizing reasoning within the output structure improves the accuracy of subsequent scoring or categorization fields.

---

## 5. Future Optimizations

- **Context Window Monitoring**: Implement instrumentation to log token density and usage per request to identify bottlenecks.
- **Dynamic Truncation Algorithms**: Move from fixed limits to semantic-aware truncation (e.g., keeping the top/bottom of a document where most relevance usually resides).
- **Few-Shot Library Management**: Maintain a central repository of high-quality "Golden Examples" to be dynamically injected into prompts for complex reasoning tasks.
