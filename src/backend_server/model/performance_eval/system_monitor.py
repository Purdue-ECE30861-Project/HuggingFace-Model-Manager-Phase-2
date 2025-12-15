import psutil
import time
import json
import subprocess
from datetime import datetime

class SystemMonitor:
    """Monitor system performance externally"""
    
    def __init__(self, output_file="system_metrics.json"):
        self.output_file = output_file
        self.samples = []
    
    def get_nginx_stats(self):
        """Check nginx access logs for request rate"""
        try:
            result = subprocess.run(
                ['tail', '-n', '1000', '/var/log/nginx/access.log'],
                capture_output=True,
                text=True
            )
            lines = result.stdout.strip().split('\n')
            return len(lines)
        except:
            return None
    
    def get_uvicorn_workers(self):
        """Count active uvicorn worker processes"""
        try:
            workers = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                if 'uvicorn' in proc.info['name'].lower():
                    workers.append({
                        'pid': proc.info['pid'],
                        'cpu_percent': proc.info['cpu_percent']
                    })
            return workers
        except:
            return []
    
    def monitor(self, duration_seconds=60):
        """Monitor system for specified duration"""
        print(f"Monitoring system for {duration_seconds} seconds...")
        
        start_time = time.time()
        
        while time.time() - start_time < duration_seconds:
            sample = {
                'timestamp': time.time(),
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_io': psutil.disk_io_counters()._asdict(),
                'network_io': psutil.net_io_counters()._asdict(),
                'uvicorn_workers': self.get_uvicorn_workers(),
            }
            
            self.samples.append(sample)
            print(f"  Sample {len(self.samples)}: CPU={sample['cpu_percent']:.1f}% MEM={sample['memory_percent']:.1f}%")
        
        with open(self.output_file, 'w') as f:
            json.dump(self.samples, f, indent=2)
        
        print(f"\nMonitoring complete. Saved to {self.output_file}")
        return self.samples


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=int, default=60, help='Monitoring duration in seconds')
    parser.add_argument('--output', default='system_metrics.json')
    args = parser.parse_args()
    
    monitor = SystemMonitor(args.output)
    monitor.monitor(args.duration)
