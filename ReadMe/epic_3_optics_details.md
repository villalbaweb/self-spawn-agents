# Epic 3: User Optics & Polish - Detailed Steps

This document details the components of **Epic 3: User Optics & Polish**, contrasting the current system behavior with the expected behavior to enhance transparency and trust.

---

## 3.1 Visual Warning Indicators (Tier 2 Visibility) - [IMPLEMENTED]

**Objective:** Expose "Soft Warnings" (Tier 2 Interrupts) to the user in the UI without stopping execution, so they know *where* the model was unsure.

### Current Behavior ("The Silent Alarm")
*   **Mechanism:** When a Tier 2 event occurs (Confidence between 0.5 and 0.8), the backend logs a warning to the console/trace.
*   **User View:** The Node in the React Visualizer stays Green (Success) or Blue (Running).
*   **Risk:** The user assumes the output is 100% perfect. They might skip manual verification of a section that the model *knew* was shaky.
*   **Example:** A Researcher Agent finds 2/3 sources but marks the step as "Complete". The user sends the incomplete report to a client.

### Expected Behavior ("The Yellow Flag")
*   **Mechanism:**
    1.  **Backend:** The `AgentState` or `NodeOutput` includes a `warnings` list.
    2.  **SSE Streaming:** The `graph_update` event carries this warning metadata.
    3.  **Frontend:** The Node component in D3/React renders a **Yellow "!" Badge**.
*   **Interaction:**
    *   User sees a "Green Node with a Yellow Badge".
    *   Hovering/Clicking the node reveals the warning text: *"Confidence Low (60%): Could not verify source date."*
*   **Outcome:** The user trusts the system *more* because it admits weakness. They know exactly which parts to double-check.

---

## 3.2 Real-Time Cost Badge - [IMPLEMENTED]

**Objective:** Give users immediate feedback on the financial cost of their agentic run.

### Current Behavior ("The Taxometer Live")
*   **Mechanism:** **100% Cost Parity Achieved.** The `AgentState` now perfectly matches the global `CostTracker` and external traces (LangSmith).
*   **User View:** Live streaming cost badge in the header with 8-decimal precision.
*   **Outcome:** Token anxiety is eliminated with precise, real-time financial transparency.

### Expected Behavior ("The Taxometer UI")
*   **Mechanism:**
    1.  **Backend (COMPLETED):** Every LLM call execution (via LangChain callbacks) aggregates tokens used into `state.usage_stats`.
    2.  **Calculation (COMPLETED):** 100% accurate USD conversion for GPT-4o, GPT-4o-mini, and others including cached tokens.
    3.  **Frontend (COMPLETED):** A "Cost Badge" in the Header updates live via SSE with 8-decimal precision.
*   **Visual:** `Running... | $ COST $0.00620250` (Verified 100% parity with LangSmith).
*   **Outcome:**
    *   Reduces anxiety with exact financial feedback.
    *   Gamifies efficiency (users try to write better prompts to lower costs).
    *   Essential for B2B billing transparency and audit trails.
