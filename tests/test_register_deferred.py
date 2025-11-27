import unittest
import asyncio
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch, MagicMock

from src.backend_server.model.artifact_accessor.register_deferred import RaterTaskManager, rater_task
from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactData, ArtifactType
from src.contracts.model_rating import ModelRating

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestRaterTaskManager(unittest.TestCase):
    """Test suite for RaterTaskManager queueing compute system."""

    def setUp(self):
        """Set up test fixtures before each test."""
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        
        # Create a test artifact
        self.test_artifact = Artifact(
            metadata=ArtifactMetadata(
                name="test-model",
                id="test-id-1",
                type=ArtifactType.model
            ),
            data=ArtifactData(
                url="https://example.com/model",
                download_url=""
            )
        )

    def tearDown(self):
        """Clean up after each test."""
        self.temp_dir.cleanup()

    def test_initialization(self):
        """Test RaterTaskManager initialization with default parameters."""
        manager = RaterTaskManager()

        self.assertEqual(manager.max_processes_per_rater, 1)
        self.assertFalse(manager._running)
        self.assertIsNone(manager._dispatcher)
        self.assertIsNotNone(manager.executor)
        self.assertIsNotNone(manager.queue)

    def test_initialization_custom_params(self):
        """Test RaterTaskManager initialization with custom parameters."""
        manager = RaterTaskManager(max_workers=8, max_processes_per_rater=2)
        self.assertEqual(manager.max_processes_per_rater, 2)

    async def _test_start_manager(self):
        """Helper method to test starting the manager."""
        manager = RaterTaskManager(max_workers=2)
        
        await manager.start()
        
        self.assertTrue(manager._running)
        self.assertIsNotNone(manager._dispatcher)
        self.assertFalse(manager._dispatcher.done())
        
        await manager.shutdown()

    def test_start_manager(self):
        """Test starting the RaterTaskManager."""
        asyncio.run(self._test_start_manager())

    async def _test_submit_task(self):
        """Helper method to test submitting a task."""
        manager = RaterTaskManager(max_workers=2)
        await manager.start()
        
        # Submit a task
        await manager.submit(self.test_artifact, self.temp_path)
        
        # Check queue size
        self.assertEqual(manager.queue.qsize(), 1)
        
        await manager.shutdown()

    def test_submit_task(self):
        """Test submitting a task to the queue."""
        asyncio.run(self._test_submit_task())

    async def _test_multiple_submissions(self):
        """Helper method to test multiple task submissions."""
        manager = RaterTaskManager(max_workers=2)
        await manager.start()
        
        # Submit multiple tasks
        num_tasks = 5
        for i in range(num_tasks):
            artifact = Artifact(
                metadata=ArtifactMetadata(
                    name=f"test-model-{i}",
                    id=f"test-id-{i}",
                    type=ArtifactType.model
                ),
                data=ArtifactData(
                    url=f"https://example.com/model-{i}",
                    download_url=""
                )
            )
            await manager.submit(artifact, self.temp_path)
        
        # Check queue size
        self.assertEqual(manager.queue.qsize(), num_tasks)
        
        await manager.shutdown()

    def test_multiple_submissions(self):
        """Test submitting multiple tasks to the queue."""
        asyncio.run(self._test_multiple_submissions())

    async def _test_dispatch_loop_processes_tasks(self):
        """Helper method to test that dispatch loop processes tasks."""
        manager = RaterTaskManager(max_workers=2, max_processes_per_rater=1)
        await manager.start()
        
        # Submit a task
        await manager.submit(self.test_artifact, self.temp_path)
        
        # Give the dispatch loop time to process
        await asyncio.sleep(0.1)
        
        # Queue should be empty after processing
        self.assertEqual(manager.queue.qsize(), 0)
        
        await manager.shutdown()

    def test_dispatch_loop_processes_tasks(self):
        """Test that dispatch loop processes queued tasks."""
        asyncio.run(self._test_dispatch_loop_processes_tasks())

    async def _test_shutdown_stops_dispatch_loop(self):
        """Helper method to test shutdown stops dispatch loop."""
        manager = RaterTaskManager(max_workers=2)
        await manager.start()
        
        self.assertTrue(manager._running)
        self.assertIsNotNone(manager._dispatcher)
        
        await manager.shutdown()
        
        self.assertFalse(manager._running)
        # Dispatcher should be cancelled
        self.assertTrue(manager._dispatcher.done())

    def test_shutdown_stops_dispatch_loop(self):
        """Test that shutdown properly stops the dispatch loop."""
        asyncio.run(self._test_shutdown_stops_dispatch_loop())

    async def _test_shutdown_with_pending_tasks(self):
        """Helper method to test shutdown with pending tasks."""
        manager = RaterTaskManager(max_workers=2)
        await manager.start()
        
        # Submit tasks
        await manager.submit(self.test_artifact, self.temp_path)
        await manager.submit(self.test_artifact, self.temp_path)
        
        # Shutdown should complete even with pending tasks
        await manager.shutdown()
        
        self.assertFalse(manager._running)

    def test_shutdown_with_pending_tasks(self):
        """Test shutdown behavior with pending tasks in queue."""
        asyncio.run(self._test_shutdown_with_pending_tasks())

    async def _test_concurrent_submissions(self):
        """Helper method to test concurrent task submissions."""
        manager = RaterTaskManager(max_workers=4)
        
        # Submit tasks concurrently
        async def submit_task(i):
            artifact = Artifact(
                metadata=ArtifactMetadata(
                    name=f"test-model-{i}",
                    id=f"test-id-{i}",
                    type=ArtifactType.model
                ),
                data=ArtifactData(
                    url=f"https://example.com/model-{i}",
                    download_url=""
                )
            )
            await manager.submit(artifact, self.temp_path)
        
        # Submit 10 tasks concurrently
        await asyncio.gather(*[submit_task(i) for i in range(10)])
        
        # All tasks should be in queue
        self.assertEqual(manager.queue.qsize(), 10)

        await manager.start()

        await asyncio.sleep(0.5)
        
        await manager.shutdown()

    def test_concurrent_submissions(self):
        """Test concurrent task submissions."""
        asyncio.run(self._test_concurrent_submissions())

    @patch('src.backend_server.model.artifact_accessor.register_deferred.ModelRating')
    def test_rater_task_function(self, mock_model_rating):
        """Test the rater_task function."""
        # Mock ModelRating.generate_rating
        mock_rating = Mock(spec=ModelRating)
        mock_model_rating.generate_rating.return_value = mock_rating
        
        # Call rater_task
        result = rater_task(self.test_artifact, self.temp_path, processes=1)
        
        # Verify ModelRating.generate_rating was called correctly
        mock_model_rating.generate_rating.assert_called_once_with(
            self.temp_path,
            self.test_artifact,
            1
        )
        
        # Verify result
        self.assertEqual(result, mock_rating)

    async def _test_task_execution_through_executor(self):
        """Helper method to test task execution through ProcessPoolExecutor."""
        manager = RaterTaskManager(max_workers=2, max_processes_per_rater=1)
        await manager.start()
        
        # Submit a task
        await manager.submit(self.test_artifact, self.temp_path)
        
        # Wait a bit for task to be dispatched
        await asyncio.sleep(0.2)
        
        # Queue should be processed
        self.assertEqual(manager.queue.qsize(), 0)
        
        await manager.shutdown()

    def test_task_execution_through_executor(self):
        """Test that tasks are executed through ProcessPoolExecutor."""
        asyncio.run(self._test_task_execution_through_executor())

    async def _test_max_workers_configuration(self):
        """Helper method to test max_workers configuration."""
        manager = RaterTaskManager(max_workers=1)
        await manager.start()
        
        # Submit multiple tasks
        for i in range(3):
            await manager.submit(self.test_artifact, self.temp_path)
        
        # Tasks should be queued
        self.assertEqual(manager.queue.qsize(), 3)
        
        await manager.shutdown()

    def test_max_workers_configuration(self):
        """Test that max_workers limits concurrent task execution."""
        asyncio.run(self._test_max_workers_configuration())

    async def _test_empty_queue_handling(self):
        """Helper method to test handling of empty queue."""
        manager = RaterTaskManager(max_workers=2)
        await manager.start()
        
        # Start with empty queue
        self.assertEqual(manager.queue.qsize(), 0)
        
        # Dispatch loop should wait for tasks
        await asyncio.sleep(0.1)
        
        # Still running
        self.assertTrue(manager._running)
        
        await manager.shutdown()

    def test_empty_queue_handling(self):
        """Test that dispatch loop handles empty queue correctly."""
        asyncio.run(self._test_empty_queue_handling())

    async def _test_multiple_start_calls(self):
        """Helper method to test multiple start calls."""
        manager = RaterTaskManager(max_workers=2)
        
        await manager.start()
        first_dispatcher = manager._dispatcher
        
        # Starting again should create a new dispatcher
        await manager.start()
        
        # Should have a new dispatcher (old one may be cancelled or replaced)
        self.assertIsNotNone(manager._dispatcher)
        
        await manager.shutdown()

    def test_multiple_start_calls(self):
        """Test behavior when start is called multiple times."""
        asyncio.run(self._test_multiple_start_calls())

    async def _test_shutdown_idempotency(self):
        """Helper method to test shutdown idempotency."""
        manager = RaterTaskManager(max_workers=2)
        await manager.start()
        
        # Shutdown multiple times should not raise errors
        await manager.shutdown()
        await manager.shutdown()
        await manager.shutdown()
        
        self.assertFalse(manager._running)

    def test_shutdown_idempotency(self):
        """Test that shutdown can be called multiple times safely."""
        asyncio.run(self._test_shutdown_idempotency())


