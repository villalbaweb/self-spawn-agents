import { useState, useRef, useEffect } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import dagre from 'cytoscape-dagre';
import './App.css';

// Register dagre layout
cytoscape.use(dagre);

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
}

interface EdgeInfo {
  source: string;
  target: string;
  depth?: number;
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [taskInput, setTaskInput] = useState<string>('');
  const [logs, setLogs] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  // Graph State
  const [elements, setElements] = useState<any[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);
  const [synthesis, setSynthesis] = useState<string | null>(null); // State for final report
  const [showSynthesis, setShowSynthesis] = useState<boolean>(false);
  const [allAgents, setAllAgents] = useState<AgentInfo[]>([]);

  // Ref to access current agents in event handlers (avoids stale closure)
  const agentsRef = useRef<AgentInfo[]>([]);
  useEffect(() => {
    agentsRef.current = allAgents;
  }, [allAgents]);

  // Debug: Log when selectedAgent changes
  useEffect(() => {
    console.log('selectedAgent state changed:', selectedAgent?.role, selectedAgent?.id);
  }, [selectedAgent]);

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

    try {
      const response = await fetch(`${API_URL}/api/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: taskInput })
      });

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
                setLogs(prev => [...prev, `[START] Run ID: ${data.run_id}`]);
              }
              else if (data.type === 'progress') {
                setLogs(prev => [...prev, `[LOG] ${data.message}`]);
              }
              else if (data.type === 'unified_graph') {
                setLogs(prev => [...prev, `[SUCCESS] Unified Graph received: ${data.agents.length} agents`]);
                renderUnifiedGraph(data.agents, data.edges);
              }
              else if (data.type === 'synthesis') {
                console.log('✅ Synthesis report received, length:', data.markdown?.length);
                setLogs(prev => [...prev, `[DONE] Report synthesized`]);
                setSynthesis(data.markdown);
                setShowSynthesis(true);
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

    } catch (e: any) {
      console.error("Run failed:", e);
      setError(e.message || "Unknown error occurred");
      setLogs(prev => [...prev, `[FATAL ERROR] ${e.message}`]);
    } finally {
      setIsRunning(false);
    }
  };

  const renderUnifiedGraph = (agents: AgentInfo[], edges: EdgeInfo[]) => {
    setAllAgents(agents);

    const nodes = agents.map((agent) => ({
      data: {
        ...agent, // Spread ALL agent data (metadata, etc.)
        label: `${agent.role}\n${agent.id.substring(0, 12)}`,
      },
      style: {
        'background-color': getColorByRole(agent.role),
        'background-opacity': 0.9
      }
    }));

    const edgeElements = edges.map((edge) => ({
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
    name: 'dagre',
    rankDir: 'TB',
    nodeSep: 150,
    rankSep: 150,
    edgeSep: 50,
    padding: 100
  };

  const style = [
    {
      selector: 'node',
      style: {
        'label': 'data(label)',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '10px',
        'color': '#fff',
        'text-wrap': 'wrap',
        'width': 100,
        'height': 50,
        'shape': 'roundrectangle',
        'border-width': 2,
        'border-color': '#333'
      }
    },
    {
      selector: 'edge',
      style: {
        'width': 2,
        'line-color': '#808e9b',
        'target-arrow-color': '#808e9b',
        'target-arrow-shape': 'triangle',
        'curve-style': 'taxi', // Use taxi for cleaner routing in hierarchies
        'taxi-direction': 'vertical',
        'taxi-turn': 20
      }
    },
    {
      selector: 'edge[type="hierarchy"]',
      style: {
        'line-style': 'dashed',
        'width': 3,
        'line-color': '#0be881',
        'target-arrow-color': '#0be881'
      }
    }
  ];

  return (
    <div className="app-container">
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

          {synthesis && (
            <button className="synthesis-btn" onClick={() => setShowSynthesis(true)}>
              📝 Final Report
            </button>
          )}
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <div className="main-content">
        {/* Logs Panel */}
        <div className="logs-pane">
          <h3>Live Execution Logs</h3>
          <div className="logs-container">
            {logs.length === 0 && <span className="log-placeholder">Waiting for execution...</span>}
            {logs.map((log, i) => <div key={i} className="log-line">{log}</div>)}
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
                <label>Instruction</label>
                <div className="text-block">{selectedAgent.instruction}</div>
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
