import unittest
import logging
from sqlalchemy import create_engine, Engine
from sqlmodel import SQLModel

from src.contracts.artifact_contracts import ArtifactType, Artifact, ArtifactData, ArtifactMetadata
from src.contracts.auth_contracts import User, AuditAction
from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBRouterAudit, DBRouterArtifact
from src.backend_server.model.data_store.database_connectors.database_schemas import ModelLinkedArtifactNames
from src.backend_server.model.data_store.database_connectors.base_database import db_reset
from mock_infrastructure import docker_init

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MYSQL_PORT = getattr(docker_init, "MYSQL_HOST_PORT", 3307)
MYSQL_DATABASE = getattr(docker_init, "MYSQL_DATABASE", "test_db")
MYSQL_USER = getattr(docker_init, "MYSQL_USER", "test_user")
MYSQL_PASSWORD = getattr(docker_init, "MYSQL_PASSWORD", "test_password")


class TestDBRouterAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up MySQL container and initialize database engine."""
        logger.info("Setting up MySQL container for DBRouterAudit tests...")
        db_url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@127.0.0.1:{MYSQL_PORT}/{MYSQL_DATABASE}"
        cls.engine: Engine = create_engine(db_url)
        SQLModel.metadata.create_all(cls.engine)
        cls.router_audit = DBRouterAudit(cls.engine)
        cls.router_artifact = DBRouterArtifact(cls.engine)

    def setUp(self):
        """Reset database before each test."""
        db_reset(self.engine)

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        if hasattr(cls, 'engine'):
            db_reset(cls.engine)

    def test_db_artifact_audit(self):
        """Test retrieving audit logs for an artifact."""
        # First create an artifact with some audit history
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="audit-router-model", id="audit-router-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[], linked_code_names=[],
            linked_parent_model_name=None, linked_parent_model_relation=None
        )
        user1 = User(name="user1", is_admin=False)
        self.router_artifact.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme=None, user=user1)
        
        # Retrieve audit logs
        user2 = User(name="audit-user", is_admin=False)
        audit_logs = self.router_audit.db_artifact_audit(
            ArtifactType.model,
            "audit-router-id-1",
            user2
        )
        
        self.assertIsNotNone(audit_logs, "Audit logs should not be None")
        self.assertGreaterEqual(len(audit_logs), 1, "Should have at least 1 audit entry (CREATE)")
        
        # Verify the audit entry
        create_entries = [log for log in audit_logs if log.action == AuditAction.CREATE]
        self.assertGreaterEqual(len(create_entries), 1, "Should have CREATE audit entry")
        self.assertEqual(create_entries[0].artifact.id, "audit-router-id-1")

    def test_db_artifact_audit_nonexistent(self):
        """Test retrieving audit logs for non-existent artifact returns None."""
        user = User(name="test-user", is_admin=False)
        audit_logs = self.router_audit.db_artifact_audit(
            ArtifactType.model,
            "nonexistent-id",
            user
        )
        self.assertIsNone(audit_logs, "Non-existent artifact should return None")

    def test_db_artifact_audit_multiple_actions(self):
        """Test audit logs with multiple actions."""
        # Create artifact
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="multi-audit-model", id="multi-audit-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[], linked_code_names=[],
            linked_parent_model_name=None, linked_parent_model_relation=None
        )
        user = User(name="test-user", is_admin=False)
        self.router_artifact.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme=None, user=user)
        
        # Download the artifact (creates DOWNLOAD audit entry)
        self.router_artifact.db_artifact_get_id("multi-audit-id-1", ArtifactType.model, user)
        
        # Retrieve audit logs
        audit_logs = self.router_audit.db_artifact_audit(
            ArtifactType.model,
            "multi-audit-id-1",
            user
        )
        
        self.assertIsNotNone(audit_logs, "Audit logs should not be None")
        self.assertGreaterEqual(len(audit_logs), 2, "Should have at least 2 audit entries (CREATE and DOWNLOAD)")
        
        actions = [log.action for log in audit_logs]
        self.assertIn(AuditAction.CREATE, actions)
        self.assertIn(AuditAction.DOWNLOAD, actions)
        # AUDIT action should also be present from the db_artifact_audit call itself
        self.assertIn(AuditAction.AUDIT, actions)


if __name__ == '__main__':
    unittest.main()

