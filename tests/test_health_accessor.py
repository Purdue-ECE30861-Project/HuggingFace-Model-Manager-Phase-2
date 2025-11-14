#!/usr/bin/env python3
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta, timezone
from botocore.exceptions import ClientError

from src.frontend_server.model.health_accessor import HealthAccessor
from src.external_contracts import (
    HealthStatus,
    HealthComponentCollection,
    HealthComponentDetail,
    HealthIssue,
    HealthMetricMap,
    HealthTimelineEntry,
    HealthLogReference
)

class TestHealthAccessor(unittest.TestCase):
    
    def setUp(self):
        self.mock_cloudwatch_client = Mock()
        self.mock_logs_client = Mock()
        
        self.mock_cloudwatch_client.get_metric_statistics.return_value = {
            'Datapoints': []
        }
        self.mock_logs_client.describe_log_streams.return_value = {
            'logStreams': []
        }
        
        # Sample metric datapoints
        now = datetime.now(timezone.utc)
        self.sample_metric_datapoints = [
            {
                'Timestamp': now - timedelta(minutes=10),
                'Average': 50.0,
                'Sum': 500.0,
                'Maximum': 100.0,
                'Minimum': 10.0
            },
            {
                'Timestamp': now - timedelta(minutes=5),
                'Average': 75.0,
                'Sum': 750.0,
                'Maximum': 150.0,
                'Minimum': 20.0
            },
            {
                'Timestamp': now,
                'Average': 100.0,
                'Sum': 1000.0,
                'Maximum': 200.0,
                'Minimum': 30.0
            }
        ]
    
    def create_health_accessor(self):
        """
        Helper to create HealthAccessor with mocked clients.
        """
        with patch('boto3.client') as mock_boto:
            def side_effect(service, **kwargs):
                if service == 'cloudwatch':
                    return self.mock_cloudwatch_client
                elif service == 'logs':
                    return self.mock_logs_client
                return Mock()
            
            mock_boto.side_effect = side_effect
            return HealthAccessor()
    
    def test_initialization_success(self):
        """
        Test successful initialization.
        """
        accessor = self.create_health_accessor()
        
        self.assertIsNotNone(accessor.cloudwatch)
        self.assertIsNotNone(accessor.logs_client)
        self.assertEqual(accessor.region, "us-east-2")
        self.assertEqual(len(accessor.components), 5)
 
    def test_initialization_failure(self):
        """
        Test initialization when AWS clients fail.
        """
        with patch('boto3.client', side_effect=Exception("AWS connection failed")):
            accessor = HealthAccessor()
            self.assertIsNone(accessor.cloudwatch)
            self.assertIsNone(accessor.logs_client)
    
    def test_is_alive_success(self):
        """
        Test health check passes when CloudWatch is accessible.
        """
        self.mock_cloudwatch_client.list_metrics.return_value = {'Metrics': []}
        accessor = self.create_health_accessor()
        
        result = accessor.is_alive()
        
        self.assertTrue(result)
        self.mock_cloudwatch_client.list_metrics.assert_called_once()
    
    def test_is_alive_failure_aws_error(self):
        """
        Test health check fails on AWS error.
        """
        self.mock_cloudwatch_client.list_metrics.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
            'list_metrics'
        )
        accessor = self.create_health_accessor()
        
        result = accessor.is_alive()
        
        self.assertFalse(result)
    
    def test_fetch_component_metrics_success(self):
        """
        Test successful metric fetching.
        """
        self.mock_cloudwatch_client.get_metric_statistics.return_value = {
            'Datapoints': self.sample_metric_datapoints
        }
        accessor = self.create_health_accessor()
        
        start_time = datetime.now(timezone.utc) - timedelta(hours=1)
        end_time = datetime.now(timezone.utc)
        
        result = accessor.fetch_component_metrics(
            'api_gateway',
            ['RequestCount', 'Latency'],
            start_time,
            end_time
        )
        
        self.assertIn('RequestCount', result)
        self.assertIn('Latency', result)
        self.assertEqual(result['RequestCount']['current'], 100.0)
        self.assertEqual(result['RequestCount']['max'], 200.0)
        self.assertEqual(result['RequestCount']['min'], 10.0)
        self.assertEqual(len(result['RequestCount']['datapoints']), 3)
    
    def test_fetch_component_metrics_no_data(self):
        """
        Test metric fetching when no data is available.
        """
        self.mock_cloudwatch_client.get_metric_statistics.return_value = {
            'Datapoints': []
        }
        accessor = self.create_health_accessor()
        
        start_time = datetime.now(timezone.utc) - timedelta(hours=1)
        end_time = datetime.now(timezone.utc)
        
        result = accessor.fetch_component_metrics(
            'api_gateway',
            ['RequestCount'],
            start_time,
            end_time
        )
        
        self.assertEqual(result['RequestCount']['current'], 0)
        self.assertEqual(result['RequestCount']['max'], 0)
        self.assertEqual(result['RequestCount']['datapoints'], [])
    
    def test_fetch_component_metrics_client_error(self):
        """
        Test metric fetching handles ClientError gracefully.
        """
        self.mock_cloudwatch_client.get_metric_statistics.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
            'get_metric_statistics'
        )
        accessor = self.create_health_accessor()
        
        start_time = datetime.now(timezone.utc) - timedelta(hours=1)
        end_time = datetime.now(timezone.utc)
        
        result = accessor.fetch_component_metrics(
            'api_gateway',
            ['RequestCount'],
            start_time,
            end_time
        )
        
        # Should return empty metrics instead of crashing
        self.assertEqual(result['RequestCount']['current'], 0)
    
    def test_fetch_component_metrics_no_cloudwatch(self):
        """
        Test metric fetching when CloudWatch is unavailable.
        """
        with patch('boto3.client', side_effect=Exception("Failed")):
            accessor = HealthAccessor()
            
            start_time = datetime.now(timezone.utc) - timedelta(hours=1)
            end_time = datetime.now(timezone.utc)
            
            result = accessor.fetch_component_metrics(
                'api_gateway',
                ['RequestCount'],
                start_time,
                end_time
            )
            
            self.assertEqual(result, {})
    
    def test_analyze_component_health_ok(self):
        """
        Test health analysis with normal metrics.
        """
        accessor = self.create_health_accessor()
        metrics_data = {
            'ErrorRate': {
                'current': 0.01,
                'max': 0.02,
                'min': 0.0,
                'sum': 1.0,
                'datapoints': [{'Timestamp': datetime.now(timezone.utc)}]
            },
            'Latency': {
                'current': 500,
                'max': 800,
                'min': 200,
                'sum': 5000,
                'datapoints': [{'Timestamp': datetime.now(timezone.utc)}]
            }
        }
        
        status, issues = accessor.analyze_component_health(
            'api_gateway',
            metrics_data
        )
        
        self.assertEqual(status, HealthStatus.ok)
        self.assertEqual(len(issues), 0)
    
    def test_analyze_component_health_degraded(self):
        """
        Test health analysis with warning-level metrics.
        """
        accessor = self.create_health_accessor()
        metrics_data = {
            'ErrorRate': {
                'current': 0.07,
                'max': 0.08,
                'min': 0.05,
                'sum': 7.0,
                'datapoints': [{'Timestamp': datetime.now(timezone.utc)}]
            }
        }
        
        status, issues = accessor.analyze_component_health(
            'api_gateway',
            metrics_data
        )
        
        self.assertEqual(status, HealthStatus.degraded)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "warning")
        self.assertIn("ERRORRATE_WARNING", issues[0].code)
    
    def test_analyze_component_health_critical(self):
        """
        Test health analysis with critical metrics.
        """
        accessor = self.create_health_accessor()
        metrics_data = {
            'ErrorRate': {
                'current': 0.15,
                'max': 0.20,
                'min': 0.10,
                'sum': 15.0,
                'datapoints': [{'Timestamp': datetime.now(timezone.utc)}]
            },
            'Latency': {
                'current': 2500,
                'max': 3000,
                'min': 2000,
                'sum': 25000,
                'datapoints': [{'Timestamp': datetime.now(timezone.utc)}]
            }
        }
        
        status, issues = accessor.analyze_component_health(
            'api_gateway',
            metrics_data
        )
        
        self.assertEqual(status, HealthStatus.critical)
        self.assertGreaterEqual(len(issues), 2)
        self.assertTrue(all(issue.severity == "error" for issue in issues))
    
    def test_analyze_component_health_unknown_no_data(self):
        """
        Test health analysis with no data.
        """
        accessor = self.create_health_accessor()
        metrics_data = {
            'ErrorRate': {
                'current': 0,
                'max': 0,
                'min': 0,
                'sum': 0,
                'datapoints': []
            }
        }
        
        status, issues = accessor.analyze_component_health(
            'api_gateway',
            metrics_data
        )
        
        self.assertEqual(status, HealthStatus.unknown)
        self.assertTrue(any("NO_METRICS_DATA" in issue.code for issue in issues))
    
    def test_analyze_component_health_multiple_components(self):
        """
        Test health analysis for different component types.
        """
        accessor = self.create_health_accessor()
        # Test database component with high query latency
        db_metrics = {
            'QueryLatency': {
                'current': 1500,
                'max': 2000,
                'min': 1000,
                'sum': 15000,
                'datapoints': [{'Timestamp': datetime.now(timezone.utc)}]
            }
        }
        
        status, issues = accessor.analyze_component_health(
            'database',
            db_metrics
        )
        
        self.assertEqual(status, HealthStatus.critical)
        self.assertGreater(len(issues), 0)
    
    def test_build_timeline_success(self):
        """
        Test timeline building with valid data.
        """
        accessor = self.create_health_accessor()
        metrics_data = {
            'RequestCount': {
                'datapoints': self.sample_metric_datapoints
            }
        }
        
        start_time = datetime.now(timezone.utc) - timedelta(hours=1)
        end_time = datetime.now(timezone.utc)
        
        timeline = accessor.build_timeline(
            'api_gateway',
            metrics_data,
            start_time,
            end_time
        )
        
        self.assertEqual(len(timeline), 3)
        self.assertTrue(all(isinstance(entry, HealthTimelineEntry) for entry in timeline))
        self.assertEqual(timeline[0].value, 50.0)
        self.assertEqual(timeline[-1].value, 100.0)
    
    def test_build_timeline_no_data(self):
        """
        Test timeline building with no data.
        """
        accessor = self.create_health_accessor()
        metrics_data = {
            'RequestCount': {
                'datapoints': []
            }
        }
        
        start_time = datetime.now(timezone.utc) - timedelta(hours=1)
        end_time = datetime.now(timezone.utc)
        
        timeline = accessor.build_timeline(
            'api_gateway',
            metrics_data,
            start_time,
            end_time
        )
        
        self.assertEqual(len(timeline), 0)
    
    def test_get_log_references_success(self):
        """
        Test fetching log references.
        """
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        self.mock_logs_client.describe_log_streams.return_value = {
            'logStreams': [
                {
                    'logStreamName': 'api-stream-1',
                    'lastEventTimestamp': now_ms
                },
                {
                    'logStreamName': 'api-stream-2',
                    'lastEventTimestamp': now_ms - 60000
                }
            ]
        }
        accessor = self.create_health_accessor()
        
        logs = accessor.get_log_references('api_gateway', 'api')
        
        self.assertEqual(len(logs), 2)
        self.assertTrue(all(isinstance(log, HealthLogReference) for log in logs))
        self.assertEqual(logs[0].label, 'api_gateway - api-stream-1')
        self.assertTrue(logs[0].tail_available)
    
    def test_get_log_references_with_filter(self):
        """
        Test fetching log references with filter.
        """
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        self.mock_logs_client.describe_log_streams.return_value = {
            'logStreams': [
                {
                    'logStreamName': 'api-stream-1',
                    'lastEventTimestamp': now_ms
                },
                {
                    'logStreamName': 'database-stream-1',
                    'lastEventTimestamp': now_ms
                }
            ]
        }
        accessor = self.create_health_accessor()
        
        logs = accessor.get_log_references('api_gateway', 'api')
        
        # Should only include logs matching the filter
        self.assertEqual(len(logs), 1)
        self.assertIn('api-stream-1', logs[0].label)
    
    def test_get_log_references_no_logs_client(self):
        """
        Test log references when logs client is unavailable.
        """
        with patch('boto3.client', side_effect=Exception("Failed")):
            accessor = HealthAccessor()
            logs = accessor.get_log_references('api_gateway')
            self.assertEqual(logs, [])
    
    def test_get_log_references_client_error(self):
        """
        Test log references handles ClientError.
        """
        self.mock_logs_client.describe_log_streams.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFound', 'Message': 'Log group not found'}},
            'describe_log_streams'
        )
        accessor = self.create_health_accessor()
        
        logs = accessor.get_log_references('api_gateway')
        
        self.assertEqual(logs, [])
    
    def test_get_log_references_limit(self):
        """
        Test log references respects limit.
        """
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        # Create 10 log streams
        log_streams = [
            {
                'logStreamName': f'api-stream-{i}',
                'lastEventTimestamp': now_ms - (i * 1000)
            }
            for i in range(10)
        ]
        
        self.mock_logs_client.describe_log_streams.return_value = {
            'logStreams': log_streams
        }
        accessor = self.create_health_accessor()
        
        logs = accessor.get_log_references('api_gateway', 'api')
        
        # Should limit to 3 references per component
        self.assertLessEqual(len(logs), 3)
    
    def test_component_health_success(self):
        """
        Test full component health retrieval.
        """
        self.mock_cloudwatch_client.get_metric_statistics.return_value = {
            'Datapoints': self.sample_metric_datapoints
        }
        
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        self.mock_logs_client.describe_log_streams.return_value = {
            'logStreams': [
                {
                    'logStreamName': 'test-stream',
                    'lastEventTimestamp': now_ms
                }
            ]
        }
        accessor = self.create_health_accessor()
        
        result = accessor.component_health(
            window=60,
            include_timeline=True
        )
        
        self.assertIsInstance(result, HealthComponentCollection)
        self.assertEqual(len(result.components), 5)
        self.assertEqual(result.window_minutes, 60)
        self.assertTrue(all(isinstance(comp, HealthComponentDetail) for comp in result.components))
    
    def test_component_health_window_clamping(self):
        """
        Test window parameter is clamped to valid range.
        """
        self.mock_cloudwatch_client.get_metric_statistics.return_value = {
            'Datapoints': []
        }
        accessor = self.create_health_accessor()
        
        # Test too small
        result = accessor.component_health(window=1, include_timeline=False)
        self.assertEqual(result.window_minutes, 5)
        
        # Test too large
        result = accessor.component_health(window=2000, include_timeline=False)
        self.assertEqual(result.window_minutes, 1440)
    
    def test_component_health_handles_component_errors(self):
        """
        Test component health handles individual component errors.
        """
        # Make one component fail
        def side_effect(*args, **kwargs):
            dimensions = kwargs.get('Dimensions', [])
            if any(d.get('Value') == 'api_gateway' for d in dimensions):
                raise Exception("Component error")
            return {'Datapoints': []}
        
        self.mock_cloudwatch_client.get_metric_statistics.side_effect = side_effect
        accessor = self.create_health_accessor()
        
        result = accessor.component_health(
            window=60,
            include_timeline=False
        )
        
        # Should still return results for other components
        self.assertIsInstance(result, HealthComponentCollection)
        self.assertEqual(len(result.components), 5)
        
        # Check that error component has unknown status
        error_components = [
            c for c in result.components 
            if c.id == 'api_gateway'
        ]
        self.assertEqual(len(error_components), 1)
        self.assertEqual(error_components[0].status, HealthStatus.unknown)
    
    def test_get_component_detail_complete(self):
        """
        Test getting complete component details.
        """
        # Reset mock to ensure clean state
        self.mock_cloudwatch_client.reset_mock()
        self.mock_logs_client.reset_mock()
        
        self.mock_cloudwatch_client.get_metric_statistics.return_value = {
            'Datapoints': self.sample_metric_datapoints
        }
        
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        self.mock_logs_client.describe_log_streams.return_value = {
            'logStreams': [
                {
                    'logStreamName': 'api-test-stream',
                    'lastEventTimestamp': now_ms
                }
            ]
        }
        accessor = self.create_health_accessor()
        
        component_info = accessor.components['api_gateway']
        start_time = datetime.now(timezone.utc) - timedelta(hours=1)
        end_time = datetime.now(timezone.utc)
        
        detail = accessor.get_component_detail(
            'api_gateway',
            component_info,
            start_time,
            end_time,
            include_timeline=True
        )
        
        self.assertEqual(detail.id, 'api_gateway')
        self.assertEqual(detail.display_name, 'API Gateway')
        self.assertIn(detail.status, [HealthStatus.ok, HealthStatus.degraded, HealthStatus.critical, HealthStatus.unknown])
        self.assertIsNotNone(detail.metrics)
        self.assertIsNotNone(detail.timeline)
        # Logs should be present since we have log streams with the filter
        self.assertIsNotNone(detail.logs)
        self.assertGreater(len(detail.logs), 0)
    
    def test_create_error_component(self):
        """
        Test creating error component.
        """
        accessor = self.create_health_accessor()
        component_info = {
            'display_name': 'Test Component',
            'description': 'Test description'
        }
        
        error_comp = accessor.create_error_component(
            'test_component',
            component_info,
            'Test error message'
        )
        
        self.assertEqual(error_comp.id, 'test_component')
        self.assertEqual(error_comp.status, HealthStatus.unknown)
        self.assertEqual(len(error_comp.issues), 1)
        self.assertEqual(error_comp.issues[0].code, 'HEALTH_CHECK_FAILED')
        self.assertIn('Test error message', error_comp.issues[0].details)


if __name__ == '__main__':
    unittest.main()