from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from agents.dependencies import llm
from agents.state import AgentState

async def synthesizer_node(state: AgentState) -> Dict[str, Any]:
    """
    Final synthesis node that compiles all results into a cohesive Markdown output.
    Ensures all deliverables are addressed.
    """
    task = state.get("task", "")
    subject = state.get("subject", "")
    results = state.get("results", {})
    deliverables = state.get("deliverables", [])
    
    print(f"📝 Synthesizing final output for: {subject}")
    print(f"📦 Required deliverables: {deliverables}")
    
    # Build context from all results
    results_context = []
    for node_id, output in results.items():
        # Truncate long outputs
        truncated = output[:3000] + "..." if len(output) > 3000 else output
        results_context.append(f"## {node_id}\n{truncated}")
    
    results_text = "\n\n".join(results_context)
    
    deliverables_text = ", ".join(deliverables) if deliverables else "a comprehensive summary"
    
    synthesis_prompt = f"""<role>Executive Report Writer</role>
<objective>Compile all research and execution results into a professional Markdown document.</objective>
<subject>{subject}</subject>
<deliverables_required>{deliverables_text}</deliverables_required>
<constraints>
- Output a well-structured Markdown document.
- Include ALL deliverables mentioned above as separate sections.
- If any deliverable was not addressed by the research, create a placeholder section noting it.
- Use headers (##), bullet points, and tables for clarity.
- Include an Executive Summary at the top.
- Be concise but comprehensive.
</constraints>

<input_data>
Original Task: {task}

Research Results:
{results_text}
</input_data>

<task>Create the final Markdown report addressing all deliverables.</task>"""

    messages = [
        SystemMessage(content="You are an expert report writer. Output clean, professional Markdown."),
        HumanMessage(content=synthesis_prompt)
    ]
    
    try:
        response = await llm.ainvoke(messages)
        
        # Check for missing deliverables in the output
        output = response.content
        missing = []
        for d in deliverables:
            if d.lower() not in output.lower():
                missing.append(d)
        
        if missing:
            print(f"⚠️ Synthesis may be missing deliverables: {missing}")
            output += f"\n\n---\n### ⚠️ Note: The following deliverables may need additional work:\n" + "\n".join(f"- {m}" for m in missing)
        
        print("✅ Synthesis complete.")
        return {"synthesis": output}
    except Exception as e:
        print(f"❌ Error in synthesizer_node: {e}")
        return {"synthesis": f"Error generating synthesis: {str(e)}"}
