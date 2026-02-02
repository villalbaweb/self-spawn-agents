"""
Subgraphs package for Self-Spawn Agents.

Contains native LangGraph subgraphs for modular execution,
enabling lightweight recursive task handling without full
orchestration overhead.
"""
from agents.subgraphs.worker_subgraph import worker_subgraph, build_worker_subgraph
from core.state.worker_state import WorkerState

__all__ = ["worker_subgraph", "build_worker_subgraph", "WorkerState"]
