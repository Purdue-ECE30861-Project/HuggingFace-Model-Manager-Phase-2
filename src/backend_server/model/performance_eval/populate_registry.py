import argparse
import time
import shutil
import random
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
import logging

# Setup project path
project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.backend_server.model.downloaders.hf_downloader import HFArtifactDownloader
from src.backend_server.model.artifact_accessor.register_direct import register_database
from src.backend_server.model.artifact_accessor.name_extraction import generate_unique_id, extract_name_from_url
from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactData, ArtifactType

# Setup logging
logger = logging.getLogger(__name__)


def initialize_dependencies():
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel
    from dotenv import load_dotenv
    import boto3
    from botocore.exceptions import ClientError
    
    logger.debug("Loading environment configuration")
    load_dotenv()
    
    is_deploy = os.environ.get("DEVEL_TEST", "false").lower() != "true"
    
    db_url = os.environ.get(
        "DB_URL",
        "mysql+pymysql://test_user:newpassword@localhost:3307/test_db"
    )
    
    if is_deploy:
        logger.debug("Production mode - fetching credentials from AWS Secrets Manager")
        secret_manager = boto3.client("secretsmanager")
        db_location = os.environ.get("PROD_DB_LOCATION", "localhost:3307/test_db")
        db_secrets_location = os.environ.get("DB_SECRET", "461/db_passwords")
        
        try:
            response = secret_manager.get_secret_value(SecretId=db_secrets_location)
            import json
            db_passwds = json.loads(response['SecretString'])
            db_url = f"mysql+pymysql://{db_passwds['ARTIFACT_DB_USER']}:{db_passwds['ARTIFACT_DB_PASSWORD']}@{db_location}"
            logger.debug("Successfully retrieved database credentials")
        except ClientError as e:
            raise Exception(f"Failed to get DB credentials: {e}")
    
    # Create DB engine
    logger.debug("Creating database engine")
    mysql_engine = create_engine(db_url)
    SQLModel.metadata.create_all(mysql_engine)
    
    # Import DBManager here (after engine is created)
    from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBManager
    db = DBManager(mysql_engine)
    logger.info("Database connection established")
    
    # S3 configuration
    s3_url = f'http://{os.environ.get("S3_URL", "127.0.0.1")}:{os.environ.get("S3_HOST_PORT", "9000")}'
    s3_access_key_id = os.environ.get("S3_ACCESS_KEY_ID", "minio_access_key_123")
    s3_secret_access_key = os.environ.get("S3_SECRET_ACCESS_KEY", "minio_secret_key_password_456")
    s3_bucket_name = os.environ.get("S3_BUCKET_NAME", "hfmm-artifact-storage")
    s3_data_prefix = os.environ.get("S3_DATA_PREFIX", "artifact")
    
    # Import and initialize S3 manager
    from src.backend_server.model.data_store.s3_manager import S3BucketManager
    s3_manager = S3BucketManager(
        s3_url,
        is_deploy,
        s3_access_key_id,
        s3_secret_access_key,
        s3_bucket_name,
        s3_data_prefix
    )
    logger.info("S3 connection established")
    
    return db, s3_manager


