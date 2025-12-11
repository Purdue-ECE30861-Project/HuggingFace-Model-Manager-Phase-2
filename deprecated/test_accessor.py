import tempfile
import unittest

import boto3
from botocore.exceptions import ClientError

from src.backend_server.model.artifact_accessor.artifact_accessor import ArtifactAccessor
from src.backend_server.model.artifact_accessor.register_direct import *
from src.backend_server.model.data_store.database_connectors.audit_database import SQLAuditAccessor
from src.contracts.artifact_contracts import (
    ArtifactQuery, ArtifactID, ArtifactName, ArtifactRegEx,
)
from src.mock_infrastructure import docker_init

logger = logging.getLogger(__name__)

# MySQL settings from docker_init
MYSQL_PORT = getattr(docker_init, "MYSQL_HOST_PORT", 3307)
MYSQL_ROOT_PASSWORD = getattr(docker_init, "MYSQL_ROOT_PASSWORD", "root")
MYSQL_DATABASE = getattr(docker_init, "MYSQL_DATABASE", "test_db")
MYSQL_USER = getattr(docker_init, "MYSQL_USER", "test_user")
MYSQL_PASSWORD = getattr(docker_init, "MYSQL_PASSWORD", "test_password")

DATA_PREFIX = "test_"

class TestAccessor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures using docker_init helper."""
        logger.info("Starting MySQL container via docker_init helper...")
        
        # Initialize database connection
        db_url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@127.0.0.1:{MYSQL_PORT}/{MYSQL_DATABASE}"
        cls.db = SQLMetadataAccessor(db_url)
        cls.audit_db = SQLAuditAccessor(db_url)
        
        # Create S3 client and bucket manager
        s3_client = boto3.client(
            "s3",
            endpoint_url=f"http://127.0.0.1:{docker_init.MINIO_HOST_PORT}",
            aws_access_key_id=docker_init.MINIO_ROOT_USER,
            aws_secret_access_key=docker_init.MINIO_ROOT_PASSWORD,
        )
        try: s3_client.create_bucket(Bucket=docker_init.MINIO_BUCKET)
        except ClientError:
            logger.info("S3 bucket already started")
        s3_client.close()
        cls.s3_manager = S3BucketManager(
            f"http://127.0.0.1:{docker_init.MINIO_HOST_PORT}",
            bucket_name=docker_init.MINIO_BUCKET,
            data_prefix=DATA_PREFIX,
            aws_access_key_id=docker_init.MINIO_ROOT_USER,
            aws_secret_access_key=docker_init.MINIO_ROOT_PASSWORD
        )
        cls.accessor: ArtifactAccessor = ArtifactAccessor(
            cls.db,
            cls.audit_db,
            cls.s3_manager
        )

    @classmethod
    def tearDownClass(cls):
        """Clean up test fixtures using docker_init helper."""
        logger.info("Cleaning up MySQL container via docker_init helper...")

    def tearDown(self):
        self.db.reset_db()
        self.s3_manager.s3_reset()


    def test_register_artifact_flow(self):
        """Full integration test for artifact creation, rating, and registration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            (temp_path / "dummy.txt").write_text("example artifact data")

            artifact_data = ArtifactData(
                url="https://huggingface.co/arnir0/Tiny-LLM",
                download_url=""
            )

            new_artifact, rating = artifact_and_rating_direct(
                temp_path, artifact_data, ArtifactType.model, num_processors=1
            )

            result, stored = register_data_store(
                self.s3_manager,
                self.db,
                new_artifact,
                rating,
                temp_path
            )

            self.assertEqual(result, RegisterArtifactEnum.SUCCESS)
            self.assertIsNotNone(stored)

            # Verify upload
            objects = self.s3_manager.s3_client.list_objects_v2(Bucket=docker_init.MINIO_BUCKET, Prefix=DATA_PREFIX)
            self.assertTrue(any(obj['Key'].endswith(new_artifact.metadata.id) for obj in objects.get('Contents', [])))

            # Verify DB insert
            in_db = self.db.get_by_id(new_artifact.metadata.id, ArtifactType.model)
            self.assertIsNotNone(in_db, "Artifact not stored in database")

    def test_get_artifacts_empty(self):
        query = ArtifactQuery(name="nonexistent", types=[ArtifactType.model])
        status, results = self.accessor.get_artifacts(query, "0")
        self.assertEqual(status, GetArtifactsEnum.TOO_MANY_ARTIFACTS)
        self.assertEqual(results, [])

    def test_register_and_get_artifact(self):
        # Create dummy artifact data
        data = ArtifactData(url="https://huggingface.co/prajjwal1/bert-tiny", download_url="")
        artifact_type = ArtifactType.model

        # Register artifact
        status, artifact = self.accessor.register_artifact(artifact_type, data)
        self.assertEqual(status, RegisterArtifactEnum.SUCCESS)
        self.assertIsNotNone(artifact)

        # Verify presence by ID
        status_get, retrieved = self.accessor.get_artifact(artifact_type, ArtifactID(id=artifact.metadata.id))
        self.assertEqual(status_get, GetArtifactEnum.SUCCESS)
        self.assertEqual(retrieved.metadata.id, artifact.metadata.id)
        self.assertTrue(retrieved.data.download_url.startswith("http"))

    def test_register_existing_artifact(self):
        data = ArtifactData(url="https://huggingface.co/prajjwal1/bert-tiny", download_url="")
        artifact_type = ArtifactType.model

        # First registration
        status, artifact = self.accessor.register_artifact(artifact_type, data)
        self.assertEqual(status, RegisterArtifactEnum.SUCCESS)

        # Second registration should detect existing
        status2, artifact2 = self.accessor.register_artifact(artifact_type, data)
        self.assertEqual(status2, RegisterArtifactEnum.ALREADY_EXISTS)
        self.assertIsNone(artifact2)

    def test_get_artifact_by_name(self):
        data = ArtifactData(url="https://huggingface.co/prajjwal1/bert-tiny", download_url="")
        artifact_type = ArtifactType.model
        status, artifact = self.accessor.register_artifact(artifact_type, data)

        status_name, results = self.accessor.get_artifact_by_name(ArtifactName(name=artifact.metadata.name))
        self.assertEqual(status_name, GetArtifactEnum.SUCCESS)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].id, artifact.metadata.id)

    def test_get_artifact_by_regex(self):
        data = ArtifactData(url="https://huggingface.co/prajjwal1/bert-tiny", download_url="")
        artifact_type = ArtifactType.model
        status, artifact = self.accessor.register_artifact(artifact_type, data)

        regex = artifact.metadata.name[:5]  # partial match
        status_re, results = self.accessor.get_artifact_by_regex(ArtifactRegEx(regex=regex))
        self.assertEqual(status_re, GetArtifactEnum.SUCCESS)
        self.assertTrue(any(r.id == artifact.metadata.id for r in results))

    def test_update_artifact(self):
        data = ArtifactData(url="https://huggingface.co/prajjwal1/bert-tiny", download_url="")
        artifact_type = ArtifactType.model
        status, artifact = self.accessor.register_artifact(artifact_type, data)

        # Update URL
        updated_data = Artifact(
            metadata=artifact.metadata,
            data=ArtifactData(url="https://huggingface.co/arnir0/Tiny-LLM", download_url="")
        )
        result = self.accessor.update_artifact(artifact_type, ArtifactID(id=artifact.metadata.id), updated_data)
        self.assertEqual(result, GetArtifactEnum.SUCCESS)

        # Verify updated
        status_get, updated = self.accessor.get_artifact(artifact_type, ArtifactID(id=artifact.metadata.id))
        self.assertEqual(updated.data.url, "https://huggingface.co/arnir0/Tiny-LLM")

    def test_delete_artifact(self):
        data = ArtifactData(url="https://huggingface.co/arnir0/Tiny-LLM", download_url="")
        artifact_type = ArtifactType.model
        status, artifact = self.accessor.register_artifact(artifact_type, data)

        # Delete
        result = self.accessor.delete_artifact(artifact_type, ArtifactID(id=artifact.metadata.id))
        self.assertEqual(result, GetArtifactEnum.SUCCESS)

        # Verify deletion
        status_get, retrieved = self.accessor.get_artifact(artifact_type, ArtifactID(id=artifact.metadata.id))
        self.assertEqual(status_get, GetArtifactEnum.DOES_NOT_EXIST)
        self.assertIsNone(retrieved)


if __name__ == "__main__":
    unittest.main()