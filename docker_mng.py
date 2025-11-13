import os
import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]  # adjust if layout differs
sys.path.append(str(ROOT_DIR))
from pathlib import Path

# Import from existing script (assumed same directory or adjust path accordingly)
import docker
from tests.integration_tests.helpers.docker_init import (
    start_mysql_container,
    wait_for_mysql,
    start_minio_container,
    wait_for_minio,
    create_minio_bucket,
    cleanup_test_containers,
    MYSQL_HOST, MYSQL_HOST_PORT, MYSQL_ROOT_PASSWORD, MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD,
    MINIO_HOST, MINIO_HOST_PORT, MINIO_ROOT_USER, MINIO_ROOT_PASSWORD, MINIO_BUCKET
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def set_env_variables():
    """Set global environment variables as per GlobalConfig and S3Config."""
    os.environ["DB_URL"] = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_HOST_PORT}/{MYSQL_DATABASE}"
    os.environ["S3_URL"] = f"http://{MINIO_HOST}:{MINIO_HOST_PORT}"
    os.environ["S3_ACCESS_KEY_ID"] = MINIO_ROOT_USER
    os.environ["S3_SECRET_ACCESS_KEY"] = MINIO_ROOT_PASSWORD
    os.environ["S3_BUCKET_NAME"] = MINIO_BUCKET
    os.environ["S3_DATA_PREFIX"] = ""
    os.environ["S3_REGION_NAME"] = "us-east-1"
    os.environ["RATER_TASK_MANAGER_WORKERS"] = "1"
    os.environ["RATER_PROCESSES"] = "1"
    os.environ["INGEST_SCORE_THRESHOLD"] = "0.5"

    logger.info("Environment variables set for database and S3 configuration.")


def start_all():
    """Start both MySQL and MinIO containers."""
    logger.info("Starting all containers...")
    mysql_container = start_mysql_container()
    wait_for_mysql()
    minio_container = start_minio_container()
    wait_for_minio()
    create_minio_bucket()
    logger.info("All containers started successfully.")
    return mysql_container, minio_container


def stop_all():
    """Stop and remove all test containers."""
    logger.info("Stopping all test containers...")
    cleanup_test_containers()
    logger.info("All test containers stopped and removed.")


def start_service(service: str):
    """Start individual service (mysql or s3)."""
    if service == "mysql":
        container = start_mysql_container()
        wait_for_mysql()
        logger.info("MySQL container started.")
    elif service == "s3":
        container = start_minio_container()
        wait_for_minio()
        create_minio_bucket()
        logger.info("MinIO container started.")
    else:
        raise ValueError("Unknown service: must be 'mysql' or 's3'")
    return container


def stop_service(service: str):
    """Stop only specific service containers."""
    prefix = f"{service}_test_" if service in ("mysql", "minio", "s3") else None
    if not prefix:
        raise ValueError("Unknown service: must be 'mysql' or 's3'")
    cleanup_test_containers([prefix])
    logger.info("Stopped all containers matching prefix %s", prefix)


def main():
    parser = argparse.ArgumentParser(description="Manage MySQL and MinIO Docker containers for testing.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # start-all
    subparsers.add_parser("start-all", help="Start both MySQL and MinIO containers.")
    # stop-all
    subparsers.add_parser("stop-all", help="Stop all MySQL and MinIO containers.")
    # start one
    start_parser = subparsers.add_parser("start", help="Start a specific service (mysql or s3).")
    start_parser.add_argument("service", choices=["mysql", "s3"], help="Service to start")
    # stop one
    stop_parser = subparsers.add_parser("stop", help="Stop a specific service (mysql or s3).")
    stop_parser.add_argument("service", choices=["mysql", "s3"], help="Service to stop")
    # set-env
    subparsers.add_parser("set-env", help="Set environment variables globally for configuration.")

    args = parser.parse_args()

    if args.command == "start-all":
        set_env_variables()
        start_all()
    elif args.command == "stop-all":
        stop_all()
    elif args.command == "start":
        set_env_variables()
        start_service(args.service)
    elif args.command == "stop":
        stop_service(args.service)
    elif args.command == "set-env":
        set_env_variables()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()