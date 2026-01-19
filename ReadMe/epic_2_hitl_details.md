# Epic 2: The Time Machine (Advanced HITL) - Detailed Steps

This document details the components of **Epic 2: The Time Machine**, contrasting the current system behavior with the expected behavior to enable advanced Human-in-the-Loop workflows.

---

## 2.1 State Hydrator (Blueprint -> State)

**Objective:** Allow users to "Fork" or "Clone" a previous run (including its plan and context) so they can try a different approach without re-typing everything or copy-pasting widely.

### Current Behavior ("The One-Way Ticket")
*   **Mechanism:** Users can "Retry" a node if it pauses *during* execution.
*   **Limitation:** Once a graph completes (Success or Failure) or if the user wants to take a completely different path from a historical run (e.g., "Run #43 from last Tuesday"), there is no mechanism to load that state back into memory.
*   **Workaround:** The user must manually look at the old logs, copy the prompt, start a *new* run, and hope it generates a similar plan.
*   **Data:** We have the `GraphBlueprint` JSON stored, but no way to turn it back into a live `LangGraph State`.

### Expected Behavior ("The Save Game")
*   **Mechanism:** Implement a `POST /hydrate` endpoint.
*   **Workflow:**
    1.  User views history, selects Run #43.
    2.  User clicks **"Fork this Run"**.
    3.  System takes the `GraphBlueprint` (or the persisted checkpoint) from Run #43.
    4.  System initializes a **NEW Thread ID** but pre-populates the `AgentState` with the exact variables (Plan, Context, Subtasks) from the moment *before* execution started (or from a specific snapshot).
    5.  User edits the "Goal" slightly (e.g., "Change the tone to formal") and hits Start.
*   **Outcome:** The agent skips the "Planning" phase (if desired) or re-plans based on the *exact same context* as before.
*   **Benefit:** Critical for A/B testing prompts and iterating on complex tasks.

---

## 2.2 Node-Specific Invalidation (Re-runs)

**Objective:** Allow surgical re-execution of specific parts of the graph without re-running the expensive upstream dependencies.

### Current Behavior ("The All-or-Nothing")
*   **Scenario:**
    1.  **Researcher Agent** spends $0.50 gathering data (Steps 1-10).
    2.  **Writer Agent** drafts a report (Step 11).
    3.  **Review:** User hates the *tone* of the report.
*   **Issue:** If the graph has finished (or if the user wants to change something *upstream*), they often have to re-run the whole thing.
*   **Partial Solution:** The configured `interrupt_before=["writer"]` allows pausing *before* the writer. But if the writer *already finished*, you can't easily say "Undo Step 11 and try again with this different instruction."

### Expected Behavior (" The Time Travel Undo")
*   **Mechanism:**
    1.  **UI Action:** User clicks on the **Writer Node** (which is Green/Success).
    2.  **Command:** Selects **"Invalidate & Re-run"**.
    3.  **Backend Logic:**
        *   Identifies the checkpoint associated with the *start* of the Writer Node.
        *   "Rewinds" the thread state to that checkpoint.
        *   (Optional) Updates the state with a **New Instruction** provided by the user (e.g., "Make it funnier").
        *   Resumes execution from that exact point.
*   **Outcome:** The expensive Research (Steps 1-10) is preserved. Only the Writer (Step 11) runs again.
*   **Benefit:** Massive improvement in "Time to Value" for the user and significant cost savings. The user iterates purely on the final generation step.
