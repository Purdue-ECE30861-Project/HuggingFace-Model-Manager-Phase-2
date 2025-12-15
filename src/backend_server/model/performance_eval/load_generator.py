import asyncio
import aiohttp
import time
from dataclasses import dataclass, asdict
from typing import List, Optional
from enum import Enum

class TestEnvironment(Enum):
    LOCAL = "local"
    PRODUCTION = "aws_production"

@dataclass
class DownloadMetrics:
    """Raw data from a single client download"""
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
    """
    Core load generator - runs concurrent downloads only.
    No calculation, formatting, or reporting.
    """
    ENVIRONMENT_URLS = {
        TestEnvironment.LOCAL: "http://localhost:80",
        TestEnvironment.PRODUCTION: "http://3.132.140.58"
    }

    def __init__(self, environment: TestEnvironment, num_clients: int = 100):
        self.registry_url = self.ENVIRONMENT_URLS[environment]
        self.environment = environment
        self.num_clients = num_clients
        self.results: List[DownloadMetrics] = []

    async def download_model(self, client_id: int, artifact_id: str, session: aiohttp.ClientSession) -> DownloadMetrics:
        """Single client download - returns raw metrics"""
        start_time = time.time()
        bytes_downloaded = 0
        status_code = None

        try:
            # Step 1: Get artifact metadata
            metadata_url = f"{self.registry_url}/artifacts/model/{artifact_id}"
            
            async with session.get(metadata_url) as response:
                status_code = response.status
                
                if response.status != 200:
                    error_body = await response.text()
                    raise Exception(f"Metadata failed - HTTP {response.status}: {error_body[:100]}")
                
                artifact_data = await response.json()
                s3_download_url = artifact_data.get('data', {}).get('download_url')
                
                if not s3_download_url:
                    raise Exception("No download_url in artifact metadata")
            
            # Step 2: Download from S3
            async with session.get(s3_download_url) as response:
                if response.status != 200:
                    error_body = await response.text()
                    raise Exception(f"S3 download failed - HTTP {response.status}: {error_body[:100]}")
                
                async for chunk in response.content.iter_chunked(8192):
                    bytes_downloaded += len(chunk)
                    await asyncio.sleep(0)
            
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000

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
        """
        Run load test - returns raw results only.
        No calculation or formatting.
        
        Returns:
            dict with raw results and test metadata
        """
        # Configure connection
        connector = aiohttp.TCPConnector(
            limit=self.num_clients,
            limit_per_host=self.num_clients,
            ttl_dns_cache=300
        )
        
        timeout = aiohttp.ClientTimeout(total=600, connect=30, sock_read=60)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            test_start = time.time()
            
            # Launch all clients
            tasks = [
                self.download_model(i, artifact_id, session)
                for i in range(self.num_clients)
            ]
            
            # Gather results
            self.results = await asyncio.gather(*tasks, return_exceptions=False)
            
            test_end = time.time()
        
        # Return raw data only
        return {
            "test_metadata": {
                "environment": self.environment.value,
                "registry_url": self.registry_url,
                "artifact_id": artifact_id,
                "num_clients": self.num_clients,
                "start_time": test_start,
                "end_time": test_end,
                "total_duration": test_end - test_start
            },
            "raw_results": [r.to_dict() for r in self.results]
        }


# CLI entry point
# Add at the end of load_generator.py

async def main():
    """Main entry point - supports both CLI and interactive modes"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Load test for model registry")
    parser.add_argument('--environment', choices=['local', 'production'])
    parser.add_argument('--artifact-id', help='Artifact ID from populate_registry.py')
    parser.add_argument('--clients', type=int, default=100)
    parser.add_argument('--output', help='Output file for raw results')
    args = parser.parse_args()
    
    # Check if CLI mode (any arg provided)
    cli_mode = args.environment or args.artifact_id or args.output
    
    if cli_mode:
        # CLI Mode - for automation
        if not args.environment or not args.artifact_id or not args.output:
            print("Error: --environment, --artifact-id, and --output required in CLI mode")
            return 1
        
        env = TestEnvironment.PRODUCTION if args.environment == 'production' else TestEnvironment.LOCAL
        artifact_id = args.artifact_id
        output_file = args.output
        num_clients = args.clients
        
    else:
        # Interactive Mode - for manual use
        print("Load Test Configuration")
        print("=" * 60)
        print("1. Local testing (10 clients)")
        print("2. AWS Production (100 clients)")
        
        choice = input("\nSelect environment (1, 2): ").strip()
        
        if choice == "1":
            env = TestEnvironment.LOCAL
            num_clients = 10
        elif choice == "2":
            confirm = input("\nTest PRODUCTION with 100 clients? (yes/no): ")
            if confirm.lower() != "yes":
                print("Test cancelled.")
                return 0
            env = TestEnvironment.PRODUCTION
            num_clients = 100
        else:
            print("Invalid choice")
            return 1
        
        artifact_id = input("Enter Tiny-LLM artifact ID: ").strip()
        if not artifact_id:
            print("Error: Artifact ID required")
            return 1
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_file = f"load_test_{env.value}_{timestamp}.json"
    
    # Run test (same for both modes)
    try:
        generator = LoadGenerator(environment=env, num_clients=num_clients)
        raw_results = await generator.run_load_test(artifact_id)
        
        # Save raw results
        import json
        with open(output_file, 'w') as f:
            json.dump(raw_results, f, indent=2)
        
        print(f"\nRaw results saved to {output_file}")
        return 0
        
    except Exception as e:
        print(f"\nTest failed: {e}")
        return 1

if __name__ == "__main__":
    exit(asyncio.run(main())) 
