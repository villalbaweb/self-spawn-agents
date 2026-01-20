import { useState, useEffect } from 'react';

interface RunInfo {
    run_id: string;
    last_active: string;
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
            <button
                className="history-toggle"
                onClick={() => setIsOpen(!isOpen)}
                title="Toggle History"
            >
                {isOpen ? '«' : '»'}
            </button>

            {isOpen && (
                <div className="history-content">
                    <h3>Run History</h3>
                    <button className="refresh-btn" onClick={fetchRuns}>↻ Refresh</button>

                    <div className="run-list">
                        {loading ? (
                            <div className="loading">Loading...</div>
                        ) : runs.length === 0 ? (
                            <div className="empty">No history found</div>
                        ) : (
                            runs.map(run => (
                                <div key={run.run_id} className={`run-item ${currentRunId === run.run_id ? 'active' : ''}`}>
                                    <div className="run-header">
                                        <span className="run-id" title={run.run_id}>
                                            {run.run_id.substring(0, 8)}...
                                        </span>
                                        <span className="run-date">
                                            {new Date(run.last_active + "Z").toLocaleDateString()}
                                        </span>
                                    </div>
                                    <div className="run-actions">
                                        <button
                                            className="fork-btn"
                                            onClick={() => onForkRun(run.run_id)}
                                        >
                                            🍴 Fork
                                        </button>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
