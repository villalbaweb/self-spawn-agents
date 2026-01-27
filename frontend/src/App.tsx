import { useState, useRef, useEffect } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import fcose from 'cytoscape-fcose';
import { HistorySidebar } from './HistorySidebar';
import './App.css';

// Register fcose layout
cytoscape.use(fcose);

interface AgentInfo {
  id: string;
  role: string;
  system_prompt: string;
  instruction: string;
  output?: string; // Add output field
  tools: string[];
  depth?: number;
  // Rich metadata from backend
  tool_used?: string | null;
  execution_time_seconds?: number;
  status?: string;
  error_message?: string;
  tools_available?: string[];
  // Confidence (HITL)
  confidence_score?: number;
  confidence_reasoning?: string;
  // Tier 2 Warnings
  warning?: string;
  low_confidence_flag?: boolean;
}

interface EdgeInfo {
  source: string;
  target: string;
  depth?: number;
}

interface UsageStats {
  cost: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  llm_calls: number;
  tool_calls: number;
  steps: number;
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [taskInput, setTaskInput] = useState<string>('');
  const [logs, setLogs] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [isInterrupted, setIsInterrupted] = useState<boolean>(false);
  const [interruptReason, setInterruptReason] = useState<string | null>(null);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);

  // Graph State
  const [elements, setElements] = useState<any[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);
  const [synthesis, setSynthesis] = useState<string | null>(null); // State for final report
  const [showSynthesis, setShowSynthesis] = useState<boolean>(false);
  const [allAgents, setAllAgents] = useState<AgentInfo[]>([]);
  const [showRefine, setShowRefine] = useState<boolean>(false);
  const [refinementText, setRefinementText] = useState<string>('');
  const [usageStats, setUsageStats] = useState<UsageStats>({
    cost: 0,
    input_tokens: 0,
    output_tokens: 0,
    cached_tokens: 0,
    llm_calls: 0,
    tool_calls: 0,
    steps: 0
  });

  // Specific Node Editing State
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editInstruction, setEditInstruction] = useState<string>('');

  // UI State
  const [isLogsOpen, setIsLogsOpen] = useState<boolean>(true);

  // Ref to access current agents in event handlers (avoids stale closure)
  const agentsRef = useRef<AgentInfo[]>([]);
  useEffect(() => {
    agentsRef.current = allAgents;
  }, [allAgents]);

  const processSSEResponse = async (response: Response) => {
    if (!response.body) throw new Error("No response body");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));

            if (data.type === 'start') {
              setCurrentRunId(data.run_id);
              setLogs(prev => [...prev, `[START] Run ID: ${data.run_id}`]);

              // Save metadata to localStorage for History UI
              try {
                const existing = JSON.parse(localStorage.getItem('agent_run_history') || '{}');
                existing[data.run_id] = {
                  task: taskInput || "Untitled Task",
                  timestamp: new Date().toISOString()
                };
                localStorage.setItem('agent_run_history', JSON.stringify(existing));
                // Dispatch event to notify sidebar
                window.dispatchEvent(new Event('history-updated'));
              } catch (e) {
                console.warn("Failed to save run history", e);
              }
            }
            else if (data.type === 'progress') {
              setLogs(prev => [...prev, `[LOG] ${data.message}`]);
            }
            else if (data.type === 'usage_stats') {
              setUsageStats(data.stats);
            }
            else if (data.type === 'unified_graph') {
              setLogs(prev => [...prev, `[SUCCESS] Unified Graph received: ${data.agents.length} agents`]);
              renderUnifiedGraph(data.agents, data.edges);
            }
            else if (data.type === 'synthesis') {
              console.log('✅ Synthesis report received');
              setLogs(prev => [...prev, `[DONE] Report synthesized`]);
              setSynthesis(data.markdown);
              setShowSynthesis(true);
            }
            else if (data.type === 'interrupt') {
              setIsInterrupted(true);
              setInterruptReason(data.confidence_reasoning || null);
              setLogs(prev => [...prev, `[PAUSE] Human Review Required (Confidence: ${data.confidence_score ? (data.confidence_score * 100).toFixed(0) : 'low'}%)`]);
              if (data.confidence_reasoning) {
                setLogs(prev => [...prev, `[REASON] ${data.confidence_reasoning}`]);
              }
            }
            else if (data.type === 'error') {
              setLogs(prev => [...prev, `[ERROR] ${data.message}`]);
            }
          } catch (e) {
            console.warn("Failed to parse SSE line", line);
          }
        }
      }
    }
  };

  const startRun = async () => {
    if (!taskInput) return;

    setIsRunning(true);
    setLogs([]);
    setError('');
    setElements([]);
    setSelectedAgent(null);
    setSynthesis(null);
    setShowSynthesis(false);
    setAllAgents([]);
    setIsInterrupted(false);
    setCurrentRunId(null);
    setUsageStats({
      cost: 0,
      input_tokens: 0,
      output_tokens: 0,
      cached_tokens: 0,
      llm_calls: 0,
      tool_calls: 0,
      steps: 0
    });

    try {
      const response = await fetch(`${API_URL}/api/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: taskInput })
      });

      await processSSEResponse(response);

    } catch (e: any) {
      console.error("Run failed:", e);
      setError(e.message || "Unknown error occurred");
      setLogs(prev => [...prev, `[FATAL ERROR] ${e.message}`]);
    } finally {
      setIsRunning(false);
    }
  };

  const handleResume = async (action: 'proceed' | 'refine', overrides?: any) => {
    if (!currentRunId) return;

    setIsRunning(true);
    setIsInterrupted(false);
    setLogs(prev => [...prev, `[RESUME] Sending ${action} command...`]);

    try {
      const response = await fetch(`${API_URL}/api/run/${currentRunId}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, overrides })
      });

      await processSSEResponse(response);
    } catch (e: any) {
      console.error("Resume failed:", e);
      setLogs(prev => [...prev, `[ERROR] Resume failed: ${e.message}`]);
    } finally {
      setIsRunning(false);
    }
  };

  // Load a run's state without executing it (e.g. after fork or URL load)
  const loadRun = async (runId: string) => {
    setIsRunning(true);
    setLogs([]);
    setError('');
    setElements([]);
    setSelectedAgent(null);
    setSynthesis(null);
    setShowSynthesis(false);
    setIsInterrupted(false);
    setCurrentRunId(runId);

    // Update URL without reload
    const newUrl = `${window.location.pathname}?run_id=${runId}`;
    window.history.pushState({ path: newUrl }, '', newUrl);

    try {
      const response = await fetch(`${API_URL}/api/run/${runId}/state`);
      await processSSEResponse(response);
    } catch (e: any) {
      console.error("Load run failed:", e);
      setError(e.message || "Failed to load run state");
      setLogs(prev => [...prev, `[ERROR] Load run failed: ${e.message}`]);
    } finally {
      setIsRunning(false);
    }
  };

  // Auto-load run from URL on startup
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const runId = params.get('run_id');
    if (runId && !currentRunId) {
      console.log("Auto-loading run from URL:", runId);
      loadRun(runId);
    }
  }, []); // Run once on mount

  const handleForkRun = async (sourceRunId: string, nodeId?: string, modifications?: any) => {
    setIsRunning(true);
    setLogs(prev => [...prev, `[FORK] ${nodeId ? `Rewinding to node ${nodeId}` : 'Cloning run'} ${sourceRunId}...`]);

    // For node-specific rewind, reset UI state so user sees the rerun happen
    if (nodeId) {
      setElements([]);
      setSelectedAgent(null);
      setSynthesis(null);
      setShowSynthesis(false);
      setIsInterrupted(false);
    }

    try {
      let url = `${API_URL}/api/run/${sourceRunId}/fork`;
      let body: any = {};

      if (nodeId) {
        // specific rewind fork
        body.node_id = nodeId;
        if (modifications) body.modifications = modifications;
      } else {
        // Full clone/hydrate
        url = `${API_URL}/api/hydrate`;
        body = { source_thread_id: sourceRunId };
      }

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      // If using /hydrate, it returns { run_id }, so we need to switch to that run
      if (url.includes('/hydrate')) {
        const data = await response.json();
        if (data.run_id) {
          setLogs(prev => [...prev, `[SUCCESS] Cloned to new run: ${data.run_id}`]);
          // Load the new run immediately
          await loadRun(data.run_id);
        }
      } else {
        // /fork streams events and auto-resumes execution
        setLogs(prev => [...prev, `[REWIND] Re-executing from node...`]);
        await processSSEResponse(response);
      }

    } catch (e: any) {
      console.error("Fork failed:", e);
      setLogs(prev => [...prev, `[ERROR] Fork failed: ${e.message}`]);
    } finally {
      setIsRunning(false);
    }
  };

  // Helper placeholder - in reality we keep the old /fork for rewinds for now
  // and use /hydrate for the "Fork Button".
  const renderUnifiedGraph = (agents: AgentInfo[], edges: EdgeInfo[]) => {
    setAllAgents(agents);

    // Create a set of valid node IDs for fast lookup
    const validNodeIds = new Set(agents.map((agent) => agent.id));

    const nodes = agents.map((agent) => ({
      data: {
        ...agent, // Spread ALL agent data (metadata, etc.)
        label: `${agent.warning ? '⚠️ ' : ''}${agent.role}\n${agent.id.substring(0, 12)}`,
      },
      style: {
        'background-color': getColorByRole(agent.role),
        'background-opacity': 0.2, // Glassmorphism base
        'border-color': agent.warning ? '#f1c40f' : getColorByRole(agent.role),
        'border-opacity': 0.6,
        'border-width': agent.warning ? 4 : 2,
        'text-outline-color': '#000',
        'text-outline-width': 2,
        'text-outline-opacity': 1,
        'color': '#fff'
      }
    }));

    // Filter out edges that reference non-existent nodes to prevent Cytoscape crash
    const validEdges = edges.filter((edge) => {
      const sourceExists = validNodeIds.has(edge.source);
      const targetExists = validNodeIds.has(edge.target);
      if (!sourceExists || !targetExists) {
        console.warn(`Skipping edge: source=${edge.source} (${sourceExists ? 'exists' : 'missing'}), target=${edge.target} (${targetExists ? 'exists' : 'missing'})`);
        return false;
      }
      return true;
    });

    const edgeElements = validEdges.map((edge) => ({
      data: {
        source: edge.source,
        target: edge.target,
        type: (edge as any).type // hierarchy marker
      }
    }));

    setElements([...nodes, ...edgeElements]);
  };

  const getColorByRole = (role: string): string => {
    const colors: Record<string, string> = {
      'Orchestrator': '#ff9f43',
      'Coder': '#48dbfb',
      'Researcher': '#1dd1a1',
      'Analyst': '#f368e0',
      'Writer': '#ff6b6b',
      'Planner': '#feca57'
    };
    return colors[role] || '#54a0ff';
  };

  const handleNodeClick = (event: any) => {
    const nodeId = event.target.id();
    console.log('Node clicked:', nodeId, 'Available agents:', agentsRef.current.length);
    const agent = agentsRef.current.find(a => a.id === nodeId);
    if (agent) {
      console.log('Found agent:', agent.role);
      setSelectedAgent(agent);
    } else {
      console.warn('Agent not found for ID:', nodeId);
    }
  };

  const layout = {
    name: 'fcose',
    quality: "default",
    randomize: true,
    animate: true,
    animationDuration: 1000,
    fit: true,
    padding: 30,
    nodeDimensionsIncludeLabels: true,
    uniformNodeDimensions: false,
    packComponents: true,
    step: "all",
    nodeRepulsion: (_node: any) => 4500,
    idealEdgeLength: (_edge: any) => 100,
    edgeElasticity: (_edge: any) => 0.45,
    nestingFactor: 0.1,
    gravity: 0.25,
    numIter: 2500,
    tile: true,
    tilingPaddingVertical: 10,
    tilingPaddingHorizontal: 10
  };

  const style = [
    {
      selector: 'node',
      style: {
        'label': 'data(label)',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-family': 'Inter, Roboto, sans-serif',
        'font-size': '10px',
        'font-weight': 500,
        'color': '#fff',
        'text-wrap': 'wrap',
        'width': 80,
        'height': 80,
        'shape': 'ellipse',
        'overlay-padding': '6px',
        'z-index': 10
      }
    },
    {
      selector: 'node[warning]',
      style: {
        'border-width': 4,
        'border-color': '#f1c40f',
        'background-color': '#f1c40f',
        'background-opacity': 0.2,
        'text-outline-width': 2,
        'text-outline-color': '#333',
        'shadow-blur': 10,
        'shadow-color': '#f1c40f',
        'shadow-opacity': 0.5
      }
    },
    {
      selector: 'edge',
      style: {
        'width': 1.5,
        'line-color': '#a4b0be',
        'line-opacity': 0.6,
        'target-arrow-color': '#a4b0be',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'arrow-scale': 0.8
      }
    },
    {
      selector: 'edge[type="hierarchy"]',
      style: {
        'line-style': 'solid', // solid but thinner/lighter looks better in modern UI than dashed sometimes, but let's keep it distinct
        'width': 2,
        'line-color': '#2ed573',
        'line-opacity': 0.8,
        'target-arrow-color': '#2ed573',
        'curve-style': 'unbundled-bezier',
        'control-point-distances': [20, -20], // subtle wave
        'control-point-weights': [0.25, 0.75]
      }
    }
  ];

  return (
    <div className="app-container">
      <HistorySidebar onForkRun={(runId) => handleForkRun(runId)} currentRunId={currentRunId} />
      {/* HITL Interrupt Overlay */}
      {isInterrupted && (
        <div className="hitl-overlay">
          <div className="hitl-banner">
            <div className="hitl-icon">⚠️</div>
            <div className="hitl-text">
              <h3>Human Review Required</h3>
              <p>{interruptReason || "Aggregate confidence is below threshold. Please review research or refine instructions."}</p>
            </div>
            <div className="hitl-actions">
              {!showRefine ? (
                <>
                  <button className="hitl-btn proceed" onClick={() => handleResume('proceed')}>
                    Proceed Anyway
                  </button>
                  <button className="hitl-btn refine" onClick={() => setShowRefine(true)}>
                    Refine Instructions
                  </button>
                  <button className="hitl-btn close" onClick={() => setIsInterrupted(false)}>
                    Close
                  </button>
                </>
              ) : (
                <div className="hitl-refine-area">
                  <textarea
                    className="hitl-input"
                    placeholder="Enter new instructions or critique..."
                    value={refinementText}
                    onChange={(e) => setRefinementText(e.target.value)}
                  />
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <button className="hitl-btn proceed" onClick={() => {
                      handleResume('refine', {
                        additional_instructions: refinementText
                      });
                      setShowRefine(false);
                    }}>
                      Submit & Resume
                    </button>
                    <button className="hitl-btn close" onClick={() => setShowRefine(false)}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <header className="app-header">
        <div className="logo">
          <span className="dot"></span>
          agent_forge_studio <span className="badge">VISUALIZER</span>
        </div>

        <div className="task-bar">
          <input
            type="text"
            className="task-input"
            placeholder="Describe your agentic task..."
            value={taskInput}
            onChange={(e) => setTaskInput(e.target.value)}
            disabled={isRunning}
          />
          <button className="run-btn" onClick={startRun} disabled={isRunning}>
            {isRunning ? 'Running...' : '▶ Start Run'}
          </button>

          {/* Fork Button */}
          {currentRunId && !isRunning && (
            <button
              className="header-fork-btn"
              onClick={() => {
                if (confirm("Create a new copy of this run?")) handleForkRun(currentRunId);
              }}
              title="Fork Run"
            >
              ⑂ Fork Run
            </button>
          )}

          {synthesis && (
            <button className="synthesis-btn" onClick={() => setShowSynthesis(true)}>
              📝 Final Report
            </button>
          )}
        </div>

        <div className="performance-stats">
          <div className="stat-item cost" title="Total estimated cost">
            <span className="stat-label">$ COST</span>
            <span className="stat-value">${usageStats.cost.toFixed(8)}</span>
          </div>
          <div className="stat-divider"></div>
          <div className="stat-item tokens" title="Input / Output (Cached)">
            <span className="stat-label">TOKENS</span>
            <span className="stat-value">
              {usageStats.input_tokens.toLocaleString()} / {usageStats.output_tokens.toLocaleString()}
              {usageStats.cached_tokens > 0 && (
                <span className="cached-badge">({usageStats.cached_tokens.toLocaleString()} cached)</span>
              )}
            </span>
          </div>
          <div className="stat-divider"></div>
          <div className="stat-item calls" title="LLM / Tool Calls / Steps">
            <span className="stat-label">CALLS</span>
            <span className="stat-value">{usageStats.llm_calls} LLM | {usageStats.tool_calls} Tool | {usageStats.steps} Steps</span>
          </div>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <div className="main-content">
        {/* Logs Panel */}
        {/* Logs Panel */}
        <div className={`logs-pane ${isLogsOpen ? 'open' : 'closed'}`}>
          <button
            className="logs-toggle"
            onClick={() => setIsLogsOpen(!isLogsOpen)}
            title="Toggle Logs"
          >
            {isLogsOpen ? 'Logs' : 'Logs'}
          </button>
          <div className="logs-content">
            <h3>Live Execution Logs</h3>
            <div className="logs-container">
              {logs.length === 0 && <span className="log-placeholder">Waiting for execution...</span>}
              {logs.map((log, i) => <div key={i} className="log-line">{log}</div>)}
            </div>
          </div>
        </div>

        {/* Graph Pane */}
        <div className="graph-pane">
          {elements.length > 0 ? (
            <CytoscapeComponent
              elements={elements}
              style={{ width: '100%', height: '100%' }}
              stylesheet={style}
              layout={layout}
              cy={(cy: any) => {
                cy.removeListener('tap');
                cy.on('tap', 'node', handleNodeClick);
              }}
            />
          ) : (
            <div className="empty-state">
              {isRunning ? 'Executing agents... Graph will render when complete.' : 'Enter a task and click Start Run to begin.'}
            </div>
          )}
        </div>

        {/* Inspector Pane */}
        {selectedAgent && (
          <div className="inspector-pane" style={{
            position: 'fixed',
            right: 0,
            top: 60,
            bottom: 0,
            width: '400px',
            zIndex: 9999,
            background: '#2f3640',
            borderLeft: '3px solid #0be881'
          }}>
            <div className="inspector-header">
              <div>
                <h2>{selectedAgent.role}</h2>
                <span className="agent-id">{selectedAgent.id}</span>
              </div>
              <button className="close-btn" onClick={() => setSelectedAgent(null)}>×</button>
            </div>

            <div className="inspector-content">
              {/* Status & Metrics Row */}
              <div className="metrics-row">
                <div className={`status-badge ${selectedAgent.status || 'unknown'}`}>
                  {selectedAgent.status || 'N/A'}
                </div>
                {selectedAgent.execution_time_seconds !== undefined && (
                  <span className="metric">⏱️ {selectedAgent.execution_time_seconds}s</span>
                )}
                {selectedAgent.depth !== undefined && (
                  <span className="metric">📊 Depth: {selectedAgent.depth}</span>
                )}
              </div>

              {selectedAgent.error_message && (
                <div className="error-box">
                  ⚠️ {selectedAgent.error_message}
                </div>
              )}

              {selectedAgent.warning && (
                <div className="warning-box" style={{
                  background: 'rgba(241, 196, 15, 0.2)',
                  border: '1px solid #f1c40f',
                  borderRadius: '4px',
                  padding: '8px 12px',
                  marginBottom: '12px',
                  color: '#f1c40f'
                }}>
                  ⚠️ {selectedAgent.warning}
                </div>
              )}

              {/* Confidence Display */}
              {selectedAgent.confidence_score !== undefined && (
                <div className="field-group">
                  <label>Confidence</label>
                  <div className="confidence-meter">
                    <div
                      className={`confidence-bar ${selectedAgent.confidence_score >= 0.7 ? 'high' : selectedAgent.confidence_score >= 0.4 ? 'medium' : 'low'}`}
                      style={{ width: `${(selectedAgent.confidence_score * 100).toFixed(0)}%` }}
                    />
                    <span className="confidence-value">{(selectedAgent.confidence_score * 100).toFixed(0)}%</span>
                  </div>
                  {selectedAgent.confidence_reasoning && (
                    <div className="confidence-reasoning">{selectedAgent.confidence_reasoning}</div>
                  )}
                </div>
              )}

              <div className="field-group">
                <label>Resolution Result</label>
                <div className="text-block result-text">
                  {selectedAgent.output || "No output recorded yet."}
                </div>
              </div>

              <div className="field-group">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <label>Instruction</label>
                  {!isEditing && (
                    <button
                      className="metric"
                      onClick={() => {
                        setIsEditing(true);
                        setEditInstruction(selectedAgent.instruction);
                      }}
                      style={{ cursor: 'pointer', border: 'none', background: 'transparent', color: '#3498db' }}
                    >
                      ✎ Edit (Refine)
                    </button>
                  )}
                  {/* Rewind Button */}
                  {currentRunId && !isEditing && (
                    <button
                      className="metric"
                      onClick={() => {
                        if (!currentRunId || !selectedAgent || !confirm("Start new run from this point?")) return;
                        handleForkRun(currentRunId, selectedAgent.id);
                      }}
                      style={{ cursor: 'pointer', border: 'none', background: 'transparent', color: '#e67e22', marginLeft: '10px' }}
                    >
                      ⏪ Rewind
                    </button>
                  )}
                </div>

                {isEditing ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <textarea
                      className="hitl-input"
                      value={editInstruction}
                      onChange={(e) => setEditInstruction(e.target.value)}
                    />
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                      <button
                        className="hitl-btn close"
                        onClick={() => setIsEditing(false)}
                        style={{ fontSize: '11px', padding: '4px 8px' }}
                      >
                        Cancel
                      </button>
                      <button
                        className="hitl-btn refine"
                        onClick={() => {
                          handleResume('refine', {
                            additional_instructions: editInstruction,
                            target_node_id: selectedAgent.id
                          });
                          setIsEditing(false);
                        }}
                        style={{ fontSize: '11px', padding: '4px 8px' }}
                      >
                        Save & Refine
                      </button>
                      <button
                        className="hitl-btn refine"
                        onClick={() => {
                          if (!currentRunId || !selectedAgent || !confirm("Start new run from this point with modified instruction?")) return;
                          handleForkRun(currentRunId, selectedAgent.id, { new_instruction: editInstruction });
                          setIsEditing(false);
                        }}
                        style={{ fontSize: '11px', padding: '4px 8px', backgroundColor: '#e67e22' }}
                      >
                        Rewind with New Instruction
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="text-block">{selectedAgent.instruction}</div>
                )}
              </div>

              {selectedAgent.tool_used && (
                <div className="field-group">
                  <label>Tool Used</label>
                  <span className="tag highlight">{selectedAgent.tool_used}</span>
                </div>
              )}

              {selectedAgent.tools_available && selectedAgent.tools_available.length > 0 && (
                <div className="field-group">
                  <label>Tools Available</label>
                  <div className="tags">
                    {selectedAgent.tools_available.map(t => <span key={t} className="tag">{t}</span>)}
                  </div>
                </div>
              )}

              <div className="field-group">
                <label>System Prompt</label>
                <pre className="code-block">{selectedAgent.system_prompt}</pre>
              </div>
            </div>
          </div>
        )}
        {/* Final Synthesis Overlay */}
        {showSynthesis && synthesis && (
          <div className="synthesis-overlay">
            <div className="synthesis-modal">
              <div className="synthesis-header">
                <h2>Final Task Resolution</h2>
                <button className="close-btn" onClick={() => setShowSynthesis(false)}>×</button>
              </div>
              <div className="synthesis-body">
                {synthesis.split('\n').map((line, i) => (
                  <p key={i}>{line}</p>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
