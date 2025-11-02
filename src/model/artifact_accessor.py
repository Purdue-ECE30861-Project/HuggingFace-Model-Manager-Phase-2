import mysql.connector
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
    def __init__(self):
        self.mysql_connection = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            database=os.getenv('MYSQL_DATABASE', 'artifact_manager'),
            user=os.getenv('MYSQL_USER', 'root'),
            password=os.getenv('MYSQL_PASSWORD'),
            autocommit=False,
            connection_timeout=28800
        )
        self.metadata_cache: Dict[str, ArtifactMetadata] = {}

        self.s3_client = boto3.client('s3')
        self.bucket_name = 'hfmm-artifact-storage'

        self.data_prefix = 'artifacts/'

        self._init_local_db()


    def _init_local_db(self):
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


    @validate_call
    def get_artifacts(self, body: ArtifactQuery, offset: str) -> tuple[GetArtifactsEnum, List[ArtifactMetadata]]:
        try:
            local_results = self._search_mysql_metadata(body, offset)
            return GetArtifactsEnum.SUCCESS, local_results

        except Exception as e:
            logging.error(f"Error in get_artifacts: {e}")
            return GetArtifactsEnum.INVALID_REQUEST, []


    @validate_call
    def get_artifact(self, artifact_type: ArtifactType, id: ArtifactID) ->tuple[GetArtifactEnum, Artifact]:
        try:
            metadata = self._get_cached_metadata(id.id)
            if not metadata:
                error_metadata = ArtifactMetadata(
                    id=id.id, name="not-found", version="0.0.0", type=artifact_type
                )
                not_found_data = ArtifactData(url="")
                not_found_artifact = Artifact(metadata=error_metadata, data=not_found_data)
                return GetArtifactEnum.DOES_NOT_EXIST, not_found_artifact

            data = ArtifactData(url=self._generate_presigned_url(id.id))
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
            return GetArtifactEnum.SUCCESS, results
        
        except Exception as e:
            logging.error(f"Error in get_artifact_by_name: {e}")
            return GetArtifactEnum.INVALID_REQUEST, []
        

    @validate_call
    def get_artifact_by_regex(self, regex_exp: ArtifactRegEx) -> tuple[GetArtifactEnum, list[ArtifactMetadata]]:
        try:
            pattern = re.compile(regex_exp.regex)
            
            cursor = self.mysql_connection.cursor()
            cursor.execute("SELECT metadata_json FROM artifact_metadata WHERE name REGEXP %s", (regex_exp.regex,))

            results = []
            for row in cursor.fetchall():
                try:
                    metadata_dict = json.loads(row[0])
                    results.append(ArtifactMetadata(**metadata_dict))
                except (json.JSONDecodeError, ValueError) as e:
                    logging.warning(f"Skipping malformed metadata JSON: {e}")
                    continue
            
            cursor.close()
            return GetArtifactEnum.SUCCESS, results
        
        except Exception as e:
            logging.error(f"Error in get_artifact_by_regex: {e}")
            return GetArtifactEnum.INVALID_REQUEST, []
        

    @validate_call
    def register_artifact(self, artifact_type: ArtifactType, body: ArtifactData) -> tuple[RegisterArtifactEnum, Artifact]:
        try:
            artifact_id = self._generate_unique_id(body.url)

            if self._artifact_exists_in_mysql(artifact_id):
                existing_metadata = self._get_cached_metadata(artifact_id)
                if existing_metadata:
                    existing_data = ArtifactData(url=self._generate_presigned_url(artifact_id))
                    existing_artifact = Artifact(metadata=existing_metadata, data=existing_data)
                    return RegisterArtifactEnum.ALREADY_EXISTS, existing_artifact
            
            artifact_content = self._download_and_validate(body.url)
            if not artifact_content:
                disqualified_metadata = ArtifactMetadata(
                    id=artifact_id,
                    name="artifact-disqualified",
                    version="0.0.0",
                    type=artifact_type
                )
                disqualified_data = ArtifactData(url=body.url)  # Keep original URL
                disqualified_artifact = Artifact(metadata=disqualified_metadata, data=disqualified_data)
                return RegisterArtifactEnum.DISQUALIFIED, disqualified_artifact
            
            # extract metadata before storing
            metadata = self._extract_metadata(artifact_content, artifact_type, artifact_id)
            # compress before S3 upload
            compressed_content = gzip.compress(artifact_content)
            # upload data and metadata to S3
            self._upload_artifact_to_s3(artifact_id, compressed_content)
            self._cache_metadata(metadata)

            data = ArtifactData(url=self._generate_presigned_url(artifact_id))
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
        raise NotImplementedError()
    

    def _generate_presigned_url(self, artifact_id: str) -> str:
        """Generate presigned URL for direct client download (no Lightsail transfer)"""
        return self.s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket_name, 'Key': f"{self.data_prefix}{artifact_id}"},
            ExpiresIn=3600  # 1 hour
        )
    

    def _cache_metadata(self, metadata: ArtifactMetadata):
        """Cache metadata locally and in-memory"""
        # In-memory cache for speed
        self.metadata_cache[metadata.id] = metadata

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


    def _search_mysql_metadata(self, query: ArtifactQuery, offset: str) -> List[ArtifactMetadata]:
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
            return []
        finally:
            cursor.close()


    def _get_cached_metadata(self, artifact_id: str) -> Optional[ArtifactMetadata]:
        if artifact_id in self.metadata_cache:
            return self.metadata_cache[artifact_id]
        
        cursor = self.mysql_connection.cursor()
        try:
            cursor.execute(
                "SELECT metadata_json FROM artifact_metadata WHERE id = %s",
                (artifact_id,)
            )
            row = cursor.fetchone()
            if row:
                try:
                    metadata_dict = json.loads(row[0])
                    metadata = ArtifactMetadata(**metadata_dict)
                    self.metadata_cache[artifact_id] = metadata
                    return metadata
                except (json.JSONDecodeError, ValueError) as json_error:
                    logging.warning(f"Malformed metadata JSON for artifact {artifact_id}: {json_error}")
                    return None
            return None
        
        except Error as e:
            logging.error(f"Error getting cached metadata: {e}")
            return None
        finally:
            cursor.close()


    def _generate_unique_id(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()


    def _artifact_exists_in_mysql(self, artifact_id: str) -> bool:
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


    def _download_and_validate(self, url: str) -> Optional[bytes]:
        try:
            if not url.startswith(('http://','https://')):
                return None
            
            response = requests.get(url,
                                    timeout=30,
                                    stream= True)
            response.raise_for_status()

            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > 1024 * 1024 * 1024:  # 1 GB limit
                logging.error(f"Artifact too large : {content_length} bytes")
                return None
            
            return response.content
        
        except Exception as e:
            logging.error(f"Error downloading artifact from {url}: {e}")
            return None
        

    def _extract_metadata(self, artifact_content: bytes, artifact_type: ArtifactType, artifact_id: str) -> ArtifactMetadata:
        return ArtifactMetadata(
            # currently hardcoded limited implementation want to check exactly what this needs to contain
            id=artifact_id,
            name=f"artifact_{artifact_id}",
            version="1.0.0",
            type=artifact_type
        )
    

    def _upload_artifact_to_s3(self, artifact_id: str, content: bytes):
        try:
            self.s3_client.put_object(
                Bucket = self.bucket_name,
                Key = f"{self.data_prefix}{artifact_id}",
                Body = content
            )
        except Exception as e:
            logging.error(f"Error uploading artifact to S3: {e}")
            raise

async def artifact_accessor() -> ArtifactAccessor:
    return ArtifactAccessor()
