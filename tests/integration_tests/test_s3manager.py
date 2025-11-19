import unittest
import logging
import uuid
import tempfile
import zipfile
from pathlib import Path
import boto3
import requests
from mock_infrastructure import docker_init

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MinIO configuration (kept for test-level visibility; docker_init controls actual values)
MINIO_PORT = getattr(docker_init, "MINIO_HOST_PORT", 9000)
MINIO_CONSOLE_PORT = getattr(docker_init, "MINIO_CONSOLE_PORT", 9001)
MINIO_ROOT_USER = getattr(docker_init, "MINIO_ROOT_USER", "minio_access_key_123")
MINIO_ROOT_PASSWORD = getattr(docker_init, "MINIO_ROOT_PASSWORD", "minio_secret_key_password_456")
BUCKET_NAME = getattr(docker_init, "MINIO_BUCKET", "hfmm-artifact-storage")

class TestS3BucketManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up MinIO container before all tests using docker_init helper."""
        logger.info("Setting up MinIO container via docker_init helper...")
        # ensure bucket exists (idempotent)
        docker_init.create_minio_bucket(bucket=BUCKET_NAME)
        # expose boto3 client from docker_init for convenience if available
        cls.s3_client = getattr(docker_init, "boto3_client", None)
        if cls.s3_client is None:
            # create a local boto3 client if docker_init didn't expose one
            cls.s3_client = boto3.client(
                's3',
                endpoint_url=f'http://localhost:{MINIO_PORT}',
                aws_access_key_id=MINIO_ROOT_USER,
                aws_secret_access_key=MINIO_ROOT_PASSWORD,
                config=boto3.session.Config(signature_version='s3v4'),
                verify=False
            )

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

    def test_s3_upload_and_download(self):
        """Test uploading and downloading an artifact"""
        # Create temporary zip file
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
            with zipfile.ZipFile(tmp_zip, 'w') as zipf:
                zipf.writestr("dummy.txt", "test content")
            tmp_zip_path = Path(tmp_zip.name)

        artifact_id = f"artifact_{uuid.uuid4().hex[:8]}"
        download_path = Path(tempfile.mktemp(suffix=".zip"))

        # Upload and download
        self.s3_manager.s3_artifact_upload(artifact_id, tmp_zip_path)
        self.assertTrue(self.s3_manager.s3_artifact_exists(artifact_id))

        self.s3_manager.s3_artifact_download(artifact_id, download_path)
        self.assertTrue(download_path.exists())
        self.assertGreater(download_path.stat().st_size, 0)

        with zipfile.ZipFile(download_path, 'r') as zipf:
            with zipf.open("dummy.txt") as f:
                content = f.read().decode()
                self.assertEqual(content, "test content")
        # Cleanup
        tmp_zip_path.unlink(missing_ok=True)
        download_path.unlink(missing_ok=True)

    def test_s3_artifact_exists_and_delete(self):
        """Test existence check and deletion of artifact"""
        artifact_id = f"artifact_{uuid.uuid4().hex[:8]}"
        temp_file = Path(tempfile.mktemp())
        temp_file.write_text("dummy content")

        self.s3_manager.s3_artifact_upload(artifact_id, temp_file)
        self.assertTrue(self.s3_manager.s3_artifact_exists(artifact_id))

        self.s3_manager.s3_artifact_delete(artifact_id)
        self.assertFalse(self.s3_manager.s3_artifact_exists(artifact_id))

        temp_file.unlink(missing_ok=True)

    def test_s3_presigned_url(self):
        """Test generating and downloading via presigned URL"""
        artifact_id = f"artifact_{uuid.uuid4().hex[:8]}"
        content = b"presigned test content"
        temp_file = Path(tempfile.mktemp())
        temp_file.write_bytes(content)

        self.s3_manager.s3_artifact_upload(artifact_id, temp_file)
        url = self.s3_manager.s3_generate_presigned_url(artifact_id, expires_in=300)
        self.assertIsNotNone(url)

        # Verify content can be downloaded via presigned URL
        response = requests.get(url, timeout=10)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, content)

        download_path = Path(tempfile.mktemp())
        self.s3_manager.s3_artifact_download(artifact_id, download_path)
        self.assertEqual(download_path.read_bytes(), content)

        temp_file.unlink(missing_ok=True)
        download_path.unlink(missing_ok=True)

    def test_s3_reset(self):
            """Test clearing all artifacts in the bucket"""
            artifact_ids = [f"artifact_{uuid.uuid4().hex[:8]}" for _ in range(3)]

            # Upload dummy files
            for artifact_id in artifact_ids:
                tmp = Path(tempfile.mktemp())
                tmp.write_text("reset test")
                self.s3_manager.s3_artifact_upload(artifact_id, tmp)
                tmp.unlink(missing_ok=True)

            # Verify existence
            for artifact_id in artifact_ids:
                self.assertTrue(self.s3_manager.s3_artifact_exists(artifact_id))

            # Reset and verify deletion
            self.s3_manager.s3_reset()
            for artifact_id in artifact_ids:
                self.assertFalse(self.s3_manager.s3_artifact_exists(artifact_id))

    def test_full_s3_integration_flow(self):
        # Step 1: Create temporary zip artifact
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
            with zipfile.ZipFile(tmp_zip, 'w') as zipf:
                zipf.writestr("artifact.txt", "integrated content check")
            tmp_zip_path = Path(tmp_zip.name)

        artifact_id = f"artifact_{uuid.uuid4().hex[:8]}"
        expected_text = "integrated content check"
        download_path_1 = Path(tempfile.mktemp(suffix=".zip"))
        download_path_2 = Path(tempfile.mktemp(suffix=".zip"))

        # Step 2: Upload artifact
        self.s3_manager.s3_artifact_upload(artifact_id, tmp_zip_path)
        self.assertTrue(self.s3_manager.s3_artifact_exists(artifact_id))

        # Step 3: Generate presigned URL and download via HTTP
        url = self.s3_manager.s3_generate_presigned_url(artifact_id, expires_in=300)
        self.assertIsNotNone(url)
        response = requests.get(url, timeout=10)
        self.assertEqual(response.status_code, 200)
        with tempfile.NamedTemporaryFile(delete=False) as presigned_download:
            presigned_download.write(response.content)
            presigned_path = Path(presigned_download.name)

        # Step 4: Download directly via boto3 and compare
        self.s3_manager.s3_artifact_download(artifact_id, download_path_1)
        self.assertTrue(download_path_1.exists())
        self.assertGreater(download_path_1.stat().st_size, 0)
        self.assertEqual(download_path_1.read_bytes(), presigned_path.read_bytes())

        # Step 5: Verify file contents inside zip
        with zipfile.ZipFile(download_path_1, 'r') as zipf:
            with zipf.open("artifact.txt") as f:
                content = f.read().decode()
                self.assertEqual(content, expected_text)

        # Step 6: Re-upload modified artifact to simulate overwrite
        with zipfile.ZipFile(tmp_zip_path, 'w') as zipf:
            zipf.writestr("artifact.txt", "modified content")
        self.s3_manager.s3_artifact_upload(artifact_id, tmp_zip_path)
        self.s3_manager.s3_artifact_download(artifact_id, download_path_2)

        with zipfile.ZipFile(download_path_2, 'r') as zipf:
            with zipf.open("artifact.txt") as f:
                modified_content = f.read().decode()
                self.assertEqual(modified_content, "modified content")

        # Step 7: Delete artifact and verify nonexistence
        self.s3_manager.s3_artifact_delete(artifact_id)
        self.assertFalse(self.s3_manager.s3_artifact_exists(artifact_id))

        # Step 8: Upload multiple artifacts and reset bucket
        for i in range(3):
            tmp = Path(tempfile.mktemp())
            tmp.write_text(f"bulk content {i}")
            self.s3_manager.s3_artifact_upload(f"bulk_{i}", tmp)
            tmp.unlink(missing_ok=True)

        self.s3_manager.s3_reset()
        for i in range(3):
            self.assertFalse(self.s3_manager.s3_artifact_exists(f"bulk_{i}"))

        # Cleanup
        for p in [tmp_zip_path, download_path_1, download_path_2, presigned_path]:
            p.unlink(missing_ok=True)
