import { useState, useEffect } from 'react';

interface RunInfo {
    run_id: string;
    last_active: string;
}

interface RunMetadata {
    task: string;
    timestamp: string;
}

interface HistorySidebarProps {
    onForkRun: (runId: string) => void;
    currentRunId: string | null;
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function HistorySidebar({ onForkRun, currentRunId }: HistorySidebarProps) {
    const [runs, setRuns] = useState<RunInfo[]>([]);
    const [metadata, setMetadata] = useState<Record<string, RunMetadata>>({});
    const [loading, setLoading] = useState(false);
    const [isOpen, setIsOpen] = useState(false);

    const loadMetadata = () => {
        try {
            const data = JSON.parse(localStorage.getItem('agent_run_history') || '{}');
            setMetadata(data);
        } catch (e) {
            console.warn("Failed to load history metadata", e);
        }
    };

    const fetchRuns = async () => {
        setLoading(true);
        loadMetadata(); // Refresh metadata too
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

    // Listen for updates from App.tsx
    useEffect(() => {
        const handler = () => loadMetadata();
        window.addEventListener('history-updated', handler);
        return () => window.removeEventListener('history-updated', handler);
    }, []);

    const formatDate = (runId: string, _backendDate: string) => {
        // Prefer local metadata timestamp if available
        if (metadata[runId]?.timestamp) {
            return new Date(metadata[runId].timestamp).toLocaleString(undefined, {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
            });
        }
        // Fallback: If backend date is invalid (uuid?), just show empty or "Unknown"
        // We know backend sends checkpoint_id which is NOT a date.
        return "";
    };

    const getRunTitle = (runId: string) => {
        if (metadata[runId]?.task) {
            return metadata[runId].task;
        }
        return `Run ${runId.substring(0, 6)}...`;
    };

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
                                    <div className="run-title" title={getRunTitle(run.run_id)}>
                                        {getRunTitle(run.run_id)}
                                    </div>
                                    <div className="run-meta">
                                        <span className="run-id">#{run.run_id.substring(0, 6)}</span>
                                        <span className="run-date">{formatDate(run.run_id, run.last_active)}</span>
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
