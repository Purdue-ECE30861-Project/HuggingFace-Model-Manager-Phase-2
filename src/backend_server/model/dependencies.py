from dataclasses import dataclass

from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBManager
from src.backend_server.model.data_store.s3_manager import S3BucketManager
from src.backend_server.model.llm_api import LLMAccessor


@dataclass
class DependencyBundle:
    def __init__(self, db: DBManager,
                 s3: S3BucketManager,
                 llm_accessor: LLMAccessor,
                 num_processors: int = 1,
                 ingest_score_threshold: float = 0.5,):
        self.db: DBManager = db
        self.s3_manager = s3
        self.llm_accessor = llm_accessor
        self.num_processors: int = num_processors
        self.ingest_score_threshold: float = ingest_score_threshold
