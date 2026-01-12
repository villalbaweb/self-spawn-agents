import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import sys
import os

# Add paths to allow importing 'backend' package and 'agent' module
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Import after path setup
# We need to test specific functions, not necessarily mock the whole module dict at import time 
# if we can just patch it in the test method or setup.
# But "running_tasks" is global.
from backend.main import cancel_orchestrator, running_tasks

class TestCancellation(unittest.IsolatedAsyncioTestCase):
    
    async def test_cancel_existing_task(self):
        """Verify that cancel_orchestrator calls .cancel() on the task."""
        print("\n🧪 Testing Task Cancellation...")
        
        req_id = "test-req-123"
        mock_task = MagicMock()
        
        # Manually add to the real global registry for the test
        running_tasks[req_id] = mock_task
        
        try:
            response = await cancel_orchestrator(req_id)
            
            print(f"Cancel Response: {response}")
            self.assertEqual(response["status"], "cancelled")
            mock_task.cancel.assert_called_once()
        finally:
            # Cleanup
            if req_id in running_tasks:
                del running_tasks[req_id]
        
    async def test_cancel_non_existent_task(self):
        """Verify 404 for unknown task."""
        print("\n🧪 Testing Cancel Unknown Task...")
        
        from fastapi import HTTPException
        
        with self.assertRaises(HTTPException) as cm:
            await cancel_orchestrator("unknown-id")
            
        self.assertEqual(cm.exception.status_code, 404)

if __name__ == "__main__":
    unittest.main()
