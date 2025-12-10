import unittest
import logging
from sqlalchemy import create_engine, Engine
from sqlmodel import SQLModel

from src.contracts.artifact_contracts import ArtifactType, ArtifactMetadata, ArtifactID
from src.contracts.auth_contracts import User, AuditAction
from src.backend_server.model.data_store.database_connectors.audit_database import DBAuditAccessor
from src.backend_server.model.data_store.database_connectors.base_database import db_reset
from src.mock_infrastructure import docker_init

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MYSQL_PORT = getattr(docker_init, "MYSQL_HOST_PORT", 3307)
MYSQL_DATABASE = getattr(docker_init, "MYSQL_DATABASE", "test_db")
MYSQL_USER = getattr(docker_init, "MYSQL_USER", "test_user")
MYSQL_PASSWORD = getattr(docker_init, "MYSQL_PASSWORD", "test_password")


class TestDBAuditAccessor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up MySQL container and initialize database engine."""
        logger.info("Setting up MySQL container for DBAuditAccessor tests...")
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

    def test_append_audit_create(self):
        """Test appending a CREATE audit entry."""
        metadata = ArtifactMetadata(
            name="audit-model",
            id="audit-id-1",
            type=ArtifactType.model
        )
        user = User(name="test-user", is_admin=False)
        
        result = DBAuditAccessor.append_audit(
            self.engine,
            AuditAction.CREATE,
            user,
            metadata
        )
        self.assertTrue(result, "Failed to append audit entry")

    def test_append_audit_update(self):
        """Test appending an UPDATE audit entry."""
        metadata = ArtifactMetadata(
            name="audit-model-update",
            id="audit-id-2",
            type=ArtifactType.model
        )
        user = User(name="test-user", is_admin=True)
        
        result = DBAuditAccessor.append_audit(
            self.engine,
            AuditAction.UPDATE,
            user,
            metadata
        )
        self.assertTrue(result, "Failed to append audit entry")

    def test_append_audit_download(self):
        """Test appending a DOWNLOAD audit entry."""
        metadata = ArtifactMetadata(
            name="audit-model-download",
            id="audit-id-3",
            type=ArtifactType.model
        )
        user = User(name="test-user", is_admin=False)
        
        result = DBAuditAccessor.append_audit(
            self.engine,
            AuditAction.DOWNLOAD,
            user,
            metadata
        )
        self.assertTrue(result, "Failed to append audit entry")

    def test_get_by_id_single_entry(self):
        """Test retrieving audit entries by artifact ID."""
        metadata = ArtifactMetadata(
            name="audit-get-model",
            id="audit-get-id-1",
            type=ArtifactType.model
        )
        user = User(name="test-user", is_admin=False)
        
        # Append an audit entry
        DBAuditAccessor.append_audit(
            self.engine,
            AuditAction.CREATE,
            user,
            metadata
        )
        
        # Retrieve entries
        entries = DBAuditAccessor.get_by_id(
            self.engine,
            ArtifactID(id="audit-get-id-1"),
            ArtifactType.model
        )
        
        self.assertIsNotNone(entries, "Entries should not be None")
        self.assertEqual(len(entries), 1, "Should find 1 audit entry")
        self.assertEqual(entries[0].artifact.id, "audit-get-id-1")
        self.assertEqual(entries[0].action, AuditAction.CREATE)
        self.assertEqual(entries[0].user.name, "test-user")

    def test_get_by_id_multiple_entries(self):
        """Test retrieving multiple audit entries for same artifact."""
        metadata = ArtifactMetadata(
            name="audit-multi-model",
            id="audit-multi-id-1",
            type=ArtifactType.model
        )
        user = User(name="test-user", is_admin=False)
        
        # Append multiple audit entries
        DBAuditAccessor.append_audit(self.engine, AuditAction.CREATE, user, metadata)
        DBAuditAccessor.append_audit(self.engine, AuditAction.UPDATE, user, metadata)
        DBAuditAccessor.append_audit(self.engine, AuditAction.DOWNLOAD, user, metadata)
        
        # Retrieve entries
        entries = DBAuditAccessor.get_by_id(
            self.engine,
            ArtifactID(id="audit-multi-id-1"),
            ArtifactType.model
        )
        
        self.assertIsNotNone(entries, "Entries should not be None")
        self.assertEqual(len(entries), 3, "Should find 3 audit entries")
        
        actions = [entry.action for entry in entries]
        self.assertIn(AuditAction.CREATE, actions)
        self.assertIn(AuditAction.UPDATE, actions)
        self.assertIn(AuditAction.DOWNLOAD, actions)

    def test_get_by_id_nonexistent(self):
        """Test retrieving audit entries for non-existent artifact returns None."""
        entries = DBAuditAccessor.get_by_id(
            self.engine,
            ArtifactID(id="nonexistent-id"),
            ArtifactType.model
        )
        self.assertIsNone(entries, "Non-existent artifact should return None")

    def test_get_by_id_different_type(self):
        """Test that entries are filtered by artifact type."""
        model_metadata = ArtifactMetadata(
            name="type-model",
            id="type-id-1",
            type=ArtifactType.model
        )
        dataset_metadata = ArtifactMetadata(
            name="type-dataset",
            id="type-id-1",  # Same ID, different type
            type=ArtifactType.dataset
        )
        user = User(name="test-user", is_admin=False)
        
        DBAuditAccessor.append_audit(self.engine, AuditAction.CREATE, user, model_metadata)
        DBAuditAccessor.append_audit(self.engine, AuditAction.CREATE, user, dataset_metadata)
        
        # Retrieve model entries
        model_entries = DBAuditAccessor.get_by_id(
            self.engine,
            ArtifactID(id="type-id-1"),
            ArtifactType.model
        )
        self.assertIsNotNone(model_entries)
        self.assertEqual(len(model_entries), 1, "Should find only model entries")
        self.assertEqual(model_entries[0].artifact.type, ArtifactType.model)


if __name__ == '__main__':
    unittest.main()
