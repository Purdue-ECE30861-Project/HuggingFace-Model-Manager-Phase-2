import asyncio
import aiohttp
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import numpy as np
import json
from enum import Enum

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
    """
    simulates concurrent clients downloading from registry
    """
    ENVIRONMENT_URLS = {
        TestEnvironment.LOCAL: "http://localhost:80",
        TestEnvironment.PRODUCTION: "http://3.132.140.58"
    }

    def __init__(
            self,
            environment: TestEnvironment = TestEnvironment.LOCAL,
            custom_url: Optional[str] = None,
            num_clients: int = 100
    ):
        if custom_url:
            self.registry_url = custom_url
        else:
            self.registry_url = self.ENVIRONMENT_URLS[environment]

        self.environment = environment
        self.num_clients = num_clients
        self.results: List[DownloadMetrics] = []

        print(f"Load Generator configured for: {self.registry_url}")
        print(f"Number of clients: {num_clients}")

    async def download_model(self, client_id: int, model_name: str, session: aiohttp.ClientSession) -> DownloadMetrics:
        """
        simulates a single client downloading a model
        """
        start_time = time.time()
        bytes_downloaded = 0
        status_code = None

        try:
            download_url = f"{self.registry_url}/package/{model_name}"

            async with session.get(download_url) as response:
                status_code = response.status

                if response.status == 200:
                    async for chunk in response.content.iter_chunked(8192):
                        bytes_downloaded += len(chunk)
                        await asyncio.sleep(0)

                else:
                    # Read error response
                    error_body = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_body[:100]}")
                
                end_time = time.time()
                latency_ms = (end_time - start_time) * 1000

                print(f"Client {client_id} downloaded {bytes_downloaded} bytes in {latency_ms:.2f} ms")

                return DownloadMetrics(
                    client_id = client_id,
                    start_time = start_time,
                    end_time = end_time,
                    latency_ms = latency_ms,
                    success = True,
                    status_code = status_code,
                    bytes_downloaded = bytes_downloaded
                )
            
        except asyncio.TimeoutError:
            end_time = time.time()
            print(f"Client {client_id}: Timeout")
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
            print(f"Client {client_id}: Error - {str(e)[:100]}")
            return DownloadMetrics(
                client_id=client_id,
                start_time=start_time,
                end_time=end_time,
                latency_ms=(end_time - start_time) * 1000,
                success=False,
                status_code=status_code,
                error_message=str(e)
            )
        
    async def run_load_test(self, model_name: str) -> Dict:
        """
        Run load test with concurrent clients and return dictionary with performance metrics
        """
        
        print(f"\n{'='*60}")
        print(f"STARTING LOAD TEST")
        print(f"{'='*60}")
        print(f"Target Model: {model_name}")
        print(f"Environment: {self.environment.value if isinstance(self.environment, TestEnvironment) else 'custom'}")
        print(f"Registry URL: {self.registry_url}")
        print(f"Concurrent Clients: {self.num_clients}")
        print(f"{'='*60}\n")
        
        # Configure connection pooling for realistic client behavior
        connector = aiohttp.TCPConnector(
            limit=self.num_clients,  # Total connection pool size
            limit_per_host=self.num_clients,  # Per-host connection limit
            ttl_dns_cache=300  # DNS cache TTL
        )
        
        # Set reasonable timeout (adjust based on expected model size)
        timeout = aiohttp.ClientTimeout(
            total=600,  # 10 minutes total
            connect=30,  # 30 seconds to establish connection
            sock_read=60  # 60 seconds between reads
        )
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        ) as session:
            
            # Launch all clients simultaneously
            test_start = time.time()
            
            tasks = [
                self.download_model(i, model_name, session)
                for i in range(self.num_clients)
            ]
            
            print(f"Waiting for all {self.num_clients} clients to complete...\n")
            
            # Gather all results
            self.results = await asyncio.gather(*tasks, return_exceptions=False)
            
            test_end = time.time()
            total_duration = test_end - test_start
        
        # Calculate and return metrics
        metrics = self.calculate_metrics(total_duration)
        self.print_results(metrics)
        return metrics
    
    def calculate_metrics(self, total_duration: float) -> Dict:
        """Calculate performance metrics from test results."""
        
        successful = [r for r in self.results if r.success]
        failed = [r for r in self.results if not r.success]
        latencies = [r.latency_ms for r in successful]
        
        if not latencies:
            return {
                "error": "No successful requests",
                "total_clients": self.num_clients,
                "successful_requests": 0,
                "failed_requests": len(failed),
                "failure_reasons": [r.error_message for r in failed[:10]]  # Sample errors
            }
        
        # Calculate total bytes transferred
        total_bytes = sum(r.bytes_downloaded for r in successful)
        
        return {
            # Test configuration
            "environment": self.environment.value if isinstance(self.environment, TestEnvironment) else "custom",
            "registry_url": self.registry_url,
            "total_clients": self.num_clients,
            
            # Success metrics
            "successful_requests": len(successful),
            "failed_requests": len(failed),
            "success_rate": len(successful) / len(self.results) if self.results else 0,
            
            # Latency metrics (milliseconds)
            "latency_mean_ms": float(np.mean(latencies)),
            "latency_median_ms": float(np.median(latencies)),
            "latency_p99_ms": float(np.percentile(latencies, 99)),
            "latency_p95_ms": float(np.percentile(latencies, 95)),
            "latency_min_ms": float(np.min(latencies)),
            "latency_max_ms": float(np.max(latencies)),
            "latency_std_ms": float(np.std(latencies)),
            
            # Throughput metrics
            "total_duration_sec": total_duration,
            "throughput_req_per_sec": len(successful) / total_duration if total_duration > 0 else 0,
            "total_bytes_transferred": total_bytes,
            "throughput_mbps": (total_bytes * 8 / 1_000_000) / total_duration if total_duration > 0 else 0,
            
            # Error analysis
            "error_summary": self._summarize_errors(failed) if failed else None,
            
            # Raw data for further analysis
            "raw_results": [r.to_dict() for r in self.results]
        }
    
    def _summarize_errors(self, failed_results: List[DownloadMetrics]) -> Dict:
        """Summarize error types and frequencies."""
        error_types = {}
        for result in failed_results:
            error = result.error_message or "Unknown error"
            error_types[error] = error_types.get(error, 0) + 1
        
        return {
            "total_failures": len(failed_results),
            "error_types": error_types,
            "sample_errors": [r.error_message for r in failed_results[:5]]
        }
    
    def print_results(self, metrics: Dict):
        """Pretty print test results."""
        print(f"\n{'='*60}")
        print(f"LOAD TEST RESULTS")
        print(f"{'='*60}")
        
        if "error" in metrics:
            print(f"Test Failed: {metrics['error']}")
            return
        
        print(f"\nSuccess Metrics:")
        print(f"Successful: {metrics['successful_requests']}/{metrics['total_clients']} "
              f"({metrics['success_rate']:.1%})")
        
        if metrics['failed_requests'] > 0:
            print(f"Failed: {metrics['failed_requests']}")
        
        print(f"\nLatency (milliseconds):")
        print(f"  Mean:   {metrics['latency_mean_ms']:>10.2f} ms")
        print(f"  Median: {metrics['latency_median_ms']:>10.2f} ms")
        print(f"  P95:    {metrics['latency_p95_ms']:>10.2f} ms")
        print(f"  P99:    {metrics['latency_p99_ms']:>10.2f} ms")
        print(f"  Min:    {metrics['latency_min_ms']:>10.2f} ms")
        print(f"  Max:    {metrics['latency_max_ms']:>10.2f} ms")
        
        print(f"\nThroughput:")
        print(f"  Requests/sec: {metrics['throughput_req_per_sec']:.2f}")
        print(f"  Total data:   {metrics['total_bytes_transferred'] / (1024**2):.2f} MB")
        print(f"  Bandwidth:    {metrics['throughput_mbps']:.2f} Mbps")
        print(f"  Duration:     {metrics['total_duration_sec']:.2f} seconds")
        
        if metrics.get('error_summary'):
            print(f"\nErrors:")
            for error, count in list(metrics['error_summary']['error_types'].items())[:5]:
                print(f"  • {error[:60]}: {count} occurrences")
        
        print(f"\n{'='*60}\n")
    
    def save_results(self, metrics: Dict, filename: str = "load_test_results.json"):
        """Save results to file for later analysis."""
        with open(filename, 'w') as f:
            json.dump(metrics, f, indent=2)
        print(f"Results saved to {filename}")


