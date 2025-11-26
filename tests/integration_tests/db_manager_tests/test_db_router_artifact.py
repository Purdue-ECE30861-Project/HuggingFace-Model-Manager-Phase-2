import unittest
import logging
from sqlalchemy import create_engine, Engine
from sqlmodel import SQLModel

from src.backend_server.model.data_store.database_connectors.artifact_database import DBArtifactAccessor
from src.contracts.artifact_contracts import (
    ArtifactType, Artifact, ArtifactData, ArtifactMetadata, 
    ArtifactQuery, ArtifactName, ArtifactRegEx
)
from src.contracts.auth_contracts import User, AuditAction
from src.contracts.model_rating import ModelRating
from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBRouterArtifact
from src.backend_server.model.data_store.database_connectors.database_schemas import ModelLinkedArtifactNames
from src.backend_server.model.data_store.database_connectors.base_database import db_reset
from mock_infrastructure import docker_init

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MYSQL_PORT = getattr(docker_init, "MYSQL_HOST_PORT", 3307)
MYSQL_DATABASE = getattr(docker_init, "MYSQL_DATABASE", "test_db")
MYSQL_USER = getattr(docker_init, "MYSQL_USER", "test_user")
MYSQL_PASSWORD = getattr(docker_init, "MYSQL_PASSWORD", "test_password")


