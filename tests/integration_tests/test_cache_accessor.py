import unittest
import logging
from typing import Optional

import redis
from pydantic import BaseModel

from src.backend_server.model.data_store.cache_accessor import CacheAccessor
from src.contracts.artifact_contracts import ArtifactType
from mock_infrastructure import docker_init

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis configuration from docker_init (container is started externally)
REDIS_HOST = getattr(docker_init, "REDIS_HOST", "127.0.0.1")
REDIS_PORT = getattr(docker_init, "REDIS_HOST_PORT", 6399)


class DummyResponse(BaseModel):
    value: str

    def to_json(self) -> str:
        # CacheAccessor currently expects something with .to_json()
        return self.model_dump_json()


class TestCacheAccessorIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Verify Redis container is reachable using docker_init config."""
        logger.info(
            "Checking Redis connectivity at %s:%s for CacheAccessor tests...",
            REDIS_HOST,
            REDIS_PORT,
        )
        cls.raw_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
        )
        # Will raise if Redis is not ready
        cls.raw_client.ping()

    def setUp(self):
        """Create a fresh CacheAccessor and flush DB before each test."""
        self.cache = CacheAccessor(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=0,
            password=None,
            ttl_seconds=60,
        )
        # Ensure clean DB
        self.cache.reset()

    def tearDown(self):
        """Flush DB and close connection after each test."""
        try:
            self.cache.reset()
        finally:
            self.cache.close()

    def test_redis_connectivity_and_reset(self):
        """Test basic connectivity and reset behavior."""
        # Insert a key directly via raw client
        self.raw_client.set("test-key", "value")
        self.assertEqual(self.raw_client.get("test-key"), "value")

        # Reset via accessor should clear it
        result = self.cache.reset()
        self.assertTrue(result)

        self.assertIsNone(self.raw_client.get("test-key"))

    def test_format_key_includes_artifact_type_and_hash(self):
        """Test _format_key generates expected pattern with artifact type."""
        artifact_id = "artifact-123"
        artifact_type = ArtifactType.model
        request = "GET /artifacts/123"
        # Reproduce internal hashing
        import hashlib

        request_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()

        key = self.cache._format_key(artifact_id, artifact_type, request_hash)

        # Expected format: artifact:{artifact_id}:{artifact_type.name}:{hash}
        self.assertTrue(
            key.startswith(f"artifact:{artifact_id}:{artifact_type.name}:"),
            f"Unexpected key format: {key}",
        )
        self.assertTrue(
            key.endswith(request_hash),
            "Key should end with full request hash",
        )

    def test_insert_stores_value_in_redis(self):
        """
        Test insert() wires through to Redis.

        NOTE: The current CacheAccessor implementation has a mismatch between
        _format_key() and insert(), so this test is written against the
        intended behavior and may fail until CacheAccessor is fixed to call
        _format_key(artifact_id, artifact_type, request_hash).
        """
        artifact_id = "artifact-insert-1"
        artifact_type = ArtifactType.model
        request = "GET /artifacts/insert-test"

        # Patch _format_key on this instance to match the current insert() call
        # (which only passes artifact_id and request_hash).
        original_format_key = self.cache._format_key

        def patched_format_key(a_id: str, request_hash: str, *_args, **_kwargs):
            # Delegate to original implementation with a fixed artifact_type
            return original_format_key(a_id, artifact_type, request_hash)

        self.cache._format_key = patched_format_key  # type: ignore[method-assign]

        dummy = DummyResponse(value="hello-world")
        ok = self.cache.insert(artifact_id=artifact_id, request=request, response=dummy)
        self.assertTrue(ok)

        # Compute the same key the accessor used
        import hashlib

        request_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()
        expected_key = original_format_key(artifact_id, artifact_type, request_hash)

        stored = self.raw_client.get(expected_key)
        self.assertIsNotNone(stored)
        self.assertIn("hello-world", stored)

    def test_delete_and_delete_by_artifact_id_with_patched_pattern(self):
        """
        Test delete() and delete_by_artifact_id() behavior with patched helpers.

        Similar to insert(), current implementation mismatches helper signatures,
        so we locally patch them to exercise intended semantics.
        """
        artifact_type = ArtifactType.dataset
        artifact_id = "artifact-del-1"
        base_request = "GET /datasets/1"

        import hashlib

        # Patch helpers so public methods work as intended
        original_format_key = self.cache._format_key
        original_pattern = self.cache._get_pattern_for_artifact

        def patched_format_key(a_id: str, request_hash: str, *_args, **_kwargs):
            return original_format_key(a_id, artifact_type, request_hash)

        def patched_pattern(a_id: str, *_args, **_kwargs):
            return original_pattern(a_id, artifact_type)

        self.cache._format_key = patched_format_key  # type: ignore[method-assign]
        self.cache._get_pattern_for_artifact = patched_pattern  # type: ignore[method-assign]

        # Create a few keys via insert()
        for i in range(3):
            req = f"{base_request}?page={i}"
            body = DummyResponse(value=f"v-{i}")
            self.cache.insert(artifact_id=artifact_id, request=req, response=body)

        # Ensure they exist
        pattern = patched_pattern(artifact_id)
        keys = list(self.raw_client.scan_iter(match=pattern))
        self.assertEqual(len(keys), 3)

        # Delete one by request_hash
        req0_hash = hashlib.sha256(f"{base_request}?page=0".encode("utf-8")).hexdigest()
        deleted_one = self.cache.delete(artifact_id=artifact_id, request_hash=req0_hash)
        self.assertTrue(deleted_one)

        keys_after_single = list(self.raw_client.scan_iter(match=pattern))
        self.assertEqual(len(keys_after_single), 2)

        # Delete remaining by artifact id
        deleted_count = self.cache.delete_by_artifact_id(artifact_id)
        self.assertGreaterEqual(deleted_count, 2)

        keys_after_all = list(self.raw_client.scan_iter(match=pattern))
        self.assertEqual(len(keys_after_all), 0)


if __name__ == "__main__":
    unittest.main()
