from pydantic import BaseModel
import os

from sqlalchemy import Engine, create_engine
from sqlmodel import SQLModel

from src.backend_server.model.artifact_accessor.artifact_accessor import ArtifactAccessor
from src.backend_server.model.artifact_accessor.register_deferred import RaterTaskManager
from src.backend_server.model.data_store.cache_accessor import CacheAccessor
from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBManager
from src.backend_server.model.data_store.s3_manager import S3BucketManager


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
    redis_user: str
    redis_password: str
    redis_ttl_seconds: int


class GlobalConfig(BaseModel):
    ingest_asynchronous: bool
    db_url: str
    s3_config: S3Config
    rater_task_manager_workers: int
    rater_processes: int
    ingest_score_threshold: float
    redis_config: RedisConfig
    max_ingest_queue_size: int

    @staticmethod
    def read_env() -> "GlobalConfig":
        return GlobalConfig(
            ingest_asynchronous=bool(os.environ.get("INGEST_ASYNCHRONOUS", "True")),
            db_url=os.environ.get("DB_URL", "mysql+pymysql://test_user:newpassword@localhost:3307/test_db"),
            s3_config=S3Config(
                s3_url=f'http://{os.environ.get("S3_URL", "127.0.0.1")}:{os.environ.get("S3_HOST_PORT", "9000")}',
                s3_access_key_id=os.environ.get("S3_ACCESS_KEY_ID", "minio_access_key_123"),
                s3_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY", "minio_secret_key_password_456"),
                s3_bucket_name=os.environ.get("S3_BUCKET_NAME", "hfmm-artifact-storage"),
                s3_data_prefix=os.environ.get("S3_DATA_PREFIX", "artifact"),
                s3_region_name=os.environ.get("S3_REGION_NAME", ""),
            ),
            rater_task_manager_workers=int(os.environ.get("RATER_TASK_MANAGER_WORKERS", 1)),
            rater_processes=int(os.environ.get("RATER_PROCESSES", 1)),
            ingest_score_threshold=float(os.environ.get("INGEST_SCORE_THRESHOLD", 0.5)),
            max_ingest_queue_size=int(os.environ.get("MAX_INGEST_QUEUE_SIZE", 100)),
            redis_config=RedisConfig(
                redis_host=os.environ.get("REDIS_HOST", "127.0.0.1"),
                redis_port=int(os.environ.get("REDIS_PORT", 6379)),
                redis_image=os.environ.get("REDIS_IMAGE", "redis:7.2"),
                redis_user=os.environ.get("REDIS_USER", "TestUser"),
                redis_password=os.environ.get("REDIS_PASSWORD", "TestPassword"),
                redis_ttl_seconds=int(os.environ.get("REDIS_TTL_SECONDS", 180)),
            )
        )


global_config: GlobalConfig = GlobalConfig.read_env()

mysql_engine: Engine = create_engine(global_config.db_url)
SQLModel.metadata.create_all(mysql_engine)

database_manager: DBManager = DBManager(mysql_engine)

s3_accessor: S3BucketManager = S3BucketManager(
    global_config.s3_config.s3_url,
    global_config.s3_config.s3_access_key_id,
    global_config.s3_config.s3_secret_access_key,
    global_config.s3_config.s3_bucket_name,
    global_config.s3_config.s3_data_prefix,
    global_config.s3_config.s3_region_name
)

rater_task_manager: RaterTaskManager = RaterTaskManager(
    global_config.ingest_score_threshold,
    s3_accessor,
    database_manager,
    max_workers=global_config.rater_task_manager_workers,
    max_processes_per_rater=global_config.rater_processes,
    max_queue_size=global_config.max_ingest_queue_size,
)
cache_accessor = CacheAccessor(
    host=global_config.redis_config.redis_host,
    port=global_config.redis_config.redis_port,
    db=global_config.redis_config.redis_database,
    password=global_config.redis_config.redis_password,
    ttl_seconds=global_config.redis_config.redis_ttl_seconds,
)
artifact_accessor: ArtifactAccessor = ArtifactAccessor(
    database_manager,
    s3_accessor,
    rater_task_manager,
    global_config.rater_processes,
    global_config.ingest_score_threshold,
)