class TestDBRouterArtifact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up MySQL container and initialize database engine."""
        logger.info("Setting up MySQL container for DBRouterArtifact tests...")
        db_url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@127.0.0.1:{MYSQL_PORT}/{MYSQL_DATABASE}"
        cls.engine: Engine = create_engine(db_url)
        SQLModel.metadata.create_all(cls.engine)
        cls.router = DBRouterArtifact(cls.engine)

    def setUp(self):
        """Reset database before each test."""
        db_reset(self.engine)

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        if hasattr(cls, 'engine'):
            db_reset(cls.engine)

    def test_db_model_ingest(self):
        """Test ingesting a model artifact."""
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="router-model", id="router-model-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[],
            linked_code_names=[],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )
        user = User(name="test-user", is_admin=False)
        
        result = self.router.db_model_ingest(
            model_artifact,
            linked_names,
            size_mb=100.0,
            readme="# Test Model",
            user=user
        )
        self.assertTrue(result, "Failed to ingest model")

    def test_db_model_ingest_without_readme(self):
        """Test ingesting a model artifact without README."""
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="router-model-no-readme", id="router-model-id-2", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[],
            linked_code_names=[],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )
        
        result = self.router.db_model_ingest(
            model_artifact,
            linked_names,
            size_mb=100.0,
            readme=None
        )
        self.assertTrue(result, "Failed to ingest model without README")

    def test_db_model_ingest_wrong_type(self):
        """Test that ingesting non-model artifact returns False."""
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="router-dataset", id="router-dataset-id-1", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[],
            linked_code_names=[],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )
        
        result = self.router.db_model_ingest(
            dataset_artifact,
            linked_names,
            size_mb=50.0,
            readme=None
        )
        self.assertFalse(result, "Should return False for non-model artifact")

    def test_db_artifact_ingest_dataset(self):
        """Test ingesting a dataset artifact."""
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="router-dataset", id="router-dataset-id-1", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        user = User(name="test-user", is_admin=False)
        
        result = self.router.db_artifact_ingest(
            dataset_artifact,
            size_mb=50.0,
            readme="# Test Dataset",
            user=user
        )
        self.assertTrue(result, "Failed to ingest dataset")

    def test_db_artifact_ingest_code(self):
        """Test ingesting a code artifact."""
        code_artifact = Artifact(
            metadata=ArtifactMetadata(name="router-code", id="router-code-id-1", type=ArtifactType.code),
            data=ArtifactData(url="https://example.com/code", download_url="")
        )
        
        result = self.router.db_artifact_ingest(
            code_artifact,
            size_mb=10.0,
            readme=None
        )
        self.assertTrue(result, "Failed to ingest code")

    def test_db_artifact_ingest_model_returns_false(self):
        """Test that ingesting model through db_artifact_ingest returns False."""
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="router-model-wrong", id="router-model-id-3", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        
        result = self.router.db_artifact_ingest(
            model_artifact,
            size_mb=100.0,
            readme=None
        )
        self.assertFalse(result, "Should return False for model artifact")

    def test_db_artifact_delete(self):
        """Test deleting an artifact."""
        # First create an artifact
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="delete-router-model", id="delete-router-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[],
            linked_code_names=[],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )
        self.router.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme=None)
        
        # Delete it
        user = User(name="test-user", is_admin=False)
        result = self.router.db_artifact_delete("delete-router-id-1", ArtifactType.model, user)
        self.assertTrue(result, "Failed to delete artifact")
        
        # Verify it no longer exists
        exists = self.router.db_artifact_exists("delete-router-id-1", ArtifactType.model)
        self.assertFalse(exists, "Artifact should not exist after deletion")

    def test_db_artifact_delete_nonexistent(self):
        """Test deleting non-existent artifact returns False."""
        user = User(name="test-user", is_admin=False)
        result = self.router.db_artifact_delete("nonexistent-id", ArtifactType.model, user)
        self.assertFalse(result, "Should return False for non-existent artifact")

    def test_db_artifact_get_query(self):
        """Test querying artifacts."""
        # Create multiple artifacts
        artifacts = [
            Artifact(metadata=ArtifactMetadata(name="query-router-model", id="q-router-id-1", type=ArtifactType.model),
                    data=ArtifactData(url="https://example.com/model1", download_url="")),
            Artifact(metadata=ArtifactMetadata(name="query-router-dataset", id="q-router-id-2", type=ArtifactType.dataset),
                    data=ArtifactData(url="https://example.com/dataset1", download_url="")),
        ]
        
        for art in artifacts:
            if art.metadata.type == ArtifactType.model:
                linked_names = ModelLinkedArtifactNames(
                    linked_dset_names=[], linked_code_names=[],
                    linked_parent_model_name=None, linked_parent_model_relation=None
                )
                self.router.db_model_ingest(art, linked_names, size_mb=10.0, readme=None)
            else:
                self.router.db_artifact_ingest(art, size_mb=10.0, readme=None)
        
        query = ArtifactQuery(name="*", types=None)
        results = self.router.db_artifact_get_query(query, "0")
        self.assertIsNotNone(results, "Results should not be None")
        self.assertEqual(len(results), 2, "Should find 2 artifacts")

    def test_db_artifact_get_id(self):
        """Test retrieving artifact by ID."""
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="get-router-model", id="get-router-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[], linked_code_names=[],
            linked_parent_model_name=None, linked_parent_model_relation=None
        )
        self.router.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme=None)
        
        user = User(name="test-user", is_admin=False)
        result = self.router.db_artifact_get_id("get-router-id-1", ArtifactType.model, user)
        self.assertIsNotNone(result, "Artifact should be retrieved")
        self.assertEqual(result.metadata.id, "get-router-id-1")
        self.assertEqual(result.metadata.name, "get-router-model")

    def test_db_artifact_get_id_nonexistent(self):
        """Test retrieving non-existent artifact returns None."""
        user = User(name="test-user", is_admin=False)
        result = self.router.db_artifact_get_id("nonexistent-id", ArtifactType.model, user)
        self.assertIsNone(result, "Non-existent artifact should return None")

    def test_db_artifact_get_name(self):
        """Test retrieving artifacts by name."""
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="name-router-shared", id="name-router-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="name-router-shared", id="name-router-id-2", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[], linked_code_names=[],
            linked_parent_model_name=None, linked_parent_model_relation=None
        )
        self.router.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme=None)
        self.router.db_artifact_ingest(dataset_artifact, size_mb=50.0, readme=None)
        
        results = self.router.db_artifact_get_name(ArtifactName(name="name-router-shared"))
        self.assertIsNotNone(results, "Results should not be None")
        self.assertEqual(len(results), 2, "Should find 2 artifacts with same name")

    def test_db_artifact_get_regex(self):
        """Test retrieving artifacts by regex."""
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="regex-router-test", id="regex-router-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[], linked_code_names=[],
            linked_parent_model_name=None, linked_parent_model_relation=None
        )
        self.router.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme="# regex-router-test content")

        self.assertTrue(len(DBArtifactAccessor.get_all(self.router.engine)) > 0, "Must be at least one artifact")
        self.assertTrue(len(DBArtifactAccessor.artifact_get_by_regex(self.router.engine, "regex-router.*")[0]) > 0, "Must be at least one artifact")

        regex = ArtifactRegEx(regex="regex-router.*")
        results = self.router.db_artifact_get_regex(regex)
        print(results)
        self.assertIsNotNone(results, "Results should not be None")
        self.assertGreaterEqual(len(results), 1, "Should find at least 1 artifact matching regex")

    def test_db_artifact_exists(self):
        """Test checking if artifact exists."""
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="exists-router-model", id="exists-router-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[], linked_code_names=[],
            linked_parent_model_name=None, linked_parent_model_relation=None
        )
        
        # Should not exist before insert
        exists_before = self.router.db_artifact_exists("exists-router-id-1", ArtifactType.model)
        self.assertFalse(exists_before, "Artifact should not exist before insert")
        
        self.router.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme=None)
        
        # Should exist after insert
        exists_after = self.router.db_artifact_exists("exists-router-id-1", ArtifactType.model)
        self.assertTrue(exists_after, "Artifact should exist after insert")


if __name__ == '__main__':
    unittest.main()
