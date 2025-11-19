#!/usr/bin/env python3
import unittest
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError

from src.frontend_server.model.cloudwatch_publisher import CloudWatchPublisher

class TestCloudWatchPublisher(unittest.TestCase):
    
    def setUp(self):
        self.mock_cloudwatch_client = Mock()
        self.mock_cloudwatch_client.put_metric_data.return_value = {}
    
    def create_publisher(self, component_name='test_component'):
        """
        Helper to create CloudWatchPublisher with mocked client.
        """
        with patch('boto3.client', return_value=self.mock_cloudwatch_client):
            return CloudWatchPublisher(component_name)
    
    def test_initialization_success(self):
        """
        Test successful initialization.
        """
        publisher = self.create_publisher('api_gateway')
        
        self.assertEqual(publisher.component_name, 'api_gateway')
        self.assertEqual(publisher.namespace, 'ECE461/ModelRegistry')
        self.assertEqual(publisher.region, 'us-east-2')
        self.assertIsNotNone(publisher.cloudwatch)
  
    def test_initialization_failure(self):
        """
        Test initialization handles AWS client failure gracefully.
        """
        with patch('boto3.client', side_effect=Exception("AWS connection failed")):
            publisher = CloudWatchPublisher('test_component')
            
            self.assertIsNone(publisher.cloudwatch)
            self.assertEqual(publisher.component_name, 'test_component')
    
    def test_publish_metric_success(self):
        """
        Test successful metric publication.
        """
        publisher = self.create_publisher()
        
        result = publisher.publish_metric(
            metric_name='RequestCount',
            value=100.0,
            unit='Count'
        )
        
        self.assertTrue(result)
        
        # Verify put_metric_data was called correctly
        self.mock_cloudwatch_client.put_metric_data.assert_called_once()
        call_args = self.mock_cloudwatch_client.put_metric_data.call_args
        
        self.assertEqual(call_args[1]['Namespace'], 'ECE461/ModelRegistry')
        self.assertEqual(len(call_args[1]['MetricData']), 1)
        
        metric_data = call_args[1]['MetricData'][0]
        self.assertEqual(metric_data['MetricName'], 'RequestCount')
        self.assertEqual(metric_data['Value'], 100.0)
        self.assertEqual(metric_data['Unit'], 'Count')
        self.assertEqual(len(metric_data['Dimensions']), 1)
        self.assertEqual(metric_data['Dimensions'][0]['Name'], 'Component')
        self.assertEqual(metric_data['Dimensions'][0]['Value'], 'test_component')
    
    def test_publish_metric_with_dimensions(self):
        """
        Test metric publication with additional dimensions.
        """
        publisher = self.create_publisher()
        
        result = publisher.publish_metric(
            metric_name='ErrorRate',
            value=0.05,
            unit='None',
            dimensions={'ErrorType': 'ValidationError', 'Severity': 'Warning'}
        )
        
        self.assertTrue(result)
        
        call_args = self.mock_cloudwatch_client.put_metric_data.call_args
        metric_data = call_args[1]['MetricData'][0]
        
        # Should have Component + 2 custom dimensions
        self.assertEqual(len(metric_data['Dimensions']), 3)
        
        dimension_dict = {d['Name']: d['Value'] for d in metric_data['Dimensions']}
        self.assertEqual(dimension_dict['Component'], 'test_component')
        self.assertEqual(dimension_dict['ErrorType'], 'ValidationError')
        self.assertEqual(dimension_dict['Severity'], 'Warning')
    
    def test_publish_metric_client_error(self):
        """
        Test metric publication handles ClientError.
        """
        self.mock_cloudwatch_client.put_metric_data.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
            'put_metric_data'
        )
        publisher = self.create_publisher()
        
        result = publisher.publish_metric('TestMetric', 1.0)
        
        self.assertFalse(result)
    
    def test_publish_metric_different_units(self):
        """
        Test publishing metrics with different unit types.
        """
        publisher = self.create_publisher()
        test_cases = [
            ('RequestCount', 100, 'Count'),
            ('Latency', 250.5, 'Milliseconds'),
            ('MemoryUsage', 1024, 'Bytes'),
            ('CPUUtilization', 75.0, 'Percent'),
            ('CustomMetric', 42.0, 'None')
        ]
        
        for metric_name, value, unit in test_cases:
            result = publisher.publish_metric(metric_name, value, unit)
            self.assertTrue(result)
    
    def test_publish_batch_success(self):
        """
        Test successful batch metric publication.
        """
        publisher = self.create_publisher()
        metrics = [
            {'name': 'RequestCount', 'value': 100, 'unit': 'Count'},
            {'name': 'ErrorRate', 'value': 0.05, 'unit': 'None'},
            {'name': 'Latency', 'value': 250.5, 'unit': 'Milliseconds'}
        ]
        
        result = publisher.publish_batch(metrics)
        
        self.assertTrue(result)
        self.mock_cloudwatch_client.put_metric_data.assert_called_once()
        
        call_args = self.mock_cloudwatch_client.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        self.assertEqual(len(metric_data), 3)
        self.assertEqual(metric_data[0]['MetricName'], 'RequestCount')
        self.assertEqual(metric_data[1]['MetricName'], 'ErrorRate')
        self.assertEqual(metric_data[2]['MetricName'], 'Latency')
    
    def test_publish_batch_with_dimensions(self):
        """
        Test batch publication with custom dimensions.
        """
        publisher = self.create_publisher()
        metrics = [
            {
                'name': 'RequestCount',
                'value': 100,
                'unit': 'Count',
                'dimensions': {'Route': '/api/v1/artifacts'}
            },
            {
                'name': 'ErrorRate',
                'value': 0.05,
                'dimensions': {'ErrorType': 'ValidationError'}
            }
        ]
        
        result = publisher.publish_batch(metrics)
        
        self.assertTrue(result)
        
        call_args = self.mock_cloudwatch_client.put_metric_data.call_args
        metric_data = call_args[1]['MetricData']
        
        # Check first metric dimensions
        self.assertEqual(len(metric_data[0]['Dimensions']), 2)
        dimension_dict = {d['Name']: d['Value'] for d in metric_data[0]['Dimensions']}
        self.assertEqual(dimension_dict['Component'], 'test_component')
        self.assertEqual(dimension_dict['Route'], '/api/v1/artifacts')
    
    def test_publish_batch_large_batch(self):
        """
        Test batch publication splits large batches (>20 metrics).
        """
        publisher = self.create_publisher()
        metrics = [
            {'name': f'Metric_{i}', 'value': i, 'unit': 'Count'}
            for i in range(50)
        ]
        
        result = publisher.publish_batch(metrics)
        
        self.assertTrue(result)
        self.assertEqual(self.mock_cloudwatch_client.put_metric_data.call_count, 3)
        
        first_call = self.mock_cloudwatch_client.put_metric_data.call_args_list[0]
        self.assertEqual(len(first_call[1]['MetricData']), 20)
        
        second_call = self.mock_cloudwatch_client.put_metric_data.call_args_list[1]
        self.assertEqual(len(second_call[1]['MetricData']), 20)
        
        third_call = self.mock_cloudwatch_client.put_metric_data.call_args_list[2]
        self.assertEqual(len(third_call[1]['MetricData']), 10)
    
    def test_publish_batch_empty_list(self):
        """
        Test batch publication with empty metrics list.
        """
        publisher = self.create_publisher()
        
        result = publisher.publish_batch([])
        
        self.assertTrue(result)
        self.mock_cloudwatch_client.put_metric_data.assert_not_called()
    
    def test_publish_batch_no_client(self):
        """
        Test batch publication when CloudWatch client is None.
        """
        with patch('boto3.client', side_effect=Exception("Failed")):
            publisher = CloudWatchPublisher('test_component')
            
            metrics = [{'name': 'TestMetric', 'value': 1.0}]
            result = publisher.publish_batch(metrics)
            
            self.assertFalse(result)
    
    def test_publish_batch_client_error(self):
        """
        Test batch publication handles ClientError.
        """
        self.mock_cloudwatch_client.put_metric_data.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
            'put_metric_data'
        )
        publisher = self.create_publisher()
        
        metrics = [{'name': 'TestMetric', 'value': 1.0}]
        result = publisher.publish_batch(metrics)
        
        self.assertFalse(result)
    
    def test_increment_counter_default(self):
        """
        Test incrementing counter with default value.
        """
        publisher = self.create_publisher()
        
        result = publisher.increment_counter('RequestCount')
        
        self.assertTrue(result)
        
        call_args = self.mock_cloudwatch_client.put_metric_data.call_args
        metric_data = call_args[1]['MetricData'][0]
        
        self.assertEqual(metric_data['MetricName'], 'RequestCount')
        self.assertEqual(metric_data['Value'], 1)
        self.assertEqual(metric_data['Unit'], 'Count')
    
    def test_record_latency(self):
        """
        Test recording operation latency.
        """
        publisher = self.create_publisher()
        
        result = publisher.record_latency('DatabaseQuery', 125.5)
        
        self.assertTrue(result)
        
        call_args = self.mock_cloudwatch_client.put_metric_data.call_args
        metric_data = call_args[1]['MetricData'][0]
        
        self.assertEqual(metric_data['MetricName'], 'DatabaseQueryLatency')
        self.assertEqual(metric_data['Value'], 125.5)
        self.assertEqual(metric_data['Unit'], 'Milliseconds')
    
    def test_record_latency_various_operations(self):
        """
        Test recording latency for different operations.
        """
        publisher = self.create_publisher()
        operations = [
            ('APIRequest', 50.0),
            ('ModelIngest', 5000.0),
            ('CacheRead', 5.5),
            ('S3Upload', 2500.0)
        ]
        
        for operation, latency in operations:
            result = publisher.record_latency(operation, latency)
            self.assertTrue(result)
        
        self.assertEqual(self.mock_cloudwatch_client.put_metric_data.call_count, len(operations))
    
    def test_record_error_default(self):
        """
        Test recording error with default type.
        """
        publisher = self.create_publisher()
        
        result = publisher.record_error()
        
        self.assertTrue(result)
        
        call_args = self.mock_cloudwatch_client.put_metric_data.call_args
        metric_data = call_args[1]['MetricData'][0]
        
        self.assertEqual(metric_data['MetricName'], 'ErrorRate')
        self.assertEqual(metric_data['Value'], 1)
        self.assertEqual(metric_data['Unit'], 'Count')
        
        # Check dimensions
        dimension_dict = {d['Name']: d['Value'] for d in metric_data['Dimensions']}
        self.assertEqual(dimension_dict['ErrorType'], 'Generic')
    
    def test_record_error_custom_type(self):
        """
        Test recording error with custom type.
        """
        publisher = self.create_publisher()
        
        result = publisher.record_error('ValidationError')
        
        self.assertTrue(result)
        
        call_args = self.mock_cloudwatch_client.put_metric_data.call_args
        metric_data = call_args[1]['MetricData'][0]
        
        dimension_dict = {d['Name']: d['Value'] for d in metric_data['Dimensions']}
        self.assertEqual(dimension_dict['ErrorType'], 'ValidationError')
    
    def test_record_error_various_types(self):
        """
        Test recording different error types.
        """
        publisher = self.create_publisher()
        error_types = [
            'ValidationError',
            'AuthenticationError',
            'DatabaseConnectionError',
            'TimeoutError',
            'NotFoundError'
        ]
        
        for error_type in error_types:
            result = publisher.record_error(error_type)
            self.assertTrue(result)
        
        self.assertEqual(self.mock_cloudwatch_client.put_metric_data.call_count, len(error_types))
    
    def test_mixed_operations(self):
        """
        Test mixed operations in sequence.
        """
        publisher = self.create_publisher()
        
        # Simulate a typical API request flow
        publisher.increment_counter('RequestCount')
        publisher.record_latency('APIRequest', 125.5)
        publisher.increment_counter('CacheHits')
        publisher.record_latency('DatabaseQuery', 50.0)
        
        self.assertEqual(self.mock_cloudwatch_client.put_metric_data.call_count, 4)
   
    def test_component_name_in_all_metrics(self):
        """
        Test that component name appears in all metric dimensions.
        """
        publisher = self.create_publisher()
        
        operations = [
            lambda: publisher.publish_metric('TestMetric', 1.0),
            lambda: publisher.increment_counter('Counter'),
            lambda: publisher.record_latency('Operation', 100.0),
            lambda: publisher.record_error('ErrorType')
        ]
        
        for operation in operations:
            self.mock_cloudwatch_client.reset_mock()
            operation()
            
            call_args = self.mock_cloudwatch_client.put_metric_data.call_args
            metric_data = call_args[1]['MetricData'][0]
            
            dimension_dict = {d['Name']: d['Value'] for d in metric_data['Dimensions']}
            self.assertIn('Component', dimension_dict)
            self.assertEqual(dimension_dict['Component'], 'test_component')
   
    def test_publish_metric_with_very_large_value(self):
        """
        Test publishing metric with very large value.
        """
        publisher = self.create_publisher()
        
        result = publisher.publish_metric('BytesProcessed', 1e12, 'Bytes')
        
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main()