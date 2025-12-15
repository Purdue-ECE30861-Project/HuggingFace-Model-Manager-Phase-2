import json
import statistics
from typing import Dict, List

class MetricsCalculator:
    """Calculate performance metrics from raw load test data"""
    
    def __init__(self, raw_results_file: str):
        """
        Args:
            raw_results_file: Path to JSON file from load_generator.py
        """
        with open(raw_results_file) as f:
            self.data = json.load(f)
        
        self.test_metadata = self.data['test_metadata']
        self.raw_results = self.data['raw_results']
    
    def calculate_all_metrics(self) -> Dict:
        """Calculate all performance metrics"""
        
        # Separate successful and failed
        successful = [r for r in self.raw_results if r['success']]
        failed = [r for r in self.raw_results if not r['success']]
        
        if not successful:
            return {
                "error": "No successful requests",
                "total_clients": len(self.raw_results),
                "successful_requests": 0,
                "failed_requests": len(failed)
            }
        
        # Extract latencies and bytes
        latencies = [r['latency_ms'] for r in successful]
        total_bytes = sum(r['bytes_downloaded'] for r in successful)
        duration = self.test_metadata['total_duration']
        
        return {
            # Test configuration
            "environment": self.test_metadata['environment'],
            "registry_url": self.test_metadata['registry_url'],
            "artifact_id": self.test_metadata['artifact_id'],
            "total_clients": self.test_metadata['num_clients'],
            "test_duration_sec": duration,
            
            # Success metrics
            "successful_requests": len(successful),
            "failed_requests": len(failed),
            "success_rate": len(successful) / len(self.raw_results),
            
            # Latency metrics (milliseconds)
            "latency_mean_ms": statistics.mean(latencies),
            "latency_median_ms": statistics.median(latencies),
            "latency_min_ms": min(latencies),
            "latency_max_ms": max(latencies),
            "latency_std_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            "latency_p95_ms": statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else max(latencies),
            "latency_p99_ms": statistics.quantiles(latencies, n=100)[98] if len(latencies) > 100 else max(latencies),
            
            # Throughput metrics
            "throughput_req_per_sec": len(successful) / duration if duration > 0 else 0,
            "total_bytes_transferred": total_bytes,
            "throughput_mbps": (total_bytes * 8 / 1_000_000) / duration if duration > 0 else 0,
            
            # Error analysis
            "errors": self._analyze_errors(failed) if failed else None
        }
    
    def _analyze_errors(self, failed: List[Dict]) -> Dict:
        """Analyze error patterns"""
        error_counts = {}
        for result in failed:
            error = result.get('error_message', 'Unknown')
            error_counts[error] = error_counts.get(error, 0) + 1
        
        return {
            "total_failures": len(failed),
            "error_types": error_counts,
            "sample_errors": [r.get('error_message') for r in failed[:5]]
        }


# CLI entry point
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Calculate metrics from raw load test data")
    parser.add_argument('--input', required=True, help='Raw results JSON from load_generator.py')
    parser.add_argument('--output', required=True, help='Output file for calculated metrics')
    args = parser.parse_args()
    
    # Calculate metrics
    calculator = MetricsCalculator(args.input)
    metrics = calculator.calculate_all_metrics()
    
    # Save calculated metrics
    with open(args.output, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print(f"Metrics calculated and saved to {args.output}")
    return 0

if __name__ == "__main__":
  exit(main())
    exit(main())
ubuntu@ip-172-31-34-188:~/HuggingFace-Model-Manager-Phase-2/src/backend_server/model/performance_eval$ 