# Example usage script
async def run_tiny_llm_test(environment: TestEnvironment, num_clients: int = 100):
    """
    Run the specific test required by the performance track:
    100 clients downloading Tiny-LLM from a registry with 500 models
    """
    
    generator = LoadGenerator(
        environment=environment,
        num_clients=num_clients
    )
    
    # The model ID - adjust based on how your registry stores it
    model_id = "arnir0/Tiny-LLM"
    
    # Run the test
    metrics = await generator.run_load_test(model_id)
    
    # Save results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"tiny_llm_load_test_{environment.value}_{timestamp}.json"
    generator.save_results(metrics, filename)
    
    return metrics


# Main entry point
async def main():
    """
    Main test runner with options for different environments
    """
    
    print("Load Test Configuration")
    print("=" * 60)
    print("1. Local testing (10 clients)")
    print("2. AWS Production (actual performance metrics with 100 clients)")
    
    choice = input("\nSelect environment (1, 2): ").strip()
    
    if choice == "1":
        env = TestEnvironment.LOCAL
        clients = 10
        print(f"\nTesting Local with {clients} clients")
    elif choice == "2":
        confirm = input("\nThis will test PRODUCTION with 100 clients. Continue? (yes/no): ")
        if confirm.lower() != "yes":
            print("Test cancelled.")
            return
        env = TestEnvironment.PRODUCTION
        clients = 100
        print(f"\nTesting production with {clients} clients")
    else:
        print("Invalid choice")
        return
    
    await run_tiny_llm_test(env, clients)


if __name__ == "__main__":
    asyncio.run(main())