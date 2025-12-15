import json
import statistics

class BottleneckAnalyzer:
    """Identify bottlenecks from external metrics"""
    
    def __init__(self, load_test_results, system_metrics):
        self.load_results = self._load_json(load_test_results)
        self.system_metrics = self._load_json(system_metrics)
        self.bottlenecks = []
    
    def _load_json(self, filepath):
        with open(filepath) as f:
            return json.load(f)
    
    def check_worker_saturation(self):
        """Detect if uvicorn workers are saturated"""
        if not self.system_metrics:
            return False
        
        # Average worker CPU across samples
        worker_cpus = []
        for sample in self.system_metrics:
            workers = sample.get('uvicorn_workers', [])
            if workers:
                avg_cpu = statistics.mean([w['cpu_percent'] for w in workers])
                worker_cpus.append(avg_cpu)
        
        if worker_cpus:
            avg_worker_cpu = statistics.mean(worker_cpus)
            
            # If workers are >80% CPU on average, they're saturated
            if avg_worker_cpu > 80:
                num_workers = len(self.system_metrics[0].get('uvicorn_workers', []))
                self.bottlenecks.append({
                    'name': 'Worker Saturation',
                    'type': 'white-box',
                    'evidence': f'{num_workers} workers at {avg_worker_cpu:.1f}% CPU average',
                    'root_cause': f'Only {num_workers} Uvicorn workers configured',
                    'impact': 'Moderate - causes request queuing',
                    'fix': 'Increase worker count to 8 or more'
                })
                return True
        return False
    
    def check_network_bandwidth(self):
        """Detect network bandwidth saturation"""
        if not self.system_metrics:
            return False
        
        # Calculate network throughput
        first_sample = self.system_metrics[0]
        last_sample = self.system_metrics[-1]
        
        duration = last_sample['timestamp'] - first_sample['timestamp']
        bytes_sent = last_sample['network_io']['bytes_sent'] - first_sample['network_io']['bytes_sent']
        
        mbps = (bytes_sent * 8) / (duration * 1_000_000)  # Convert to Mbps
        
        # If network is >80% of typical EC2 t3.medium limit (~5 Gbps)
        if mbps > 4000:  # 80% of 5 Gbps
            self.bottlenecks.append({
                'name': 'Network Bandwidth',
                'type': 'black-box',
                'evidence': f'Network throughput at {mbps:.1f} Mbps',
                'root_cause': 'EC2 instance network limit reached',
                'impact': 'Moderate - limits download speed',
                'fix': 'Upgrade to larger EC2 instance type'
            })
            return True
        return False
    
    def check_s3_latency(self):
        """Detect S3 download latency issues"""
        # Use P99 from calculated metrics (not raw latencies)
        p99_ms = self.load_results.get('latency_p99_ms', 0)
        
        # If P99 latency is >5 seconds (5000ms), S3 might be slow
        if p99_ms > 5000:
            self.bottlenecks.append({
                'name': 'S3 Download Latency',
                'type': 'black-box',
                'evidence': f'P99 latency: {p99_ms:.0f}ms ({p99_ms/1000:.1f}s)',
                'root_cause': 'S3 download speed or distance',
                'impact': 'Moderate - affects worst-case performance',
                'fix': 'Use S3 Transfer Acceleration or CloudFront CDN'
            })
            return True
        return False

    def check_database_performance(self):
        """Detect database query performance issues"""
        # Use mean latency from calculated metrics
        mean_latency_ms = self.load_results.get('latency_mean_ms', 0)
        
        # Typical S3 download for 100MB at 50 Mbps: ~16 seconds = 16000ms
        # If total latency is much higher, database might be slow
        expected_s3_time_ms = 16000  # Rough estimate
        
        if mean_latency_ms > expected_s3_time_ms * 1.5:
            overhead_ms = mean_latency_ms - expected_s3_time_ms
            
            self.bottlenecks.append({
                'name': 'Database Query Overhead',
                'type': 'white-box',
                'evidence': f'Mean latency {mean_latency_ms:.0f}ms vs expected {expected_s3_time_ms:.0f}ms',
                'root_cause': f'{overhead_ms:.0f}ms unexplained overhead (likely database)',
                'impact': 'Moderate - adds latency to each request',
                'fix': 'Add database connection pooling or indexes'
            })
            return True
        return False
    
    def check_low_throughput(self):
        """Detect overall low throughput"""
        throughput = self.load_results.get('throughput_req_per_sec', 0)
        
        # If throughput is very low (<10 req/sec with 100 clients), something is wrong
        total_clients = self.load_results.get('total_clients', 100)
        
        if throughput < 10 and total_clients >= 100:
            self.bottlenecks.append({
                'name': 'Low Overall Throughput',
                'type': 'black-box',
                'evidence': f'Throughput only {throughput:.1f} req/sec with {total_clients} clients',
                'root_cause': 'Multiple bottlenecks or system overload',
                'impact': 'Severe - system not handling load',
                'fix': 'Investigate worker count, database connections, and nginx settings'
            })
            return True
        return False
    
    def analyze(self):
        """Run all bottleneck checks"""
        print("="*70)
        print("BOTTLENECK ANALYSIS")
        print("="*70)
        
        print("\nChecking for bottlenecks...")
        self.check_worker_saturation()
        self.check_network_bandwidth()
        self.check_s3_latency()
        self.check_database_performance()
        self.check_low_throughput()
        
        print(f"\nFound {len(self.bottlenecks)} bottleneck(s):\n")
        
        if len(self.bottlenecks) == 0:
            print("No significant bottlenecks detected")
            print("System appears to be performing well")
        else:
            for i, bottleneck in enumerate(self.bottlenecks, 1):
                print(f"{i}. {bottleneck['name']} ({bottleneck['type']})")
                print(f"   Evidence: {bottleneck['evidence']}")
                print(f"   Root cause: {bottleneck['root_cause']}")
                print(f"   Impact: {bottleneck['impact']}")
                print(f"   Fix: {bottleneck['fix']}")
                print()
        
        # Save bottlenecks
        with open('bottlenecks.json', 'w') as f:
            json.dump(self.bottlenecks, f, indent=2)
        
        print("="*70)
        return self.bottlenecks


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--load-results', required=True, help='Load test results JSON')
    parser.add_argument('--system-metrics', required=True, help='System metrics JSON')
    args = parser.parse_args()
    
    analyzer = BottleneckAnalyzer(args.load_results, args.system_metrics)
    analyzer.analyze()
