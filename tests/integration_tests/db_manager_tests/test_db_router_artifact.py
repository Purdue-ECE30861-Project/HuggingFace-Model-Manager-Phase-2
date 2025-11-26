import logging
import unittest

from sqlalchemy import create_engine, Engine
from sqlmodel import SQLModel, Session, select

from mock_infrastructure import docker_init
from src.backend_server.model.data_store.database_connectors.artifact_database import (
    DBArtifactAccessor
)
from src.backend_server.model.data_store.database_connectors.audit_database import DBAuditAccessor
from src.backend_server.model.data_store.database_connectors.base_database import db_reset
from src.backend_server.model.data_store.database_connectors.database_schemas import ModelLinkedArtifactNames, \
    DBConnectiveSchema, DBArtifactReadmeSchema
from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBRouterArtifact
from src.contracts.artifact_contracts import (
    ArtifactType, Artifact, ArtifactData, ArtifactMetadata,
    ArtifactQuery, ArtifactName, ArtifactRegEx, ArtifactID
)
from src.contracts.auth_contracts import User, AuditAction

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

    def test_db_model_update(self):
        # Create and ingest initial model
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="update-router-model", id="update-router-model-id-1",
                                      type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        initial_linked_names = ModelLinkedArtifactNames(
            linked_dset_names=["dataset-1"],
            linked_code_names=["code-1"],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )
        user = User(name="test-user", is_admin=False)

        result = self.router.db_model_ingest(
            model_artifact,
            initial_linked_names,
            size_mb=100.0,
            readme="# Initial README",
            user=user
        )
        self.assertTrue(result, "Failed to ingest initial model")

        # First, create linked artifacts that the model will reference
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="dataset-1", id="dataset-1-id", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset1", download_url="")
        )
        code_artifact = Artifact(
            metadata=ArtifactMetadata(name="code-1", id="code-1-id", type=ArtifactType.code),
            data=ArtifactData(url="https://example.com/code1", download_url="")
        )
        self.router.db_artifact_ingest(dataset_artifact, size_mb=50.0, readme=None, user=user)
        self.router.db_artifact_ingest(code_artifact, size_mb=10.0, readme=None, user=user)

        # Ingest initial model

        # Update model with new values
        new_size_mb = 200.0
        new_readme = "# Updated README\n\nThis is the updated content."
        new_linked_names = ModelLinkedArtifactNames(
            linked_dset_names=["dataset-1", "dataset-2"],
            linked_code_names=["code-2"],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )

        update_result = self.router.db_model_update(
            model_artifact,
            new_size_mb,
            new_linked_names,
            new_readme,
            user=user
        )
        self.assertTrue(update_result, "Failed to update model")

        # Create additional linked artifacts for update
        dataset2_artifact = Artifact(
            metadata=ArtifactMetadata(name="dataset-2", id="dataset-2-id", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset2", download_url="")
        )
        code2_artifact = Artifact(
            metadata=ArtifactMetadata(name="code-2", id="code-2-id", type=ArtifactType.code),
            data=ArtifactData(url="https://example.com/code2", download_url="")
        )
        self.router.db_artifact_ingest(dataset2_artifact, size_mb=60.0, readme=None, user=user)
        self.router.db_artifact_ingest(code2_artifact, size_mb=15.0, readme=None, user=user)

        # Perform updat

        # Verify artifact database - size_mb should be updated
        updated_artifact = DBArtifactAccessor.artifact_get_by_id(
            self.engine, "update-router-model-id-1", ArtifactType.model
        )
        self.assertIsNotNone(updated_artifact, "Updated artifact should exist")
        self.assertEqual(updated_artifact.size_mb, new_size_mb, "Size should be updated in artifact database")

        # Verify readme database - readme should be updated
        with Session(self.engine) as session:
            readme_query = select(DBArtifactReadmeSchema).where(
                DBArtifactReadmeSchema.id == "update-router-model-id-1",
                DBArtifactReadmeSchema.artifact_type == ArtifactType.model
            )
            readme = session.exec(readme_query).first()
            self.assertIsNotNone(readme, "README should exist after update")
            self.assertEqual(readme.readme_content, new_readme, "README content should be updated")

        # Verify audit database - UPDATE entry should be added
        audit_entries = DBAuditAccessor.get_by_id(
            self.engine,
            ArtifactID(id="update-router-model-id-1"),
            ArtifactType.model
        )
        self.assertIsNotNone(audit_entries, "Audit entries should exist")
        # Should have at least CREATE and UPDATE entries
        self.assertGreaterEqual(len(audit_entries), 2, "Should have at least CREATE and UPDATE audit entries")
        # Find UPDATE entry
        update_audit = next((entry for entry in audit_entries if entry.action == AuditAction.UPDATE), None)
        self.assertIsNotNone(update_audit, "UPDATE audit entry should exist")
        self.assertEqual(update_audit.user.name, "test-user", "Audit entry should have correct user")

        # Verify connection database - connections should be updated
        with Session(self.engine) as session:
            # Get all connections for this model
            connections_query = select(DBConnectiveSchema).where(
                DBConnectiveSchema.dst_id == "update-router-model-id-1"
            )
            connections = session.exec(connections_query).fetchall()
            self.assertIsNotNone(connections, "Connections should exist")

            # Should have connections to dataset-1, dataset-2, and code-2
            # Old connection to code-1 should be removed, new connections added
            dataset_connections = [c for c in connections if
                                   "dataset" in c.dst_name.lower() or "dataset" in c.src_name.lower()]
            code_connections = [c for c in connections if "code" in c.dst_name.lower() or "code" in c.src_name.lower()]

            # Verify we have connections to the new datasets and code
            self.assertGreaterEqual(len(connections), 2, "Should have at least 2 connections after update")

    def test_db_artifact_update_non_model(self):
        # Create and ingest initial dataset
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="update-router-dataset", id="update-router-dataset-id-1",
                                      type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        user = User(name="test-user", is_admin=False)

        # Ingest initial dataset
        result = self.router.db_artifact_ingest(
            dataset_artifact,
            size_mb=50.0,
            readme="# Initial Dataset README",
            user=user
        )
        self.assertTrue(result, "Failed to ingest initial dataset")

        # Update dataset with new values
        new_size_mb = 75.0
        new_readme = "# Updated Dataset README\n\nThis is the updated dataset content."

        # Perform update
        update_result = self.router.db_artifact_update(
            dataset_artifact,
            new_size_mb,
            new_readme,
            user=user
        )
        self.assertTrue(update_result, "Failed to update dataset")

        # Verify artifact database - size_mb should be updated
        updated_artifact = DBArtifactAccessor.artifact_get_by_id(
            self.engine, "update-router-dataset-id-1", ArtifactType.dataset
        )
        self.assertIsNotNone(updated_artifact, "Updated artifact should exist")
        self.assertEqual(updated_artifact.size_mb, new_size_mb, "Size should be updated in artifact database")

        # Verify readme database - readme should be updated
        with Session(self.engine) as session:
            readme_query = select(DBArtifactReadmeSchema).where(
                DBArtifactReadmeSchema.id == "update-router-dataset-id-1",
                DBArtifactReadmeSchema.artifact_type == ArtifactType.dataset
            )
            readme = session.exec(readme_query).first()
            self.assertIsNotNone(readme, "README should exist after update")
            self.assertEqual(readme.readme_content, new_readme, "README content should be updated")

        # Verify audit database - UPDATE entry should be added
        audit_entries = DBAuditAccessor.get_by_id(
            self.engine,
            ArtifactID(id="update-router-dataset-id-1"),
            ArtifactType.dataset
        )
        self.assertIsNotNone(audit_entries, "Audit entries should exist")
        # Should have at least CREATE and UPDATE entries
        self.assertGreaterEqual(len(audit_entries), 2, "Should have at least CREATE and UPDATE audit entries")
        # Find UPDATE entry
        update_audit = next((entry for entry in audit_entries if entry.action == AuditAction.UPDATE), None)
        self.assertIsNotNone(update_audit, "UPDATE audit entry should exist")
        self.assertEqual(update_audit.user.name, "test-user", "Audit entry should have correct user")

        # Verify connection database - for non-model artifacts, connections are handled differently
        # The update should have deleted old connections and potentially added new ones
        # Since non-models don't have explicit connections like models, we verify the connection
        # deletion/insertion logic was executed
        with Session(self.engine) as session:
            # Check that connections_delete_by_artifact_id was called (connections with this as dst_id should be deleted)
            connections_query = select(DBConnectiveSchema).where(
                DBConnectiveSchema.dst_id == "update-router-dataset-id-1"
            )
            connections_as_dst = session.exec(connections_query).fetchall()
            # After update, connections where this artifact is destination should be deleted
            self.assertEqual(len(connections_as_dst), 0,
                             "Connections with this artifact as destination should be deleted after update")


if __name__ == '__main__':
    unittest.main()
