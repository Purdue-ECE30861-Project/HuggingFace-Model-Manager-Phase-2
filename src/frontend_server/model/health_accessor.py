from src.contracts.health_contracts import (
    HealthComponentCollection,
    HealthComponentDetail,
    HealthStatus,
    HealthMetricMap,
    HealthMetricValue,
    HealthIssue,
    HealthTimelineEntry,
    HealthLogReference,
)
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

class HealthAccessor:
    def __init__(self):
        self.region = os.getenv("AWS_REGION", "us-east-2")
        self.log_group = os.getenv("CLOUDWATCH_LOG_GROUP", "/ece461/project")
        self.namespace = os.getenv("CLOUDWATCH_NAMESPACE", "ECE461/ModelRegistry")

        try:
            self.cloudwatch = boto3.client('cloudwatch', region_name=self.region)
            self.logs_client = boto3.client('logs', region_name=self.region)
            logger.info("CloudWatch clients initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize CloudWatch clients: {e}")
            self.cloudwatch = None
            self.logs_client = None
            
        # Component definitions
        self.components = {
            "api_gateway": {
                "display_name": "API Gateway",
                "description": "REST API request routing and validation",
                "metrics": ["RequestCount", "Latency", "ErrorRate"],
                "log_filter": "api"
            },
            "model_ingest": {
                "display_name": "Model Ingest Service",
                "description": "HuggingFace model ingestion pipeline",
                "metrics": ["IngestCount", "IngestLatency", "IngestErrors"],
                "log_filter": "ingest"
            },
            "scoring_engine": {
                "display_name": "Model Scoring Engine",
                "description": "Computes model quality metrics",
                "metrics": ["ScoringJobs", "ScoringLatency", "MetricErrors"],
                "log_filter": "scoring"
            },
            "database": {
                "display_name": "Database Layer",
                "description": "Model metadata and artifact storage",
                "metrics": ["QueryCount", "QueryLatency", "ConnectionErrors"],
                "log_filter": "database"
            },
            "cache_layer": {
                "display_name": "Cache Layer",
                "description": "Redis cache for query optimization",
                "metrics": ["CacheHits", "CacheMisses", "CacheLatency"],
                "log_filter": "cache"
            }
        }
            
    def is_alive(self) -> bool:
        """
        Lightweight health check - tests CloudWatch connectivity.
        Returns True if service is healthy, False otherwise.
        """
        if not self.cloudwatch:
            logger.warning("CloudWatch client not initialized")
            return False
            
        try:
            # Test CloudWatch connectivity
            self.cloudwatch.list_metrics(
                Namespace=self.namespace,
                MaxRecords=1
            )
            return True
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    def component_health(
        self, 
        window: int, 
        include_timeline: bool
    ) -> HealthComponentCollection:
        """
        Get detailed health for all components.
            
        Returns:
            HealthComponentCollection with all component details
        """
        window = max(5, min(1440, window))
        
        # Calculate time range
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=window)
        
        components = []
        
        for component_id, component_info in self.components.items():
            try:
                component_detail = self.get_component_detail(
                    component_id,
                    component_info,
                    start_time,
                    end_time,
                    include_timeline
                )
                components.append(component_detail)
            except Exception as e:
                logger.warning(f"Error getting health for component {component_id}: {e}")
                # Add component with unknown status on error
                components.append(self.create_error_component(
                    component_id, 
                    component_info,
                    str(e)
                ))
        
        return HealthComponentCollection(
            components=components,
            generated_at=end_time,
            window_minutes=window
        )
        
    def get_component_detail(
        self,
        component_id: str,
        component_info: Dict,
        start_time: datetime,
        end_time: datetime,
        include_timeline: bool
    ) -> HealthComponentDetail:
        """
        Get detailed health information for a single component.
        """
        # Fetch metrics from CloudWatch
        metrics_data = self.fetch_component_metrics(
            component_id,
            component_info["metrics"],
            start_time,
            end_time
        )
        
        # Determine component status based on metrics
        status, issues = self.analyze_component_health(component_id, metrics_data)
        
        # Build metrics map
        metrics_map = None
        if metrics_data:
            metrics_map = HealthMetricMap(
                metrics={
                    metric_name: HealthMetricValue(value=data["current"])
                    for metric_name, data in metrics_data.items()
                }
            )
        
        # Build timeline 
        timeline = None
        if include_timeline:
            timeline = self.build_timeline(component_id, metrics_data, start_time, end_time)
        
        # Get log references
        logs = self.get_log_references(component_id, component_info.get("log_filter"))
        
        return HealthComponentDetail(
            id=component_id,
            display_name=component_info["display_name"],
            status=status,
            observed_at=end_time,
            description=component_info["description"],
            metrics=metrics_map,
            issues=issues if issues else None,
            timeline=timeline if timeline else None,
            logs=logs if logs else None
        )

    def fetch_component_metrics(
        self,
        component_id: str,
        metric_names: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Dict]:
        """
        Fetch metrics from CloudWatch for a component.
        
        Returns:
            Dict mapping metric names to their data (current value, stats, etc.)
        """
        if not self.cloudwatch:
            logger.warning("CloudWatch not available, returning empty metrics")
            return {}
        
        metrics_data = {}
        
        for metric_name in metric_names:
            try:
                response = self.cloudwatch.get_metric_statistics(
                    Namespace=self.namespace,
                    MetricName=metric_name,
                    Dimensions=[
                        {'Name': 'Component', 'Value': component_id}
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=300,
                    Statistics=['Average', 'Sum', 'Maximum', 'Minimum']
                )
                
                datapoints = response.get('Datapoints', [])
                
                if datapoints:
                    datapoints.sort(key=lambda x: x['Timestamp'])
                    latest = datapoints[-1]
                    
                    metrics_data[metric_name] = {
                        "current": latest.get('Average', 0),
                        "max": max(d.get('Maximum', 0) for d in datapoints),
                        "min": min(d.get('Minimum', 0) for d in datapoints),
                        "sum": sum(d.get('Sum', 0) for d in datapoints),
                        "datapoints": datapoints
                    }
                else:
                    # No data available
                    metrics_data[metric_name] = {
                        "current": 0,
                        "max": 0,
                        "min": 0,
                        "sum": 0,
                        "datapoints": []
                    }
                    
            except ClientError as e:
                logger.warning(f"Failed to fetch metric {metric_name} for {component_id}: {e}")
                metrics_data[metric_name] = {
                    "current": 0,
                    "max": 0,
                    "min": 0,
                    "sum": 0,
                    "datapoints": []
                }
        
        return metrics_data

    def analyze_component_health(
        self,
        component_id: str,
        metrics_data: Dict[str, Dict]
    ) -> tuple[HealthStatus, List[HealthIssue]]:
        """
        Analyze metrics to determine component health status and issues.
        
        Returns:
            Tuple of (status, list of issues)
        """
        issues = []
        status = HealthStatus.ok
        
        # Define thresholds for different components
        thresholds = {
            "api_gateway": {
                "ErrorRate": {"warning": 0.05, "critical": 0.10},
                "Latency": {"warning": 1000, "critical": 2000}
            },
            "model_ingest": {
                "IngestErrors": {"warning": 5, "critical": 10},
                "IngestLatency": {"warning": 30000, "critical": 60000}
            },
            "scoring_engine": {
                "MetricErrors": {"warning": 3, "critical": 10},
                "ScoringLatency": {"warning": 10000, "critical": 20000}
            },
            "database": {
                "ConnectionErrors": {"warning": 5, "critical": 15},
                "QueryLatency": {"warning": 500, "critical": 1000}
            },
            "cache_layer": {
                "CacheMisses": {"warning": 100, "critical": 500}
            }
        }
        
        component_thresholds = thresholds.get(component_id, {})
        
        for metric_name, data in metrics_data.items():
            if metric_name not in component_thresholds:
                continue
            
            current_value = data["current"]
            metric_threshold = component_thresholds[metric_name]
            
            # Check critical threshold
            if current_value >= metric_threshold.get("critical", float('inf')):
                status = HealthStatus.critical
                issues.append(HealthIssue(
                    code=f"{metric_name.upper()}_CRITICAL",
                    severity="error",
                    summary=f"{metric_name} is critically high: {current_value:.2f}",
                    details=f"Current value {current_value:.2f} exceeds critical threshold {metric_threshold['critical']}. Immediate action required."
                ))
            # Check warning threshold
            elif current_value >= metric_threshold.get("warning", float('inf')):
                if status == HealthStatus.ok:
                    status = HealthStatus.degraded
                issues.append(HealthIssue(
                    code=f"{metric_name.upper()}_WARNING",
                    severity="warning",
                    summary=f"{metric_name} is elevated: {current_value:.2f}",
                    details=f"Current value {current_value:.2f} exceeds warning threshold {metric_threshold['warning']}. Monitor closely."
                ))
        
        # Check for no data
        if not any(data["datapoints"] for data in metrics_data.values()):
            status = HealthStatus.unknown
            issues.append(HealthIssue(
                code="NO_METRICS_DATA",
                severity="warning",
                summary="No metrics data available",
                details="CloudWatch has no recent data for this component. It may not be reporting metrics."
            ))
        
        return status, issues
    
    def build_timeline(
        self,
        component_id: str,
        metrics_data: Dict[str, Dict],
        start_time: datetime,
        end_time: datetime
    ) -> List[HealthTimelineEntry]:
        """
        Build time-series data for component metrics.
        """
        timeline = []
        
        # Use the first metric with data for timeline
        for metric_name, data in metrics_data.items():
            datapoints = data.get("datapoints", [])
            if datapoints:
                for dp in datapoints:
                    timeline.append(HealthTimelineEntry(
                        bucket=dp['Timestamp'],
                        value=dp.get('Average', 0),
                        unit=metric_name
                    ))
                break
        
        timeline.sort(key=lambda x: x.bucket)
        
        return timeline
    
    def get_log_references(
        self, 
        component_id: str,
        log_filter: Optional[str] = None
    ) -> List[HealthLogReference]:
        """
        Get CloudWatch log stream references for a component.
        
        Args:
            component_id: ID of the component
            log_filter: Optional filter string to match in log stream names
        """
        if not self.logs_client:
            return []
        
        try:
            # List recent log streams
            response = self.logs_client.describe_log_streams(
                logGroupName=self.log_group,
                orderBy='LastEventTime',
                descending=True,
                limit=10
            )
            
            log_refs = []
            for stream in response.get('logStreams', []):
                stream_name = stream['logStreamName']
                
                # Filter by component if filter provided
                if log_filter and log_filter.lower() not in stream_name.lower():
                    continue
                
                last_event = stream.get('lastEventTimestamp')
                
                # Create log reference
                log_refs.append(HealthLogReference(
                    label=f"{component_id} - {stream_name}",
                    url=f"https://console.aws.amazon.com/cloudwatch/home?region={self.region}#logsV2:log-groups/log-group/{self.log_group.replace('/', '$252F')}/log-events/{stream_name.replace('/', '$252F')}",
                    tail_available=True,
                    last_updated_at=datetime.fromtimestamp(last_event / 1000, tz=timezone.utc) if last_event else None
                ))
                
                # Limit to 3 log references per component
                if len(log_refs) >= 3:
                    break
            
            return log_refs
            
        except ClientError as e:
            logger.warning(f"Failed to get log references for {component_id}: {e}")
            return []
    
    def create_error_component(
        self,
        component_id: str,
        component_info: Dict,
        error_message: str = None
    ) -> HealthComponentDetail:
        """
        Create a component detail with error status when health check fails.
        """
        details = "An error occurred while fetching health metrics for this component."
        if error_message:
            details += f" Error: {error_message}"
            
        return HealthComponentDetail(
            id=component_id,
            display_name=component_info["display_name"],
            status=HealthStatus.unknown,
            observed_at=datetime.now(timezone.utc),
            description=component_info["description"],
            metrics=None,
            issues=[HealthIssue(
                code="HEALTH_CHECK_FAILED",
                severity="error",
                summary="Failed to retrieve component health",
                details=details
            )],
            timeline=None,
            logs=None
        )
