import unittest
import logging
from pydantic import HttpUrl
from sqlalchemy import create_engine, Engine
from sqlmodel import SQLModel

from src.contracts.artifact_contracts import ArtifactType, Artifact, ArtifactData, ArtifactMetadata, ArtifactQuery, ArtifactName
from src.backend_server.model.data_store.database_connectors.artifact_database import DBArtifactAccessor
from src.backend_server.model.data_store.database_connectors.database_schemas import DBArtifactSchema, DBModelSchema, DBDSetSchema, DBCodeSchema
from src.backend_server.model.data_store.database_connectors.base_database import db_reset
from mock_infrastructure import docker_init

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MYSQL_PORT = getattr(docker_init, "MYSQL_HOST_PORT", 3307)
MYSQL_DATABASE = getattr(docker_init, "MYSQL_DATABASE", "test_db")
MYSQL_USER = getattr(docker_init, "MYSQL_USER", "test_user")
MYSQL_PASSWORD = getattr(docker_init, "MYSQL_PASSWORD", "test_password")


class TestDBArtifactAccessor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up MySQL container and initialize database engine."""
        logger.info("Setting up MySQL container for DBArtifactAccessor tests...")
        db_url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@127.0.0.1:{MYSQL_PORT}/{MYSQL_DATABASE}"
        cls.engine: Engine = create_engine(db_url)
        SQLModel.metadata.create_all(cls.engine)

    def setUp(self):
        """Reset database before each test."""
        db_reset(self.engine)

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        if hasattr(cls, 'engine'):
            db_reset(cls.engine)

    def test_artifact_insert_model(self):
        """Test inserting a model artifact."""
        artifact = Artifact(
            metadata=ArtifactMetadata(name="test-model", id="test-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        db_artifact = DBModelSchema.from_artifact(artifact, size_mb=100.0).to_concrete()
        
        result = DBArtifactAccessor.artifact_insert(self.engine, db_artifact)
        self.assertTrue(result, "Failed to insert model artifact")
        
        # Verify it exists
        exists = DBArtifactAccessor.artifact_exists(self.engine, "test-id-1", ArtifactType.model)
        self.assertTrue(exists, "Inserted artifact not found")

    def test_artifact_insert_dataset(self):
        """Test inserting a dataset artifact."""
        artifact = Artifact(
            metadata=ArtifactMetadata(name="test-dataset", id="test-id-2", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        db_artifact = DBArtifactSchema.from_artifact(artifact, size_mb=50.0).to_concrete()
        
        result = DBArtifactAccessor.artifact_insert(self.engine, db_artifact)
        self.assertTrue(result, "Failed to insert dataset artifact")
        
        exists = DBArtifactAccessor.artifact_exists(self.engine, "test-id-2", ArtifactType.dataset)
        self.assertTrue(exists, "Inserted artifact not found")

    def test_artifact_insert_code(self):
        """Test inserting a code artifact."""
        artifact = Artifact(
            metadata=ArtifactMetadata(name="test-code", id="test-id-3", type=ArtifactType.code),
            data=ArtifactData(url="https://example.com/code", download_url="")
        )
        db_artifact = DBArtifactSchema.from_artifact(artifact, size_mb=10.0).to_concrete()
        
        result = DBArtifactAccessor.artifact_insert(self.engine, db_artifact)
        self.assertTrue(result, "Failed to insert code artifact")
        
        exists = DBArtifactAccessor.artifact_exists(self.engine, "test-id-3", ArtifactType.code)
        self.assertTrue(exists, "Inserted artifact not found")

    def test_artifact_insert_duplicate(self):
        """Test that inserting duplicate artifact returns False."""
        artifact = Artifact(
            metadata=ArtifactMetadata(name="duplicate-model", id="dup-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        db_artifact = DBArtifactSchema.from_artifact(artifact, size_mb=100.0).to_concrete()
        
        # First insert should succeed
        result1 = DBArtifactAccessor.artifact_insert(self.engine, db_artifact)
        self.assertTrue(result1, "First insert should succeed")
        
        # Second insert should fail
        result2 = DBArtifactAccessor.artifact_insert(self.engine, db_artifact)
        self.assertFalse(result2, "Duplicate insert should return False")

    def test_artifact_delete(self):
        """Test deleting an artifact."""
        artifact = Artifact(
            metadata=ArtifactMetadata(name="delete-model", id="del-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        db_artifact = DBModelSchema.from_artifact(artifact, size_mb=100.0).to_concrete()
        
        DBArtifactAccessor.artifact_insert(self.engine, db_artifact)
        
        # Delete the artifact
        result = DBArtifactAccessor.artifact_delete(self.engine, "del-id-1", ArtifactType.model)
        self.assertTrue(result, "Failed to delete artifact")
        
        # Verify it no longer exists
        exists = DBArtifactAccessor.artifact_exists(self.engine, "del-id-1", ArtifactType.model)
        self.assertFalse(exists, "Artifact still exists after deletion")

    def test_artifact_delete_nonexistent(self):
        """Test deleting a non-existent artifact."""
        result = DBArtifactAccessor.artifact_delete(self.engine, "nonexistent-id", ArtifactType.model)
        self.assertFalse(result, "Deleting non-existent artifact should return False")

    def test_artifact_get_by_id(self):
        """Test retrieving artifact by ID."""
        artifact = Artifact(
            metadata=ArtifactMetadata(name="get-model", id="get-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        db_artifact = DBArtifactSchema.from_artifact(artifact, size_mb=100.0).to_concrete()
        
        DBArtifactAccessor.artifact_insert(self.engine, db_artifact)
        
        retrieved = DBArtifactAccessor.artifact_get_by_id(self.engine, "get-id-1", ArtifactType.model)
        self.assertIsNotNone(retrieved, "Artifact should be retrieved")
        self.assertEqual(retrieved.id, "get-id-1")
        self.assertEqual(retrieved.name, "get-model")
        self.assertEqual(retrieved.type, ArtifactType.model)

    def test_artifact_get_by_id_nonexistent(self):
        """Test retrieving non-existent artifact returns None."""
        retrieved = DBArtifactAccessor.artifact_get_by_id(self.engine, "nonexistent-id", ArtifactType.model)
        self.assertIsNone(retrieved, "Non-existent artifact should return None")

    def test_artifact_get_by_name(self):
        """Test retrieving artifacts by name."""
        # Insert multiple artifacts with same name but different types
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="shared-name", id="name-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="shared-name", id="name-id-2", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        
        DBArtifactAccessor.artifact_insert(self.engine, DBArtifactSchema.from_artifact(model_artifact, size_mb=100.0).to_concrete())
        DBArtifactAccessor.artifact_insert(self.engine, DBArtifactSchema.from_artifact(dataset_artifact, size_mb=50.0).to_concrete())
        
        results = DBArtifactAccessor.artifact_get_by_name(self.engine, ArtifactName(name="shared-name"))
        self.assertIsNotNone(results, "Results should not be None")
        self.assertEqual(len(results), 2, "Should find 2 artifacts with same name")

    def test_artifact_get_by_query_all(self):
        """Test querying all artifacts with wildcard."""
        # Insert multiple artifacts
        artifacts = [
            Artifact(metadata=ArtifactMetadata(name="query-model", id="q-id-1", type=ArtifactType.model),
                    data=ArtifactData(url="https://example.com/model1", download_url="")),
            Artifact(metadata=ArtifactMetadata(name="query-dataset", id="q-id-2", type=ArtifactType.dataset),
                    data=ArtifactData(url="https://example.com/dataset1", download_url="")),
            Artifact(metadata=ArtifactMetadata(name="query-code", id="q-id-3", type=ArtifactType.code),
                    data=ArtifactData(url="https://example.com/code1", download_url="")),
        ]
        
        for art in artifacts:
            DBArtifactAccessor.artifact_insert(self.engine, DBArtifactSchema.from_artifact(art, size_mb=10.0).to_concrete())
        
        query = ArtifactQuery(name="*", types=None)
        results = DBArtifactAccessor.artifact_get_by_query(self.engine, query, "0")
        self.assertIsNotNone(results, "Results should not be None")
        self.assertEqual(len(results), 3, "Should find all 3 artifacts")

    def test_artifact_get_by_query_filtered(self):
        """Test querying artifacts with name and type filters."""
        artifacts = [
            Artifact(metadata=ArtifactMetadata(name="filter-model", id="f-id-1", type=ArtifactType.model),
                    data=ArtifactData(url="https://example.com/model1", download_url="")),
            Artifact(metadata=ArtifactMetadata(name="filter-model", id="f-id-2", type=ArtifactType.dataset),
                    data=ArtifactData(url="https://example.com/dataset1", download_url="")),
        ]
        
        for art in artifacts:
            DBArtifactAccessor.artifact_insert(self.engine, DBArtifactSchema.from_artifact(art, size_mb=10.0).to_concrete())
        
        query = ArtifactQuery(name="filter-model", types=[ArtifactType.model])
        results = DBArtifactAccessor.artifact_get_by_query(self.engine, query, "0")
        self.assertIsNotNone(results, "Results should not be None")
        self.assertEqual(len(results), 1, "Should find 1 model artifact")
        self.assertEqual(results[0].type, ArtifactType.model)

    def test_artifact_get_by_regex(self):
        """Test querying artifacts by regex pattern."""
        artifacts = [
            Artifact(metadata=ArtifactMetadata(name="regex-test-model", id="r-id-1", type=ArtifactType.model),
                    data=ArtifactData(url="https://example.com/model1", download_url="")),
            Artifact(metadata=ArtifactMetadata(name="regex-test-dataset", id="r-id-2", type=ArtifactType.dataset),
                    data=ArtifactData(url="https://example.com/dataset1", download_url="")),
            Artifact(metadata=ArtifactMetadata(name="other-name", id="r-id-3", type=ArtifactType.model),
                    data=ArtifactData(url="https://example.com/model2", download_url="")),
        ]
        
        for art in artifacts:
            DBArtifactAccessor.artifact_insert(self.engine, DBArtifactSchema.from_artifact(art, size_mb=10.0).to_concrete())
        
        results, readme_results = DBArtifactAccessor.artifact_get_by_regex(self.engine, "regex-test.*")
        self.assertIsNotNone(results, "Results should not be None")
        self.assertEqual(len(results), 2, "Should find 2 artifacts matching regex")

    def test_artifact_exists(self):
        """Test checking if artifact exists."""
        artifact = Artifact(
            metadata=ArtifactMetadata(name="exists-model", id="exists-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        db_artifact = DBArtifactSchema.from_artifact(artifact, size_mb=100.0).to_concrete()
        
        # Should not exist before insert
        exists_before = DBArtifactAccessor.artifact_exists(self.engine, "exists-id-1", ArtifactType.model)
        self.assertFalse(exists_before, "Artifact should not exist before insert")
        
        DBArtifactAccessor.artifact_insert(self.engine, db_artifact)
        
        # Should exist after insert
        exists_after = DBArtifactAccessor.artifact_exists(self.engine, "exists-id-1", ArtifactType.model)
        self.assertTrue(exists_after, "Artifact should exist after insert")

    def test_get_all(self):
        """Test retrieving all artifacts."""
        artifacts = [
            Artifact(metadata=ArtifactMetadata(name="all-model", id="all-id-1", type=ArtifactType.model),
                    data=ArtifactData(url="https://example.com/model1", download_url="")),
            Artifact(metadata=ArtifactMetadata(name="all-dataset", id="all-id-2", type=ArtifactType.dataset),
                    data=ArtifactData(url="https://example.com/dataset1", download_url="")),
        ]
        
        for art in artifacts:
            DBArtifactAccessor.artifact_insert(self.engine, DBArtifactSchema.from_artifact(art, size_mb=10.0).to_concrete())
        
        results = DBArtifactAccessor.get_all(self.engine)
        self.assertIsNotNone(results, "Results should not be None")
        self.assertEqual(len(results), 2, "Should find all artifacts")


if __name__ == '__main__':
    unittest.main()


