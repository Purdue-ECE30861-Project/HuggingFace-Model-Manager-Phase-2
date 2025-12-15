import subprocess
import sys
import time
import json
import os
from pathlib import Path
from datetime import datetime

class PerformanceWorkflow:
    """Orchestrates complete performance evaluation workflow"""
    
    def __init__(self, results_dir: str = "results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)
        
        self.artifact_id = None
        self.baseline_complete = False
        self.optimized_complete = False
        
        # File paths
        self.paths = {
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
            'comparison': self.results_dir / 'comparison.json',
            'report': self.results_dir / 'performance_report.md',
            'csv_baseline': self.results_dir / 'baseline_summary.csv',
            'csv_optimized': self.results_dir / 'optimized_summary.csv',
        }
    
    def _run_command(self, cmd: list, description: str, background: bool = False) -> subprocess.Popen:
        """Run a command with error handling"""
        print(f"\n{'='*70}")
        print(f"{description}")
        print(f"{'='*70}")
        print(f"Command: {' '.join(cmd)}")
        print()
        
        try:
            if background:
                # Run in background, return process
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                print(f"Started background process (PID: {process.pid})")
                return process
            else:
                # Run and wait for completion
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                if result.stdout:
                    print(result.stdout)
                return None
                
        except subprocess.CalledProcessError as e:
            print(f"\nError running command:")
            print(f"Return code: {e.returncode}")
            if e.stdout:
                print(f"STDOUT:\n{e.stdout}")
            if e.stderr:
                print(f"STDERR:\n{e.stderr}")
            raise
    
    def step_1_verify_registry(self) -> bool:
        """Verify registry is populated and get artifact ID"""
        print(f"\n{'#'*70}")
        print("STEP 1: VERIFY REGISTRY")
        print(f"{'#'*70}")
        
        # Check if registry is populated
        try:
            self._run_command(
                ['python', 'populate_registry.py', '--verify'],
                "Checking registry status"
            )
        except subprocess.CalledProcessError:
            print("\nRegistry not ready!")
            response = input("Populate registry now? (yes/no): ")
            if response.lower() == 'yes':
                self._run_command(
                    ['python', 'populate_registry.py'],
                    "Populating registry"
                )
            else:
                print("Please run: python populate_registry.py")
                return False
        
        # Get artifact ID
        print("\nEnter Tiny-LLM artifact ID from populate_registry.py output:")
        print("(Look for the line: 'Tiny-LLM ID: ...')")
        self.artifact_id = input("Artifact ID: ").strip()
        
        if not self.artifact_id:
            print("Artifact ID required")
            return False
        
        print(f"\nRegistry verified. Artifact ID: {self.artifact_id[:16]}...")
        return True
    
    def step_2_baseline_test(self):
        """Run baseline performance test"""
        print(f"\n{'#'*70}")
        print("STEP 2: BASELINE PERFORMANCE TEST")
        print(f"{'#'*70}")
        
        # Start system monitor in background
        monitor_process = self._run_command(
            [
                'python', 'system_monitor.py',
                '--duration', '120',
                '--output', str(self.paths['system_baseline'])
            ],
            "Starting system monitor (120 seconds)",
            background=True
        )
        
        time.sleep(2)  # Let monitor start
        
        # Run load test
        self._run_command(
            [
                'python', 'load_generator.py',
                '--environment', 'production',
                '--artifact-id', self.artifact_id,
                '--clients', '100',
                '--output', str(self.paths['raw_baseline'])
            ],
            "Running baseline load test (100 clients)"
        )
        
        # Wait for monitor to finish
        if monitor_process:
            print("\nWaiting for system monitor to complete...")
            monitor_process.wait()
        
        # Calculate metrics
        self._run_command(
            [
                'python', 'metrics_calculator.py',
                '--input', str(self.paths['raw_baseline']),
                '--output', str(self.paths['metrics_baseline'])
            ],
            "Calculating baseline metrics"
        )
        
        # Display results
        self._run_command(
            [
                'python', 'results_formatter.py',
                '--input', str(self.paths['metrics_baseline']),
                '--enable-csv',
                '--csv-output', str(self.paths['csv_baseline'])
            ],
            "Formatting baseline results"
        )
        
        self.baseline_complete = True
        print(f"\nBaseline test complete")
    
    def step_3_analyze_bottlenecks(self):
        """Analyze performance bottlenecks"""
        print(f"\n{'#'*70}")
        print("STEP 3: BOTTLENECK ANALYSIS")
        print(f"{'#'*70}")
        
        if not self.baseline_complete:
            print("Run baseline test first (Step 2)")
            return
        
        self._run_command(
            [
                'python', 'analyze_bottlenecks.py',
                '--load-results', str(self.paths['metrics_baseline']),
                '--system-metrics', str(self.paths['system_baseline'])
            ],
            "Analyzing bottlenecks"
        )
        
        print(f"\nBottleneck analysis complete")
        print(f"Review bottlenecks above and in: {self.paths['bottlenecks']}")
    
    def step_4_apply_optimizations(self):
        """Manual step: Apply optimizations"""
        print(f"\n{'#'*70}")
        print("STEP 4: APPLY OPTIMIZATIONS")
        print(f"{'#'*70}")
        
        print("\nBased on bottleneck analysis, apply optimizations:")
        print("\nCommon optimizations:")
        print("  1. Increase uvicorn workers")
        print("     - Stop current server")
        print("     - Restart with: uvicorn main:app --workers 8")
        print()
        print("  2. Optimize database connections")
        print("     - Increase connection pool size")
        print()
        print("  3. Add caching layer")
        print("     - Deploy Redis")
        print("     - Update application code")
        print()
        
        input("Press ENTER when optimizations are applied...")
        
        print("\nReady for optimized test")
    
    def step_5_optimized_test(self):
        """Run optimized performance test"""
        print(f"\n{'#'*70}")
        print("STEP 5: OPTIMIZED PERFORMANCE TEST")
        print(f"{'#'*70}")
        
        # Start system monitor in background
        monitor_process = self._run_command(
            [
                'python', 'system_monitor.py',
                '--duration', '120',
                '--output', str(self.paths['system_optimized'])
            ],
            "Starting system monitor (120 seconds)",
            background=True
        )
        
        time.sleep(2)
        
        # Run load test
        self._run_command(
            [
                'python', 'load_generator.py',
                '--environment', 'production',
                '--artifact-id', self.artifact_id,
                '--clients', '100',
                '--output', str(self.paths['raw_optimized'])
            ],
            "Running optimized load test (100 clients)"
        )
        
        # Wait for monitor
        if monitor_process:
            print("\nWaiting for system monitor to complete...")
            monitor_process.wait()
        
        # Calculate metrics
        self._run_command(
            [
                'python', 'metrics_calculator.py',
                '--input', str(self.paths['raw_optimized']),
                '--output', str(self.paths['metrics_optimized'])
            ],
            "Calculating optimized metrics"
        )
        
        # Display results
        self._run_command(
            [
                'python', 'results_formatter.py',
                '--input', str(self.paths['metrics_optimized']),
                '--enable-csv',
                '--csv-output', str(self.paths['csv_optimized'])
            ],
            "Formatting optimized results"
        )
        
        self.optimized_complete = True
        print(f"\nOptimized test complete")
    
    def step_6_generate_report(self):
        """Generate final comparison report"""
        print(f"\n{'#'*70}")
        print("STEP 6: GENERATE FINAL REPORT")
        print(f"{'#'*70}")
        
        if not self.baseline_complete:
            print("Baseline test required")
            return
        
        # Generate comparison
        self._compare_results()
        
        # Generate report
        cmd = [
            'python', 'report_generator.py',
            '--baseline', str(self.paths['metrics_baseline']),
            '--output', str(self.paths['report'])
        ]
        
        if self.optimized_complete:
            cmd.extend(['--optimized', str(self.paths['metrics_optimized'])])
        
        if self.paths['bottlenecks'].exists():
            cmd.extend(['--bottlenecks', str(self.paths['bottlenecks'])])
        
        self._run_command(cmd, "Generating final report")
        
        print(f"\nReport generated: {self.paths['report']}")
        
        # Print summary
        self._print_final_summary()
    
    def _compare_results(self):
        """Compare baseline and optimized results"""
        if not self.optimized_complete:
            return
        
        with open(self.paths['metrics_baseline']) as f:
            baseline = json.load(f)
        
        with open(self.paths['metrics_optimized']) as f:
            optimized = json.load(f)
        
        comparison = {
            'baseline': {
                'mean_latency_ms': baseline['latency_mean_ms'],
                'p99_latency_ms': baseline['latency_p99_ms'],
                'throughput_req_per_sec': baseline['throughput_req_per_sec']
            },
            'optimized': {
                'mean_latency_ms': optimized['latency_mean_ms'],
                'p99_latency_ms': optimized['latency_p99_ms'],
                'throughput_req_per_sec': optimized['throughput_req_per_sec']
            },
            'improvements': {
                'mean_latency_percent': ((baseline['latency_mean_ms'] - optimized['latency_mean_ms']) / 
                                        baseline['latency_mean_ms']) * 100,
                'p99_latency_percent': ((baseline['latency_p99_ms'] - optimized['latency_p99_ms']) / 
                                       baseline['latency_p99_ms']) * 100,
                'throughput_percent': ((optimized['throughput_req_per_sec'] - baseline['throughput_req_per_sec']) / 
                                      baseline['throughput_req_per_sec']) * 100
            }
        }
        
        with open(self.paths['comparison'], 'w') as f:
            json.dump(comparison, f, indent=2)
        
        print(f"\nComparison saved to: {self.paths['comparison']}")
    
    def _print_final_summary(self):
        """Print final summary of all results"""
        print(f"\n{'='*70}")
        print("PERFORMANCE EVALUATION SUMMARY")
        print(f"{'='*70}")
        
        print(f"\nGenerated Files:")
        for name, path in self.paths.items():
            if path.exists():
                print(f" {name}: {path}")
        
        if self.paths['comparison'].exists():
            with open(self.paths['comparison']) as f:
                comparison = json.load(f)
            
            print(f"\nPerformance Improvements:")
            print(f"  Mean Latency: {comparison['improvements']['mean_latency_percent']:+.1f}%")
            print(f"  P99 Latency:  {comparison['improvements']['p99_latency_percent']:+.1f}%")
            print(f"  Throughput:   {comparison['improvements']['throughput_percent']:+.1f}%")
        
        print(f"\nFinal Report: {self.paths['report']}")
        print(f"{'='*70}")
    
    def run_full_workflow(self):
        """Run complete workflow from start to finish"""
        try:
            # Step 1: Verify registry
            if not self.step_1_verify_registry():
                return 1
            
            # Step 2: Baseline test
            self.step_2_baseline_test()
            
            # Step 3: Analyze bottlenecks
            self.step_3_analyze_bottlenecks()
            
            # Step 4: Apply optimizations (manual)
            response = input("\nProceed with optimization phase? (yes/no): ")
            if response.lower() == 'yes':
                self.step_4_apply_optimizations()
                
                # Step 5: Optimized test
                self.step_5_optimized_test()
            
            # Step 6: Generate final report
            self.step_6_generate_report()
            
            print("\nPerformance evaluation complete!")
            return 0
            
        except KeyboardInterrupt:
            print("\n\nWorkflow interrupted by user")
            return 1
        except Exception as e:
            print(f"\nWorkflow failed: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    def run_interactive(self):
        """Run workflow with step-by-step menu"""
        while True:
            print(f"\n{'='*70}")
            print("PERFORMANCE EVALUATION WORKFLOW")
            print(f"{'='*70}")
            print("\nSteps:")
            print("  1. Verify registry")
            print("  2. Run baseline test")
            print("  3. Analyze bottlenecks")
            print("  4. Apply optimizations (manual)")
            print("  5. Run optimized test")
            print("  6. Generate final report")
            print("\nOptions:")
            print("  7. Run full workflow (steps 1-6)")
            print("  8. View current status")
            print("  0. Exit")
            
            choice = input("\nSelect option: ").strip()
            
            if choice == '1':
                self.step_1_verify_registry()
            elif choice == '2':
                self.step_2_baseline_test()
            elif choice == '3':
                self.step_3_analyze_bottlenecks()
            elif choice == '4':
                self.step_4_apply_optimizations()
            elif choice == '5':
                self.step_5_optimized_test()
            elif choice == '6':
                self.step_6_generate_report()
            elif choice == '7':
                return self.run_full_workflow()
            elif choice == '8':
                self._print_status()
            elif choice == '0':
                print("Exiting...")
                return 0
            else:
                print("Invalid choice")
    
    def _print_status(self):
        """Print current workflow status"""
        print(f"\n{'='*70}")
        print("CURRENT STATUS")
        print(f"{'='*70}")
        print(f"Artifact ID: {self.artifact_id if self.artifact_id else 'Not set'}")
        print(f"Baseline test: {'Complete' if self.baseline_complete else '✗ Not run'}")
        print(f"Optimized test: {'Complete' if self.optimized_complete else '✗ Not run'}")
        print(f"\nResults directory: {self.results_dir}")
        print(f"{'='*70}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Performance evaluation workflow orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  Interactive: python performance_workflow.py
  Automated:   python performance_workflow.py --auto
  
Examples:
  python performance_workflow.py              # Interactive menu
  python performance_workflow.py --auto       # Run full workflow
  python performance_workflow.py --results my_results/  # Custom output dir
        """
    )
    
    parser.add_argument(
        '--auto',
        action='store_true',
        help='Run full workflow automatically'
    )
    
    parser.add_argument(
        '--results',
        default='results',
        help='Results directory (default: results/)'
    )
    
    args = parser.parse_args()
    
    workflow = PerformanceWorkflow(results_dir=args.results)
    
    if args.auto:
        return workflow.run_full_workflow()
    else:
        return workflow.run_interactive()


if __name__ == "__main__":
    exit(main())
