import unittest
import docker
import time
import logging
import botocore
import botocore.session
import uuid
from src.backend_server.model.data_store.s3_manager import S3BucketManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MinIO configuration
MINIO_IMAGE = "minio/minio:latest"
MINIO_PORT = 9000
MINIO_CONSOLE_PORT = 9001
MINIO_ROOT_USER = "minio_access_key_123"
MINIO_ROOT_PASSWORD = "minio_secret_key_password_456"
BUCKET_NAME = "hfmm-artifact-storage"

class TestS3BucketManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up MinIO container before all tests."""
        logger.info("Setting up MinIO container...")
        cls.client = docker.from_env()
        
        # Start MinIO container
        cls.container = cls.client.containers.run(
            MINIO_IMAGE,
            command=["server", "/data", "--console-address", f":{MINIO_CONSOLE_PORT}"],
            environment={
                'MINIO_ROOT_USER': MINIO_ROOT_USER,
                'MINIO_ROOT_PASSWORD': MINIO_ROOT_PASSWORD,
            },
            ports={
                '9000/tcp': ('127.0.0.1', MINIO_PORT),
                '9001/tcp': ('127.0.0.1', MINIO_CONSOLE_PORT)
            },
            detach=True,
            remove=True,
            name=f"minio_test_{uuid.uuid4().hex[:8]}"
        )
        
        # Wait for MinIO to be ready
        cls._wait_for_minio()
        
        # Create S3 client and bucket
        cls.s3_client = botocore.session.get_session().create_client(
            's3',
            endpoint_url=f'http://localhost:{MINIO_PORT}',
            aws_access_key_id=MINIO_ROOT_USER,
            aws_secret_access_key=MINIO_ROOT_PASSWORD,
        )
        
        # Create test bucket
        try:
            cls.s3_client.create_bucket(Bucket=BUCKET_NAME)
            logger.info(f"Created bucket: {BUCKET_NAME}")
        except Exception as e:
            logger.error(f"Error creating bucket: {e}")
            raise

    @classmethod
    def _wait_for_minio(cls, max_attempts: int = 30, delay: int = 2):
        """Wait for MinIO to be ready."""
        for attempt in range(max_attempts):
            try:
                s3_client = botocore.session.get_session().create_client(
                    's3',
                    endpoint_url=f'http://localhost:{MINIO_PORT}',
                    aws_access_key_id=MINIO_ROOT_USER,
                    aws_secret_access_key=MINIO_ROOT_PASSWORD,
                )
                s3_client.list_buckets()
                logger.info(f"MinIO ready after {attempt + 1} attempts")
                return
            except Exception as e:
                logger.info(f"Attempt {attempt + 1}: MinIO not ready yet ({e})")
                time.sleep(delay)
        raise Exception("MinIO container failed to become ready")

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        logger.info("Cleaning up MinIO container...")
        if hasattr(cls, 'container') and cls.container:
            cls.container.stop()

    def setUp(self):
        """Set up test fixtures before each test."""
        from src.backend_server.model.data_store.s3_manager import S3BucketManager
        
        # Initialize S3BucketManager with test configuration
        self.s3_manager = S3BucketManager(
            endpoint_url=f'http://localhost:{MINIO_PORT}',
            aws_access_key_id=MINIO_ROOT_USER,
            aws_secret_access_key=MINIO_ROOT_PASSWORD,
            bucket_name=BUCKET_NAME
        )

    def tearDown(self):
        """Clean up all objects from S3 after each test."""
        self.s3_manager.s3_reset()

    def test_s3_connectivity(self):
        """Test basic connectivity to MinIO."""
        
        # Try to list buckets to verify connectivity
        try:
            buckets = self.s3_manager.s3_client.list_buckets()
            self.assertIn(
                BUCKET_NAME,
                [bucket['Name'] for bucket in buckets['Buckets']],
                f"Bucket {BUCKET_NAME} not found in MinIO"
            )
        except Exception as e:
            self.fail(f"Failed to connect to MinIO: {e}")

    def test_artifact_upload_and_exists(self):
        """Test uploading an artifact and checking its existence."""
        artifact_id = "test-artifact-1"
        content = b"Test content for artifact 1"

        # Upload artifact
        self.s3_manager.s3_artifact_upload(artifact_id, content)

        # Check existence
        self.assertTrue(
            self.s3_manager.s3_artifact_exists(artifact_id),
            "Uploaded artifact should exist in bucket"
        )

    def test_artifact_delete(self):
        """Test deleting an artifact."""
        artifact_id = "test-artifact-2"
        content = b"Test content for artifact 2"

        # Upload and verify
        self.s3_manager.s3_artifact_upload(artifact_id, content)
        self.assertTrue(self.s3_manager.s3_artifact_exists(artifact_id))

        # Delete and verify
        self.s3_manager.s3_artifact_delete(artifact_id)
        self.assertFalse(
            self.s3_manager.s3_artifact_exists(artifact_id),
            "Artifact should not exist after deletion"
        )

    def test_presigned_url_generation(self):
        """Test generating a presigned URL for an artifact."""
        artifact_id = "test-artifact-3"
        content = b"Test content for artifact 3"
        
        # Upload artifact
        self.s3_manager.s3_artifact_upload(artifact_id, content)
        
        # Generate presigned URL
        url = self.s3_manager.s3_generate_presigned_url(artifact_id, expires_in=60)
        
        # Verify URL format and components
        self.assertIsInstance(url, str)
        self.assertIn(f'localhost:{MINIO_PORT}', url)
        self.assertIn(BUCKET_NAME, url)
        self.assertIn(artifact_id, url)

    def test_nonexistent_artifact(self):
        """Test operations with non-existent artifacts."""
        nonexistent_id = "nonexistent-artifact"
        
        # Check existence
        self.assertFalse(
            self.s3_manager.s3_artifact_exists(nonexistent_id),
            "Non-existent artifact should return False"
        )
        
        # Try to delete (should not raise exception)
        try:
            self.s3_manager.s3_artifact_delete(nonexistent_id)
        except Exception as e:
            self.fail(f"Delete of non-existent artifact raised exception: {e}")

    def test_artifact_upload_with_prefix(self):
        """Test artifact upload with custom prefix."""
        custom_prefix = "custom/prefix/"
        s3_manager_with_prefix = S3BucketManager(
            endpoint_url=f'http://localhost:{MINIO_PORT}',
            aws_access_key_id=MINIO_ROOT_USER,
            aws_secret_access_key=MINIO_ROOT_PASSWORD,
            bucket_name=BUCKET_NAME,
            data_prefix=custom_prefix
        )
        
        artifact_id = "test-artifact-4"
        content = b"Test content for artifact 4"
        
        # Upload with custom prefix
        s3_manager_with_prefix.s3_artifact_upload(artifact_id, content)
        
        # Verify existence using the same prefix
        self.assertTrue(
            s3_manager_with_prefix.s3_artifact_exists(artifact_id),
            "Artifact with custom prefix should exist"
        )

    def test_multiple_artifacts(self):
        """Test handling multiple artifacts simultaneously."""
        artifacts = {
            "artifact1": b"Content 1",
            "artifact2": b"Content 2",
            "artifact3": b"Content 3"
        }
        
        # Upload multiple artifacts
        for artifact_id, content in artifacts.items():
            self.s3_manager.s3_artifact_upload(artifact_id, content)
            self.assertTrue(self.s3_manager.s3_artifact_exists(artifact_id))
        
        # Delete them in reverse
        for artifact_id in reversed(list(artifacts.keys())):
            self.s3_manager.s3_artifact_delete(artifact_id)
            self.assertFalse(self.s3_manager.s3_artifact_exists(artifact_id))

    def test_s3_reset(self):
        """Test that s3_reset properly cleans all objects from the bucket."""
        # First ensure bucket is empty
        self.s3_manager.s3_reset()
        
        # Upload multiple artifacts with different prefixes
        test_artifacts = {
            "test1": b"Content 1",
            "nested/test2": b"Content 2",
            "deeply/nested/test3": b"Content 3",
            f"{self.s3_manager.data_prefix}test4": b"Content 4"
        }
        
        # Upload all test artifacts
        for key, content in test_artifacts.items():
            self.s3_manager.s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=key,
                Body=content
            )
        
        # Verify objects were uploaded
        response = self.s3_manager.s3_client.list_objects_v2(Bucket=BUCKET_NAME)
        self.assertIn('Contents', response, "Bucket should contain objects")
        
        # Debug: Print all objects in bucket
        actual_objects = [obj['Key'] for obj in response['Contents']]
        logger.info(f"Objects in bucket: {actual_objects}")
        logger.info(f"Expected objects: {list(test_artifacts.keys())}")
        
        self.assertEqual(
            sorted([obj['Key'] for obj in response['Contents']]),
            sorted(list(test_artifacts.keys())),
            "Bucket should contain exactly the test artifacts"
        )
        
        # Call reset
        self.s3_manager.s3_reset()
        
        # Verify bucket is empty
        response = self.s3_manager.s3_client.list_objects_v2(Bucket=BUCKET_NAME)
        self.assertNotIn(
            'Contents', 
            response, 
            "Bucket should be empty after reset"
        )