#!/usr/bin/env python3
import unittest
import time
from deprecated.threading import MetricRunner, MetricTask, run_metric_task, MetricBatch


class MockMetric:
    """
    Mock metric class for testing.
    """ 
    def __init__(self, name="TestMetric", score=0.5, latency=100):
        self.name = name
        self.metricScore = score
        self.metricLatency = latency
        
    def getMetricName(self):
        return self.name
    
    def getMetricScore(self):
        return self.metricScore
    
    def getLatency(self):
        return self.metricLatency
    
    def compute(self, *args, **kwargs):
        return (self.metricScore, self.metricLatency)
    
    def compute_with_args(self, value, multiplier=1):
        return value * multiplier
    
    def failing_compute(self):
        raise ValueError("Intentional test error")


class TestThreading(unittest.TestCase):
    
    def test_task_creation(self):
        """
        Test creating a MetricTask.
        """
        metric = MockMetric()
        task = MetricTask(metric, "compute")
        
        self.assertEqual(task.metric, metric)
        self.assertEqual(task.method_name, "compute")
        self.assertEqual(task.args, ())
        self.assertEqual(task.kwargs, {})
    
    def test_task_with_args(self):
        """
        Test creating a MetricTask with arguments.
        """
        metric = MockMetric()
        task = MetricTask(metric, "compute_with_args", 5, multiplier=2)
        
        self.assertEqual(task.args, (5,))
        self.assertEqual(task.kwargs, {"multiplier": 2})
    
    def test_task_to_tuple(self):
        """
        Test converting task to tuple for multiprocessing.
        """
        metric = MockMetric()
        task = MetricTask(metric, "compute", "arg1", kwarg1="value1")
        
        task_tuple = task.to_tuple()
        
        self.assertEqual(len(task_tuple), 5)
        self.assertEqual(task_tuple[0], metric)
        self.assertEqual(task_tuple[1], "compute")
        self.assertTrue(callable(task_tuple[2]))  # method_func
        self.assertEqual(task_tuple[3], ("arg1",))
        self.assertEqual(task_tuple[4], {"kwarg1": "value1"})

    def test_successful_task_execution(self):
        """
        Test successful execution of a metric task.
        """
        metric = MockMetric()
        method_func = getattr(metric, "compute")
        task_tuple = (metric, "compute", method_func, (), {})
        
        result_metric, result, error = run_metric_task(task_tuple)
        
        self.assertEqual(result_metric, metric)
        self.assertIsNotNone(result)
        self.assertIsNone(error)
        self.assertEqual(result, (0.5, 100))
    
    def test_task_with_arguments(self):
        """
        Test task execution with arguments.
        """
        metric = MockMetric()
        method_func = getattr(metric, "compute_with_args")
        task_tuple = (metric, "compute_with_args", method_func, (10,), {"multiplier": 3})
        
        result_metric, result, error = run_metric_task(task_tuple)
        
        self.assertEqual(result_metric, metric)
        self.assertEqual(result, 30)
        self.assertIsNone(error)
    
    def test_task_with_exception(self):
        """
        Test task execution that raises an exception.
        """
        metric = MockMetric()
        method_func = getattr(metric, "failing_compute")
        task_tuple = (metric, "failing_compute", method_func, (), {})
        
        result_metric, result, error = run_metric_task(task_tuple)
        
        self.assertEqual(result_metric, metric)
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertIn("error_type", error)
        self.assertIn("message", error)
        self.assertIn("traceback", error)
        self.assertEqual(error["error_type"], "ValueError")
        self.assertIn("Intentional test error", error["message"])

    def test_runner_initialization(self):
        """
        Test creating a MetricRunner.
        """
        runner = MetricRunner(num_processes=2)
        
        self.assertEqual(runner.num_processes, 2)
        self.assertEqual(len(runner.tasks), 0)
    
    def test_add_task_with_arguments(self):
        """
        Test adding a task with arguments.
        """
        runner = MetricRunner()
        metric = MockMetric()
        
        runner.add_task(metric, "compute_with_args", 5, multiplier=2)
        
        self.assertEqual(len(runner.tasks), 1)
        task = runner.tasks[0]
        self.assertEqual(task.args, (5,))
        self.assertEqual(task.kwargs, {"multiplier": 2})
    
    def test_run_single_task(self):
        """
        Test running a single task.
        """
        runner = MetricRunner(num_processes=1)
        metric = MockMetric()
        runner.add_task(metric, "compute")
        
        results = runner.run()
        
        self.assertEqual(len(results), 1)
        result_metric, result, error = results[0]
        self.assertEqual(result_metric.getMetricName(), "TestMetric")
        self.assertIsNotNone(result)
        self.assertIsNone(error)
    
    def test_run_multiple_tasks(self):
        """
        Test running multiple tasks in parallel.
        """
        runner = MetricRunner(num_processes=2)
        
        metrics = [
            MockMetric("Metric1", score=0.1),
            MockMetric("Metric2", score=0.2),
            MockMetric("Metric3", score=0.3),
            MockMetric("Metric4", score=0.4),
        ]
        
        for m in metrics:
            runner.add_task(m, "compute")
        
        results = runner.run()
        
        self.assertEqual(len(results), 4)
        
        for result_metric, result, error in results:
            self.assertIsNone(error)
            self.assertIsNotNone(result)
    
    def test_run_with_failures(self):
        """
        Test running tasks where some fail.
        """
        runner = MetricRunner(num_processes=2)
        
        metric1 = MockMetric("Success")
        metric2 = MockMetric("Failure")
        
        runner.add_task(metric1, "compute")
        runner.add_task(metric2, "failing_compute")
        
        results = runner.run()
        
        self.assertEqual(len(results), 2)
        
        success_count = sum(1 for _, _, error in results if error is None)
        failure_count = sum(1 for _, _, error in results if error is not None)
        
        self.assertEqual(success_count, 1)
        self.assertEqual(failure_count, 1)
    
    def test_clear_tasks(self):
        """
        Test clearing tasks from the runner.
        """
        runner = MetricRunner()
        metric = MockMetric()
        
        runner.add_task(metric, "compute")
        self.assertEqual(len(runner.tasks), 1)
        
        result = runner.clear_tasks()
        
        self.assertEqual(result, runner)
        self.assertEqual(len(runner.tasks), 0)
    
    def test_run_clears_after_execution(self):
        """
        Test that tasks persist after run.
        """
        runner = MetricRunner()
        metric = MockMetric()
        
        runner.add_task(metric, "compute")
        runner.run()
    
        self.assertEqual(len(runner.tasks), 1)

    def test_batch_initialization(self):
        """
        Test creating a MetricBatch.
        """
        metrics = [MockMetric("M1"), MockMetric("M2")]
        batch = MetricBatch(metrics)
        
        self.assertEqual(batch.metrics, metrics)
        self.assertEqual(len(batch.metrics), 2)
    
    def test_compute_all_empty(self):
        """
        Test compute_all with no metrics.
        """
        batch = MetricBatch([])
        results = batch.compute_all()
        
        self.assertEqual(results, {})
    
    def test_compute_all_basic(self):
        """
        Test compute_all with simple metrics.
        """
        metrics = [MockMetric("M1"), MockMetric("M2")]
        batch = MetricBatch(metrics)
        
        results = batch.compute_all(num_processes=2)
        
        self.assertIsInstance(results, dict)


class TestEdgeCases(unittest.TestCase):
    """
    Test edge cases and error conditions.
    """
    
    def test_metric_without_getMetricName(self):
        """
        Test handling metric without getMetricName method.
        """
        metric = object()
        
        method_func = lambda: "result"
        task_tuple = (metric, "method", method_func, (), {})
        
        result_metric, result, error = run_metric_task(task_tuple)
        
        self.assertEqual(result_metric, metric)
        self.assertEqual(result, "result")
        self.assertIsNone(error)
    
    def test_large_number_of_tasks(self):
        """
        Test running many tasks in parallel.
        """
        runner = MetricRunner(num_processes=4)
        
        num_tasks = 50
        metrics = [MockMetric(f"Metric{i}", score=i/100.0) for i in range(num_tasks)]
        
        for m in metrics:
            runner.add_task(m, "compute")
        
        start_time = time.time()
        results = runner.run()
        end_time = time.time()
        
        self.assertEqual(len(results), num_tasks)
        
        for _, _, error in results:
            self.assertIsNone(error)
        
  
        self.assertLess(end_time - start_time, 0.5)