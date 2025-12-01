import unittest
import logging
import hashlib

from pydantic import BaseModel
import redis

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
        # CacheAccessor.insert() calls response.to_json()
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
        self.cache.reset()

    def tearDown(self):
        """Flush DB and close connection after each test."""
        try:
            self.cache.reset()
        finally:
            self.cache.close()

    def test_redis_connectivity_and_reset(self):
        """Test basic connectivity and reset behavior using the real Redis client."""
        # Set a key directly
        self.cache.redis_client.set("test-key", "value")
        self.assertEqual(self.cache.redis_client.get("test-key"), "value")

        # Reset via accessor should clear it
        ok = self.cache.reset()
        self.assertTrue(ok)
        self.assertIsNone(self.cache.redis_client.get("test-key"))

    def test_format_key_and_pattern_helpers(self):
        """
        Test private helpers _format_key and _get_pattern_for_artifact
        with their actual signatures.
        """
        artifact_id = "artifact-123"
        artifact_type = ArtifactType.model
        request = "GET /artifacts/123"
        request_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()

        key = self.cache._format_key(artifact_id, artifact_type, request_hash)
        self.assertTrue(
            key.startswith(f"artifact:{artifact_id}:{artifact_type.name}:"),
            f"Unexpected key format: {key}",
        )
        self.assertTrue(
            key.endswith(request_hash),
            "Key should end with full request hash",
        )

        pattern = self.cache._get_pattern_for_artifact(artifact_id, artifact_type)
        self.assertEqual(
            pattern,
            f"artifact:{artifact_id}:{artifact_type.name}:*",
        )

    def test_insertion_procedure(self):
        artifact_id = "artifact-123"
        artifact_type = ArtifactType.model
        request = "GET /artifacts/123"
        request_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()
        response = "200 OK"

        self.assertTrue(self.cache.insert(artifact_id, artifact_type, request_hash, response), "Insertion failed")
        result_list = list(self.cache.redis_client.scan_iter(self.cache._get_pattern_for_artifact(artifact_id, artifact_type)))
        self.assertIsNotNone(result_list)
        self.assertGreater(len(result_list), 0, "Did not add properly")
        self.assertEqual(self.cache.delete_by_artifact_id(artifact_id, artifact_type), 1, "Deletion failure")
        result_list = list(self.cache.redis_client.scan_iter(self.cache._get_pattern_for_artifact(artifact_id, artifact_type)))
        self.assertEqual(len(result_list), 0, "Did delete properly")

        self.assertTrue(self.cache.insert(artifact_id, artifact_type, request_hash, response), "Insertion failed")

        artifact_id = "artifact-123"
        artifact_type = ArtifactType.model
        request = "GET /artifacts/123"
        request_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()
        response = "500 BAD REQUEST"
        self.assertTrue(self.cache.insert(artifact_id, artifact_type, request_hash, response), "Insertion failed")
        result_list = list(
            self.cache.redis_client.scan_iter(self.cache._get_pattern_for_artifact(artifact_id, artifact_type)))
        result_list[0] = "500 BAD REQUEST"


if __name__ == "__main__":
    unittest.main()
