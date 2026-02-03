"""
PostgreSQL Persistence Layer Unit Tests

Tests verify that the PostgreSQL checkpointer handles concurrent writes
without database locking errors.
"""
import asyncio
import os
import sys
import pytest
from uuid import uuid4

# Add backend to path for imports
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../backend'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from core.persistence.checkpointer import (
    init_checkpointer,
    close_checkpointer,
    get_checkpointer,
)


@pytest.mark.asyncio
async def test_concurrent_writes_same_thread():
    """
    Test concurrent writes to the same thread_id.
    
    This test verifies that PostgreSQL handles concurrent writes without
    locking errors that would occur with SQLite.
    
    Scenario:
    - 5 parallel tasks
    - All write to the same thread_id
    - Each performs 10 checkpoint operations
    - Should complete without OperationalError
    """
    await init_checkpointer()
    checkpointer = get_checkpointer()
    
    if checkpointer is None:
        pytest.fail("Checkpointer not initialized")
    
    # Shared thread ID for all concurrent writes
    thread_id = f"test-thread-{uuid4()}"
    
    async def write_checkpoints(task_id: int):
        """Simulate concurrent checkpoint writes."""
        errors = []
        
        for i in range(10):
            try:
                # Create a checkpoint
                config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": "",
                    }
                }
                
                # Simulate state update
                state = {
                    "task_id": task_id,
                    "iteration": i,
                    "data": f"Task {task_id} - Iteration {i}",
                }
                
                # Write checkpoint (this would fail with SQLite under concurrency)
                await checkpointer.aput(
                    config=config,
                    checkpoint={
                        "v": 1,
                        "ts": f"2026-02-02T20:28:{i:02d}Z",
                        "id": f"{task_id}-{i}",
                        "channel_values": state,
                    },
                    metadata={"source": "test", "task_id": task_id},
                    new_versions={},  # Required for PostgreSQL checkpointer
                )
                
                # Small delay to increase concurrency overlap
                await asyncio.sleep(0.01)
                
            except Exception as e:
                errors.append(f"Task {task_id}, iteration {i}: {e}")
        
        return errors
    
    # Run 5 concurrent tasks
    tasks = [write_checkpoints(i) for i in range(5)]
    results = await asyncio.gather(*tasks)
    
    # Collect all errors
    all_errors = [error for task_errors in results for error in task_errors]
    
    await close_checkpointer()
    
    # Assert no errors occurred
    assert len(all_errors) == 0, f"Concurrent write errors: {all_errors}"


@pytest.mark.asyncio
async def test_connection_pool_handling():
    """
    Test that connection pool handles multiple concurrent connections.
    
    This test verifies that the connection pool (2-10 connections) properly
    manages concurrent access without exhaustion or errors.
    """
    await init_checkpointer()
    checkpointer = get_checkpointer()
    
    if checkpointer is None:
        pytest.fail("Checkpointer not initialized")
    
    async def concurrent_read(task_id: int):
        """Simulate concurrent checkpoint reads."""
        try:
            thread_id = f"pool-test-{task_id}"
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": "",
                }
            }
            
            # Attempt to get checkpoint (will return None if not exists)
            result = await checkpointer.aget(config)
            return True
        except Exception as e:
            return f"Task {task_id} error: {e}"
    
    # Spawn 20 concurrent connections (exceeds min pool size)
    tasks = [concurrent_read(i) for i in range(20)]
    results = await asyncio.gather(*tasks)
    
    await close_checkpointer()
    
    # Check for errors
    errors = [r for r in results if isinstance(r, str)]
    assert len(errors) == 0, f"Connection pool errors: {errors}"


@pytest.mark.asyncio
async def test_checkpointer_requires_database_url():
    """
    Test that checkpointer fails gracefully when DATABASE_URL is not set.
    """
    # Temporarily unset DATABASE_URL
    original_url = os.environ.get("DATABASE_URL")
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
    
    try:
        # Re-import to pick up environment change
        from core.persistence import checkpointer as cp_module
        cp_module.DATABASE_URL = None
        
        with pytest.raises(RuntimeError, match="DATABASE_URL environment variable is required"):
            await cp_module.init_checkpointer()
    
    finally:
        # Restore original DATABASE_URL
        if original_url:
            os.environ["DATABASE_URL"] = original_url


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
