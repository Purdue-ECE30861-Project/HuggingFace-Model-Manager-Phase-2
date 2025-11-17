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


class RedisConfig(BaseModel):
    redis_image: str
    redis_host: str
    redis_port: int


class GlobalConfig(BaseModel):
    db_url: str
    s3_config: S3Config
    rater_task_manager_workers: int
    rater_processes: int
    ingest_score_threshold: float
    redis_config: RedisConfig

    @staticmethod
    def read_env() -> "GlobalConfig":
        return GlobalConfig(
            db_url=os.environ.get("DB_URL", "mysql+pymysql://test_user:newpassword@localhost:3307/test_db"),
            s3_config=S3Config(
                s3_url=f"http://{os.environ.get("S3_URL", "127.0.0.1")}:{os.environ.get("S3_HOST_PORT", "9000")}",
                s3_access_key_id=os.environ.get("S3_ACCESS_KEY_ID", "minio_access_key_123"),
                s3_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY", "minio_secret_key_password_456"),
                s3_bucket_name=os.environ.get("S3_BUCKET_NAME", "hfmm-artifact-storage"),
                s3_data_prefix=os.environ.get("S3_DATA_PREFIX", "artifact"),
                s3_region_name=os.environ.get("S3_REGION_NAME", ""),
            ),
            rater_task_manager_workers=int(os.environ.get("RATER_TASK_MANAGER_WORKERS", 1)),
            rater_processes=int(os.environ.get("RATER_PROCESSES", 1)),
            ingest_score_threshold=float(os.environ.get("INGEST_SCORE_THRESHOLD", 0.5)),
            redis_config=RedisConfig(
                redis_host=os.environ.get("REDIS_HOST", "127.0.0.1"),
                redis_port=int(os.environ.get("REDIS_PORT", 6379)),
                redis_image=os.environ.get("REDIS_IMAGE", "redis:7.2"),
            )
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