import unittest
import time
import logging
import pymysql
from pydantic import HttpUrl
from src.contracts.artifact_contracts import ArtifactType, Artifact, ArtifactData, ArtifactMetadata, ArtifactQuery
from src.backend_server.model.data_store.database import SQLMetadataAccessor
from tests.integration_tests.helpers import docker_init
from src.contracts.model_rating import ModelRating
from src.backend_server.model.data_store.database import SQLMetadataAccessor, ArtifactDataDB


# configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MySQL settings are taken from docker_init defaults
MYSQL_PORT = getattr(docker_init, "MYSQL_HOST_PORT", 3307)
MYSQL_ROOT_PASSWORD = getattr(docker_init, "MYSQL_ROOT_PASSWORD", "root")
MYSQL_DATABASE = getattr(docker_init, "MYSQL_DATABASE", "test_db")
MYSQL_USER = getattr(docker_init, "MYSQL_USER", "test_user")
MYSQL_PASSWORD = getattr(docker_init, "MYSQL_PASSWORD", "test_password")


class TestMySQLInfrastructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up MySQL container and initialize database accessor."""
        logger.info("Starting MySQL container via docker_init helper...")
        # start and wait are handled by helper which will raise if something fails
        cls.container = docker_init.start_mysql_container()
        docker_init.wait_for_mysql(port=MYSQL_PORT)

        # Initialize database accessor
        db_url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@127.0.0.1:{MYSQL_PORT}/{MYSQL_DATABASE}"
        cls.db_accessor = SQLMetadataAccessor(db_url)

    def tearDown(self):
        self.db_accessor.reset_db()

    @classmethod
    def tearDownClass(cls):
        """Clean up after each test."""
        if hasattr(cls, 'db_accessor'):
            cls.db_accessor.reset_db()
        # use docker_init helper to remove any test containers
        try:
            docker_init.cleanup_test_containers(("mysql_test_",))
        except Exception:
            logger.exception("Error cleaning up mysql test containers")

    def _wait_for_mysql(self, max_attempts: int = 20, delay: int = 2):
        """Wait for MySQL to be ready to accept connections."""
        # Keep this helper for tests that call it directly; delegate to docker_init.wait_for_mysql
        docker_init.wait_for_mysql(port=MYSQL_PORT, retries=max_attempts, delay=delay)

    def test_mysql_connection(self):
        try:
            connection = pymysql.connect(
                host='127.0.0.1',
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE
            )
            self.assertTrue(connection.open, "Connection should be open")
            logger.info("Connected")
            connection.close()
        except Exception as e:
            self.fail(f"Failed to connect to MySQL: {e}")

    def test_reset_database(self):
        test_rating: ModelRating = ModelRating.test_value()
        test_rating.name = "test-model-get"
        test_rating.category = ArtifactType.model

        test_artifact = ArtifactDataDB(
            id="test-id-1",
            url=HttpUrl("https://example.com/model"),
            rating=test_rating
        )

        success = self.db_accessor.add_to_db(test_artifact)
        in_db = self.db_accessor.get_by_id("test-id-1", ArtifactType.model)
        self.assertTrue(success, "Failed to add artifact to database")
        self.assertTrue(in_db, "not added success")

        self.db_accessor.reset_db()
        in_db = self.db_accessor.get_by_id("test-id-1", ArtifactType.model)
        self.assertFalse(in_db, "reset unsuccessful")

    def test_add_and_get_artifact(self):
        test_rating: ModelRating = ModelRating.test_value()
        test_rating.name = "test-model-get"
        test_rating.category = ArtifactType.model

        test_artifact = ArtifactDataDB(
            id="test-id-1",
            url=HttpUrl("https://example.com/model"),
            rating=test_rating
        )
        valid_artifact: Artifact = Artifact(data=ArtifactData(url="https://example.com/model", download_url=""), metadata=ArtifactMetadata(name="test-model-get", id="test-id-1", type=ArtifactType.model))

        success = self.db_accessor.add_to_db(test_artifact)
        self.assertTrue(success, "Failed to add artifact to database")

        exists = self.db_accessor.is_in_db("test-model-get", ArtifactType.model)
        self.assertTrue(exists, "Added artifact not found in database")

        exists_id = self.db_accessor.is_in_db_id("test-id-1", ArtifactType.model)
        self.assertTrue(exists_id, "Added artifact not found in database (by id)")

        received_value: Artifact = self.db_accessor.get_by_id("test-id-1", ArtifactType.model)
        print(received_value)
        self.assertTrue(received_value == valid_artifact, "wrong value")

    def test_add_multiple(self):
        test_rating1: ModelRating = ModelRating.test_value()
        test_rating1.name = "test-model"
        test_rating1.category = ArtifactType.model

        test_rating2: ModelRating = ModelRating.test_value()
        test_rating2.name = "test-model"
        test_rating2.category = ArtifactType.dataset

        test_rating3: ModelRating = ModelRating.test_value()
        test_rating3.name = "gooner"
        test_rating3.category = ArtifactType.model

        artifact_0 = ArtifactDataDB(
                id="test-id-1",
                url=HttpUrl("https://example.com/model1"),
                rating=test_rating1
            )
        artifact_1 = ArtifactDataDB(
                id="test-id-2",
                url=HttpUrl("https://example.com/model2"),
                rating=test_rating2
            )
        artifact_2 = ArtifactDataDB(
                id="silly-thing",
                url=HttpUrl("https://silly.com"),
                rating=test_rating3
            )
        self.assertFalse(self.db_accessor.is_in_db("test-model", ArtifactType.dataset))
        self.assertFalse(self.db_accessor.is_in_db("test-model", ArtifactType.model))
        self.assertFalse(self.db_accessor.is_in_db("gooner", ArtifactType.model))

        self.assertTrue(self.db_accessor.add_to_db(artifact_0))
        self.assertFalse(self.db_accessor.is_in_db("test-model", ArtifactType.dataset))
        self.assertTrue(self.db_accessor.is_in_db("test-model", ArtifactType.model))
        self.assertFalse(self.db_accessor.is_in_db("gooner", ArtifactType.model))

        self.assertTrue(self.db_accessor.add_to_db(artifact_1))
        self.assertTrue(self.db_accessor.is_in_db("test-model", ArtifactType.dataset))
        self.assertTrue(self.db_accessor.is_in_db("test-model", ArtifactType.model))
        self.assertFalse(self.db_accessor.is_in_db("gooner", ArtifactType.model))

        self.assertTrue(self.db_accessor.add_to_db(artifact_2))
        self.assertTrue(self.db_accessor.is_in_db("test-model", ArtifactType.dataset))
        self.assertTrue(self.db_accessor.is_in_db("test-model", ArtifactType.model))
        self.assertTrue(self.db_accessor.is_in_db("gooner", ArtifactType.model))


    def test_get_by_query(self):
        test_rating1: ModelRating = ModelRating.test_value()
        test_rating1.name = "test-model"
        test_rating1.category = ArtifactType.model

        test_rating2: ModelRating = ModelRating.test_value()
        test_rating2.name = "test-model"
        test_rating2.category = ArtifactType.dataset

        test_rating3: ModelRating = ModelRating.test_value()
        test_rating3.name = "gooner"
        test_rating3.category = ArtifactType.model

        test_artifacts = [
            ArtifactDataDB(
                id="test-id-1",
                url=HttpUrl("https://example.com/model1"),
                rating=test_rating1
            ),
            ArtifactDataDB(
                id="test-id-2",
                url=HttpUrl("https://example.com/model2"),
                rating=test_rating2
            ),
            ArtifactDataDB(
                id="sillything",
                url=HttpUrl("https://silly"),
                rating=test_rating3
            )
        ]

        for artifact in test_artifacts:
            self.assertTrue(self.db_accessor.add_to_db(artifact))

        query = ArtifactQuery(name="test-model", types=[ArtifactType.model, ArtifactType.dataset])
        results = self.db_accessor.get_by_query(query, "0")

        print(results)

        self.assertIsNotNone(results)
        self.assertEqual(len(results), 2)

        query.name = "*"
        results = self.db_accessor.get_by_query(query, "0")
        self.assertEqual(len(results), 3)

    def test_delete_artifact(self):
        test_rating: ModelRating = ModelRating.test_value()
        test_rating.name = "test-model-delete"
        test_rating.category=ArtifactType.model

        test_artifact = ArtifactDataDB(
            id="test-id-delete",
            url=HttpUrl("https://example.com/model"),
            rating=test_rating
        )

        self.db_accessor.add_to_db(test_artifact)

        success = self.db_accessor.delete_artifact("test-id-delete", ArtifactType.model)
        self.assertTrue(success, "Failed to delete artifact")

        exists = self.db_accessor.is_in_db("test-model-delete", ArtifactType.model)
        self.assertFalse(exists, "Artifact still exists after deletion")

    def test_update_artifact(self):
        test_rating: ModelRating = ModelRating.test_value()
        test_rating.name = "test-model-update"
        test_rating.category = ArtifactType.model

        initial_artifact = ArtifactDataDB(
            id="test-id-update",
            url=HttpUrl("https://example.com/model"),
            rating=test_rating
        )

        self.db_accessor.add_to_db(initial_artifact)

        # Create updated artifact
        updated_data = Artifact(
            metadata=ArtifactMetadata(
                name="updated-name",
                id="test-id-update",
                type=ArtifactType.model
            ),
            data=ArtifactData(
                url="https://example.com/updated",
                download_url=""
            )
        )

        # Update artifact
        success = self.db_accessor.update_artifact("test-id-update", updated_data, ArtifactType.model)
        self.assertTrue(success, "Failed to update artifact")

        newly_updated = self.db_accessor.get_by_id('test-id-update', ArtifactType.model)
        self.assertEqual(newly_updated.data.url, "https://example.com/updated")
        self.assertEqual(newly_updated.metadata.name, 'updated-name')

    def test_full_integration_flow(self):
        """Simulates end-to-end database behavior across add, get, update, query, and delete."""

        # Step 1: Add multiple artifacts
        rating_model = ModelRating.test_value()
        rating_model.name = "artifact-model"
        rating_model.category = ArtifactType.model

        rating_dataset = ModelRating.test_value()
        rating_dataset.name = "artifact-dataset"
        rating_dataset.category = ArtifactType.dataset

        artifact_model = ArtifactDataDB(
            id="int-id-1",
            url=HttpUrl("https://example.com/model"),
            rating=rating_model
        )
        artifact_dataset = ArtifactDataDB(
            id="int-id-2",
            url=HttpUrl("https://example.com/dataset"),
            rating=rating_dataset
        )

        self.assertTrue(self.db_accessor.add_to_db(artifact_model))
        self.assertTrue(self.db_accessor.add_to_db(artifact_dataset))

        # Step 2: Verify presence by name and id
        self.assertTrue(self.db_accessor.is_in_db("artifact-model", ArtifactType.model))
        self.assertTrue(self.db_accessor.is_in_db("artifact-dataset", ArtifactType.dataset))
        self.assertTrue(self.db_accessor.is_in_db_id("int-id-1", ArtifactType.model))

        # Step 3: Retrieve by id and verify
        retrieved_model = self.db_accessor.get_by_id("int-id-1", ArtifactType.model)
        self.assertIsNotNone(retrieved_model)
        self.assertEqual(retrieved_model.metadata.name, "artifact-model")

        # Step 4: Query by combined filter
        query = ArtifactQuery(name="artifact-model", types=[ArtifactType.model, ArtifactType.dataset])
        query_results = self.db_accessor.get_by_query(query, "0")
        self.assertEqual(len(query_results), 1)

        # Step 5: Update the model artifact
        updated_artifact = Artifact(
            metadata=ArtifactMetadata(
                name="artifact-model-updated",
                id="int-id-1",
                type=ArtifactType.model
            ),
            data=ArtifactData(
                url="https://example.com/model-updated",
                download_url=""
            )
        )
        success = self.db_accessor.update_artifact("int-id-1", updated_artifact, ArtifactType.model)
        self.assertTrue(success)

        updated_entry = self.db_accessor.get_by_id("int-id-1", ArtifactType.model)
        self.assertEqual(updated_entry.data.url, "https://example.com/model-updated")
        self.assertEqual(updated_entry.metadata.name, "artifact-model-updated")

        # Step 6: Delete one artifact
        deleted = self.db_accessor.delete_artifact("int-id-1", ArtifactType.model)
        self.assertTrue(deleted)
        self.assertFalse(self.db_accessor.is_in_db("artifact-model-updated", ArtifactType.model))

        # Step 7: Confirm other entries remain
        remaining = self.db_accessor.get_by_id("int-id-2", ArtifactType.dataset)
        self.assertIsNotNone(remaining)
        self.assertEqual(remaining.metadata.name, "artifact-dataset")

        # Step 8: Reset database and confirm empty
        self.db_accessor.reset_db()
        self.assertFalse(self.db_accessor.is_in_db("artifact-dataset", ArtifactType.dataset))
        self.assertFalse(self.db_accessor.is_in_db_id("int-id-2", ArtifactType.dataset))

    # ADD TESTS FOR REGEX AND BY NAME


if __name__ == '__main__':
    unittest.main()