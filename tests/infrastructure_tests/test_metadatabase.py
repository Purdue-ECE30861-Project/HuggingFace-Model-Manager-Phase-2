import unittest
import docker
import pymysql
import logging
import time
import uuid

from src.external_contracts import ModelRating, Artifact, ArtifactMetadata, ArtifactQuery, ArtifactType, ArtifactData
from src.backend_server.model.data_store.database import SQLMetadataAccessor, ArtifactDataDB
from pydantic import HttpUrl


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MySQL configuration
MYSQL_IMAGE = "mysql:8.0"
MYSQL_PORT = 3307  # Using non-default port to avoid conflicts
MYSQL_ROOT_PASSWORD = "root"
MYSQL_DATABASE = "test_db"
MYSQL_USER = "test_user"
MYSQL_PASSWORD = "test_password"

class TestMySQLInfrastructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logger.info("Setting up MySQL container...")
        cls.client = docker.from_env()

        cls.container = cls.client.containers.run(
            MYSQL_IMAGE,
            environment={
                'MYSQL_ROOT_PASSWORD': MYSQL_ROOT_PASSWORD,
                'MYSQL_DATABASE': MYSQL_DATABASE,
                'MYSQL_USER': MYSQL_USER,
                'MYSQL_PASSWORD': MYSQL_PASSWORD,
            },
            ports={'3306/tcp': ('127.0.0.1', MYSQL_PORT)},
            detach=True,
            remove=True,
            name=f"mysql_test_{uuid.uuid4().hex[:8]}"
        )
        logger.info("Started setup")

        cls._wait_for_mysql()

        db_url = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@127.0.0.1:{MYSQL_PORT}/{MYSQL_DATABASE}"
        cls.db_accessor = SQLMetadataAccessor(db_url)

    @classmethod
    def _wait_for_mysql(cls, max_attempts: int = 20, delay: int = 2):
        for attempt in range(max_attempts):
            try:
                connection = pymysql.connect(
                    host='127.0.0.1',
                    port=MYSQL_PORT,
                    user='root',
                    password=MYSQL_ROOT_PASSWORD,
                    database=MYSQL_DATABASE,
                    connect_timeout=5
                )
                connection.close()
                logger.info(f"MySQL ready after {attempt + 1} attempts")
                return
            except Exception as e:
                logger.info(f"Attempt {attempt + 1}: MySQL not ready yet ({e})")
                time.sleep(delay)
        raise Exception("MySQL container failed to become ready")

    @classmethod
    def tearDownClass(cls):
        logger.info("Cleaning up MySQL container...")
        if hasattr(cls, 'container') and cls.container:
            cls.container.stop()

    def tearDown(self):
        self.db_accessor.reset_db()

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


if __name__ == '__main__':
    unittest.main()