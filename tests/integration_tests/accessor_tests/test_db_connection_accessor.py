import unittest
import logging
from pydantic import HttpUrl
from sqlalchemy import create_engine, Engine
from sqlmodel import SQLModel, Session, select

from src.contracts.artifact_contracts import ArtifactType, Artifact, ArtifactData, ArtifactMetadata
from src.backend_server.model.data_store.database_connectors.artifact_database import DBConnectionAccessor, DBArtifactAccessor
from src.backend_server.model.data_store.database_connectors.database_schemas import (
    DBArtifactSchema, DBModelSchema, DBDSetSchema, DBCodeSchema, 
    ModelLinkedArtifactNames, DBConnectiveSchema, DBConnectiveRelation
)
from src.backend_server.model.data_store.database_connectors.base_database import db_reset
from mock_infrastructure import docker_init

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MYSQL_PORT = getattr(docker_init, "MYSQL_HOST_PORT", 3307)
MYSQL_DATABASE = getattr(docker_init, "MYSQL_DATABASE", "test_db")
MYSQL_USER = getattr(docker_init, "MYSQL_USER", "test_user")
MYSQL_PASSWORD = getattr(docker_init, "MYSQL_PASSWORD", "test_password")


class TestDBConnectionAccessor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up MySQL container and initialize database engine."""
        logger.info("Setting up MySQL container for DBConnectionAccessor tests...")
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

    def test_model_insert_with_datasets(self):
        """Test inserting model connections with datasets."""
        # First create a dataset
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="test-dataset", id="dset-id-1", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        db_dataset = DBArtifactSchema.from_artifact(dataset_artifact, size_mb=50.0).to_concrete()
        DBArtifactAccessor.artifact_insert(self.engine, db_dataset)

        # Create a model
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="test-model", id="model-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        db_model = DBModelSchema.from_artifact(model_artifact, size_mb=100.0)
        DBArtifactAccessor.artifact_insert(self.engine, db_model)

        # Create linked names
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=["test-dataset"],
            linked_code_names=[],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )

        # Insert connections
        DBConnectionAccessor.model_insert(self.engine, db_model, linked_names)

        # Verify connection exists
        with Session(self.engine) as session:
            query = select(DBConnectiveSchema).where(
                DBConnectiveSchema.dst_id == "model-id-1",
                DBConnectiveSchema.relationship == DBConnectiveRelation.MODEL_DATASET
            )
            connections = session.exec(query).all()
            self.assertEqual(len(connections), 1, "Should have 1 dataset connection")
            self.assertEqual(connections[0].src_id, "dset-id-1")
            self.assertEqual(connections[0].dst_id, "model-id-1")

    def test_model_insert_with_code(self):
        """Test inserting model connections with code."""
        # First create a code artifact
        code_artifact = Artifact(
            metadata=ArtifactMetadata(name="test-code", id="code-id-1", type=ArtifactType.code),
            data=ArtifactData(url="https://example.com/code", download_url="")
        )
        db_code = DBArtifactSchema.from_artifact(code_artifact, size_mb=10.0).to_concrete()
        DBArtifactAccessor.artifact_insert(self.engine, db_code)

        # Create a model
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="test-model-code", id="model-code-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        db_model = DBModelSchema.from_artifact(model_artifact, size_mb=100.0)
        DBArtifactAccessor.artifact_insert(self.engine, db_model)

        # Create linked names
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[],
            linked_code_names=["test-code"],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )

        # Insert connections
        DBConnectionAccessor.model_insert(self.engine, db_model, linked_names)

        # Verify connection exists
        with Session(self.engine) as session:
            query = select(DBConnectiveSchema).where(
                DBConnectiveSchema.dst_id == "model-code-id-1",
                DBConnectiveSchema.relationship == DBConnectiveRelation.MODEL_CODEBASE
            )
            connections = session.exec(query).all()
            self.assertEqual(len(connections), 1, "Should have 1 code connection")
            self.assertEqual(connections[0].src_id, "code-id-1")

    def test_model_insert_with_parent_model(self):
        """Test inserting model connections with parent model."""
        # First create a parent model
        parent_artifact = Artifact(
            metadata=ArtifactMetadata(name="parent-model", id="parent-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/parent", download_url="")
        )
        db_parent = DBModelSchema.from_artifact(parent_artifact, size_mb=200.0)
        DBArtifactAccessor.artifact_insert(self.engine, db_parent)

        # Create a child model
        child_artifact = Artifact(
            metadata=ArtifactMetadata(name="child-model", id="child-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/child", download_url="")
        )
        db_child = DBModelSchema.from_artifact(child_artifact, size_mb=100.0)
        DBArtifactAccessor.artifact_insert(self.engine, db_child)

        # Create linked names
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[],
            linked_code_names=[],
            linked_parent_model_name="parent-model",
            linked_parent_model_relation=None
        )

        # Insert connections
        DBConnectionAccessor.model_insert(self.engine, db_child, linked_names)

        # Verify connection exists
        with Session(self.engine) as session:
            query = select(DBConnectiveSchema).where(
                DBConnectiveSchema.dst_id == "child-id-1",
                DBConnectiveSchema.relationship == DBConnectiveRelation.MODEL_PARENT_MODEL
            )
            connection = session.exec(query).first()
            self.assertIsNotNone(connection, "Should have parent model connection")
            self.assertEqual(connection.src_id, "parent-id-1")

    def test_non_model_insert(self):
        """Test inserting connections for non-model artifacts."""
        # Create a model that references a dataset by name
        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="model-ref", id="model-ref-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        db_model = DBModelSchema.from_artifact(model_artifact, size_mb=100.0)
        DBArtifactAccessor.artifact_insert(self.engine, db_model)

        # Create a connection that references a dataset by name (before dataset exists)
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=["future-dataset"],
            linked_code_names=[],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )
        DBConnectionAccessor.model_insert(self.engine, db_model, linked_names)

        # Now create the dataset
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="future-dataset", id="future-dset-id-1", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        db_dataset = DBDSetSchema.from_artifact(dataset_artifact, size_mb=50.0)
        DBArtifactAccessor.artifact_insert(self.engine, db_dataset)

        # Insert connections for the dataset (should update existing connection)
        DBConnectionAccessor.non_model_insert(self.engine, db_dataset)

        # Verify connection was updated with ID
        with Session(self.engine) as session:
            query = select(DBConnectiveSchema).where(
                DBConnectiveSchema.src_name == "future-dataset"
            )
            connection = session.exec(query).first()
            self.assertIsNotNone(connection, "Connection should exist")
            self.assertEqual(connection.src_id, "future-dset-id-1", "Connection should have src_id set")

    def test_connections_delete_by_artifact_id(self):
        """Test deleting connections by artifact ID."""
        # Create artifacts
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="del-dataset", id="del-dset-id-1", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        db_dataset = DBArtifactSchema.from_artifact(dataset_artifact, size_mb=50.0).to_concrete()
        DBArtifactAccessor.artifact_insert(self.engine, db_dataset)

        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="del-model", id="del-model-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        db_model = DBModelSchema.from_artifact(model_artifact, size_mb=100.0)
        DBArtifactAccessor.artifact_insert(self.engine, db_model)

        # Create connection
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=["del-dataset"],
            linked_code_names=[],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )
        DBConnectionAccessor.model_insert(self.engine, db_model, linked_names)

        # Verify connection exists
        with Session(self.engine) as session:
            query = select(DBConnectiveSchema).where(DBConnectiveSchema.dst_id == "del-model-id-1")
            connections_before = session.exec(query).all()
            self.assertEqual(len(connections_before), 1, "Connection should exist")

        # Delete connections
        DBConnectionAccessor.connections_delete_by_artifact_id(self.engine, "del-model-id-1")

        # Verify connection is deleted
        with Session(self.engine) as session:
            query = select(DBConnectiveSchema).where(DBConnectiveSchema.dst_id == "del-model-id-1")
            connections_after = session.exec(query).all()
            self.assertEqual(len(connections_after), 0, "Connection should be deleted")

    def test_model_get_associated_dset_and_code(self):
        """Test retrieving associated datasets and code for a model."""
        # Create artifacts
        dataset_artifact = Artifact(
            metadata=ArtifactMetadata(name="get-dataset", id="get-dset-id-1", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        db_dataset = DBArtifactSchema.from_artifact(dataset_artifact, size_mb=50.0).to_concrete()
        DBArtifactAccessor.artifact_insert(self.engine, db_dataset)

        code_artifact = Artifact(
            metadata=ArtifactMetadata(name="get-code", id="get-code-id-1", type=ArtifactType.code),
            data=ArtifactData(url="https://example.com/code", download_url="")
        )
        db_code = DBArtifactSchema.from_artifact(code_artifact, size_mb=10.0).to_concrete()
        DBArtifactAccessor.artifact_insert(self.engine, db_code)

        model_artifact = Artifact(
            metadata=ArtifactMetadata(name="get-model", id="get-model-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        db_model = DBModelSchema.from_artifact(model_artifact, size_mb=100.0)
        DBArtifactAccessor.artifact_insert(self.engine, db_model)

        # Create connections
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=["get-dataset"],
            linked_code_names=["get-code"],
            linked_parent_model_name=None,
            linked_parent_model_relation=None
        )
        DBConnectionAccessor.model_insert(self.engine, db_model, linked_names)

        # Retrieve associations
        connections = DBConnectionAccessor.model_get_associated_dset_and_code(self.engine, db_model)
        self.assertEqual(len(connections), 2, "Should have 2 connections (dataset and code)")

    def test_model_get_parent_model(self):
        """Test retrieving parent model for a model."""
        # Create parent model
        parent_artifact = Artifact(
            metadata=ArtifactMetadata(name="parent-get", id="parent-get-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/parent", download_url="")
        )
        db_parent = DBModelSchema.from_artifact(parent_artifact, size_mb=200.0)
        DBArtifactAccessor.artifact_insert(self.engine, db_parent)

        # Create child model
        child_artifact = Artifact(
            metadata=ArtifactMetadata(name="child-get", id="child-get-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/child", download_url="")
        )
        db_child = DBModelSchema.from_artifact(child_artifact, size_mb=100.0)
        DBArtifactAccessor.artifact_insert(self.engine, db_child)

        self.assertEqual(len(DBArtifactAccessor.get_all(self.engine)), 2, "Should have 2 artifacts")

        # Create connection
        linked_names = ModelLinkedArtifactNames(
            linked_dset_names=[],
            linked_code_names=[],
            linked_parent_model_name="parent-get",
            linked_parent_model_relation=None
        )
        DBConnectionAccessor.model_insert(self.engine, db_child, linked_names)
        self.assertEqual(len(DBConnectionAccessor.connections_get_all(self.engine)), 1, "Should have 1 connection")

        # Retrieve parent
        parent_connection = DBConnectionAccessor.model_get_parent_model(self.engine, db_child)
        self.assertIsNotNone(parent_connection, "Should have parent model connection")
        self.assertEqual(parent_connection.src_id, "parent-get-id-1")
        self.assertEqual(parent_connection.dst_id, "child-get-id-1")


if __name__ == '__main__':
    unittest.main()

