import os
import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# Set env before importing main
test_db_path = "test_checkpoints.db"
os.environ["CHECKPOINT_DB_PATH"] = test_db_path

# Import using top-level names assuming backend/ is in PYTHONPATH
from main import app
from agents.shared_memory import init_checkpointer, close_checkpointer, memory
from history import list_runs

# Remove test DB if exists
if os.path.exists(test_db_path):
    os.remove(test_db_path)

@pytest.fixture(scope="module")
def test_client():
    with TestClient(app) as client:
        yield client
    # Cleanup
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_history_flow():
    # Initialize checkpointer manually for setup
    await init_checkpointer()
    
    # Create a dummy run entry in the DB
    # We do this by writing a checkpoint
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    
    run_id = "test-run-1"
    config = {"configurable": {"thread_id": run_id, "checkpoint_ns": ""}}
    
    # Write a dummy checkpoint
    checkpoint = {
        "v": 1,
        "id": "1d6c8e34-5f1b-4f1b-b1b1-1b1b1b1b1b1b",
        "ts": "2024-01-01T00:00:00.000000+00:00",
        "channel_values": {"some": "state"},
        "channel_versions": {},
        "versions_seen": {},
        "pending_sends": []
    }
    metadata = {"langgraph_node": "test_node"}
    
    # We need to access the underlying memory object which is available via 'agents.shared_memory.memory'
    # initialized by init_checkpointer
    from agents.shared_memory import memory as mem
    if not mem:
        pytest.fail("Memory verification failed")
        
    await mem.aput(config, checkpoint, metadata, {})
    
    # 1. Test List Runs
    # Since we are testing async function list_runs directly (unit test style)
    runs = await list_runs()
    assert len(runs) >= 1
    assert any(r["run_id"] == run_id for r in runs)
    
    # 2. Test Fork Endpoint via Client
    # We need to use TestClient.
    # Note: TestClient is synchronous wrapper. StreamingResponse works but we need to iterate it.
    
    client = TestClient(app)
    
    # Fork 'test-run-1'
    response = client.post(f"/api/run/{run_id}/fork", json={})
    assert response.status_code == 200
    
    # Read stream (partial)
    content = ""
    for line in response.iter_lines():
        if line:
            content += line
            if "run_id" in line:
                break
    
    # Verify we got a start event
    assert "start" in content
    assert "forked_from" in content
    
    # verify new run exists in list
    runs_after = await list_runs()
    assert len(runs_after) > len(runs)
    
    await close_checkpointer()
