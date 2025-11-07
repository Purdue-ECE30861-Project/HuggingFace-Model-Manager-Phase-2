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


from src.external_contracts import ArtifactQuery, ArtifactMetadata, Artifact, ArtifactID, ArtifactType, ArtifactName, ArtifactRegEx, ArtifactData
from data_store.s3_manager import S3BucketManager
from data_store.database import SQLMetadataAccessor


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
    TOO_MANY_ARTIFACTS = 413

class GetArtifactEnum(Enum):
    SUCCESS = 200
    DOES_NOT_EXIST = 404

class RegisterArtifactEnum(Enum):
    SUCCESS = 200
    ALREADY_EXISTS = 409
    DISQUALIFIED = 424

class ArtifactAccessor:
    def __init__(self, amdb_url: str,
                 s3_url: str = None,
                 download_timeout: int = 30,
                 max_artifact_size_gb: int = 1):
        self.db: SQLMetadataAccessor = SQLMetadataAccessor(db_url=amdb_url)
        self.s3_manager = S3BucketManager(endpoint_url=s3_url)
        self.downloader = ArtifactDownloader(
            timeout=download_timeout,
            max_size_gb=max_artifact_size_gb
        )

    @validate_call
    def get_artifacts(self, body: ArtifactQuery, offset: str) -> tuple[GetArtifactsEnum, List[ArtifactMetadata]]:
        result = self.db.get_by_query(body, offset)

        if not result:
            return GetArtifactsEnum.TOO_MANY_ARTIFACTS, []
        return GetArtifactsEnum.SUCCESS, result


    @validate_call
    def get_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[GetArtifactEnum, Artifact | None]:
        result = self.db.get_by_id(id, artifact_type)

        if not result:
            return GetArtifactEnum.DOES_NOT_EXIST, result
        return GetArtifactEnum.SUCCESS, result


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
        pass

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
