import { useState } from 'react';
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
  tools: string[];
  depth?: number;
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
  const [allAgents, setAllAgents] = useState<AgentInfo[]>([]);

  const startRun = async () => {
    if (!taskInput) return;

    setIsRunning(true);
    setLogs([]);
    setError('');
    setElements([]);
    setSelectedAgent(null);
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
                setLogs(prev => [...prev, `[DONE] Report synthesized`]);
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
        id: agent.id,
        label: `${agent.role}\n${agent.id.substring(0, 12)}`,
        role: agent.role,
        depth: agent.depth || 0
      },
      style: {
        'background-color': getColorByRole(agent.role),
        'background-opacity': 0.9
      }
    }));

    const edgeElements = edges.map((edge) => ({
      data: { source: edge.source, target: edge.target }
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
    const agent = allAgents.find(a => a.id === nodeId);
    if (agent) {
      setSelectedAgent(agent);
    }
  };

  const layout = { name: 'dagre', rankDir: 'TB', nodeSep: 80, rankSep: 100 };

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
        'curve-style': 'bezier'
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
          <div className="inspector-pane">
            <div className="inspector-header">
              <div>
                <h2>{selectedAgent.role}</h2>
                <span className="agent-id">{selectedAgent.id}</span>
              </div>
              <button className="close-btn" onClick={() => setSelectedAgent(null)}>×</button>
            </div>

            <div className="inspector-content">
              <div className="field-group">
                <label>Instruction</label>
                <div className="text-block">{selectedAgent.instruction}</div>
              </div>

              <div className="field-group">
                <label>System Prompt</label>
                <pre className="code-block">{selectedAgent.system_prompt}</pre>
              </div>

              {selectedAgent.tools && selectedAgent.tools.length > 0 && (
                <div className="field-group">
                  <label>Tools</label>
                  <div className="tags">
                    {selectedAgent.tools.map(t => <span key={t} className="tag">{t}</span>)}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
