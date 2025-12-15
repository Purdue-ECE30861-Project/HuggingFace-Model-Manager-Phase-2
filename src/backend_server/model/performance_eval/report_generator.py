import json
from datetime import datetime
from typing import Dict

class ReportGenerator:
    """Generate performance evaluation report"""
    
    def __init__(self, baseline_metrics: str, optimized_metrics: str = None, bottlenecks: str = None):
        """
        Args:
            baseline_metrics: Path to baseline metrics JSON
            optimized_metrics: Path to optimized metrics JSON (optional)
            bottlenecks: Path to bottlenecks JSON (optional)
        """
        with open(baseline_metrics) as f:
            self.baseline = json.load(f)
        
        self.optimized = None
        if optimized_metrics:
            with open(optimized_metrics) as f:
                self.optimized = json.load(f)
        
        self.bottlenecks = None
        if bottlenecks:
            with open(bottlenecks) as f:
                self.bottlenecks = json.load(f)
    
    def generate_markdown_report(self, output_file: str):
        """Generate comprehensive Markdown report"""
        
        report = []
        report.append("# Performance Evaluation Report")
        report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"\n## Test Configuration")
        report.append(f"- Environment: {self.baseline['environment']}")
        report.append(f"- Concurrent Clients: {self.baseline['total_clients']}")
        report.append(f"- Test Duration: {self.baseline['test_duration_sec']:.2f}s")
        
        # Baseline results
        report.append(f"\n## Baseline Performance")
        report.append(f"- Mean Latency: {self.baseline['latency_mean_ms']:.2f} ms")
        report.append(f"- Median Latency: {self.baseline['latency_median_ms']:.2f} ms")
        report.append(f"- P99 Latency: {self.baseline['latency_p99_ms']:.2f} ms")
        report.append(f"- Throughput: {self.baseline['throughput_req_per_sec']:.2f} req/sec")
        report.append(f"- Bandwidth: {self.baseline['throughput_mbps']:.2f} Mbps")
        
        # Bottlenecks
        if self.bottlenecks:
            report.append(f"\n## Identified Bottlenecks")
            for i, bottleneck in enumerate(self.bottlenecks, 1):
                report.append(f"\n### {i}. {bottleneck['name']}")
                report.append(f"- **Type**: {bottleneck['type']}")
                report.append(f"- **Evidence**: {bottleneck['evidence']}")
                report.append(f"- **Root Cause**: {bottleneck['root_cause']}")
                report.append(f"- **Impact**: {bottleneck['impact']}")
                report.append(f"- **Fix**: {bottleneck['fix']}")
        
        # Optimized results
        if self.optimized:
            report.append(f"\n## Optimized Performance")
            report.append(f"- Mean Latency: {self.optimized['latency_mean_ms']:.2f} ms")
            report.append(f"- Median Latency: {self.optimized['latency_median_ms']:.2f} ms")
            report.append(f"- P99 Latency: {self.optimized['latency_p99_ms']:.2f} ms")
            report.append(f"- Throughput: {self.optimized['throughput_req_per_sec']:.2f} req/sec")
            report.append(f"- Bandwidth: {self.optimized['throughput_mbps']:.2f} Mbps")
            
            # Calculate improvements
            report.append(f"\n## Performance Improvements")
            mean_improvement = ((self.baseline['latency_mean_ms'] - self.optimized['latency_mean_ms']) / 
                              self.baseline['latency_mean_ms']) * 100
            throughput_improvement = ((self.optimized['throughput_req_per_sec'] - self.baseline['throughput_req_per_sec']) / 
                                     self.baseline['throughput_req_per_sec']) * 100
            
            report.append(f"- Mean Latency: {mean_improvement:+.1f}%")
            report.append(f"- Throughput: {throughput_improvement:+.1f}%")
        
        # Write report
        with open(output_file, 'w') as f:
            f.write('\n'.join(report))
        
        print(f"Report generated: {output_file}")


# CLI entry point
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate performance evaluation report")
    parser.add_argument('--baseline', required=True, help='Baseline metrics JSON')
    parser.add_argument('--optimized', help='Optimized metrics JSON')
    parser.add_argument('--bottlenecks', help='Bottlenecks JSON')
    parser.add_argument('--output', default='performance_report.md', help='Output report file')
    args = parser.parse_args()
    
    generator = ReportGenerator(args.baseline, args.optimized, args.bottlenecks)
    generator.generate_markdown_report(args.output)
    
    return 0

if __name__ == "__main__":
    exit(main())
