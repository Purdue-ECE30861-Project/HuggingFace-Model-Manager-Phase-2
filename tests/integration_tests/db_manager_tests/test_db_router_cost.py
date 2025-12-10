import unittest
import logging
from sqlalchemy import create_engine, Engine
from sqlmodel import SQLModel

from src.contracts.artifact_contracts import ArtifactType, Artifact, ArtifactData, ArtifactMetadata
from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBRouterCost, DBRouterArtifact
from src.backend_server.model.data_store.database_connectors.database_schemas import ModelLinkedArtifactNames
from src.backend_server.model.data_store.database_connectors.base_database import db_reset
from src.mock_infrastructure import docker_init

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MYSQL_PORT = getattr(docker_init, "MYSQL_HOST_PORT", 3307)
MYSQL_DATABASE = getattr(docker_init, "MYSQL_DATABASE", "test_db")
MYSQL_USER = getattr(docker_init, "MYSQL_USER", "test_user")
MYSQL_PASSWORD = getattr(docker_init, "MYSQL_PASSWORD", "test_password")


class TestDBRouterCost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up MySQL container and initialize database engine."""
        logger.info("Setting up MySQL container for DBRouterCost tests...")
        db_url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@127.0.0.1:{MYSQL_PORT}/{MYSQL_DATABASE}"
        cls.engine: Engine = create_engine(db_url)
        SQLModel.metadata.create_all(cls.engine)
        cls.router_cost = DBRouterCost(cls.engine)
        cls.router_artifact = DBRouterArtifact(cls.engine)

    def setUp(self):
        """Reset database before each test."""
        db_reset(self.engine)

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        if hasattr(cls, 'engine'):
            db_reset(cls.engine)

    def test_db_artifact_cost_model_standalone(self):
        """Test cost calculation for model without dependencies."""
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="cost-model", id="cost-model-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[], linked_code_names=[],
            linked_parent_model_name=None, linked_parent_model_relation=None
        )
        self.router_artifact.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme=None)
        
        cost = self.router_cost.db_artifact_cost("cost-model-id-1", ArtifactType.model, dependency=False)
        self.assertIsNotNone(cost, "Cost should not be None")
        self.assertEqual(cost.standalone_cost, 100.0, "Standalone cost should equal model size")
        self.assertEqual(cost.total_cost, 100.0, "Total cost should equal standalone when dependency=False")

    def test_db_artifact_cost_dataset_standalone(self):
        """Test cost calculation for dataset."""
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="cost-dataset", id="cost-dataset-id-1", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        self.router_artifact.db_artifact_ingest(dataset_artifact, size_mb=50.0, readme=None)
        
        cost = self.router_cost.db_artifact_cost("cost-dataset-id-1", ArtifactType.dataset, dependency=True)
        self.assertIsNotNone(cost, "Cost should not be None")
        self.assertEqual(cost.standalone_cost, 50.0, "Standalone cost should equal dataset size")
        self.assertEqual(cost.total_cost, 50.0, "Total cost should equal standalone for non-model")

    def test_db_artifact_cost_nonexistent(self):
        """Test cost calculation for non-existent artifact returns None."""
        cost = self.router_cost.db_artifact_cost("nonexistent-id", ArtifactType.model, dependency=False)
        self.assertIsNone(cost, "Non-existent artifact should return None")

    def test_db_artifact_cost_model_with_dependencies(self):
        """Test cost calculation for model with dependencies."""
        # Create dataset
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="cost-dset", id="cost-dset-id-1", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        self.router_artifact.db_artifact_ingest(dataset_artifact, size_mb=30.0, readme=None)
        
        # Create code
        code_artifact = Artifact(
            metadata=ArtifactMetadata(name="cost-code", id="cost-code-id-1", type=ArtifactType.code),
            data=ArtifactData(url="https://example.com/code", download_url="")
        )
        self.router_artifact.db_artifact_ingest(code_artifact, size_mb=10.0, readme=None)
        
        # Create model with dependencies
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="cost-model-dep", id="cost-model-dep-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=["cost-dset"],
            linked_code_names=["cost-code"],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )
        self.router_artifact.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme=None)
        
        # Calculate cost with dependencies
        cost = self.router_cost.db_artifact_cost("cost-model-dep-id-1", ArtifactType.model, dependency=True)
        self.assertIsNotNone(cost, "Cost should not be None")
        self.assertEqual(cost.standalone_cost, 100.0, "Standalone cost should equal model size")
        # Total cost should include model + dataset + code = 100 + 30 + 10 = 140
        self.assertGreater(cost.total_cost, cost.standalone_cost, "Total cost should be greater than standalone when dependencies exist")

    def test_db_artifact_cost_model_with_dependencies_nested(self):
        """Test cost calculation for model with dependencies."""
        # Create dataset

        dataset_artifact2 = Artifact(
            metadata=ArtifactMetadata(name="cost-dset2", id="cost-dset-id-2", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset2", download_url="")
        )
        self.router_artifact.db_artifact_ingest(dataset_artifact2, size_mb=30.0, readme=None)

        # Create code
        code_artifact2 = Artifact(
            metadata=ArtifactMetadata(name="cost-code2", id="cost-code-id-2", type=ArtifactType.code),
            data=ArtifactData(url="https://example.com/code2", download_url="")
        )
        self.router_artifact.db_artifact_ingest(code_artifact2, size_mb=10.0, readme=None)

        parent_model = Artifact(
            metadata=ArtifactMetadata(name="cost-model-2", id="cost-model-id-2", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model/2", download_url="")
        )

        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=["cost-dset2"],
            linked_code_names=["cost-code2"],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )

        self.router_artifact.db_model_ingest(parent_model, linked_names, size_mb=100.0, readme=None)
        cost = self.router_cost.db_artifact_cost("cost-model-id-2", ArtifactType.model, dependency=True)
        self.assertEqual(cost.total_cost, 140.0, "Root Total cost does not match expected value")
        # THE CURRENT MODEL

        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="cost-dset", id="cost-dset-id-1", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        self.router_artifact.db_artifact_ingest(dataset_artifact, size_mb=30.0, readme=None)

        # Create code
        code_artifact = Artifact(
            metadata=ArtifactMetadata(name="cost-code", id="cost-code-id-1", type=ArtifactType.code),
            data=ArtifactData(url="https://example.com/code", download_url="")
        )
        self.router_artifact.db_artifact_ingest(code_artifact, size_mb=10.0, readme=None)

        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="cost-model-dep", id="cost-model-dep-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=["cost-dset"],
            linked_code_names=["cost-code"],
            linked_parent_model_name="cost-model-2",
            linked_parent_model_relation="fine tune"
        )
        self.router_artifact.db_model_ingest(model_artifact, linked_names, size_mb=100.0, readme=None)

        # Calculate cost with dependencies
        cost = self.router_cost.db_artifact_cost("cost-model-dep-id-1", ArtifactType.model, dependency=True)
        self.assertIsNotNone(cost, "Cost should not be None")
        self.assertEqual(cost.standalone_cost, 100.0, "Standalone cost should equal model size")
        # Total cost should include model + dataset + code = 100 + 30 + 10 = 140
        self.assertGreater(cost.total_cost, cost.standalone_cost,
                           "Total cost should be greater than standalone when dependencies exist")
        self.assertEqual(cost.total_cost, 280.0, "Total cost does not match expected value")


if __name__ == '__main__':
    unittest.main()

