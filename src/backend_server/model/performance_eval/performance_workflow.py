import subprocess
import sys
import time
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PerformanceWorkflow:
    def __init__(
        self,
        artifact_id: str,
        results_dir: str = "results",
        num_clients: int = 100,
        environment: str = "production",
        monitor_duration: int = 120
    ):
        self.artifact_id = artifact_id
        self.num_clients = num_clients
        self.environment = environment
        self.monitor_duration = monitor_duration
        
        # Setup results directory
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True,exist_ok=True)
        
        # File paths
        self.paths = self._setup_paths()
        
        # State tracking
        self.baseline_complete = False
        self.optimized_complete = False
        
        logger.info(f"Workflow initialized")
        logger.info(f"  Artifact ID: {artifact_id[:16]}...")
        logger.info(f"  Results dir: {results_dir}")
        logger.info(f"  Clients: {num_clients}")
        logger.info(f"  Environment: {environment}")
    
    def _setup_paths(self) -> Dict[str, Path]:
        """Setup all file paths"""
        return {
            # Raw data
            'raw_baseline': self.results_dir / 'raw_baseline.json',
            'raw_optimized': self.results_dir / 'raw_optimized.json',
            
            # System metrics
            'system_baseline': self.results_dir / 'system_baseline.json',
            'system_optimized': self.results_dir / 'system_optimized.json',
            
            # Calculated metrics
            'metrics_baseline': self.results_dir / 'metrics_baseline.json',
            'metrics_optimized': self.results_dir / 'metrics_optimized.json',
            
            # Analysis
            'bottlenecks': self.results_dir / 'bottlenecks.json',
            
            # Final outputs
            'report': self.results_dir / 'performance_report.md',
            'csv_baseline': self.results_dir / 'baseline_summary.csv',
            'csv_optimized': self.results_dir / 'optimized_summary.csv',
        }
    
    def _run_command(
        self,
        cmd: List[str],
        description: str,
        background: bool = False
    ) -> Optional[subprocess.Popen]:
        logger.info(f"{description}")
        logger.debug(f"Command: {' '.join(cmd)}")
        
        try:
            if background:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                logger.info(f"  Started background process (PID: {process.pid})")
                return process
            else:
                result = subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True
                )
                if result.stdout:
                    logger.debug(result.stdout)
                logger.info(f"  ✓ Complete")
                return None
                
        except subprocess.CalledProcessError as e:
            logger.error(f"  ✗ Command failed (exit code {e.returncode})")
            if e.stderr:
                logger.error(f"  Error: {e.stderr}")
            raise
    
    def run_baseline_test(self) -> bool:
        """
        1. Start system monitor (background)
        2. Run load test
        3. Wait for monitor to complete
        4. Calculate metrics
        5. Format and display results
        """
        logger.info("="*70)
        logger.info("BASELINE PERFORMANCE TEST")
        logger.info("="*70)
        
        try:
            # Start system monitor in background
            monitor_process = self._run_command(
                [
                    'python3', 'system_monitor.py',
                    '--duration', str(self.monitor_duration),
                    '--output', str(self.paths['system_baseline'])
                ],
                f"Starting system monitor ({self.monitor_duration}s)",
                background=True
            )
            
            time.sleep(2)  # Let monitor start
            
            # Run load test
            self._run_command(
                [
                    'python3', 'load_generator.py',
                    '--environment', self.environment,
                    '--artifact-id', self.artifact_id,
                    '--clients', str(self.num_clients),
                    '--output', str(self.paths['raw_baseline'])
                ],
                f"Running load test ({self.num_clients} clients)"
            )
            
            # Wait for monitor
            if monitor_process:
                logger.info("Waiting for system monitor to complete...")
                monitor_process.wait()
                logger.info("  ✓ Monitor complete")
            
            # Calculate metrics
            self._run_command(
                [
                    'python3', 'metrics_calculator.py',
                    '--input', str(self.paths['raw_baseline']),
                    '--output', str(self.paths['metrics_baseline'])
                ],
                "Calculating metrics"
            )
            
            # Format and display results
            self._run_command(
                [
                    'python3', 'results_formatter.py',
                    '--input', str(self.paths['metrics_baseline']),
                    '--enable-csv',
                    '--csv-output', str(self.paths['csv_baseline'])
                ],
                "Formatting results"
            )
            
            self.baseline_complete = True
            logger.info("✓ Baseline test complete")
            logger.info(f"  Results: {self.paths['metrics_baseline']}")
            logger.info(f"  CSV: {self.paths['csv_baseline']}")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Baseline test failed: {e}")
            return False
    
    def analyze_bottlenecks(self) -> bool:
        """
        Analyze performance bottlenecks from baseline test.
        
        Returns:
            True if successful
        """
        logger.info("="*70)
        logger.info("BOTTLENECK ANALYSIS")
        logger.info("="*70)
        
        if not self.baseline_complete:
            logger.error("Baseline test required first")
            return False
        
        try:
            self._run_command(
                [
                    'python3', 'analyze_bottlenecks.py',
                    '--load-results', str(self.paths['metrics_baseline']),
                    '--system-metrics', str(self.paths['system_baseline'])
                ],
                "Analyzing bottlenecks"
            )
            
            # Display bottlenecks
            if self.paths['bottlenecks'].exists():
                with open(self.paths['bottlenecks']) as f:
                    bottlenecks = json.load(f)
                
                logger.info(f"\nFound {len(bottlenecks)} bottleneck(s):")
                for i, b in enumerate(bottlenecks, 1):
                    logger.info(f"  {i}. {b['name']} ({b['type']})")
                    logger.info(f"     Fix: {b['fix']}")
            
            logger.info(f"✓ Analysis complete")
            logger.info(f"  Report: {self.paths['bottlenecks']}")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Analysis failed: {e}")
            return False
    
    def run_optimized_test(self) -> bool:
        """
        Run optimized performance test (after fixes applied).
        
        Returns:
            True if successful
        """
        logger.info("="*70)
        logger.info("OPTIMIZED PERFORMANCE TEST")
        logger.info("="*70)
        logger.info("Ensure optimizations have been applied before running!")
        
        try:
            # Start system monitor
            monitor_process = self._run_command(
                [
                    'python3', 'system_monitor.py',
                    '--duration', str(self.monitor_duration),
                    '--output', str(self.paths['system_optimized'])
                ],
                f"Starting system monitor ({self.monitor_duration}s)",
                background=True
            )
            
            time.sleep(2)
            
            # Run load test
            self._run_command(
                [
                    'python3', 'load_generator.py',
                    '--environment', self.environment,
                    '--artifact-id', self.artifact_id,
                    '--clients', str(self.num_clients),
                    '--output', str(self.paths['raw_optimized'])
                ],
                f"Running optimized load test ({self.num_clients} clients)"
            )
            
            # Wait for monitor
            if monitor_process:
                logger.info("Waiting for system monitor...")
                monitor_process.wait()
                logger.info("  ✓ Monitor complete")
            
            # Calculate metrics
            self._run_command(
                [
                    'python3', 'metrics_calculator.py',
                    '--input', str(self.paths['raw_optimized']),
                    '--output', str(self.paths['metrics_optimized'])
                ],
                "Calculating metrics"
            )
            
            # Format results
            self._run_command(
                [
                    'python3', 'results_formatter.py',
                    '--input', str(self.paths['metrics_optimized']),
                    '--enable-csv',
                    '--csv-output', str(self.paths['csv_optimized'])
                ],
                "Formatting results"
            )
            
            self.optimized_complete = True
            logger.info("✓ Optimized test complete")
            logger.info(f"  Results: {self.paths['metrics_optimized']}")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Optimized test failed: {e}")
            return False
    
    def generate_report(self) -> bool:
        """
        Generate final comparison report.
        
        Returns:
            True if successful
        """
        logger.info("="*70)
        logger.info("GENERATING FINAL REPORT")
        logger.info("="*70)
        
        if not self.baseline_complete:
            logger.error("Baseline test required")
            return False
        
        try:
            # Build command
            cmd = [
                'python3', 'report_generator.py',
                '--baseline', str(self.paths['metrics_baseline']),
                '--output', str(self.paths['report'])
            ]
            
            if self.optimized_complete:
                cmd.extend(['--optimized', str(self.paths['metrics_optimized'])])
            
            if self.paths['bottlenecks'].exists():
                cmd.extend(['--bottlenecks', str(self.paths['bottlenecks'])])
            
            self._run_command(cmd, "Generating report")
            
            # Print summary
            self._print_summary()
            
            logger.info("✓ Report generated")
            logger.info(f"  Location: {self.paths['report']}")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Report generation failed: {e}")
            return False
    
    def _print_summary(self):
        """Print performance summary"""
        if not self.paths['metrics_baseline'].exists():
            return
        
        with open(self.paths['metrics_baseline']) as f:
            baseline = json.load(f)
        
        logger.info("\n" + "="*70)
        logger.info("PERFORMANCE SUMMARY")
        logger.info("="*70)
        
        logger.info(f"\nBaseline Performance:")
        logger.info(f"  Mean Latency:   {baseline['latency_mean_ms']:.2f} ms")
        logger.info(f"  Median Latency: {baseline['latency_median_ms']:.2f} ms")
        logger.info(f"  P99 Latency:    {baseline['latency_p99_ms']:.2f} ms")
        logger.info(f"  Throughput:     {baseline['throughput_req_per_sec']:.2f} req/sec")
        
        if self.optimized_complete and self.paths['metrics_optimized'].exists():
            with open(self.paths['metrics_optimized']) as f:
                optimized = json.load(f)
            
            mean_improvement = ((baseline['latency_mean_ms'] - optimized['latency_mean_ms']) / 
                              baseline['latency_mean_ms']) * 100
            throughput_improvement = ((optimized['throughput_req_per_sec'] - baseline['throughput_req_per_sec']) / 
                                     baseline['throughput_req_per_sec']) * 100
            
            logger.info(f"\nOptimized Performance:")
            logger.info(f"  Mean Latency:   {optimized['latency_mean_ms']:.2f} ms")
            logger.info(f"  P99 Latency:    {optimized['latency_p99_ms']:.2f} ms")
            logger.info(f"  Throughput:     {optimized['throughput_req_per_sec']:.2f} req/sec")
            
            logger.info(f"\nImprovements:")
            logger.info(f"  Mean Latency: {mean_improvement:+.1f}%")
            logger.info(f"  Throughput:   {throughput_improvement:+.1f}%")
        
        logger.info("="*70)
    
    def run_baseline_workflow(self) -> int:
        """
        Run baseline workflow only.
        
        Steps:
            1. Baseline test
            2. Analyze bottlenecks
            3. Generate report
            
        Returns:
            0 if successful, 1 if failed
        """
        logger.info("\n" + "="*70)
        logger.info("STARTING BASELINE WORKFLOW")
        logger.info("="*70 + "\n")
        
        try:
            # Baseline test
            if not self.run_baseline_test():
                return 1
            
            # Analyze bottlenecks
            if not self.analyze_bottlenecks():
                return 1
            
            # Generate report
            if not self.generate_report():
                return 1
            
            logger.info("\n✓ Baseline workflow complete!")
            return 0
            
        except KeyboardInterrupt:
            logger.warning("\n✗ Workflow interrupted by user")
            return 1
        except Exception as e:
            logger.error(f"\n✗ Workflow failed: {e}")
            return 1
    
    def run_full_workflow(self) -> int:
        """
        Run complete workflow (baseline + optimized).
        
        Steps:
            1. Baseline test
            2. Analyze bottlenecks
            3. Pause for optimizations
            4. Optimized test
            5. Generate final report
            
        Returns:
            0 if successful, 1 if failed
        """
        logger.info("\n" + "="*70)
        logger.info("STARTING FULL WORKFLOW")
        logger.info("="*70 + "\n")
        
        try:
            # Baseline test
            if not self.run_baseline_test():
                return 1
            
            # Analyze bottlenecks
            if not self.analyze_bottlenecks():
                return 1
            
            # Manual optimization step
            logger.info("\n" + "="*70)
            logger.info("APPLY OPTIMIZATIONS")
            logger.info("="*70)
            logger.info("Review bottleneck analysis and apply fixes.")
            logger.info("Common optimizations:")
            logger.info("  - Increase uvicorn workers")
            logger.info("  - Optimize database connection pool")
            logger.info("  - Enable caching")
            logger.info("\nPress ENTER when optimizations are applied...")
            input()
            
            # Optimized test
            if not self.run_optimized_test():
                return 1
            
            # Generate final report
            if not self.generate_report():
                return 1
            
            logger.info("\n✓ Full workflow complete!")
            return 0
            
        except KeyboardInterrupt:
            logger.warning("\n✗ Workflow interrupted by user")
            return 1
        except Exception as e:
            logger.error(f"\n✗ Workflow failed: {e}")
            return 1


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Performance evaluation workflow orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run baseline test only
    python3 performance_workflow.py --artifact-id abc123 --baseline
    
    # Run full workflow (with optimization step)
    python3 performance_workflow.py --artifact-id abc123 --full
    
    # Custom configuration
    python3 performance_workflow.py \\
        --artifact-id abc123 \\
        --clients 50 \\
        --baseline \\
        --results my_results/
    
    # Get artifact ID first
    python3 populate_registry_standalone.py --get-artifact-id
        """
    )
    
    # Required arguments
    parser.add_argument(
        '--artifact-id',
        required=True,
        help='Tiny-LLM artifact ID from populate_registry'
    )
    
    # Workflow mode
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        '--baseline',
        action='store_true',
        help='Run baseline workflow only (test + analysis + report)'
    )
    mode_group.add_argument(
        '--full',
        action='store_true',
        help='Run full workflow (baseline + optimized)'
    )
    mode_group.add_argument(
        '--optimized-only',
        action='store_true',
        help='Run optimized test only (assumes baseline already done)'
    )
    
    # Optional configuration
    parser.add_argument(
        '--clients',
        type=int,
        default=100,
        help='Number of concurrent clients (default: 100)'
    )
    parser.add_argument(
        '--environment',
        choices=['local', 'production'],
        default='production',
        help='Test environment (default: production)'
    )
    parser.add_argument(
        '--results',
        default='results',
        help='Results directory (default: results/)'
    )
    parser.add_argument(
        '--monitor-duration',
        type=int,
        default=120,
        help='System monitoring duration in seconds (default: 120)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create workflow
    workflow = PerformanceWorkflow(
        artifact_id=args.artifact_id,
        results_dir=args.results,
        num_clients=args.clients,
        environment=args.environment,
        monitor_duration=args.monitor_duration
    )
    
    # Run requested workflow
    try:
        if args.baseline:
            return workflow.run_baseline_workflow()
        elif args.full:
            return workflow.run_full_workflow()
        elif args.optimized_only:
            if not workflow.run_optimized_test():
                return 1
            if not workflow.generate_report():
                return 1
            logger.info("\n✓ Optimized test complete!")
            return 0
    
    except KeyboardInterrupt:
        logger.warning("\n\n✗ Interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())