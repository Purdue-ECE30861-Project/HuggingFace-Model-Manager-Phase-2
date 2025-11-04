import botocore.session
import mysql.connector
from boto3 import Session as BOTO3Session
from mysql.connector import Error
from mysql.connector import pooling
import os
from datetime import datetime
import hashlib
import requests

import boto3
import json
import gzip
from typing import Dict, List, Optional
import logging
import re

from enum import Enum
from pydantic import validate_call
from src.model.external_contracts import ArtifactQuery, ArtifactMetadata, Artifact, ArtifactID, ArtifactType, ArtifactName, ArtifactRegEx, ArtifactData


class AccessorDatabase:
    def __init__(self, host: str, database: str, user: str, password: str, autocommit: bool, timeout: int):
        self.mysql_connection = mysql.connector.connect(
            host=host,
            database=database,
            user=user,
            password=password,
            autocommit=autocommit,
            connection_timeout=timeout
        )

    def _init_local_db(self):
        """
        KEEP THIS HERE FOR NOW. BUT THIS SHOULD BE IMPLEMENTED AS AN AUTOMATIC SETUP FOR WHATEVER INFRASTRUCTURE WE ARE RUNNING THE DATABASE ON!
        """
        cursor = self.mysql_connection.cursor()
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS artifact_metadata (
                    id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(500) NOT NULL,
                    version VARCHAR(100) NOT NULL,
                    type ENUM('model', 'dataset', 'code') NOT NULL,
                    metadata_json JSON,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_name (name),
                    INDEX idx_type (type)
                ) ENGINE=InnoDB
            ''')
            self.mysql_connection.commit()

        except Error as e:
            logging.error(f"Error creating table: {e}")
            self.mysql_connection.rollback()

        finally:
            cursor.close()
            
    def reset_database(self):
        raise NotImplementedError()

    def adb_artifact_store_metadata(self, metadata: ArtifactMetadata):
        cursor = self.mysql_connection.cursor()
        try:
            cursor.execute(
                """INSERT INTO artifact_metadata (id, name, version, type, metadata_json, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    version = VALUES(version),
                    type = VALUES(type),
                    metadata_json = VALUES(metadata_json),
                    last_updated = VALUES(last_updated)""",
                    (metadata.id, metadata.name, metadata.version, metadata.type.value, json.dumps(metadata.model_dump()), datetime.now())
            )
            self.mysql_connection.commit()

        except Error as e:
            logging.error(f"Error caching metadata: {e}")
            self.mysql_connection.rollback()
        finally:
            cursor.close()

    def adb_artifact_get_metadata_by_query(self, query: ArtifactQuery, offset: str) -> List[ArtifactMetadata]:
        cursor = self.mysql_connection.cursor()
        try:
            sql = "SELECT metadata_json FROM artifact_metadata WHERE name LIKE %s"
            params = [f"%{query.name}%"]

            if query.types:
                placeholders = ','.join(['%s'] * len(query.types))
                sql += f" AND type IN ({placeholders})"
                params.extend([t.value for t in query.types])

            if offset:
                sql += " And id > %s"
                params.append(offset)

            sql += " ORDER BY id LIMIT 100"

            cursor.execute(sql, params)

            results = []
            for row in cursor.fetchall():
                try:
                    metadata_dict = json.loads(row[0])
                    results.append(ArtifactMetadata(**metadata_dict))
                except (json.JSONDecodeError, ValueError) as e:
                    logging.warning(f"Skipping malformed metadata JSON: {e}")
                    continue

            return results

        except Error as e:
            logging.error(f"Error searching local metadata: {e}")
            raise
        finally:
            cursor.close()

    def adb_artifact_exists_in_mysql(self, artifact_id: str) -> bool:
        cursor = self.mysql_connection.cursor()
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM artifact_metadata WHERE id = %s", (artifact_id,)
            )
            count = cursor.fetchone()[0]
            return count > 0

        except Error as e:
            logging.error(f"Error checking artifact existence: {e}")
            return False
        finally:
            cursor.close()

    def adb_artifact_get_metadata_by_name(self, name: ArtifactName) -> tuple[GetArtifactEnum, list[ArtifactMetadata]]:
        try:
            cursor = self.mysql_connection.cursor()
            cursor.execute(
                "SELECT metadata_json FROM artifact_metadata WHERE name = %s",
                (name.name,)
            )

            results = []
            for row in cursor.fetchall():
                try:
                    metadata_dict = json.loads(row[0])
                    results.append(ArtifactMetadata(**metadata_dict))
                except (json.JSONDecodeError, ValueError) as e:
                    logging.warning(f"Skipping malformed metadata JSON: {e}")
                    continue

            cursor.close()
            return results

        except Exception as e:
            logging.error(f"Error in get_artifact_by_name: {e}")
            return GetArtifactEnum.INVALID_REQUEST, []
        
    def adb_artifact_get_metadata_by_regex(self):
        pass
        #cursor.execute("SELECT metadata_json FROM artifact_metadata WHERE name REGEXP %s", (regex_exp.regex,))
        
        
class ArtifactDownloader:
    def __init__(self, timeout: int = 30, max_size_gb: int = 1):
        self.timeout = timeout
        self.max_size_bytes = max_size_gb * 1024 * 1024 * 1024

    def download_artifact(self, url: str) -> Optional[bytes]:
        try:
            if not self._validate_url(url):
                return None

            # PLEASE NOTE: we must download the whole repository, is that what this is doing????
            # is this loading into memory? we must find a way to handle that
            response = requests.get(url, timeout=self.timeout, stream=True)
            response.raise_for_status()

            if not self._validate_content_size(response):
                return None
        
            return response.content
    
        except Exception as e:
            logging.error(f"Error downloading artifact from {url}: {e}")
            return None

    def compress_artifact(self, content: bytes) -> bytes:
        """Compress artifact content using gzip"""
        # this must be redesigned so the entire content does not have to be loaded in memory to zip
        try:
            return gzip.compress(content)
        except Exception as e:
            logging.error(f"Error compressing artifact: {e}")
            raise

    def download_and_compress(self, url: str) -> Optional[bytes]:
        """Download and compress artifact in one operation"""
        content = self.download_artifact(url)
        if content is None:
            return None
        
        return self.compress_artifact(content)

    def validate_url_format(self, url: str) -> bool:
        """Validate URL format without downloading"""
        return self._validate_url(url)

    def estimate_compressed_size(self, original_size: int, compression_ratio: float = 0.3) -> int:
        """Estimate compressed size based on original size and compression ratio"""
        return int(original_size * compression_ratio)

    def _validate_url(self, url: str) -> bool:
        """Internal method to validate URL format"""
        return url.startswith(('http://', 'https://'))

    def _validate_content_size(self, response: requests.Response) -> bool:
        """Internal method to validate content size from response headers"""
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) > self.max_size_bytes:
            logging.error(f"Artifact too large: {content_length} bytes (max: {self.max_size_bytes})")
            return False
        return True
    

class GetArtifactsEnum(Enum):
    SUCCESS = 200
    INVALID_REQUEST = 400
    TOO_MANY_ARTIFACTS = 413

class GetArtifactEnum(Enum):
    SUCCESS = 200
    INVALID_REQUEST = 400
    DOES_NOT_EXIST = 404

class RegisterArtifactEnum(Enum):
    SUCCESS = 200
    INVALID_REQUEST = 400
    ALREADY_EXISTS = 409
    DISQUALIFIED = 424

class ArtifactAccessor:
    def __init__(self, s3_url: str = None, 
                 host: str = "localhost", 
                 database: str = "artifacts", 
                 user: str = "root", 
                 password: str = "password", 
                 autocommit: bool = True, 
                 timeout: int = 10,
                 download_timeout: int = 30,
                 max_artifact_size_gb: int = 1):
        self.db = AccessorDatabase(
            host=host,
            database=database,
            user=user,
            password=password,
            autocommit=autocommit,
            timeout=timeout
        )
        self.s3_manager = S3BucketManager(
            endpoint_url=s3_url or 'http://localhost:9000'
        )
        self.downloader = ArtifactDownloader(
            timeout=download_timeout,
            max_size_gb=max_artifact_size_gb
        )
        
        # Initialize database tables
        self.db._init_local_db()

    @validate_call
    def get_artifacts(self, body: ArtifactQuery, offset: str) -> tuple[GetArtifactsEnum, List[ArtifactMetadata]]:
        try:
            results = self.db.adb_artifact_get_metadata_by_query(body, offset)
            return GetArtifactsEnum.SUCCESS, results
        except Exception as e:
            logging.error(f"Error in get_artifacts: {e}")
            return GetArtifactsEnum.INVALID_REQUEST, []


    @validate_call
    def get_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[GetArtifactEnum, Artifact]:
        try:
            # Check if metadata exists in database
            if not self.db.adb_artifact_exists_in_mysql(id.id):
                error_metadata = ArtifactMetadata(
                    id=id.id, name="not-found", version="0.0.0", type=artifact_type
                )
                not_found_data = ArtifactData(url="")
                not_found_artifact = Artifact(metadata=error_metadata, data=not_found_data)
                return GetArtifactEnum.DOES_NOT_EXIST, not_found_artifact

            # Get metadata from database using name lookup
            name = ArtifactName(name=id.id)  # Using ID as name for lookup
            results = self.db.adb_artifact_get_metadata_by_name(name)
            
            if not results:
                error_metadata = ArtifactMetadata(
                    id=id.id, name="not-found", version="0.0.0", type=artifact_type
                )
                not_found_data = ArtifactData(url="")
                not_found_artifact = Artifact(metadata=error_metadata, data=not_found_data)
                return GetArtifactEnum.DOES_NOT_EXIST, not_found_artifact

            metadata = results[0]  # Get first result
            data = ArtifactData(url=self.s3_manager.s3_generate_presigned_url(id.id))
            artifact = Artifact(metadata=metadata, data=data)
            return GetArtifactEnum.SUCCESS, artifact
        
        except Exception as e:
            logging.error(f"Error in get_artifact: {e}")
            error_metadata = ArtifactMetadata(
                id=id.id, 
                name="artifact-error", 
                version="0.0.0", 
                type=artifact_type
            )
            error_data = ArtifactData(url="")
            error_artifact = Artifact(metadata=error_metadata, data=error_data)
            return GetArtifactEnum.DOES_NOT_EXIST, error_artifact

    @validate_call
    def get_artifact_by_name(self, name: ArtifactName) -> tuple[GetArtifactEnum, list[ArtifactMetadata]]:
        try:
            results = self.db.adb_artifact_get_metadata_by_name(name)
            return GetArtifactEnum.SUCCESS, results
        except Exception as e:
            logging.error(f"Error in get_artifact_by_name: {e}")
            return GetArtifactEnum.INVALID_REQUEST, []

    @validate_call
    def get_artifact_by_regex(self, regex_exp: ArtifactRegEx) -> tuple[GetArtifactEnum, list[ArtifactMetadata]]:
        try:
            pattern = re.compile(regex_exp.regex)
            # Get all artifacts and filter by regex (since AccessorDatabase doesn't have regex method)
            query = ArtifactQuery(name="", types=None)  # Get all artifacts
            all_artifacts = self.db.adb_artifact_get_metadata_by_query(query, "")
            
            results = []
            for artifact in all_artifacts:
                if pattern.search(artifact.name):
                    results.append(artifact)
            
            return GetArtifactEnum.SUCCESS, results
        
        except Exception as e:
            logging.error(f"Error in get_artifact_by_regex: {e}")
            return GetArtifactEnum.INVALID_REQUEST, []

    @validate_call
    def register_artifact(self, artifact_type: ArtifactType, body: ArtifactData) -> tuple[RegisterArtifactEnum, Artifact]:
        try:
            artifact_id = self._generate_unique_id(body.url)

            # Check if artifact already exists
            if self.db.adb_artifact_exists_in_mysql(artifact_id):
                # Get existing metadata
                name = ArtifactName(name=artifact_id)
                existing_results = self.db.adb_artifact_get_metadata_by_name(name)
                
                if existing_results:
                    existing_metadata = existing_results[0]
                    existing_data = ArtifactData(url=self.s3_manager.s3_generate_presigned_url(artifact_id))
                    existing_artifact = Artifact(metadata=existing_metadata, data=existing_data)
                    return RegisterArtifactEnum.ALREADY_EXISTS, existing_artifact

            # Validate URL format first
            if not self.downloader.validate_url_format(body.url):
                disqualified_metadata = ArtifactMetadata(
                    id=artifact_id,
                    name="artifact-disqualified",
                    version="0.0.0",
                    type=artifact_type
                )
                disqualified_data = ArtifactData(url=body.url)
                disqualified_artifact = Artifact(metadata=disqualified_metadata, data=disqualified_data)
                return RegisterArtifactEnum.DISQUALIFIED, disqualified_artifact

            # Download artifact content using ArtifactDownloader
            artifact_content = self.downloader.download_artifact(body.url)
            if not artifact_content:
                disqualified_metadata = ArtifactMetadata(
                    id=artifact_id,
                    name="artifact-disqualified",
                    version="0.0.0",
                    type=artifact_type
                )
                disqualified_data = ArtifactData(url=body.url)
                disqualified_artifact = Artifact(metadata=disqualified_metadata, data=disqualified_data)
                return RegisterArtifactEnum.DISQUALIFIED, disqualified_artifact

            # Extract metadata
            metadata = self._extract_metadata(artifact_content, artifact_type, artifact_id)
        
            # Compress using ArtifactDownloader and upload to S3
            compressed_content = self.downloader.compress_artifact(artifact_content)
            self.s3_manager.s3_artifact_upload(artifact_id, compressed_content)
        
            # Store metadata in database
            self.db.adb_artifact_store_metadata(metadata)

            # Create response
            data = ArtifactData(url=self.s3_manager.s3_generate_presigned_url(artifact_id))
            artifact = Artifact(metadata=metadata, data=data)

            return RegisterArtifactEnum.SUCCESS, artifact
    
        except Exception as e:
            logging.error(f"Error in register_artifact: {e}")
            invalid_metadata = ArtifactMetadata(
                id=self._generate_unique_id(body.url),
                name="artifact-invalid-request",
                version="0.0.0",
                type=artifact_type
            )
            invalid_data = ArtifactData(url=body.url)
            invalid_artifact = Artifact(metadata=invalid_metadata, data=invalid_data)
            return RegisterArtifactEnum.INVALID_REQUEST, invalid_artifact

    @validate_call
    def update_artifact(self, artifact_type: ArtifactType, id: ArtifactID, body: Artifact) -> tuple[GetArtifactEnum, None]:
        raise NotImplementedError()

    @validate_call
    def delete_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[GetArtifactEnum, Artifact]:
        try:
            # Check if artifact exists
            if not self.db.adb_artifact_exists_in_mysql(id.id):
                error_metadata = ArtifactMetadata(
                    id=id.id, name="not-found", version="0.0.0", type=artifact_type
                )
                error_data = ArtifactData(url="")
                error_artifact = Artifact(metadata=error_metadata, data=error_data)
                return GetArtifactEnum.DOES_NOT_EXIST, error_artifact

            # Get metadata before deletion
            name = ArtifactName(name=id.id)
            results = self.db.adb_artifact_get_metadata_by_name(name)
        
            if results:
                metadata = results[0]
                # Delete from S3
                self.s3_manager.s3_artifact_delete(id.id)
                # Note: Database deletion would need a new method in AccessorDatabase
            
                data = ArtifactData(url="")  # Empty URL since deleted
                artifact = Artifact(metadata=metadata, data=data)
                return GetArtifactEnum.SUCCESS, artifact
        
            return GetArtifactEnum.DOES_NOT_EXIST, None
        
        except Exception as e:
            logging.error(f"Error in delete_artifact: {e}")
            return GetArtifactEnum.INVALID_REQUEST, None

    def _generate_unique_id(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _extract_metadata(self, artifact_content: bytes, artifact_type: ArtifactType, artifact_id: str) -> ArtifactMetadata:
        return ArtifactMetadata(
            id=artifact_id,
            name=f"artifact_{artifact_id}",
            version="1.0.0",
            type=artifact_type
        )

    # Remove the old _download_and_validate method - it's now handled by ArtifactDownloader

async def artifact_accessor() -> ArtifactAccessor:
    return ArtifactAccessor(s3_url="http://127.0.0.1:9000")
