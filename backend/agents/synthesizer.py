from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from agents.dependencies import llm
from agents.state import AgentState
from agents.cost import CostTrackingCallback, CostTracker

async def synthesizer_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Final synthesis node that compiles all results into a cohesive Markdown output.
    Uses results aggregated in previous steps.
    """
    task = state.get("task", "")
    subject = state.get("subject", "")
    results = state.get("results", {})
    deliverables = state.get("deliverables", [])
    
    print(f"📝 Synthesizing final output for: {subject}")
    print(f"📦 Required deliverables: {deliverables}")
    
    # Cost tracking setup
    task_id = config.get("configurable", {}).get("thread_id") if config else None
    cost_callback = CostTrackingCallback(task_id=task_id, node_name="synthesizer")
    llm_config: RunnableConfig = {"callbacks": [cost_callback]}
    
    # Build context from all results
    results_context = []
    for node_id, output in results.items():
        # Truncate long outputs
        truncated = output[:3000] + "..." if len(output) > 3000 else output
        results_context.append(f"## {node_id}\n{truncated}")
    
    results_text = "\n\n".join(results_context)
    
    deliverables_text = ", ".join(deliverables) if deliverables else "a comprehensive summary"
    
    synthesis_prompt = f"""<role>Professional Executive Report Writer</role>
<objective>Synthesize all research and execution results into a high-fidelity, professional Markdown document.</objective>

<input_data>
    <report_subject>
    {subject}
    </report_subject>
    <required_deliverables>
    {deliverables_text}
    </required_deliverables>
    <original_task>
    {task}
    </original_task>
    <execution_results>
    {results_text}
    </execution_results>
</input_data>

<constraints>
- Output a well-structured, professional Markdown document.
- **Deliverable Check**: Ensure EVERY item in <required_deliverables> is addressed in its own section.
- **Formatting**: Use headers (##), bullet points, and tables.
- **Structure**: Include a concise Executive Summary at the top.
- **Gaps**: If a deliverable is missing in <execution_results>, create a placeholder section explaining the limitation.
- **Tone**: Professional, objective, and technical.
</constraints>

<task>Create the final synthesis report based on the <execution_results>.</task>"""


    messages = [
        SystemMessage(content="You are a professional technical writer specialized in executive reports. Your goal is to provide clear, actionable, and well-structured documentation."),
        HumanMessage(content=synthesis_prompt)
    ]
    
    try:
        response = await llm.ainvoke(messages, config=llm_config)
        
        # Check for missing deliverables in the output (Fuzzy keyword check)
        output = response.content
        missing = []
        for d in deliverables:
            # Extract keywords (words > 3 chars)
            keywords = [word.lower() for word in d.split() if len(word) > 3]
            # If at least 50% of keywords are missing, consider it missing
            if keywords:
                found_count = sum(1 for k in keywords if k in output.lower())
                if found_count / len(keywords) < 0.5:
                    missing.append(d)
            elif d.lower() not in output.lower():
                # Fallback for very short deliverable strings
                missing.append(d)
        
        if missing:
            print(f"⚠️ Synthesis may be missing deliverables: {missing}")
            output += f"\n\n---\n### ⚠️ Note: The following deliverables may need additional work:\n" + "\n".join(f"- {m}" for m in missing)
        
        # Record costs to global tracker
        tracker = CostTracker.get_instance()
        for record in cost_callback.records:
            tracker._add_record(record)
        print(f"💰 [synthesizer] Cost: ${cost_callback.get_total_cost():.6f}")
        
        print("✅ Synthesis complete.")
        
        # Add Synthesizer to visualization
        synthesizer_agent = {
            "id": "synthesizer",
            "role": "Orchestrator", # Or Writer/System
            "instruction": "Synthesize final report from results",
            "output": output[:200] + "...", # Truncate for graph view
            "tools": [],
            "depth": state.get("depth", 0),
            "status": "completed",
            "execution_time_seconds": 0.0
        }
        
        # Connect all result producers to synthesizer
        synthesizer_edges = [
            {"source": node_id, "target": "synthesizer", "depth": state.get("depth", 0)}
            for node_id in results.keys()
        ]
        
        return {
            "synthesis": output, 
            "usage_stats": cost_callback.to_usage_stats(),
            "all_agents": [synthesizer_agent],
            "all_edges": synthesizer_edges
        }
    except Exception as e:
        print(f"❌ Error in synthesizer_node: {e}")
        return {"synthesis": f"Error generating synthesis: {str(e)}", "usage_stats": {}}
