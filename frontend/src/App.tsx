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
  const [runId, setRunId] = useState('a971497b-870b-4bb0-bce1-13f46e1de55f'); // Default for demo
  const [blueprint, setBlueprint] = useState<AppBlueprint | null>(null);
  const [elements, setElements] = useState<any[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);
  const [error, setError] = useState<string>('');

  const fetchBlueprint = async () => {
    try {
      setError('');
      console.log(`Fetching from ${API_URL}/api/run/${runId}/blueprint`);
      const response = await axios.get(`${API_URL}/api/run/${runId}/blueprint`);
      const data: AppBlueprint = response.data;
      setBlueprint(data);
      console.log("Blueprint loaded:", data);

      // Transform to Cytoscape elements
      const nodes = data.agents.map(agent => ({
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

      const edges = data.edges.map(edge => ({
        data: { source: edge.source, target: edge.target }
      }));

      setElements([...nodes, ...edges]);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.error || err.message || 'Failed to fetch blueprint');
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
        <div className="control-bar">
          <input
            type="text"
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
            placeholder="Enter Run ID"
            className="run-input"
          />
          <button onClick={fetchBlueprint} className="load-btn">Load Blueprint</button>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <div className="main-content">
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
