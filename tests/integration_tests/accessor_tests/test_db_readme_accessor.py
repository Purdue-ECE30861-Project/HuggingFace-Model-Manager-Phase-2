import unittest
import logging
from pydantic import HttpUrl
from sqlalchemy import create_engine, Engine
from sqlmodel import SQLModel, Session, select

from src.contracts.artifact_contracts import ArtifactType, Artifact, ArtifactData, ArtifactMetadata
from src.backend_server.model.data_store.database_connectors.artifact_database import DBReadmeAccessor, DBArtifactAccessor
from src.backend_server.model.data_store.database_connectors.database_schemas import (
    DBArtifactSchema, DBArtifactReadmeSchema
)
from src.backend_server.model.data_store.database_connectors.base_database import db_reset
from mock_infrastructure import docker_init

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MYSQL_PORT = getattr(docker_init, "MYSQL_HOST_PORT", 3307)
MYSQL_DATABASE = getattr(docker_init, "MYSQL_DATABASE", "test_db")
MYSQL_USER = getattr(docker_init, "MYSQL_USER", "test_user")
MYSQL_PASSWORD = getattr(docker_init, "MYSQL_PASSWORD", "test_password")


class TestDBReadmeAccessor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up MySQL container and initialize database engine."""
        logger.info("Setting up MySQL container for DBReadmeAccessor tests...")
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

    def test_artifact_insert_readme_model(self):
        """Test inserting a README for a model artifact."""
        artifact = Artifact(
            metadata=ArtifactMetadata(name="readme-model", id="readme-model-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        readme_content = "# Test Model\n\nThis is a test model README."
        
        DBReadmeAccessor.artifact_insert_readme(self.engine, artifact, readme_content)
        
        # Verify README was inserted
        with Session(self.engine) as session:
            query = select(DBArtifactReadmeSchema).where(
                DBArtifactReadmeSchema.id == "readme-model-id-1",
                DBArtifactReadmeSchema.artifact_type == ArtifactType.model
            )
            readme = session.exec(query).first()
            self.assertIsNotNone(readme, "README should be inserted")
            self.assertEqual(readme.readme_content, readme_content)
            self.assertEqual(readme.name, "readme-model")

    def test_artifact_insert_readme_dataset(self):
        """Test inserting a README for a dataset artifact."""
        artifact = Artifact(
            metadata=ArtifactMetadata(name="readme-dataset", id="readme-dataset-id-1", type=ArtifactType.dataset),
            data=ArtifactData(url="https://example.com/dataset", download_url="")
        )
        readme_content = "# Test Dataset\n\nThis is a test dataset README."
        
        DBReadmeAccessor.artifact_insert_readme(self.engine, artifact, readme_content)
        
        # Verify README was inserted
        with Session(self.engine) as session:
            query = select(DBArtifactReadmeSchema).where(
                DBArtifactReadmeSchema.id == "readme-dataset-id-1",
                DBArtifactReadmeSchema.artifact_type == ArtifactType.dataset
            )
            readme = session.exec(query).first()
            self.assertIsNotNone(readme, "README should be inserted")
            self.assertEqual(readme.readme_content, readme_content)
            self.assertEqual(readme.artifact_type, ArtifactType.dataset)

    def test_artifact_insert_readme_code(self):
        """Test inserting a README for a code artifact."""
        artifact = Artifact(
            metadata=ArtifactMetadata(name="readme-code", id="readme-code-id-1", type=ArtifactType.code),
            data=ArtifactData(url="https://example.com/code", download_url="")
        )
        readme_content = "# Test Code\n\nThis is a test code README."
        
        DBReadmeAccessor.artifact_insert_readme(self.engine, artifact, readme_content)
        
        # Verify README was inserted
        with Session(self.engine) as session:
            query = select(DBArtifactReadmeSchema).where(
                DBArtifactReadmeSchema.id == "readme-code-id-1",
                DBArtifactReadmeSchema.artifact_type == ArtifactType.code
            )
            readme = session.exec(query).first()
            self.assertIsNotNone(readme, "README should be inserted")
            self.assertEqual(readme.readme_content, readme_content)
            self.assertEqual(readme.artifact_type, ArtifactType.code)

    def test_artifact_insert_readme_long_content(self):
        """Test inserting a README with long content."""
        artifact = Artifact(
            metadata=ArtifactMetadata(name="readme-long", id="readme-long-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        # Create a long README content
        readme_content = "# Long README\n\n" + "This is a very long README content. " * 100
        
        DBReadmeAccessor.artifact_insert_readme(self.engine, artifact, readme_content)
        
        # Verify README was inserted
        with Session(self.engine) as session:
            query = select(DBArtifactReadmeSchema).where(
                DBArtifactReadmeSchema.id == "readme-long-id-1"
            )
            readme = session.exec(query).first()
            self.assertIsNotNone(readme, "README should be inserted")
            self.assertEqual(len(readme.readme_content), len(readme_content))

    def test_artifact_delete_readme(self):
        """Test deleting a README for an artifact."""
        artifact = Artifact(
            metadata=ArtifactMetadata(name="delete-readme-model", id="delete-readme-id-1", type=ArtifactType.model),
            data=ArtifactData(url="https://example.com/model", download_url="")
        )
        readme_content = "# Delete Test\n\nThis README will be deleted."
        
        # Insert README first
        DBReadmeAccessor.artifact_insert_readme(self.engine, artifact, readme_content)
        
        # Verify it exists
        with Session(self.engine) as session:
            query = select(DBArtifactReadmeSchema).where(
                DBArtifactReadmeSchema.id == "delete-readme-id-1"
            )
            readme_before = session.exec(query).first()
            self.assertIsNotNone(readme_before, "README should exist before deletion")
        
        # Delete README
        DBReadmeAccessor.artifact_delete_readme(self.engine, "delete-readme-id-1", ArtifactType.model)
        
        # Verify it no longer exists
        with Session(self.engine) as session:
            query = select(DBArtifactReadmeSchema).where(
                DBArtifactReadmeSchema.id == "delete-readme-id-1"
            )
            readme_after = session.exec(query).first()
            self.assertIsNone(readme_after, "README should not exist after deletion")

    def test_artifact_delete_readme_nonexistent(self):
        """Test deleting a non-existent README (should not raise error)."""
        # Should not raise an error when deleting non-existent README
        DBReadmeAccessor.artifact_delete_readme(self.engine, "nonexistent-readme-id", ArtifactType.model)

    def test_multiple_readmes_different_types(self):
        """Test inserting READMEs for multiple artifacts of different types."""
        artifacts = [
            Artifact(
                metadata=ArtifactMetadata(name="multi-readme-model", id="multi-readme-model-id", type=ArtifactType.model),
                data=ArtifactData(url="https://example.com/model", download_url="")
            ),
            Artifact(
                metadata=ArtifactMetadata(name="multi-readme-dataset", id="multi-readme-dataset-id", type=ArtifactType.dataset),
                data=ArtifactData(url="https://example.com/dataset", download_url="")
            ),
            Artifact(
                metadata=ArtifactMetadata(name="multi-readme-code", id="multi-readme-code-id", type=ArtifactType.code),
                data=ArtifactData(url="https://example.com/code", download_url="")
            ),
        ]
        
        for artifact in artifacts:
            readme_content = f"# README for {artifact.metadata.name}\n\nContent here."
            DBReadmeAccessor.artifact_insert_readme(self.engine, artifact, readme_content)
        
        # Verify all READMEs exist
        with Session(self.engine) as session:
            query = select(DBArtifactReadmeSchema)
            all_readmes = session.exec(query).all()
            self.assertEqual(len(all_readmes), 3, "Should have 3 READMEs")


if __name__ == '__main__':
    unittest.main()
