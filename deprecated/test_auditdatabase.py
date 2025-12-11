import unittest
import logging

from src.backend_server.model.data_store.database_connectors.audit_database import SQLAuditAccessor
from src.contracts.artifact_contracts import ArtifactMetadata, ArtifactType, ArtifactID
from src.contracts.auth_contracts import User, AuditAction
from src.mock_infrastructure import docker_init

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestAuditDatabaseDockerized(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db_url = f"mysql+pymysql://{docker_init.MYSQL_USER}:{docker_init.MYSQL_PASSWORD}@{docker_init.MYSQL_HOST}:{docker_init.MYSQL_HOST_PORT}/{docker_init.MYSQL_DATABASE}"
        cls.audit_accessor = SQLAuditAccessor(db_url)

    def tearDown(self):
        self.audit_accessor.reset_db()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "audit_accessor"):
            cls.audit_accessor.reset_db()
        try:
            docker_init.cleanup_test_containers(("mysql_audit_test_",))
        except Exception:
            logger.exception("Error cleaning up mysql audit test containers")

    def test_append_and_get_audit_entries(self):
        metadata = ArtifactMetadata(
            name="audit-model",
            id="audit-id-1",
            type=ArtifactType.model
        )
        user = User(name="audit-user", is_admin=True)

        success = self.audit_accessor.append_audit(AuditAction.CREATE, user, metadata)
        self.assertTrue(success, "Failed to append audit record")

        entries = self.audit_accessor.get_by_id(ArtifactID(id=metadata.id), ArtifactType.model)
        self.assertIsNotNone(entries, "Audit entries should be returned")
        self.assertGreaterEqual(len(entries), 1)

        entry = entries[0]
        self.assertEqual(entry.artifact.id, metadata.id)
        self.assertEqual(entry.action, AuditAction.CREATE)
        self.assertEqual(entry.user.name, user.name)

    def test_multiple_actions_and_reset(self):
        metadata = ArtifactMetadata(
            name="audit-dataset",
            id="audit-dataset-1",
            type=ArtifactType.dataset
        )
        user = User(name="audit-runner", is_admin=False)
        actions = [AuditAction.CREATE, AuditAction.UPDATE, AuditAction.DOWNLOAD]

        for action in actions:
            self.assertTrue(
                self.audit_accessor.append_audit(action, user, metadata),
                f"Failed to append action {action}"
            )

        entries = self.audit_accessor.get_by_id(ArtifactID(id=metadata.id), ArtifactType.dataset)
        self.assertIsNotNone(entries, "Expected entries for dataset audit")
        self.assertEqual(len(entries), len(actions))

        stored_actions = [entry.action for entry in entries]
        for action in actions:
            self.assertIn(action, stored_actions)

        self.audit_accessor.reset_db()
        self.assertIsNone(
            self.audit_accessor.get_by_id(ArtifactID(id=metadata.id), ArtifactType.dataset),
            "Audit records should be removed after reset"
        )

    def test_get_by_id_returns_none_when_missing(self):
        result = self.audit_accessor.get_by_id(ArtifactID(id="missing-artifact"), ArtifactType.code)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()

