import asyncio
import aiohttp
import time
from dataclasses import dataclass, asdict
from typing import List, Optional
from enum import Enum
from pathlib import Path
import logging
import json

logger = logging.getLogger(__name__)

class TestEnvironment(Enum):
    LOCAL = "local"
    PRODUCTION = "aws_production"


@dataclass
class DownloadMetrics:
    client_id: int
    start_time: float
    end_time: float
    latency_ms: float
    success: bool
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    bytes_downloaded: int = 0

    def to_dict(self):
        return asdict(self)


class LoadGenerator:
    ENVIRONMENT_URLS = {
        TestEnvironment.LOCAL: "http://localhost:80",
        TestEnvironment.PRODUCTION: "http://3.132.140.58"
    }

    def __init__(self, environment: TestEnvironment, num_clients: int = 100):
        self.registry_url = self.ENVIRONMENT_URLS[environment]
        self.environment = environment
        self.num_clients = num_clients
        self.results: List[DownloadMetrics] = []
        
        logger.info(f"Load generator initialized")
        logger.info(f"  Environment: {environment.value}")
        logger.info(f"  Registry URL: {self.registry_url}")
        logger.info(f"  Concurrent clients: {num_clients}")

    async def download_model(
        self,
        client_id: int,
        artifact_id: str,
        session: aiohttp.ClientSession
    ) -> DownloadMetrics:
        start_time = time.time()
        bytes_downloaded = 0
        status_code = None

        try:
            metadata_url = f"{self.registry_url}/artifacts/model/{artifact_id}"
            logger.debug(f"Client {client_id}: Requesting metadata from {metadata_url}")
            
            async with session.get(metadata_url) as response:
                status_code = response.status
                
                if response.status != 200:
                    error_body = await response.text()
                    raise Exception(f"Metadata failed - HTTP {response.status}: {error_body[:100]}")
                
                artifact_data = await response.json()
                s3_download_url = artifact_data.get('data', {}).get('download_url')
                
                if not s3_download_url:
                    raise Exception("No download_url in artifact metadata")
                
                logger.debug(f"Client {client_id}: Got S3 URL, starting download")
            
            async with session.get(s3_download_url) as response:
                if response.status != 200:
                    error_body = await response.text()
                    raise Exception(f"S3 download failed - HTTP {response.status}: {error_body[:100]}")
                
                async for chunk in response.content.iter_chunked(8192):
                    bytes_downloaded += len(chunk)
                    await asyncio.sleep(0)
            
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            
            logger.debug(f"Client {client_id}: Success - {bytes_downloaded} bytes in {latency_ms:.0f}ms")

            return DownloadMetrics(
                client_id=client_id,
                start_time=start_time,
                end_time=end_time,
                latency_ms=latency_ms,
                success=True,
                status_code=response.status,
                bytes_downloaded=bytes_downloaded
            )
            
        except asyncio.TimeoutError:
            end_time = time.time()
            logger.warning(f"Client {client_id}: Timeout after {(end_time - start_time):.1f}s")
            return DownloadMetrics(
                client_id=client_id,
                start_time=start_time,
                end_time=end_time,
                latency_ms=(end_time - start_time) * 1000,
                success=False,
                status_code=status_code,
                error_message="Request timeout"
            )
        
        except Exception as e:
            end_time = time.time()
            logger.warning(f"Client {client_id}: Failed - {str(e)[:100]}")
            return DownloadMetrics(
                client_id=client_id,
                start_time=start_time,
                end_time=end_time,
                latency_ms=(end_time - start_time) * 1000,
                success=False,
                status_code=status_code,
                error_message=str(e)
            )
        
    async def run_load_test(self, artifact_id: str) -> dict:
        logger.info(f"Starting load test")
        logger.info(f"  Artifact ID: {artifact_id[:16]}...")
        logger.info(f"  Launching {self.num_clients} concurrent clients")
