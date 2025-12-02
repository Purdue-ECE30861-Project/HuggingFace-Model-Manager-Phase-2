from dataclasses import dataclass

from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBManager
from src.backend_server.model.data_store.s3_manager import S3BucketManager


@dataclass
class ArtifactAccessorDependencies:
    def __init__(self, db: DBManager,
                 s3: S3BucketManager,
                 num_processors: int = 1,
                 ingest_score_threshold: float = 0.5,):
        self.db: DBManager = db
        self.s3_manager = s3
        self.num_processors: int = num_processors
        self.ingest_score_threshold: float = ingest_score_threshold