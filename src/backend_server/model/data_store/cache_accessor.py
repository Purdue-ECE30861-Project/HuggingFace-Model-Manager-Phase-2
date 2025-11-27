from __future__ import annotations

import hashlib
import logging
from typing import Optional

import redis
from pydantic import BaseModel

from src.contracts.artifact_contracts import ArtifactType

logger = logging.getLogger(__name__)


class CacheAccessor:
    """
    Efficient Redis cache accessor for artifact request caching.
    
    Cache keys are tuples of (artifact_id, request_hash) allowing efficient
    invalidation of all cache entries for a specific artifact when it's modified.
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
        decode_responses: bool = True,
        ttl_seconds: int = 180
    ):
        try:
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=decode_responses,
                password=password
            )
            self.ttl_seconds = ttl_seconds

            self.redis_client.ping()
            logger.info(f"Connected to Redis at {host}:{port}")
        except redis.AuthenticationError as e:
            logger.error(f"Redis authentication failed: {e}")
            raise
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis at {host}:{port}: {e}")
            raise
    
    def _format_key(self, artifact_id: str, artifact_type: ArtifactType, request_hash: str) -> str:
        """
        Format cache key from artifact ID and request hash.
        
        Args:
            artifact_id: Artifact identifier
            request_hash: Hash of the request (from Pydantic model)
            
        Returns:
            Formatted Redis key string
        """
        return f"artifact:{artifact_id}:{artifact_type.name}:{request_hash}"
    
    def _get_pattern_for_artifact(self, artifact_id: str, artifact_type: ArtifactType) -> str:
        """
        Get Redis key pattern for all entries of an artifact.
        
        Args:
            artifact_id: Artifact identifier
            
        Returns:
            Redis key pattern string
        """
        return f"artifact:{artifact_id}:{artifact_type.name}:*"
    
    def insert(
        self,
        artifact_id: str,
        artifact_type: ArtifactType,
        request_hash: str,
        response_content: str,
    ) -> bool:
        """
        Insert a cache entry.
        
        Args:
            artifact_id: Artifact identifier
            value: Value to cache (as string)
            ttl: Optional time-to-live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            key = self._format_key(artifact_id, artifact_type, request_hash)

            self.redis_client.setex(key, self.ttl_seconds, response_content)
            
            logger.info(f"Inserted cache entry for artifact {artifact_id} with hash {request_hash[:8]}...{request_hash[-8:]}")
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to insert cache entry: {e}")
            return False
    
    def delete_by_artifact_id(self, artifact_id: str, artifact_type: ArtifactType) -> int:
        """
        Delete all cache entries for a specific artifact ID.
        
        This is useful when an artifact is modified and all cached
        responses for that artifact should be invalidated.
        
        Args:
            artifact_id: Artifact identifier
            
        Returns:
            Number of keys deleted
        """
        try:
            pattern = self._get_pattern_for_artifact(artifact_id, artifact_type)
            
            # Find all keys matching the pattern
            keys = list(self.redis_client.scan_iter(match=pattern))
            
            if not keys:
                logger.debug(f"No cache entries found for artifact {artifact_id}")
                return 0
            
            # Delete all matching keys
            deleted_count: int = self.redis_client.delete(*keys)

            logger.info(f"Deleted {deleted_count} cache entries for artifact {artifact_id}")
            return deleted_count
        except redis.RedisError as e:
            logger.error(f"Failed to delete cache entries for artifact {artifact_id}: {e}")
            return 0
    
    def delete(
        self,
        artifact_id: str,
        artifact_type: ArtifactType,
        request_hash: str
    ) -> bool:
        """
        Delete a specific cache entry.
        
        Args:
            artifact_id: Artifact identifier
            request_hash: Hash of the request (from Pydantic model)
            
        Returns:
            True if key was deleted, False if key didn't exist or error occurred
        """
        try:
            key = self._format_key(artifact_id, artifact_type, request_hash)
            deleted = self.redis_client.delete(key)
            
            if deleted:
                logger.debug(f"Deleted cache entry for artifact {artifact_id} with hash {request_hash[:8]}...")
            else:
                logger.debug(f"Cache entry not found for artifact {artifact_id} with hash {request_hash[:8]}...")
            
            return bool(deleted)
        except redis.RedisError as e:
            logger.error(f"Failed to delete cache entry: {e}")
            return False
    
    def close(self):
        """Close Redis connection."""
        try:
            self.redis_client.close()
            logger.info("Closed Redis connection")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")

    def reset(self) -> bool:
        """
        Clear the entire Redis database (DB index selected for this client).
        Returns True on success.
        """
        try:
            self.redis_client.flushdb()
            logger.info("Flushed entire Redis DB")
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to flush Redis DB: {e}")
            return False