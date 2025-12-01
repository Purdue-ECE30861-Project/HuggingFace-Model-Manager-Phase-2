import unittest
import logging
from sqlalchemy import create_engine, Engine
from sqlmodel import SQLModel

from src.backend_server.model.data_store.database_connectors.audit_database import DBAuditAccessor
from src.contracts.artifact_contracts import ArtifactType, Artifact, ArtifactData, ArtifactMetadata, ArtifactID
from src.contracts.auth_contracts import AuditAction
from src.contracts.model_rating import ModelRating
from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBRouterRating, DBRouterArtifact
from src.backend_server.model.data_store.database_connectors.database_schemas import ModelLinkedArtifactNames
from src.backend_server.model.data_store.database_connectors.base_database import db_reset
from mock_infrastructure import docker_init

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MYSQL_PORT = getattr(docker_init, "MYSQL_HOST_PORT", 3307)
MYSQL_DATABASE = getattr(docker_init, "MYSQL_DATABASE", "test_db")
MYSQL_USER = getattr(docker_init, "MYSQL_USER", "test_user")
MYSQL_PASSWORD = getattr(docker_init, "MYSQL_PASSWORD", "test_password")


class TestDBRouterRating(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up MySQL container and initialize database engine."""
        logger.info("Setting up MySQL container for DBRouterRating tests...")
        db_url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@127.0.0.1:{MYSQL_PORT}/{MYSQL_DATABASE}"
        cls.engine: Engine = create_engine(db_url)
        SQLModel.metadata.create_all(cls.engine)
        cls.router_rating = DBRouterRating(cls.engine)
        cls.router_artifact = DBRouterArtifact(cls.engine)

    def setUp(self):
        """Reset database before each test."""
        db_reset(self.engine)

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        if hasattr(cls, 'engine'):
            db_reset(cls.engine)

    def test_db_rating_add(self):
        """Test adding a rating to a model."""
        # First create a model
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="rating-router-model", id="rating-router-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[], linked_code_names=[],
            linked_parent_model_name=None, linked_parent_model_relation=None
        )
        self.router_artifact.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme=None)
        
        # Add rating
        rating = ModelRating.test_value()
        rating.name = "rating-router-model"
        rating.category = "model"
        
        result = self.router_rating.db_rating_add("rating-router-id-1", rating)
        self.assertTrue(result, "Failed to add rating")

        # try to get the rating back
        rating_result = self.router_rating.db_rating_get("rating-router-id-1")
        self.assertEqual(rating_result.name, "rating-router-model")

        audit_result = DBAuditAccessor.get_by_id(self.engine, ArtifactID(id="rating-router-id-1"), ArtifactType.model)
        self.assertEqual(len(audit_result), 2)
        types = [x.action for x in audit_result]
        self.assertTrue(AuditAction.RATE in types)

    def test_db_rating_add_nonexistent(self):
        """Test adding rating to non-existent artifact returns False."""
        rating = ModelRating.test_value()
        rating.name = "nonexistent-model"
        rating.category = "model"
        
        result = self.router_rating.db_rating_add("nonexistent-id", rating)
        self.assertFalse(result, "Should return False for non-existent artifact")

    def test_db_rating_add_wrong_category(self):
        """Test adding rating with wrong category returns False."""
        # Create a model
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="rating-wrong-cat", id="rating-wrong-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[], linked_code_names=[],
            linked_parent_model_name=None, linked_parent_model_relation=None
        )
        self.router_artifact.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme=None)
        
        # Try to add rating with wrong category
        rating = ModelRating.test_value()
        rating.name = "rating-wrong-cat"
        rating.category = "dataset"  # Wrong category
        
        result = self.router_rating.db_rating_add("rating-wrong-id-1", rating)
        self.assertFalse(result, "Should return False when rating category doesn't match artifact type")


if __name__ == '__main__':
    unittest.main()
