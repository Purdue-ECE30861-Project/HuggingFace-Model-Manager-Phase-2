import os
import time
import uuid
import logging
from typing import Optional, List

import docker
import pymysql
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Defaults (can be overridden via environment)
MYSQL_IMAGE = os.environ.get("TEST_MYSQL_IMAGE", "mysql:8.0")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_HOST_PORT = int(os.environ.get("MYSQL_HOST_PORT", "3307"))
MYSQL_ROOT_PASSWORD = os.environ.get("MYSQL_ROOT_PASSWORD", "root")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "test_db")
MYSQL_USER = os.environ.get("MYSQL_USER", "test_user")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "test_password")

MINIO_IMAGE = os.environ.get("TEST_MINIO_IMAGE", "minio/minio:latest")
MINIO_HOST = os.environ.get("MINIO_HOST", "127.0.0.1")
MINIO_HOST_PORT = int(os.environ.get("MINIO_HOST_PORT", "9000"))
MINIO_CONSOLE_PORT = int(os.environ.get("MINIO_CONSOLE_PORT", "9001"))
MINIO_ROOT_USER = os.environ.get("MINIO_ROOT_USER", "minio_access_key_123")
MINIO_ROOT_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD", "minio_secret_key_password_456")
MINIO_BUCKET = os.environ.get("S3_BUCKET", "hfmm-artifact-storage")


def _client() -> docker.DockerClient:
    return docker.from_env()


def start_mysql_container(name_prefix: str = "mysql_test_", host_port: int | None = None, keep: bool = False):
    """Start a MySQL container for tests. Returns docker.Container."""
    client = _client()
    host_port = host_port or MYSQL_HOST_PORT
    name = f"{name_prefix}{uuid.uuid4().hex[:8]}"
    logger.info("Starting MySQL container %s -> host:%s", name, host_port)

    container = client.containers.run(
        MYSQL_IMAGE,
        environment={
            "MYSQL_ROOT_PASSWORD": MYSQL_ROOT_PASSWORD,
            "MYSQL_DATABASE": MYSQL_DATABASE,
            "MYSQL_USER": MYSQL_USER,
            "MYSQL_PASSWORD": MYSQL_PASSWORD,
        },
        ports={"3306/tcp": (MYSQL_HOST, host_port)},
        detach=True,
        remove=False,  # keep container for debugging; caller may remove
        name=name
    )
    return container


def wait_for_mysql(host: str = MYSQL_HOST, port: int = MYSQL_HOST_PORT, retries: int = 60, delay: float = 2.0):
    """Wait until MySQL accepts connections as root. Raises on timeout."""
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            conn = pymysql.connect(
                host=host,
                port=port,
                user="root",
                password=MYSQL_ROOT_PASSWORD,
                database=MYSQL_DATABASE,
                connect_timeout=5
            )
            conn.close()
            logger.info("MySQL ready after %d attempts", attempt + 1)
            return
        except Exception as e:
            last_exc = e
            logger.debug("MySQL not ready (attempt %d): %s", attempt + 1, e)
            time.sleep(delay)
    raise RuntimeError(f"MySQL failed to become ready: {last_exc!r}")


def start_minio_container(name_prefix: str = "minio_test_", host_port: int | None = None, console_port: int | None = None, keep: bool = False):
    """Start a MinIO container for tests. Returns docker.Container."""
    client = _client()
    host_port = host_port or MINIO_HOST_PORT
    console_port = console_port or MINIO_CONSOLE_PORT
    name = f"{name_prefix}{uuid.uuid4().hex[:8]}"
    logger.info("Starting MinIO container %s -> host:%s console:%s", name, host_port, console_port)

    container = client.containers.run(
        MINIO_IMAGE,
        command=["server", "/data", "--console-address", f":{console_port}"],
        environment={
            "MINIO_ROOT_USER": MINIO_ROOT_USER,
            "MINIO_ROOT_PASSWORD": MINIO_ROOT_PASSWORD,
        },
        ports={
            "9000/tcp": (MINIO_HOST, host_port),
            "9001/tcp": (MINIO_HOST, console_port)
        },
        detach=True,
        remove=False,
        name=name
    )
    return container


def wait_for_minio(endpoint: Optional[str] = None, retries: int = 60, delay: float = 1.0):
    """Wait until MinIO responds to list_buckets. Raises on timeout."""
    endpoint = endpoint or f"http://{MINIO_HOST}:{MINIO_HOST_PORT}"
    session = boto3.session.Session()
    s3 = session.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=MINIO_ROOT_USER,
        aws_secret_access_key=MINIO_ROOT_PASSWORD,
        config=boto3.session.Config(signature_version="s3v4"),
        verify=False
    )
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            s3.list_buckets()
            logger.info("MinIO ready after %d attempts", attempt + 1)
            return
        except Exception as e:
            last_exc = e
            logger.debug("MinIO not ready (attempt %d): %s", attempt + 1, e)
            time.sleep(delay)
    raise RuntimeError(f"MinIO failed to become ready: {last_exc!r}")


def create_minio_bucket(endpoint: Optional[str] = None, bucket: Optional[str] = None, region: Optional[str] = None):
    """Create bucket on MinIO (idempotent)."""
    endpoint = endpoint or f"http://{MINIO_HOST}:{MINIO_HOST_PORT}"
    bucket = bucket or MINIO_BUCKET
    session = boto3.session.Session()
    s3 = session.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=MINIO_ROOT_USER,
        aws_secret_access_key=MINIO_ROOT_PASSWORD,
        config=boto3.session.Config(signature_version="s3v4"),
        region_name=region or "us-east-1",
        verify=False
    )
    try:
        s3.create_bucket(Bucket=bucket)
        logger.info("Created bucket %s", bucket)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            logger.info("Bucket %s already exists", bucket)
        else:
            raise


def cleanup_test_containers(name_prefixes: List[str] = ("mysql_test_", "minio_test_")):
    """Stop and remove containers whose names start with prefixes in the running/all list."""
    client = _client()
    # include stopped containers to ensure removal
    for c in client.containers.list(all=True):
        for p in name_prefixes:
            if c.name.startswith(p):
                logger.info("Stopping and removing container %s", c.name)
                try:
                    c.stop(timeout=5)
                except Exception:
                    pass
                try:
                    c.remove(force=True)
                except Exception:
                    pass
                break