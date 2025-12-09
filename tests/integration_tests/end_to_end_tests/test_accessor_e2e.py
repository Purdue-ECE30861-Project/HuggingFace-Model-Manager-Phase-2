import unittest
import json
import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from src.backend_server.model.artifact_accessor.artifact_accessor import ArtifactAccessor
from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBManager
from src.backend_server.model.data_store.s3_manager import S3BucketManager
from src.contracts.artifact_contracts import ArtifactData, ArtifactType, ArtifactID
from mock_infrastructure import docker_init

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestAccessorE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures connecting to already running containers."""
        logger.info("Setting up E2E test connections...")
        
        # DB Setup
        mysql_port = getattr(docker_init, "MYSQL_HOST_PORT", 3307)
        mysql_user = getattr(docker_init, "MYSQL_USER", "test_user")
        mysql_password = getattr(docker_init, "MYSQL_PASSWORD", "test_password")
        mysql_database = getattr(docker_init, "MYSQL_DATABASE", "test_db")
        
        db_url = f"mysql+pymysql://{mysql_user}:{mysql_password}@127.0.0.1:{mysql_port}/{mysql_database}"
        cls.db = DBManager(db_url)
        
        # S3 Setup
        minio_port = getattr(docker_init, "MINIO_HOST_PORT", 9000)
        minio_user = getattr(docker_init, "MINIO_ROOT_USER", "minio_user")
        minio_pass = getattr(docker_init, "MINIO_ROOT_PASSWORD", "minio_password")
        minio_bucket = getattr(docker_init, "MINIO_BUCKET", "test_bucket")
        
        # Create bucket if not exists (idempotent check)
        s3_client = boto3.client(
            "s3",
            endpoint_url=f"http://127.0.0.1:{minio_port}",
            aws_access_key_id=minio_user,
            aws_secret_access_key=minio_pass,
        )
        try:
            s3_client.create_bucket(Bucket=minio_bucket)
        except ClientError:
            logger.info("Bucket already exists or could not be created (check permissions)")
            
        cls.s3_manager = S3BucketManager(
            endpoint_url=f"http://127.0.0.1:{minio_port}",
            bucket_name=minio_bucket,
            data_prefix="e2e_test_",
            aws_access_key_id=minio_user,
            aws_secret_access_key=minio_pass
        )
        
        # Mock dependencies that are not part of this specific integration test scope
        cls.mock_llm = MagicMock()
        cls.mock_rater = MagicMock()
        
        # Instantiate Accessor
        cls.accessor = ArtifactAccessor(
            db=cls.db,
            s3=cls.s3_manager,
            llm_accessor=cls.mock_llm,
            rater_task_manager=cls.mock_rater,
            num_processors=1
        )
        
        # Load E2E data from e2e.json in the same directory
        e2e_file = Path(__file__).parent / "e2e.json"
        with open(e2e_file, "r") as f:
            cls.test_cases = json.load(f)

    def test_e2e_scenario(self):
        """Execute steps defined in e2e.json against the ArtifactAccessor."""
        for step in self.test_cases:
            call_name = step["call"]
            args = step["arguments"]
            expected_ret = step["return_value"]
            
            logger.info(f"Executing {call_name} with arguments: {args}")
            
            if call_name == "register_artifact":
                # Map string artifact type to Enum
                artifact_type_str = args["artifact_type"]
                artifact_type = getattr(ArtifactType, artifact_type_str)
                
                body_data = args["body"]
                data = ArtifactData(
                    url=body_data["url"], 
                    download_url=body_data.get("download_url", "")
                )
                
                # Perform Call
                status, artifact = self.accessor.register_artifact(artifact_type, data)
                
                # Assertions
                expected_status_str = expected_ret[0]
                expected_artifact_dict = expected_ret[1]
                
                self.assertEqual(status.name, expected_status_str, f"Status mismatch for {call_name}")
                
                if expected_artifact_dict:
                    self.assertIsNotNone(artifact, "Artifact should not be None")
                    self.assertEqual(artifact.metadata.name, expected_artifact_dict["metadata"]["name"])
                    self.assertEqual(artifact.metadata.type.name if hasattr(artifact.metadata.type, 'name') else artifact.metadata.type, 
                                     expected_artifact_dict["metadata"]["type"])
                    self.assertEqual(artifact.metadata.id, expected_artifact_dict["metadata"]["id"])
                    
            elif call_name == "get_artifact":
                # Map string artifact type to Enum
                artifact_type_str = args["artifact_type"]
                artifact_type = getattr(ArtifactType, artifact_type_str)
                
                art_id = ArtifactID(id=args["id"])
                
                # Perform Call
                status, artifact = self.accessor.get_artifact(artifact_type, art_id)
                
                # Assertions
                expected_status_str = expected_ret[0]
                expected_artifact_dict = expected_ret[1]
                
                self.assertEqual(status.name, expected_status_str, f"Status mismatch for {call_name}")
                
                if expected_artifact_dict:
                    self.assertIsNotNone(artifact, "Artifact should not be None")
                    self.assertEqual(artifact.metadata.id, expected_artifact_dict["metadata"]["id"])
                    # Note: The actual artifact.data.url from get_artifact might differ if it returns presigned url or original.
                    # e2e.json expects "https://huggingface.co/..."
                    # The accessor implementation: result.data.download_url = self.dependencies.s3_manager.s3_generate_presigned_url(id.id)
                    # But result.data.url should remain the original source URL.
                    self.assertEqual(artifact.data.url, expected_artifact_dict["data"]["url"])

if __name__ == '__main__':
    unittest.main()
