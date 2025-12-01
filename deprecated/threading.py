from multiprocessing import Pool
from typing import List, Optional, Callable, Any, Tuple, Generic
import traceback
from pathlib import Path
from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd


class MetricTask:
    def __init__(self, metric: MetricStd, artifact: Artifact, path: Path, *args, **kwargs):
        """
        Args:
            metric: The metric instance
            method_name: Name of the method to call on the metric
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method
        """
        self.metric = metric
        self.artifact = artifact
        self.path = path
        self.args = args
        self.kwargs = kwargs

    def execute(self) -> Tuple[float, Any]:
        """Convert task to tuple for multiprocessing."""
        return self.metric.run_score_calculation(self.path, self.artifact, *self.args, **self.kwargs)


def run_metric_task(task: MetricTask) -> dict[str, Tuple[float, Any, dict|None]]:
    try:
        latency, score = task.execute()
        return {task.metric.get_metric_name(): (latency, score, None)}
    except Exception as e:
        tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        error_info = {
            "error_type": e.__class__.__name__,
            "message": str(e),
            "traceback": tb_str,
            "metric": task.metric.get_metric_name(),
            "method": "run_score_calculation"
        }
        return {task.metric.get_metric_name(): (0.0, None, error_info)}


class MetricRunner:
    """
    Manages parallel execution of metric computations using multiprocessing.
    """
    def __init__(self, num_processes: Optional[int] = None):
        """
        Args:
            num_processes: Number of processes to use. If None, uses CPU count.
        """
        self.num_processes = num_processes
        self.tasks: List[MetricTask] = []
        
    def add_task(self, metric: MetricStd, path: Path, artifact: Artifact, *args, **kwargs) -> 'MetricRunner':
        """
        Add a metric computation task to the queue.
        
        Args:
            metric: The metric instance
            method_name: Name of the method to call
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method
            
        Returns:
            Self for method chaining
        """
        task = MetricTask(metric, artifact, path, *args, **kwargs)
        self.tasks.append(task)
        return self
        
    def run(self) -> dict[str, Tuple[float, Any, dict|None]]:
        """
        Execute all queued tasks in parallel.
        
        Returns:
            List of (metric_instance, result, exception) tuples
        """
        if not self.tasks:
            return dict()

        with Pool(processes=self.num_processes) as pool:
            results = pool.map(run_metric_task, self.tasks)

        dict_result: dict[str, Tuple[float, Any, dict|None]] = dict()

        for result in results:
            dict_result.update(result)

        self.clear_tasks()

        return dict_result
    
    def clear_tasks(self) -> 'MetricRunner':
        """Clear all queued tasks."""
        self.tasks = []
        return self


class MetricBatch:
    """
    Helper class to batch metric computations and handle results.
    """
    def __init__(self, metrics: List[Any]):
        """
        Args:
            metrics: List of metric instances
        """
        self.metrics = metrics
        
    def compute_all(self, num_processes: Optional[int] = None) -> dict:
        """
        Compute all metrics in parallel and return organized results.
        
        Args:
            num_processes: Number of processes to use
            
        Returns:
            Dictionary with metric names as keys and results as values
        """
        runner = MetricRunner(num_processes)
        
        # Add tasks based on metric type
        for metric in self.metrics:
            metric_name = metric.getMetricName()
            
            # Determine which method to call based on metric class
            if metric_name == "Bus Factor":
                # Will be set via setNumContributors in run.py
                pass
            elif metric_name == "Ramp Up Time":
                # Will be set via setRampUpTime in run.py
                pass
            elif metric_name == "Size":
                # Will be set via setSize in run.py
                pass
            # Note: Other metrics will be handled similarly in the updated run.py
                
        results = runner.run()
        
        # Organize results
        result_dict = {}
        errors = []
        
        for metric, result, error in results:
            metric_name = metric.getMetricName()
            if error:
                errors.append(error)
                result_dict[metric_name] = None
            else:
                result_dict[metric_name] = result
                
        if errors:
            result_dict['_errors'] = errors
            
        return result_dict


def create_metric_runner(num_processes: Optional[int] = None) -> MetricRunner:
    """
    Factory function to create a MetricRunner.
    
    Args:
        num_processes: Number of processes to use. If None, uses CPU count.
        
    Returns:
        MetricRunner instance
    """
    return MetricRunner(num_processes)