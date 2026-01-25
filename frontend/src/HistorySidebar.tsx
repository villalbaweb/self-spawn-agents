import { useState, useEffect } from 'react';

interface RunInfo {
    run_id: string;
    last_active: string;
    task: string;
    status: string; // 'completed', 'failed', 'active', 'unknown'
}

interface HistorySidebarProps {
    onForkRun: (runId: string) => void;
    currentRunId: string | null;
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function HistorySidebar({ onForkRun, currentRunId }: HistorySidebarProps) {
    const [runs, setRuns] = useState<RunInfo[]>([]);
    const [loading, setLoading] = useState(false);
    const [isOpen, setIsOpen] = useState(false);

    const fetchRuns = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/runs`);
            const data = await res.json();
            if (Array.isArray(data)) {
                setRuns(data);
            }
        } catch (e) {
            console.error("Failed to fetch runs", e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) {
            fetchRuns();
        }
    }, [isOpen]);

    return (
        <div className={`history-sidebar ${isOpen ? 'open' : ''}`}>
            <div className="history-content">
                <button
                    className="history-toggle"
                    onClick={() => setIsOpen(!isOpen)}
                    title="Toggle History"
                >
                    History
                </button>

                <div className="history-header">
                    <h3>Sessions</h3>
                    <button className="refresh-btn" onClick={fetchRuns} title="Refresh">↻</button>
                </div>

                <div className="run-list">
                    {loading ? (
                        <div className="loading-spinner"></div>
                    ) : runs.length === 0 ? (
                        <div className="empty-state-text">No active sessions found.</div>
                    ) : (
                        runs.map(run => (
                            <div key={run.run_id} className={`run-item ${currentRunId === run.run_id ? 'active' : ''}`}>
                                <div className="run-info">
                                    <div className="run-title" title={run.task}>
                                        {run.task || `Run ${run.run_id.substring(0, 6)}`}
                                    </div>
                                    <div className="run-meta">
                                        <span className={`status-dot ${run.status || 'unknown'}`}></span>
                                        <span className="run-id" title={run.run_id}>ID: {run.run_id.substring(0, 6)}</span>
                                    </div>
                                </div>
                                <div className="run-actions">
                                    <button
                                        className="fork-btn"
                                        onClick={() => onForkRun(run.run_id)}
                                        title="Load / Fork this run"
                                    >
                                        Load
                                    </button>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
}
