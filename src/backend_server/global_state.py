from pydantic import BaseModel
import os

from sqlalchemy import Engine, create_engine
from sqlmodel import SQLModel

from src.backend_server.model.artifact_accessor.artifact_accessor import (
    ArtifactAccessor,
)
from src.backend_server.model.artifact_accessor.register_deferred import (
    RaterTaskManager,
)
from src.backend_server.model.data_store.cache_accessor import CacheAccessor
from src.backend_server.model.data_store.database_connectors.mother_db_connector import (
    DBManager,
)
from src.backend_server.model.data_store.s3_manager import S3BucketManager
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError
import json

from src.backend_server.model.license_checker import LicenseChecker
from src.backend_server.model.llm_api import LLMAccessor


class S3Config(BaseModel):
    is_deploy: bool
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
    redis_password: str
    redis_database: int
    redis_ttl_seconds: int

class LLMConfig(BaseModel):
    bedrock_model: str
    use_bedrock: bool


class GlobalConfig(BaseModel):
    ingest_asynchronous: bool
    db_url: str
    s3_config: S3Config
    rater_task_manager_workers: int
    rater_processes: int
    ingest_score_threshold: float
    redis_config: RedisConfig
    max_ingest_queue_size: int
    genai_key: str
    github_pat: str
    llm_config: LLMConfig

    @staticmethod
    def _str_to_bool(str_value: str) -> bool:
        return str_value == "True"

    @staticmethod
    def read_env() -> "GlobalConfig":
        load_dotenv()
        is_deploy: bool = os.environ.get("DEVEL_TEST", "false").lower() == "true"
        genai_key: str = os.environ.get("GEN_AI_STUDIO_API_KEY", "sk-12345")
        github_pat: str = os.getenv("GITHUB_TOKEN", "github_pat_12345")

        redis_password: str = os.environ.get("REDIS_PASSWORD", "TestPassword")
        db_url = os.environ.get(
            "DB_URL", "mysql+pymysql://test_user:test_password@localhost:3307/test_db"
        )
        llm_model = "us.anthropic.claude-3-haiku-20240307-v1:0"

        if is_deploy:
            secret_manager = boto3.client("secretsmanager", region_name="us-east-2")
            # secret for external API connections (genai, github)
            api_key_location = os.environ.get("API_KEY_SECRET", "461/api_secrets")
            try:
                response = secret_manager.get_secret_value(SecretId=api_key_location)
            except ClientError as e:
                raise e
            api_keys = json.loads(response["SecretString"])
            genai_key = api_keys["GENAI_STUDIO_KEY"]
            github_pat = api_keys["GITHUB_PAT"]
            llm_model = api_keys["BEDROCK_MODEL_ID"]

            # secrets for database access
            db_location = os.environ.get("PROD_DB_LOCATION", "172.31.10.22:3306/artifacts_db")
            db_secrets_location = os.environ.get("DB_SECRET", "461/db_passwords")
            try:
                response = secret_manager.get_secret_value(
                    SecretId=db_secrets_location
                )
            except ClientError as e:
                raise e
            db_passwds = json.loads(response["SecretString"])
            # redis credentials
            redis_password = db_passwds["REDIS_PASSWORD"]
            # compose mysql credentials url
            db_url = f"mysql+pymysql://{db_passwds['ARTIFACT_DB_USER']}:{db_passwds['ARTIFACT_DB_PASSWORD']}@{db_location}"

        return GlobalConfig(
            ingest_asynchronous=GlobalConfig._str_to_bool(os.environ.get("INGEST_ASYNCHRONOUS", "False")),
            db_url=db_url,
            s3_config=S3Config(
                is_deploy=is_deploy,
                s3_url=f'http://{os.environ.get("S3_URL", "127.0.0.1")}:{os.environ.get("S3_HOST_PORT", "9000")}',
                s3_access_key_id=os.environ.get(
                    "S3_ACCESS_KEY_ID", "minio_access_key_123"
                ),
                s3_secret_access_key=os.environ.get(
                    "S3_SECRET_ACCESS_KEY", "minio_secret_key_password_456"
                ),
                s3_bucket_name=os.environ.get(
                    "S3_BUCKET_NAME", "hfmm-artifact-storage"
                ),
                s3_data_prefix=os.environ.get("S3_DATA_PREFIX", "artifact"),
                s3_region_name=os.environ.get("S3_REGION_NAME", ""),
            ),
            rater_task_manager_workers=int(
                os.environ.get("RATER_TASK_MANAGER_WORKERS", 1)
            ),
            rater_processes=int(os.environ.get("RATER_PROCESSES", 1)),
            ingest_score_threshold=float(os.environ.get("INGEST_SCORE_THRESHOLD", 0.2)),
            max_ingest_queue_size=int(os.environ.get("MAX_INGEST_QUEUE_SIZE", 100)),
            redis_config=RedisConfig(
                redis_host=os.environ.get("REDIS_HOST", "127.0.0.1"),
                redis_port=int(os.environ.get("REDIS_PORT", 6399)),
                redis_image=os.environ.get("REDIS_IMAGE", "redis:7.2"),
                redis_database=int(os.environ.get("REDIS_DB", 0)),
                redis_password=redis_password,
                redis_ttl_seconds=int(os.environ.get("REDIS_TTL_SECONDS", 180)),
            ),
            genai_key=genai_key,
            github_pat=github_pat,
            llm_config=LLMConfig(
                bedrock_model=llm_model,
                use_bedrock=is_deploy
            )
        )


global_config: GlobalConfig = GlobalConfig.read_env()

mysql_engine: Engine = create_engine(global_config.db_url)
SQLModel.metadata.create_all(mysql_engine)
llm_accessor: LLMAccessor = LLMAccessor(global_config.genai_key, bedrock=global_config.llm_config.use_bedrock, model_name=global_config.llm_config.bedrock_model)

database_manager: DBManager = DBManager(mysql_engine)

s3_accessor: S3BucketManager = S3BucketManager(
    global_config.s3_config.s3_url,
    global_config.s3_config.is_deploy,
    global_config.s3_config.s3_access_key_id,
    global_config.s3_config.s3_secret_access_key,
    global_config.s3_config.s3_bucket_name,
    global_config.s3_config.s3_data_prefix,
    global_config.s3_config.s3_region_name,
)
rater_task_manager: RaterTaskManager = RaterTaskManager(
    global_config.ingest_score_threshold,
    s3_accessor,
    database_manager,
    llm_accessor,
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
    llm_accessor,
    rater_task_manager,
    global_config.rater_processes,
    global_config.ingest_score_threshold,
)
license_checker: LicenseChecker = LicenseChecker(llm_accessor, github_token=global_config.github_pat)
