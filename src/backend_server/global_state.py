from pydantic import BaseModel
import os

from src.backend_server.model.artifact_accessor.artifact_accessor import ArtifactAccessor
from src.backend_server.model.artifact_accessor.register_deferred import RaterTaskManager
from src.backend_server.model.data_store.database import create_engine, SQLModel, SQLMetadataAccessor
from src.backend_server.model.data_store.s3_manager import S3BucketManager
from src.backend_server.model.model_rater import ModelRater


class S3Config(BaseModel):
    s3_url: str
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_bucket_name: str
    s3_data_prefix: str
    s3_region_name: str


class GlobalConfig(BaseModel):
    db_url: str
    s3_config: S3Config
    rater_task_manager_workers: int
    rater_processes: int
    ingest_score_threshold: float

    @staticmethod
    def read_env() -> "GlobalConfig":
        return GlobalConfig(
            db_url=os.environ.get("DB_URL", "sqlite:///local.db"),
            s3_config=S3Config(
                s3_url=os.environ.get("S3_URL", "https://s3.amazonaws.com"),
                s3_access_key_id=os.environ.get("S3_ACCESS_KEY_ID", ""),
                s3_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY", ""),
                s3_bucket_name=os.environ.get("S3_BUCKET_NAME", "default-bucket"),
                s3_data_prefix=os.environ.get("S3_DATA_PREFIX", ""),
                s3_region_name=os.environ.get("S3_REGION_NAME", "us-east-1"),
            ),
            rater_task_manager_workers=int(os.environ.get("RATER_TASK_MANAGER_WORKERS", 1)),
            rater_processes=int(os.environ.get("RATER_PROCESSES", 1)),
            ingest_score_threshold=float(os.environ.get("INGEST_SCORE_THRESHOLD", 0.5)),
        )


global_config: GlobalConfig = GlobalConfig.read_env()

database_accessor: SQLMetadataAccessor = SQLMetadataAccessor(db_url=global_config.db_url)
rater_task_manager: RaterTaskManager = RaterTaskManager(
    max_workers=global_config.rater_task_manager_workers,
    max_processes_per_rater=global_config.rater_processes
)
s3_accessor: S3BucketManager = S3BucketManager(
    global_config.s3_config.s3_url,
    global_config.s3_config.s3_access_key_id,
    global_config.s3_config.s3_secret_access_key,
    global_config.s3_config.s3_bucket_name,
    global_config.s3_config.s3_data_prefix,
    global_config.s3_config.s3_region_name
)
artifact_accessor: ArtifactAccessor = ArtifactAccessor(
    database_accessor,
    s3_accessor,
    global_config.rater_processes,
    global_config.ingest_score_threshold
)
rater_accessor: ModelRater = ModelRater(database_accessor)