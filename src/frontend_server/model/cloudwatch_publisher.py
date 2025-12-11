import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class CloudWatchPublisher:
    """
    Publishes application metrics to CloudWatch for health monitoring.
    """
    
    def __init__(self, component_name: str):
        """
        Initialize publisher for a specific component.
        
        Args:
            component_name: Name of the component (e.g., 'api_gateway', 'model_ingest')
        """
        self.component_name = component_name
        self.namespace = os.getenv("CLOUDWATCH_NAMESPACE", "ECE461/ModelRegistry")
        self.region = os.getenv("AWS_REGION", "us-east-2")
        
        try:
            self.cloudwatch = boto3.client('cloudwatch', region_name=self.region)
            logger.info(f"CloudWatch publisher initialized for {component_name}")
        except Exception as e:
            logger.warning(f"Failed to initialize CloudWatch publisher: {e}")
            self.cloudwatch = None
    
    def publish_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "None",
        dimensions: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Publish a single metric to CloudWatch.
        
        Args:
            metric_name: Name of the metric (e.g., 'RequestCount', 'Latency')
            value: Numeric value of the metric
            unit: CloudWatch unit (Count, Milliseconds, Bytes, etc.)
            dimensions: Additional dimensions for the metric
            
        Returns:
            True if successful, False otherwise
        """
        if not self.cloudwatch:
            logger.warning("CloudWatch client not initialized, skipping metric publication")
            return False
        
        try:
            metric_dimensions = [
                {'Name': 'Component', 'Value': self.component_name}
            ]
            
            if dimensions:
                for key, val in dimensions.items():
                    metric_dimensions.append({'Name': key, 'Value': val})
            
            # Put metric data
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=[
                    {
                        'MetricName': metric_name,
                        'Value': value,
                        'Unit': unit,
                        'Timestamp': datetime.now(timezone.utc),
                        'Dimensions': metric_dimensions
                    }
                ]
            )
            
            logger.debug(f"Published metric {metric_name}={value} for {self.component_name}")
            return True
            
        except ClientError as e:
            logger.warning(f"Failed to publish metric {metric_name}: {e}")
            return False
    
    def publish_batch(self, metrics: List[Dict]) -> bool:
        """
        Publish multiple metrics in a single API call (more efficient).
        
        Args:
            metrics: List of metric dictionaries with keys:
                - name: Metric name
                - value: Metric value
                - unit: (optional) CloudWatch unit
                - dimensions: (optional) Additional dimensions
        
        Returns:
            True if successful, False otherwise
        """
        if not self.cloudwatch:
            return False
        
        try:
            metric_data = []
            
            for metric in metrics:
                # Build dimensions
                dimensions = [
                    {'Name': 'Component', 'Value': self.component_name}
                ]
                
                if 'dimensions' in metric:
                    for key, val in metric['dimensions'].items():
                        dimensions.append({'Name': key, 'Value': val})
                
                # Add to batch
                metric_data.append({
                    'MetricName': metric['name'],
                    'Value': metric['value'],
                    'Unit': metric.get('unit', 'None'),
                    'Timestamp': datetime.now(timezone.utc),
                    'Dimensions': dimensions
                })
            
            for i in range(0, len(metric_data), 20):
                batch = metric_data[i:i+20]
                self.cloudwatch.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=batch
                )
            
            logger.debug(f"Published {len(metrics)} metrics for {self.component_name}")
            return True
            
        except ClientError as e:
            logger.warning(f"Failed to publish metric batch: {e}")
            return False
    
    def increment_counter(self, counter_name: str, value: int = 1) -> bool:
        """
        Increment a counter metric.
        
        Args:
            counter_name: Name of the counter
            value: Amount to increment by
            
        Returns:
            True if successful
        """
        return self.publish_metric(counter_name, value, unit="Count")
    
    def record_latency(self, operation: str, latency_ms: float) -> bool:
        """
        Record operation latency.
        
        Args:
            operation: Name of the operation
            latency_ms: Latency in milliseconds
            
        Returns:
            True if successful
        """
        return self.publish_metric(
            f"{operation}Latency",
            latency_ms,
            unit="Milliseconds"
        )
    
    def record_error(self, error_type: str = "Generic") -> bool:
        """
        Record an error occurrence.
        
        Args:
            error_type: Type of error
            
        Returns:
            True if successful
        """
        return self.publish_metric(
            "ErrorRate",
            1,
            unit="Count",
            dimensions={'ErrorType': error_type}
        )