#!/usr/bin/env python3
"""
Bottleneck Analyzer for Performance Testing

Identifies performance bottlenecks from load test and system metrics.
Categorizes issues as white-box (internal) or black-box (external).

Usage:
    python3 analyze_bottlenecks.py --load-results metrics.json --system-metrics system.json --output bottlenecks.json
"""

import json
import statistics
from pathlib import Path
import logging

# Setup logging
logger = logging.getLogger(__name__)


class BottleneckAnalyzer:
    def __init__(self, load_test_results, system_metrics):
        self.load_results = self._load_json(load_test_results)
        self.system_metrics = self._load_json(system_metrics)
        self.bottlenecks = []
    
    def _load_json(self, filepath):
        logger.debug(f"Loading {filepath}")
        with open(filepath) as f:
            return json.load(f)
    
    def check_worker_saturation(self):
        """Detect if uvicorn workers are saturated"""
        if not self.system_metrics:
            logger.debug("No system metrics available for worker saturation check")
            return False
        
        worker_cpus = []
        for sample in self.system_metrics:
            workers = sample.get('uvicorn_workers', [])
            if workers:
                avg_cpu = statistics.mean([w['cpu_percent'] for w in workers])
                worker_cpus.append(avg_cpu)
        
        if worker_cpus:
            avg_worker_cpu = statistics.mean(worker_cpus)
            logger.debug(f"Average worker CPU: {avg_worker_cpu:.1f}%")
            
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
                logger.info(f"Detected worker saturation: {num_workers} workers at {avg_worker_cpu:.1f}% CPU")
                return True
        return False
    
    def check_network_bandwidth(self):
        """Detect network bandwidth saturation"""
        if not self.system_metrics:
            logger.debug("No system metrics available for network bandwidth check")
            return False
        
        first_sample = self.system_metrics[0]
        last_sample = self.system_metrics[-1]
        
        duration = last_sample['timestamp'] - first_sample['timestamp']
        bytes_sent = last_sample['network_io']['bytes_sent'] - first_sample['network_io']['bytes_sent']
        
        mbps = (bytes_sent * 8) / (duration * 1_000_000)
        logger.debug(f"Network throughput: {mbps:.1f} Mbps")
        
        if mbps > 4000:
            self.bottlenecks.append({
                'name': 'Network Bandwidth',
                'type': 'black-box',
                'evidence': f'Network throughput at {mbps:.1f} Mbps',
                'root_cause': 'EC2 instance network limit reached',
                'impact': 'Moderate - limits download speed',
                'fix': 'Upgrade to larger EC2 instance type'
            })
            logger.info(f"Detected network bandwidth saturation: {mbps:.1f} Mbps")
            return True
        return False
    
    def check_s3_latency(self):
        """Detect S3 download latency issues"""
        p99_ms = self.load_results.get('latency_p99_ms', 0)
        logger.debug(f"P99 latency: {p99_ms:.0f}ms")
        
        if p99_ms > 5000:
            self.bottlenecks.append({
                'name': 'S3 Download Latency',
                'type': 'black-box',
                'evidence': f'P99 latency: {p99_ms:.0f}ms ({p99_ms/1000:.1f}s)',
                'root_cause': 'S3 download speed or distance',
                'impact': 'Moderate - affects worst-case performance',
                'fix': 'Use S3 Transfer Acceleration or CloudFront CDN'
            })
            logger.info(f"Detected S3 latency issue: P99 {p99_ms:.0f}ms")
            return True
        return False

    def check_database_performance(self):
        """Detect database query performance issues"""
        mean_latency_ms = self.load_results.get('latency_mean_ms', 0)
        expected_s3_time_ms = 16000
        
        logger.debug(f"Mean latency: {mean_latency_ms:.0f}ms, Expected S3 time: {expected_s3_time_ms}ms")
        
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
            logger.info(f"Detected database overhead: {overhead_ms:.0f}ms")
            return True
        return False
    
    def check_low_throughput(self):
        """Detect overall low throughput"""
        throughput = self.load_results.get('throughput_req_per_sec', 0)
        total_clients = self.load_results.get('total_clients', 100)
        
        logger.debug(f"Throughput: {throughput:.1f} req/sec with {total_clients} clients")
        
        if throughput < 10 and total_clients >= 100:
            self.bottlenecks.append({
                'name': 'Low Overall Throughput',
                'type': 'black-box',
                'evidence': f'Throughput only {throughput:.1f} req/sec with {total_clients} clients',
                'root_cause': 'Multiple bottlenecks or system overload',
                'impact': 'Severe - system not handling load',
                'fix': 'Investigate worker count, database connections, and nginx settings'
            })
            logger.info(f"Detected low throughput: {throughput:.1f} req/sec")
            return True
        return False
    
    def analyze(self, output_file: str = 'bottlenecks.json'):
        """
        Run all bottleneck checks and save results.
        
        Args:
            output_file: Path to save bottleneck analysis JSON
            
        Returns:
            List of detected bottlenecks
        """
        logger.info("="*70)
        logger.info("BOTTLENECK ANALYSIS")
        logger.info("="*70)
        
        logger.info("\nRunning bottleneck checks...")
        self.check_worker_saturation()
        self.check_network_bandwidth()
        self.check_s3_latency()
        self.check_database_performance()
        self.check_low_throughput()
        
        logger.info(f"\nFound {len(self.bottlenecks)} bottleneck(s)")
        
        if len(self.bottlenecks) == 0:
            logger.info("No significant bottlenecks detected")
            logger.info("System appears to be performing well")
        else:
            for i, bottleneck in enumerate(self.bottlenecks, 1):
                logger.info(f"\n{i}. {bottleneck['name']} ({bottleneck['type']})")
                logger.info(f"   Evidence: {bottleneck['evidence']}")
                logger.info(f"   Root cause: {bottleneck['root_cause']}")
                logger.info(f"   Impact: {bottleneck['impact']}")
                logger.info(f"   Fix: {bottleneck['fix']}")
        
        # Ensure output directory exists
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save bottlenecks to JSON
        with open(output_file, 'w') as f:
            json.dump(self.bottlenecks, f, indent=2)
        
        logger.info(f"\nAnalysis saved to: {output_file}")
        logger.info("="*70)
        
        return self.bottlenecks


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Analyze performance bottlenecks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic analysis
    python3 analyze_bottlenecks.py --load-results metrics.json --system-metrics system.json --output bottlenecks.json
    
    # Debug mode
    python3 analyze_bottlenecks.py --load-results metrics.json --system-metrics system.json --output bottlenecks.json --debug
        """
    )
    
    # Required arguments
    parser.add_argument(
        '--load-results',
        required=True,
        help='Load test results JSON from metrics_calculator.py'
    )
    parser.add_argument(
        '--system-metrics',
        required=True,
        help='System metrics JSON from system_monitor.py'
    )
    
    # Optional arguments
    parser.add_argument(
        '--output',
        default='bottlenecks.json',
        help='Output file for bottleneck analysis (default: bottlenecks.json)'
    )
    
    # Logging control
    parser.add_argument('--quiet', action='store_true', help='Minimal output (errors only)')
    parser.add_argument('--debug', action='store_true', help='Verbose debug output')
    
    args = parser.parse_args()
    
    # Configure logging
    if args.debug:
        log_level = logging.DEBUG
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    elif args.quiet:
        log_level = logging.ERROR
        log_format = '%(levelname)s - %(message)s'
    else:
        log_level = logging.INFO
        log_format = '%(message)s'
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Run analysis
    try:
        analyzer = BottleneckAnalyzer(args.load_results, args.system_metrics)
        analyzer.analyze(output_file=args.output)
        return 0
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        logger.debug("Traceback:", exc_info=True)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())