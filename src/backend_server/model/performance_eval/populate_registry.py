import argparse
import time
import shutil
import random
from pathlib import Path
from tempfile import TemporaryDirectory

class PerformanceTestPopulator:
    """
    Populates registry for performance testing.
    
    - 1 real model (Tiny-LLM): Downloaded from HuggingFace, uploaded to S3
    - 499 mock models: Metadata only in database (no files)
    """
    
    TINY_LLM_URL = "https://huggingface.co/arnir0/Tiny-LLM"
    NUM_MOCKS = 499
    
    def __init__(self, db, s3_manager, verbose: bool = True):
        """
        Initialize populator.
        
        Args:
            db: Database manager instance
            s3_manager: S3 bucket manager for file storage
            verbose: Print progress messages
        """
        self.db = db
        self.s3_manager = s3_manager
        self.verbose = verbose
        
        # Lazy import to avoid circular dependency
        from src.backend_server.model.data_store.downloaders.hf_downloader import HFArtifactDownloader
        self.downloader = HFArtifactDownloader()
        
        self.tiny_llm_id = None
        self.mock_count = 0
        
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"Performance Test Registry Populator")
            print(f"{'='*70}")
            print(f"Target: 1 real model (Tiny-LLM) + {self.NUM_MOCKS} mocks")
            print(f"Storage: S3 (Tiny-LLM only) + Database (all metadata)")
            print(f"{'='*70}\n")
    
    def _log(self, message: str):
        """Log message if verbose"""
        if self.verbose:
            print(message)
    
    def _ingest_tiny_llm(self) -> bool:
        """
        Ingest Tiny-LLM: Download from HuggingFace, upload to S3, store in DB.
        
        Returns:
            True if successful, False otherwise
        """
        # Lazy imports to avoid circular dependency
        from src.backend_server.model.artifact_accessor.register_direct import register_database
        from src.backend_server.model.artifact_accessor.name_extraction import generate_unique_id, extract_name_from_url
        from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactData, ArtifactType
        
        self._log("Ingesting Tiny-LLM (real model)")
        self._log(f"  URL: {self.TINY_LLM_URL}")
        
        try:
            artifact_id = generate_unique_id(self.TINY_LLM_URL)
            self.tiny_llm_id = artifact_id
            
            with TemporaryDirectory() as tempdir:
                temp_path = Path(tempdir)
                
                # 1. Download from HuggingFace
                self._log(f"Downloading...")
                start_time = time.time()
                size = self.downloader.download_artifact(
                    self.TINY_LLM_URL, 
                    ArtifactType.model, 
                    temp_path
                )
                download_time = time.time() - start_time
                self._log(f"Downloaded {size:.2f}MB in {download_time:.1f}s")
                
                # 2. Create artifact metadata
                artifact_data = ArtifactData(
                    url=self.TINY_LLM_URL,
                    download_url=self.TINY_LLM_URL
                )
                
                artifact = Artifact(
                    metadata=ArtifactMetadata(
                        name=extract_name_from_url(self.TINY_LLM_URL, ArtifactType.model),
                        id=artifact_id,
                        type=ArtifactType.model
                    ),
                    data=artifact_data
                )
                
                # 3. Store in database
                self._log(f"Storing in database...")
                success = register_database(
                    self.db,
                    artifact,
                    temp_path,
                    size
                )
                
                if not success:
                    self._log(f"Database registration failed")
                    return False
                
                self._log(f"Stored in database")
                
                # 4. Archive and upload to S3
                self._log(f"  Uploading to S3...")
                archive_path = shutil.make_archive(
                    str(temp_path.resolve()), 
                    "xztar", 
                    root_dir=temp_path
                )
                self.s3_manager.s3_artifact_upload(artifact_id, Path(archive_path))
                self._log(f"Uploaded to S3")
            
            self._log(f"\nTiny-LLM ID: {artifact_id}")
            self._log(f"  Use this ID in load_generator.py\n")
            
            return True
                
        except Exception as e:
            self._log(f"  ✗ Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _create_mock_model(self, index: int) -> bool:
        """
        Create a mock model entry (metadata only, no file).
        
        Args:
            index: Mock model index (1-499)
        
        Returns:
            True if successful
        """
        # Lazy imports to avoid circular dependency
        from src.backend_server.model.artifact_accessor.name_extraction import generate_unique_id
        from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactData, ArtifactType
        
        try:
            # Generate realistic metadata
            prefixes = ["bert", "gpt", "roberta", "distil", "t5", "bart", "electra", "xlnet"]
            suffixes = ["base", "small", "tiny", "mini", "micro", "nano"]
            tasks = ["qa", "classification", "generation", "translation", "summarization", "ner"]
            
            prefix = random.choice(prefixes)
            suffix = random.choice(suffixes)
            task = random.choice(tasks)
            
            name = f"mock-{prefix}-{suffix}-{task}-{index:04d}"
            org = random.choice(["mock-org", "test-team", "research-lab", "ai-models", "ml-community"])
            url = f"https://huggingface.co/{org}/{name}"
            
            artifact_id = generate_unique_id(url)
            
            # Create artifact (metadata only)
            artifact = Artifact(
                metadata=ArtifactMetadata(
                    name=name,
                    id=artifact_id,
                    type=ArtifactType.model
                ),
                data=ArtifactData(
                    url=url,
                    download_url=""  # Empty - no file in S3
                )
            )
            
            # Insert into database (metadata only, no file)
            # Using db_artifact_ingest with minimal data
            success = self.db.router_artifact.db_artifact_ingest(
                artifact,
                size=random.uniform(10, 150),  # Random realistic size
                readme=f"# {name}\n\nMock model for performance testing."
            )
            
            if success:
                self.mock_count += 1
                return True
            
            return False
            
        except Exception as e:
            # Silent failure for mocks (not critical)
            return False
    
    def populate(self) -> dict:
        """
        Populate registry with Tiny-LLM + 499 mocks.
        
        Returns:
            dict with results
        """
        self._log("="*70)
        self._log("STARTING POPULATION")
        self._log("="*70)
        
        start_time = time.time()
        
        # Step 1: Ingest Tiny-LLM (real model with S3)
        self._log("Step 1: Ingesting Tiny-LLM")
        tiny_llm_success = self._ingest_tiny_llm()
        
        if not tiny_llm_success:
            self._log("\nFailed to ingest Tiny-LLM - aborting")
            return {
                "success": False,
                "tiny_llm": False,
                "mocks": 0,
                "total_time": time.time() - start_time
            }
        
        # Step 2: Create 499 mock entries
        self._log(f"Step 2: Creating {self.NUM_MOCKS} mock database entries")
        for i in range(1, self.NUM_MOCKS + 1):
            self._create_mock_model(i)
            
            if i % 100 == 0:
                self._log(f"  Progress: {i}/{self.NUM_MOCKS} mocks created")
        
        total_time = time.time() - start_time
        
        # Summary
        self._log("\n" + "="*70)
        self._log("POPULATION COMPLETE")
        self._log("="*70)
        self._log(f"Tiny-LLM: Ingested and uploaded to S3")
        self._log(f"Mock models: {self.mock_count} created")
        self._log(f"Total models: {1 + self.mock_count}")
        self._log(f"Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
        self._log("="*70)
        
        return {
            "success": True,
            "tiny_llm": tiny_llm_success,
            "tiny_llm_id": self.tiny_llm_id,
            "mocks": self.mock_count,
            "total_models": 1 + self.mock_count,
            "total_time": total_time
        }
    
    def verify(self) -> bool:
        """
        Verify registry is ready for performance testing.
        
        Returns:
            True if ready
        """
        # Lazy imports to avoid circular dependency
        from src.backend_server.model.artifact_accessor.name_extraction import generate_unique_id
        from src.contracts.artifact_contracts import ArtifactType
        
        self._log("\n" + "="*70)
        self._log("REGISTRY VERIFICATION")
        self._log("="*70)
        
        # Check Tiny-LLM exists
        tiny_llm_id = generate_unique_id(self.TINY_LLM_URL)
        tiny_llm_exists = self.db.router_artifact.db_artifact_exists(
            tiny_llm_id, 
            ArtifactType.model
        )
        
        self._log(f"Tiny-LLM present: {'Yes' if tiny_llm_exists else 'No'}")
        if tiny_llm_exists:
            self._log(f"  ID: {tiny_llm_id}")
            self._log(f"  Use this in load_generator.py")
        
        # Check total count
        try:
            query_result = self.db.router_artifact.db_artifact_get_query(
                {"name": "*", "types": [ArtifactType.model]},
                offset="0"
            )
            total_count = len(query_result) if query_result else 0
        except:
            total_count = 0
        
        self._log(f"Total models: {total_count}")
        self._log(f"Target: 500 models")
        
        ready = tiny_llm_exists and total_count >= 500
        
        if ready:
            self._log("\nRegistry is READY for performance testing!")
        else:
            self._log("\nRegistry NOT ready")
            if not tiny_llm_exists:
                self._log("  Missing: Tiny-LLM")
            if total_count < 500:
                self._log(f"  Missing: {500 - total_count} models")
        
        self._log("="*70 + "\n")
        
        return ready
    
    def cleanup(self) -> dict:
        """
        Remove all test data from database and S3.
        
        Returns:
            dict with cleanup results
        """
        # Lazy imports to avoid circular dependency
        from src.backend_server.model.artifact_accessor.name_extraction import generate_unique_id
        from src.contracts.artifact_contracts import ArtifactType
        
        self._log("\n" + "="*70)
        self._log("CLEANUP: Removing all test data")
        self._log("="*70)
        
        deleted_db = 0
        deleted_s3 = 0
        
        try:
            # Delete all mock models (name starts with "mock-")
            self._log("\nDeleting mock entries from database...")
            query_result = self.db.router_artifact.db_artifact_get_query(
                {"name": "mock-*", "types": [ArtifactType.model]},
                offset="0"
            )
            
            if query_result:
                for artifact in query_result:
                    try:
                        self.db.router_artifact.db_artifact_delete(
                            artifact.id, 
                            ArtifactType.model
                        )
                        deleted_db += 1
                        
                        if deleted_db % 100 == 0:
                            self._log(f"  Deleted {deleted_db} mock entries")
                    except:
                        pass
            
            # Delete Tiny-LLM from database and S3
            self._log("\nDeleting Tiny-LLM...")
            tiny_llm_id = generate_unique_id(self.TINY_LLM_URL)
            
            try:
                # Delete from database
                self.db.router_artifact.db_artifact_delete(
                    tiny_llm_id, 
                    ArtifactType.model
                )
                deleted_db += 1
                self._log(f"  ✓ Deleted from database")
                
                # Delete from S3
                self.s3_manager.s3_artifact_delete(tiny_llm_id)
                deleted_s3 += 1
                self._log(f"  ✓ Deleted from S3")
                
            except Exception as e:
                self._log(f"  ✗ Error: {e}")
            
        except Exception as e:
            self._log(f"\n✗ Cleanup error: {e}")
        
        # Summary
        self._log("\n" + "="*70)
        self._log("CLEANUP COMPLETE")
        self._log("="*70)
        self._log(f"Database entries deleted: {deleted_db}")
        self._log(f"S3 files deleted: {deleted_s3}")
        self._log("="*70)
        
        return {
            "deleted_db": deleted_db,
            "deleted_s3": deleted_s3
        }


def main():
    parser = argparse.ArgumentParser(
        description="Populate registry for performance testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Populates registry with:
  - 1 real model (Tiny-LLM) stored in S3
  - 499 mock models (metadata only)

Examples:
  python populate_registry.py           # Populate registry
  python populate_registry.py --verify  # Check if ready
  python populate_registry.py --cleanup # Remove all test data
        """
    )
    
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify registry is ready for performance testing"
    )
    
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove all test data (database + S3)"
    )
    
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minimal output"
    )
    
    args = parser.parse_args()
    
    verbose = not args.quiet
    
    # Initialize database and S3 connections (same as global_state but without circular import)
    try:
        from sqlalchemy import create_engine
        from sqlmodel import SQLModel
        from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBManager
        from src.backend_server.model.data_store.s3_manager import S3BucketManager
        
        # Import GlobalConfig directly (not from global_state)
        import sys
        import os
        from pydantic import BaseModel
        from dotenv import load_dotenv
        import boto3
        from botocore.exceptions import ClientError
        
        # Read environment config (same as GlobalConfig.read_env())
        load_dotenv()
        is_deploy = os.environ.get("DEVEL_TEST", "false").lower() != "true"
        
        # Database URL
        db_url = os.environ.get(
            "DB_URL", "mysql+pymysql://test_user:newpassword@localhost:3307/test_db"
        )
        
        if is_deploy:
            secret_manager = boto3.client("secretsmanager")
            db_location = os.environ.get("PROD_DB_LOCATION", "localhost:3307/test_db")
            db_secrets_location = os.environ.get("DB_SECRET", "461/db_passwords")
            try:
                db_passwds = secret_manager.get_secret_value(SecretId=db_secrets_location)
                db_url = f"mysql+pymysql://{db_passwds['ARTIFACT_DB_USER']}:{db_passwds['ARTIFACT_DB_PASSWORD']}@{db_location}"
            except ClientError as e:
                print(f"Error reading DB secrets: {e}")
                raise e
        
        # Create DB engine and initialize
        mysql_engine = create_engine(db_url)
        SQLModel.metadata.create_all(mysql_engine)
        db = DBManager(mysql_engine)
        
        # S3 configuration
        s3_url = f'http://{os.environ.get("S3_URL", "127.0.0.1")}:{os.environ.get("S3_HOST_PORT", "9000")}'
        s3_access_key_id = os.environ.get("S3_ACCESS_KEY_ID", "minio_access_key_123")
        s3_secret_access_key = os.environ.get("S3_SECRET_ACCESS_KEY", "minio_secret_key_password_456")
        s3_bucket_name = os.environ.get("S3_BUCKET_NAME", "hfmm-artifact-storage")
        s3_data_prefix = os.environ.get("S3_DATA_PREFIX", "artifact")
        
        # Initialize S3 manager
        s3_manager = S3BucketManager(
            s3_url,
            is_deploy,
            s3_access_key_id,
            s3_secret_access_key,
            s3_bucket_name,
            s3_data_prefix
        )
        
    except Exception as e:
        print(f"Error: Could not initialize dependencies: {e}")
        print("Make sure you're running from the project root with venv activated.")
        import traceback
        traceback.print_exc()
        return 1
    
    # Create populator
    populator = PerformanceTestPopulator(db, s3_manager, verbose=verbose)
    
    # Cleanup mode
    if args.cleanup:
        result = populator.cleanup()
        return 0
    
    # Verify mode
    if args.verify:
        ready = populator.verify()
        return 0 if ready else 1
    
    # Population mode (default)
    try:
        result = populator.populate()
        
        if result["success"]:
            print(f"\nSuccess! Registry populated with {result['total_models']} models")
            print(f"Tiny-LLM ID: {result['tiny_llm_id']}")
            print(f"\nNext: Run load_generator.py with this ID")
            return 0
        else:
            print(f"\nPopulation failed")
            return 1
        
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        return 1
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