class TestRaterTaskManagerIntegration(unittest.TestCase):
    """Integration tests for RaterTaskManager with real file paths."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        
        # Create a minimal directory structure for testing
        (self.temp_path / "README.md").write_text("# Test Model\n")
        
        self.test_artifact = Artifact(
            metadata=ArtifactMetadata(
                name="integration-test-model",
                id="integration-test-id",
                type=ArtifactType.model
            ),
            data=ArtifactData(
                url="https://example.com/integration-test",
                download_url=""
            )
        )

    def tearDown(self):
        """Clean up after each test."""
        self.temp_dir.cleanup()

    async def _test_end_to_end_task_processing(self):
        """Helper method for end-to-end task processing test."""
        manager = RaterTaskManager(max_workers=2, max_processes_per_rater=1)
        await manager.start()
        
        # Submit task
        await manager.submit(self.test_artifact, self.temp_path)
        
        # Wait for processing (note: actual rating generation may take time)
        # In a real scenario, you might want to wait longer or check completion differently
        await asyncio.sleep(0.5)
        
        # Queue should be empty
        self.assertEqual(manager.queue.qsize(), 0)
        
        await manager.shutdown()

    def test_end_to_end_task_processing(self):
        """Test end-to-end task processing with real file path."""
        # Note: This test may take longer due to actual ModelRating generation
        # You may want to mock ModelRating.generate_rating for faster tests
        asyncio.run(self._test_end_to_end_task_processing())


if __name__ == '__main__':
    unittest.main()
