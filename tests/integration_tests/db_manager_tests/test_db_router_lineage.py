import unittest
import logging
from sqlalchemy import create_engine, Engine
from sqlmodel import SQLModel

from src.contracts.artifact_contracts import ArtifactType, Artifact, ArtifactData, ArtifactMetadata
from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBRouterLineage, DBRouterArtifact
from src.backend_server.model.data_store.database_connectors.database_schemas import ModelLinkedArtifactNames
from src.backend_server.model.data_store.database_connectors.base_database import db_reset
from mock_infrastructure import docker_init

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MYSQL_PORT = getattr(docker_init, "MYSQL_HOST_PORT", 3307)
MYSQL_DATABASE = getattr(docker_init, "MYSQL_DATABASE", "test_db")
MYSQL_USER = getattr(docker_init, "MYSQL_USER", "test_user")
MYSQL_PASSWORD = getattr(docker_init, "MYSQL_PASSWORD", "test_password")


class TestDBRouterLineage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up MySQL container and initialize database engine."""
        logger.info("Setting up MySQL container for DBRouterLineage tests...")
        db_url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@127.0.0.1:{MYSQL_PORT}/{MYSQL_DATABASE}"
        cls.engine: Engine = create_engine(db_url)
        SQLModel.metadata.create_all(cls.engine)
        cls.router_lineage = DBRouterLineage(cls.engine)
        cls.router_artifact = DBRouterArtifact(cls.engine)

    def setUp(self):
        """Reset database before each test."""
        db_reset(self.engine)

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        if hasattr(cls, 'engine'):
            db_reset(cls.engine)

    def test_db_artifact_lineage_nonexistent(self):
        """Test lineage for non-existent artifact returns None."""
        result = self.router_lineage.db_artifact_lineage("nonexistent-id")
        self.assertIsNone(result, "Non-existent artifact should return None")

    def test_db_artifact_lineage_not_model(self):
        """Test lineage for non-model artifact returns None."""
        # Create a dataset artifact
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="lineage-dataset", id="lineage-dataset-id-1", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        self.router_artifact.db_artifact_ingest(dataset_artifact, size_mb=50.0, readme=None)
        
        # Try to get lineage (should return None since it's not a model)
        result = self.router_lineage.db_artifact_lineage("lineage-dataset-id-1")
        self.assertIsNone(result, "Non-model artifact should return None")

    def test_db_artifact_lineage_not_implemented(self):
        """Test that lineage raises NotImplementedError for existing model."""
        # Create a model artifact
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="lineage-model", id="lineage-model-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[], linked_code_names=[],
            linked_parent_model_name=None, linked_parent_model_relation=None
        )
        self.router_artifact.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme=None)
        
        # Should raise NotImplementedError
        with self.assertRaises(NotImplementedError):
            self.router_lineage.db_artifact_lineage("lineage-model-id-1")


if __name__ == '__main__':
    unittest.main()
