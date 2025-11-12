import unittest
import docker
import time
import logging
import hashlib
import tempfile
import os
import shutil
from pathlib import Path
import pymysql
import boto3

from botocore import exceptions as botoexc
from src.backend_server.model.data_store.database import SQLMetadataAccessor, ArtifactDataDB
from src.backend_server.model.data_store.s3_manager import S3BucketManager
from src.contracts.artifact_contracts import (
    Artifact,
    ArtifactData,
    ArtifactMetadata,
    ArtifactType, ArtifactQuery, ArtifactID, ArtifactName, ArtifactRegEx,
)
from src.contracts.model_rating import ModelRating
from src.backend_server.model.artifact_accessor.register_direct import *
from src.backend_server.model.artifact_accessor.artifact_accessor import RegisterArtifactEnum, GetArtifactEnum, \
    GetArtifactsEnum, ArtifactAccessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Docker image configs
MYSQL_IMAGE = "mysql:8.0"
MINIO_IMAGE = "minio/minio:latest"

MYSQL_PORT = 3307
MINIO_PORT = 9000
MINIO_CONSOLE_PORT = 9001
MYSQL_ROOT_PASSWORD = "root"
MYSQL_DATABASE = "test_db"
MYSQL_USER = "test_user"
MYSQL_PASSWORD = "test_password"
BUCKET_NAME = "artifact-bucket"
DATA_PREFIX = "artifacts/"


class TestRegisterDataStoreIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logger.info("Setting up infrastructure")
        cls.docker_client = docker.from_env()

        # MySQL container
        cls.mysql_container = cls.docker_client.containers.run(
            MYSQL_IMAGE,
            environment={
                'MYSQL_ROOT_PASSWORD': MYSQL_ROOT_PASSWORD,
                'MYSQL_DATABASE': MYSQL_DATABASE,
                'MYSQL_USER': MYSQL_USER,
                'MYSQL_PASSWORD': MYSQL_PASSWORD,
            },
            ports={'3306/tcp': ('127.0.0.1', MYSQL_PORT)},
            detach=True,
            remove=True,
            name=f"mysql_int_{os.getpid()}"
        )

        # MinIO container
        cls.minio_container = cls.docker_client.containers.run(
            MINIO_IMAGE,
            command=["server", "/data", "--console-address", f":{MINIO_CONSOLE_PORT}"],
            environment={
                "MINIO_ROOT_USER": "minio_access_key",
                "MINIO_ROOT_PASSWORD": "minio_secret_key"
            },
            ports={
                '9000/tcp': ('127.0.0.1', MINIO_PORT),
                '9001/tcp': ('127.0.0.1', MINIO_CONSOLE_PORT)
            },
            detach=True,
            remove=True,
            name=f"minio_int_{os.getpid()}"
        )

        logger.info("Awaiting infrastructure")
        cls._wait_for_mysql()
        cls._wait_for_minio()
        logger.info("Infrastructure setup complete")

        # Create SQL accessor
        db_url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@127.0.0.1:{MYSQL_PORT}/{MYSQL_DATABASE}"
        cls.db = SQLMetadataAccessor(db_url)

        # Create S3 client and bucket manager
        s3_client = boto3.client(
            "s3",
            endpoint_url=f"http://127.0.0.1:{MINIO_PORT}",
            aws_access_key_id="minio_access_key",
            aws_secret_access_key="minio_secret_key",
        )
        s3_client.create_bucket(Bucket=BUCKET_NAME)
        s3_client.close()
        cls.s3_manager = S3BucketManager(f"http://127.0.0.1:{MINIO_PORT}", bucket_name=BUCKET_NAME, data_prefix=DATA_PREFIX, aws_access_key_id="minio_access_key", aws_secret_access_key="minio_secret_key")
        cls.accessor: ArtifactAccessor = ArtifactAccessor(
            cls.db,
            cls.s3_manager
        )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "mysql_container"):
            cls.mysql_container.stop()
        if hasattr(cls, "minio_container"):
            cls.minio_container.stop()

    @classmethod
    def _wait_for_mysql(cls, max_attempts=20, delay=2):
        for i in range(max_attempts):
            try:
                pymysql.connect(
                    host="127.0.0.1",
                    port=MYSQL_PORT,
                    user=MYSQL_USER,
                    password=MYSQL_PASSWORD,
                    database=MYSQL_DATABASE,
                ).close()
                return
            except Exception:
                time.sleep(delay)
        raise RuntimeError("MySQL not ready")

    @classmethod
    def _wait_for_minio(cls, max_attempts=20, delay=2):
        import requests
        for i in range(max_attempts):
            try:
                resp = requests.get(f"http://127.0.0.1:{MINIO_PORT}/minio/health/live")
                if resp.status_code == 200:
                    return
            except Exception:
                time.sleep(delay)
        raise RuntimeError("MinIO not ready")

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
            objects = self.s3_manager.s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix=DATA_PREFIX)
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