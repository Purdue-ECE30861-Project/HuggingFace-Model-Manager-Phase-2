import json
from typing import Dict
from pathlib import Path

class ResultsFormatter:
    """Format and display performance metrics"""
    
    def __init__(self, metrics_file: str):
        """
        Args:
            metrics_file: Path to metrics JSON from metrics_calculator.py
        """
        with open(metrics_file) as f:
            self.metrics = json.load(f)
    
    def print_summary(self):
        """Print formatted summary to console"""
        
        print(f"\n{'='*60}")
        print(f"LOAD TEST RESULTS")
        print(f"{'='*60}")
        
        if "error" in self.metrics:
            print(f"Test Failed: {self.metrics['error']}")
            return
        
        # Configuration
        print(f"\nConfiguration:")
        print(f"  Environment: {self.metrics['environment']}")
        print(f"  Artifact ID: {self.metrics['artifact_id'][:16]}...")
        print(f"  Clients: {self.metrics['total_clients']}")
        print(f"  Duration: {self.metrics['test_duration_sec']:.2f}s")
        
        # Success metrics
        print(f"\nSuccess Metrics:")
        print(f"  Successful: {self.metrics['successful_requests']}/{self.metrics['total_clients']} "
              f"({self.metrics['success_rate']:.1%})")
        
        if self.metrics['failed_requests'] > 0:
            print(f"  Failed: {self.metrics['failed_requests']}")
        
        # Latency metrics
        print(f"\nLatency (milliseconds):")
        print(f"  Mean:   {self.metrics['latency_mean_ms']:>10.2f} ms")
        print(f"  Median: {self.metrics['latency_median_ms']:>10.2f} ms")
        print(f"  P95:    {self.metrics['latency_p95_ms']:>10.2f} ms")
        print(f"  P99:    {self.metrics['latency_p99_ms']:>10.2f} ms")
        print(f"  Min:    {self.metrics['latency_min_ms']:>10.2f} ms")
        print(f"  Max:    {self.metrics['latency_max_ms']:>10.2f} ms")
        
        # Throughput metrics
        print(f"\nThroughput:")
        print(f"  Requests/sec: {self.metrics['throughput_req_per_sec']:.2f}")
        print(f"  Total data:   {self.metrics['total_bytes_transferred'] / (1024**2):.2f} MB")
        print(f"  Bandwidth:    {self.metrics['throughput_mbps']:.2f} Mbps")
        
        # Errors
        if self.metrics.get('errors'):
            print(f"\nErrors:")
            for error, count in list(self.metrics['errors']['error_types'].items())[:5]:
                print(f"  • {error[:60]}: {count} occurrences")
        
        print(f"\n{'='*60}\n")
    
    def generate_csv(self, output_file: str):
        """Generate CSV summary for spreadsheet analysis"""
        import csv

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow(['Metric', 'Value'])
            
            # Data
            writer.writerow(['Environment', self.metrics['environment']])
            writer.writerow(['Total Clients', self.metrics['total_clients']])
            writer.writerow(['Success Rate', f"{self.metrics['success_rate']:.1%}"])
            writer.writerow(['Mean Latency (ms)', f"{self.metrics['latency_mean_ms']:.2f}"])
            writer.writerow(['Median Latency (ms)', f"{self.metrics['latency_median_ms']:.2f}"])
            writer.writerow(['P99 Latency (ms)', f"{self.metrics['latency_p99_ms']:.2f}"])
            writer.writerow(['Throughput (req/sec)', f"{self.metrics['throughput_req_per_sec']:.2f}"])
            writer.writerow(['Bandwidth (Mbps)', f"{self.metrics['throughput_mbps']:.2f}"])
        
        print(f"CSV summary saved to {output_file}")


# CLI entry point
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Format and display performance metrics")
    parser.add_argument('--input', required=True, help='Metrics JSON from metrics_calculator.py')
    parser.add_argument('--enable-csv', action='store_true', help='Enable CSV output generation')
    parser.add_argument('--csv-output', default='results_summary.csv', help='CSV output filename (default: results_summary.csv)')
    args = parser.parse_args()
    
    formatter = ResultsFormatter(args.input)
    formatter.print_summary()

    if args.enable_csv:
        formatter.generate_csv(args.csv_output)
    
    return 0

if __name__ == "__main__":
    exit(main())
