import { useState } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import axios from 'axios';
import './App.css';

// Define Blueprint types
interface AgentInfo {
  id: string;
  role: string;
  system_prompt: string;
  instruction: string;
  tools: string[];
}

interface EdgeInfo {
  source: string;
  target: string;
}

interface AppBlueprint {
  run_id: string;
  task: string;
  agents: AgentInfo[];
  edges: EdgeInfo[];
  execution_flow: string[];
  timestamp: string;
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [taskInput, setTaskInput] = useState('Conduct a market entry strategy for a luxury e-bike brand in Mexico. Research ONLY the top 2 competitors.');
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [runId, setRunId] = useState('a971497b-870b-4bb0-bce1-13f46e1de55f'); // Default for demo
  const [blueprint, setBlueprint] = useState<AppBlueprint | null>(null);
  const [elements, setElements] = useState<any[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);
  const [error, setError] = useState<string>('');

  const fetchBlueprint = async (id: string = runId) => {
    try {
      setError('');
      console.log(`Fetching from ${API_URL}/api/run/${id}/blueprint`);
      const response = await axios.get(`${API_URL}/api/run/${id}/blueprint`);
      const data = response.data;

      // Handle API errors gracefully
      if (data.error || !data.agents) {
        throw new Error(data.error || 'Blueprint not ready or invalid format');
      }

      setBlueprint(data as AppBlueprint);
      console.log("Blueprint loaded:", data);

      // Transform to Cytoscape elements
      const nodes = (data.agents || []).map((agent: AgentInfo) => ({
        data: {
          id: agent.id,
          label: `${agent.role}\n${agent.id}`,
          role: agent.role,
          prompt: agent.system_prompt
        },
        style: {
          'background-color': agent.role === 'Orchestrator' ? '#ff9f43' :
            agent.role === 'Coder' ? '#48dbfb' : '#1dd1a1',
          'background-opacity': 0.8
        }
      }));

      const edges = (data.edges || []).map((edge: EdgeInfo) => ({
        data: { source: edge.source, target: edge.target }
      }));

      setElements([...nodes, ...edges]);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.error || err.message || 'Failed to fetch blueprint');
    }
  };

  const startRun = async () => {
    setIsRunning(true);
    setLogs([]);
    setError('');

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
                console.log("Run started with ID:", data.run_id);
                setRunId(data.run_id);
              }
              else if (data.type === 'progress') {
                setLogs(prev => [...prev, `[LOG] ${data.message}`]);
              }
              else if (data.type === 'blueprint') {
                setLogs(prev => [...prev, `[SUCCESS] Blueprint Generated: ${data.id}`]);
                setRunId(data.id);
                fetchBlueprint(data.id);
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
      setLogs(prev => [...prev, `[FATAL ERROR] Connection Failed: ${e.message}`]);
      setLogs(prev => [...prev, `[HINT] Check if Backend is running at ${API_URL}`]);
    } finally {
      setIsRunning(false);
    }
  };

  const layout = {
    name: 'breadthfirst',
    directed: true,
    padding: 10,
    spacingFactor: 1.5
  };

  const style = [
    {
      selector: 'node',
      style: {
        'label': 'data(label)',
        'text-wrap': 'wrap',
        'text-valign': 'center',
        'text-halign': 'center',
        'shape': 'round-rectangle',
        'width': 150,
        'height': 80,
        'font-family': 'Inter, sans-serif',
        'font-size': 12,
        'color': '#fff',
        'border-width': 2,
        'border-color': '#fff'
      }
    },
    {
      selector: 'edge',
      style: {
        'width': 2,
        'line-color': '#a4b0be',
        'target-arrow-color': '#a4b0be',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier'
      }
    }
  ];

  return (
    <div className="app-container">
      <header className="header">
        <h1>🔍 agent_forge_studio <span className="beta-tag">Visualizer</span></h1>

        <div className="task-bar">
          <input
            className="task-input"
            placeholder="Describe your agentic task..."
            value={taskInput}
            onChange={e => setTaskInput(e.target.value)}
            disabled={isRunning}
          />
          <button className="run-btn" onClick={startRun} disabled={isRunning}>
            {isRunning ? 'Running...' : '▶ Start Run'}
          </button>
        </div>

        <div className="control-bar">
          <input
            type="text"
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
            placeholder="Run ID"
            className="run-input"
          />
          <button onClick={() => fetchBlueprint(runId)} className="load-btn">Load</button>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      {/* Debug Info */}
      <div style={{ fontSize: '10px', color: '#888', textAlign: 'center', padding: '5px' }}>
        API Target: {API_URL} | Status: {isRunning ? 'Running' : 'Idle'} | RunID: {runId}
      </div>

      <div className="main-content">
        {/* Logs Panel */}
        <div className="logs-pane">
          <h3>Live Execution Logs</h3>
          <div className="logs-container">
            {logs.length === 0 && <span className="log-placeholder">Waiting for execution...</span>}
            {logs.map((log, i) => <div key={i} className="log-line">{log}</div>)}
          </div>
        </div>

        <div className="graph-pane">
          {elements.length > 0 ? (
            <CytoscapeComponent
              elements={elements}
              style={{ width: '100%', height: '100%' }}
              stylesheet={style}
              layout={layout}
              cy={(cy: any) => {
                cy.on('tap', 'node', (event: any) => {
                  const agentId = event.target.id();
                  const agent = blueprint?.agents.find(a => a.id === agentId);
                  setSelectedAgent(agent || null);
                });
              }}
            />
          ) : (
            <div className="empty-state">Load a blueprint to see the agent flow.</div>
          )}
        </div>

        {selectedAgent && (
          <div className="inspector-pane">
            <div className="inspector-header">
              <h2>{selectedAgent.role}</h2>
              <span className="agent-id">{selectedAgent.id}</span>
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

              {selectedAgent.tools.length > 0 && (
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