class Populator:
    """Populates registry with test data for performance evaluation."""
    
    TINY_LLM_URL = "https://huggingface.co/arnir0/Tiny-LLM"
    NUM_MOCKS = 499
    
    def __init__(self, db, s3_manager):
        self.db = db
        self.s3_manager = s3_manager
        self.tiny_llm_id = None
        self.mock_count = 0
    
    def get_artifact_id(self) -> Optional[str]:
        from src.backend_server.model.artifact_accessor.name_extraction import generate_unique_id
        artifact_id = generate_unique_id(self.TINY_LLM_URL)
        logger.debug(f"Generated artifact ID: {artifact_id}")
        return artifact_id
    
    def verify(self) -> bool:
        from src.backend_server.model.artifact_accessor.name_extraction import generate_unique_id
        from src.contracts.artifact_contracts import ArtifactType
        
        logger.info("="*70)
        logger.info("REGISTRY VERIFICATION")
        logger.info("="*70)
        
        # Check Tiny-LLM exists
        tiny_llm_id = generate_unique_id(self.TINY_LLM_URL)
        tiny_llm_exists = self.db.router_artifact.db_artifact_exists(
            tiny_llm_id,
            ArtifactType.model
        )
        
        logger.info(f"Tiny-LLM present: {'Yes' if tiny_llm_exists else 'No'}")
        if tiny_llm_exists:
            logger.info(f"  ID: {tiny_llm_id}")
            logger.info(f"  Use this in load_generator.py --artifact-id")
        
        # Check total count
        try:
            query_result = self.db.router_artifact.db_artifact_get_query(
                {"name": "*", "types": [ArtifactType.model]},
                offset="0"
            )
            total_count = len(query_result) if query_result else 0
            logger.debug(f"Query returned {total_count} models")
        except Exception as e:
            logger.warning(f"Failed to query models: {e}")
            total_count = 0
        
        logger.info(f"Total models: {total_count}")
        logger.info(f"Target: 500 models")
        
        ready = tiny_llm_exists and total_count >= 500
        
        if ready:
            logger.info("\nRegistry is READY for performance testing!")
        else:
            logger.warning("\nRegistry NOT ready")
            if not tiny_llm_exists:
                logger.warning("  Missing: Tiny-LLM")
            if total_count < 500:
                logger.warning(f"  Missing: {500 - total_count} models")
        
        logger.info("="*70)
        
        return ready
    
    def populate(self) -> dict:
        
        logger.info("="*70)
        logger.info("STARTING POPULATION")
        logger.info("="*70)
        
        start_time = time.time()
        
        # Download and ingest Tiny-LLM
        logger.info("\nStep 1: Ingesting Tiny-LLM")
        logger.info(f"  URL: {self.TINY_LLM_URL}")
        
        try:
            downloader = HFArtifactDownloader()
            artifact_id = generate_unique_id(self.TINY_LLM_URL)
            self.tiny_llm_id = artifact_id
            logger.debug(f"Artifact ID: {artifact_id}")
            
            with TemporaryDirectory() as tempdir:
                temp_path = Path(tempdir)
                logger.debug(f"Using temporary directory: {tempdir}")
                
                # Download from HuggingFace
                logger.info("  Downloading from HuggingFace...")
                dl_start = time.time()
                size = downloader.download_artifact(
                    self.TINY_LLM_URL,
                    ArtifactType.model,
                    temp_path
                )
                dl_time = time.time() - dl_start
                logger.info(f" Downloaded {size:.2f}MB in {dl_time:.1f}s")
                
                # Create artifact metadata
                artifact = Artifact(
                    metadata=ArtifactMetadata(
                        name=extract_name_from_url(self.TINY_LLM_URL, ArtifactType.model),
                        id=artifact_id,
                        type=ArtifactType.model
                    ),
                    data=ArtifactData(
                        url=self.TINY_LLM_URL,
                        download_url=self.TINY_LLM_URL
                    )
                )
                logger.debug(f"Created artifact metadata for {artifact.metadata.name}")
                
                # Register in database
                logger.info("  Storing in database...")
                success = register_database(self.db, artifact, temp_path, size)
                
                if not success:
                    raise Exception("Database registration failed")
                logger.info(" Stored in database")
                
                # Upload to S3
                logger.info(" Uploading to S3...")
                archive_path = shutil.make_archive(
                    str(temp_path.resolve()),
                    "xztar",
                    root_dir=temp_path
                )
                logger.debug(f"Created archive: {archive_path}")
                
                self.s3_manager.s3_artifact_upload(artifact_id, Path(archive_path))
                logger.info(" Uploaded to S3")
            
            logger.info(f"\n  Tiny-LLM ID: {artifact_id}")
            
        except Exception as e:
            logger.error(f"\nFailed to ingest Tiny-LLM: {e}")
            logger.debug("Traceback:", exc_info=True)
            return {
                "success": False,
                "tiny_llm": False,
                "mocks": 0,
                "total_time": time.time() - start_time
            }
        
        # Create mock models
        logger.info(f"\nStep 2: Creating {self.NUM_MOCKS} mock database entries")
        
        for i in range(1, self.NUM_MOCKS + 1):
            self._create_mock(i)
            if i % 100 == 0:
                logger.info(f"  Progress: {i}/{self.NUM_MOCKS} mocks created")
        
        total_time = time.time() - start_time
        
        # Summary
        logger.info("\n" + "="*70)
        logger.info("POPULATION COMPLETE")
        logger.info("="*70)
        logger.info(f"  Tiny-LLM: Ingested and uploaded to S3")
        logger.info(f"  Mock models: {self.mock_count} created")
        logger.info(f"  Total models: {1 + self.mock_count}")
        logger.info(f"  Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
        logger.info("="*70)
        
        return {
            "success": True,
            "tiny_llm_id": self.tiny_llm_id,
            "mocks": self.mock_count,
            "total_models": 1 + self.mock_count,
            "total_time": total_time
        }
    
    def _create_mock(self, index: int) -> bool:
        from src.backend_server.model.artifact_accessor.name_extraction import generate_unique_id
        from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactData, ArtifactType
        
        try:
            # Generate realistic metadata
            prefixes = ["bert", "gpt", "roberta", "distil", "t5", "bart", "electra", "xlnet"]
            suffixes = ["base", "small", "tiny", "mini", "micro", "nano"]
            tasks = ["qa", "classification", "generation", "translation", "summarization", "ner"]
            
            name = f"mock-{random.choice(prefixes)}-{random.choice(suffixes)}-{random.choice(tasks)}-{index:04d}"
            org = random.choice(["mock-org", "test-team", "research-lab", "ai-models", "ml-community"])
            url = f"https://huggingface.co/{org}/{name}"
            
            artifact = Artifact(
                metadata=ArtifactMetadata(
                    name=name,
                    id=generate_unique_id(url),
                    type=ArtifactType.model
                ),
                data=ArtifactData(url=url, download_url="")
            )
            
            success = self.db.router_artifact.db_artifact_ingest(
                artifact,
                size=random.uniform(10, 150),
                readme=f"# {name}\n\nMock model for performance testing."
            )
            
            if success:
                self.mock_count += 1
                logger.debug(f"Created mock model: {name}")
            else:
                logger.warning(f"Failed to create mock model: {name}")
            
            return success
            
        except Exception as e:
            logger.debug(f"Error creating mock {index}: {e}")
            return False
    
    def cleanup(self) -> dict:
        """
        Remove all test data from database and S3.
        
        Returns:
            Dict with cleanup results: {deleted_db, deleted_s3}
        """
        from src.backend_server.model.artifact_accessor.name_extraction import generate_unique_id
        from src.contracts.artifact_contracts import ArtifactType
        
        logger.info("\n" + "="*70)
        logger.info("CLEANUP: Removing all test data")
        logger.info("="*70)
        
        deleted_db = 0
        deleted_s3 = 0
        
        try:
            # Delete mocks
            logger.info("\nDeleting mock entries from database...")
            query_result = self.db.router_artifact.db_artifact_get_query(
                {"name": "mock-*", "types": [ArtifactType.model]},
                offset="0"
            )
            
            if query_result:
                logger.info(f"  Found {len(query_result)} mock entries to delete")
                for artifact in query_result:
                    try:
                        self.db.router_artifact.db_artifact_delete(
                            artifact.id,
                            ArtifactType.model
                        )
                        deleted_db += 1
                        if deleted_db % 100 == 0:
                            logger.info(f"  Deleted {deleted_db} mock entries")
                    except Exception as e:
                        logger.debug(f"Failed to delete mock {artifact.id}: {e}")
            else:
                logger.info("  No mock entries found")
            
            # Delete Tiny-LLM
            logger.info("\nDeleting Tiny-LLM...")
            tiny_llm_id = generate_unique_id(self.TINY_LLM_URL)
            
            try:
                self.db.router_artifact.db_artifact_delete(tiny_llm_id, ArtifactType.model)
                deleted_db += 1
                logger.info(" Deleted from database")
                
                self.s3_manager.s3_artifact_delete(tiny_llm_id)
                deleted_s3 += 1
                logger.info(" Deleted from S3")
            except Exception as e:
                logger.warning(f"  Error deleting Tiny-LLM: {e}")
        
        except Exception as e:
            logger.error(f"\nCleanup error: {e}")
            logger.debug("Traceback:", exc_info=True)
        
        # Summary
        logger.info("\n" + "="*70)
        logger.info("CLEANUP COMPLETE")
        logger.info("="*70)
        logger.info(f"  Database entries deleted: {deleted_db}")
        logger.info(f"  S3 files deleted: {deleted_s3}")
        logger.info("="*70)
        
        return {
            "deleted_db": deleted_db,
            "deleted_s3": deleted_s3
        }


def main():
    parser = argparse.ArgumentParser(
        description="Standalone registry population for performance testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 populate_registry.py --verify
    python3 populate_registry.py --populate
    python3 populate_registry.py --get-artifact-id
    python3 populate_registry.py --cleanup
    
    # Debug mode (verbose output)
    python3 populate_registry.py --populate --debug
    
    # Quiet mode (minimal output)
    python3 populate_registry.py --verify --quiet
        """
    )
    
    # Commands
    parser.add_argument("--verify", action="store_true", help="Verify registry status")
    parser.add_argument("--populate", action="store_true", help="Populate registry (5-15 min)")
    parser.add_argument("--cleanup", action="store_true", help="Remove all test data")
    parser.add_argument("--get-artifact-id", action="store_true", help="Get Tiny-LLM artifact ID")
    
    # Logging control
    parser.add_argument("--quiet", action="store_true", help="Minimal output (errors only)")
    parser.add_argument("--debug", action="store_true", help="Verbose debug output")
    
    args = parser.parse_args()
    
    # Configure logging
    if args.debug:
        log_level = logging.DEBUG
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    elif args.quiet:
        log_level = logging.ERROR
        log_format = '%(levelname)s - %(message)s'
    else:
        log_level = logging.INFO
        log_format = '%(message)s'
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Require at least one command
    if not (args.verify or args.populate or args.cleanup or args.get_artifact_id):
        parser.print_help()
        return 1
    
    # Initialize connections
    try:
        logger.info("Initializing database and S3 connections...")
        db, s3_manager = initialize_dependencies()
        logger.info("Connected successfully\n")
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        logger.debug("Traceback:", exc_info=True)
        return 1
    
    populator = Populator(db, s3_manager)
    
    # Execute command
    try:
        if args.get_artifact_id:
            artifact_id = populator.get_artifact_id()
            logger.info(f"\nTiny-LLM Artifact ID:")
            logger.info(f"  {artifact_id}")
            logger.info(f"\nUse in load_generator.py:")
            logger.info(f"  --artifact-id {artifact_id}")
            return 0
        
        elif args.verify:
            ready = populator.verify()
            return 0 if ready else 1
        
        elif args.cleanup:
            result = populator.cleanup()
            return 0
        
        elif args.populate:
            result = populator.populate()
            if result['success']:
                logger.info(f"\nSuccess! Registry populated with {result['total_models']} models")
                logger.info(f"\nTiny-LLM ID:")
                logger.info(f"  {result['tiny_llm_id']}")
                logger.info(f"\nNext steps:")
                logger.info(f"  python3 load_generator.py --artifact-id {result['tiny_llm_id']}")
                return 0
            else:
                logger.error("\nPopulation failed")
                return 1
    
    except KeyboardInterrupt:
        logger.warning("\n\nOperation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"\nError: {e}")
        logger.debug("Traceback:", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
