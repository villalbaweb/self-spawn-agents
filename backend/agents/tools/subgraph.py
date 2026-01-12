from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
import json

@tool
async def spawn_subgraph(task: str, depth: int = 0) -> str:
    """
    Spawns a recursive instance of the Agent Orchestrator to solve a complex sub-problem.
    Use this tool when a task is too complex to solve directly and requires further decomposition.
    
    Args:
        task (str): The high-level description of the sub-problem to solve.
        depth (int): Current recursion depth. DO NOT SET THIS MANUALLY - IT IS INJECTED AUTOMATICALLY.
        
    Returns:
        str: A summary of the results from the recursive execution.
    """
    from agent import app_graph # Import here to avoid circular dependencies
    from agents.dependencies import MAX_RECURSION_DEPTH, llm_mini
    
    print(f"🔄 Spawning Recursive Subgraph for: {task} (Depth: {depth})")
    print(f"🔧 [SpawnSubgraph] Input depth: {depth}")

    if depth >= MAX_RECURSION_DEPTH:
        msg = f"""⛔ DEPTH LIMIT REACHED (depth={depth}, max={MAX_RECURSION_DEPTH}).

CRITICAL INSTRUCTION: DO NOT call spawn_subgraph again. The recursion limit has been reached.
You MUST complete your current task directly without delegating to sub-agents.
Provide your best answer using only the information and capabilities you have now."""
        print(msg)
        return msg
    
    initial_state = {
        "task": task,
        "subtasks": [],
        "graph_plan": {},
        "results": {},
        "depth": depth + 1,
        "subject": ""  # Will be extracted by semantic_splitter
    }
    
    try:
        # Run the full orchestrator recursively
        final_state = await app_graph.ainvoke(initial_state)
        
        results = final_state.get("results", {})
        subtasks = final_state.get("subtasks", [])
        subject = final_state.get("subject", "")
        
        # --- FIX 3: VALIDATE RESULTS RELEVANCE ---
        validation_result = await _validate_results(task, subject, results, llm_mini)
        
        # Summarize output
        summary = {
            "subtasks_executed": subtasks,
            "results": results,
            "validation": validation_result
        }
        
        if validation_result.get("is_valid", True) == False:
            print(f"⚠️ Validation Warning: {validation_result.get('issues', [])}")
        
        return json.dumps(summary, indent=2)
        
    except Exception as e:
        return f"Error in recursive subgraph: {str(e)}"


async def _validate_results(task: str, subject: str, results: dict, llm) -> dict:
    """
    Validates that recursive results are relevant to the original task and subject.
    Uses a fast LLM call to check for semantic drift.
    """
    if not results:
        return {"is_valid": False, "issues": ["No results produced"]}
    
    # Concatenate result snippets for validation
    result_snippets = []
    for node_id, output in results.items():
        snippet = output[:500] if len(output) > 500 else output
        result_snippets.append(f"{node_id}: {snippet}")
    
    results_text = "\n".join(result_snippets)
    
    validation_prompt = f"""<role>Quality Validator</role>
<objective>Check if the results are relevant to the original task and subject.</objective>
<task>
Original Task: {task}
Expected Subject: {subject}

Results Summary:
{results_text}

Answer with a JSON object:
{{"is_valid": true/false, "issues": ["list of issues if any"], "confidence": 0.0-1.0}}

is_valid should be FALSE if:
- Results discuss a completely different topic than the subject
- Key parts of the task were not addressed
- Data is incomplete or placeholder text like "(to be researched)"
</task>"""

    try:
        messages = [
            SystemMessage(content="You are a strict quality validator. Output ONLY valid JSON."),
            HumanMessage(content=validation_prompt)
        ]
        response = await llm.ainvoke(messages)
        
        # Parse response
        content = response.content.strip()
        # Handle markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        
        return json.loads(content)
    except Exception as e:
        print(f"⚠️ Validation parsing failed: {e}")
        return {"is_valid": True, "issues": [], "confidence": 0.5, "parse_error": str(e)}
