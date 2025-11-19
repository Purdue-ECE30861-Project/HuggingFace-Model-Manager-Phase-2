from pydantic import BaseModel, Field
from typing import Dict, Union, Optional, List
from datetime import datetime
from enum import Enum


class HealthStatus(str, Enum):
    """Aggregate health classification for monitored systems."""
    ok = "ok"
    degraded = "degraded"
    critical = "critical"
    unknown = "unknown"

    @staticmethod
    def test_value() -> "HealthStatus":
        return HealthStatus.ok


class HealthMetricValue(BaseModel):
    """Flexible representation for metric values."""
    value: Union[int, float, str, bool]

    @staticmethod
    def test_value() -> "HealthMetricValue":
        return HealthMetricValue(value=42)


class HealthMetricMap(BaseModel):
    """Arbitrary metric key/value pairs describing component performance."""
    metrics: Dict[str, HealthMetricValue] = Field(..., description="Component performance metrics")

    @staticmethod
    def test_value() -> "HealthMetricMap":
        return HealthMetricMap(metrics={"cpu_usage": HealthMetricValue(value=0.75)})


class HealthTimelineEntry(BaseModel):
    """Time-series datapoint for a component metric."""
    bucket: datetime = Field(..., description="Start timestamp of the sampled bucket (UTC)")
    value: float = Field(..., description="Observed value for the bucket (e.g., requests per minute)")
    unit: Optional[str] = Field(None, description="Unit associated with the metric value")

    @staticmethod
    def test_value() -> "HealthTimelineEntry":
        return HealthTimelineEntry(
            bucket=datetime(2024, 1, 15, 10, 30, 0),
            value=125.5,
            unit="requests/min"
        )


class HealthIssue(BaseModel):
    """Outstanding issue or alert impacting a component."""
    code: str = Field(..., description="Machine readable issue identifier")
    severity: str = Field(..., description="Issue severity", enum=["info", "warning", "error"])
    summary: str = Field(..., description="Short description of the issue")
    details: Optional[str] = Field(None, description="Extended diagnostic detail and suggested remediation")

    @staticmethod
    def test_value() -> "HealthIssue":
        return HealthIssue(
            code="HIGH_MEMORY_USAGE",
            severity="warning",
            summary="Memory usage above 80%",
            details="Consider scaling up or optimizing memory usage"
        )


class HealthLogReference(BaseModel):
    """Link or descriptor for logs relevant to a health component."""
    label: str = Field(..., description="Human readable log descriptor")
    url: str = Field(..., description="Direct link to download or tail the referenced log")
    tail_available: Optional[bool] = Field(None, description="Indicates whether streaming tail access is supported")
    last_updated_at: Optional[datetime] = Field(None, description="Timestamp of the latest log entry available")

    @staticmethod
    def test_value() -> "HealthLogReference":
        return HealthLogReference(
            label="Ingest Worker 1",
            url="http://logs.example.com/worker1.log",
            tail_available=True,
            last_updated_at=datetime(2024, 1, 15, 10, 30, 0)
        )


class HealthRequestSummary(BaseModel):
    """Request activity observed within the health window."""
    window_start: datetime = Field(..., description="Beginning of the aggregation window (UTC)")
    window_end: datetime = Field(..., description="End of the aggregation window (UTC)")
    total_requests: Optional[int] = Field(None, description="Number of API requests served during the window", ge=0)
    per_route: Optional[Dict[str, int]] = Field(None, description="Request counts grouped by API route")
    per_artifact_type: Optional[Dict[str, int]] = Field(None, description="Request counts grouped by artifact type")
    unique_clients: Optional[int] = Field(None, description="Distinct API clients observed in the window", ge=0)

    @staticmethod
    def test_value() -> "HealthRequestSummary":
        return HealthRequestSummary(
            window_start=datetime(2024, 1, 15, 10, 0, 0),
            window_end=datetime(2024, 1, 15, 11, 0, 0),
            total_requests=150,
            per_route={"/artifacts": 75, "/health": 25},
            per_artifact_type={"model": 50, "dataset": 25},
            unique_clients=10
        )


class HealthComponentBrief(BaseModel):
    """Lightweight component-level status summary."""
    id: str = Field(..., description="Stable identifier for the component")
    display_name: Optional[str] = Field(None, description="Human readable component name")
    status: HealthStatus = Field(..., description="Component health status")
    issue_count: Optional[int] = Field(None, description="Number of outstanding issues", ge=0)
    last_event_at: Optional[datetime] = Field(None, description="Last significant event timestamp for the component")

    @staticmethod
    def test_value() -> "HealthComponentBrief":
        return HealthComponentBrief(
            id="ingest-worker",
            display_name="Ingest Worker",
            status=HealthStatus.test_value(),
            issue_count=1,
            last_event_at=datetime(2024, 1, 15, 10, 30, 0)
        )


class HealthComponentDetail(BaseModel):
    """Detailed status, metrics, and log references for a component."""
    id: str = Field(..., description="Stable identifier for the component")
    display_name: Optional[str] = Field(None, description="Human readable component name")
    status: HealthStatus = Field(..., description="Component health status")
    observed_at: datetime = Field(..., description="Timestamp when data for this component was last collected (UTC)")
    description: Optional[str] = Field(None, description="Overview of the component's responsibility")
    metrics: Optional[HealthMetricMap] = Field(None, description="Component performance metrics")
    issues: Optional[List[HealthIssue]] = Field(None, description="Outstanding issues")
    timeline: Optional[List[HealthTimelineEntry]] = Field(None, description="Time-series data")
    logs: Optional[List[HealthLogReference]] = Field(None, description="Log references")

    @staticmethod
    def test_value() -> "HealthComponentDetail":
        return HealthComponentDetail(
            id="ingest-worker",
            display_name="Ingest Worker",
            status=HealthStatus.test_value(),
            observed_at=datetime(2024, 1, 15, 10, 30, 0),
            description="Processes artifact ingestion requests",
            metrics=HealthMetricMap.test_value(),
            issues=[HealthIssue.test_value()],
            timeline=[HealthTimelineEntry.test_value()],
            logs=[HealthLogReference.test_value()]
        )


class HealthSummaryResponse(BaseModel):
    """High-level snapshot summarizing registry health and recent activity."""
    status: HealthStatus = Field(..., description="Overall health status")
    checked_at: datetime = Field(..., description="Timestamp when the health snapshot was generated (UTC)")
    window_minutes: int = Field(..., description="Size of the trailing observation window in minutes", ge=5)
    uptime_seconds: Optional[int] = Field(None, description="Seconds the registry API has been running", ge=0)
    version: Optional[str] = Field(None, description="Running service version or git SHA when available")
    request_summary: Optional[HealthRequestSummary] = Field(None, description="Request activity summary")
    components: Optional[List[HealthComponentBrief]] = Field(None, description="Component status rollup")
    logs: Optional[List[HealthLogReference]] = Field(None, description="Quick links to recent log files")

    @staticmethod
    def test_value() -> "HealthSummaryResponse":
        return HealthSummaryResponse(
            status=HealthStatus.test_value(),
            checked_at=datetime(2024, 1, 15, 10, 30, 0),
            window_minutes=60,
            uptime_seconds=3600,
            version="v1.0.0",
            request_summary=HealthRequestSummary.test_value(),
            components=[HealthComponentBrief.test_value()],
            logs=[HealthLogReference.test_value()]
        )


class HealthComponentCollection(BaseModel):
    """Detailed health diagnostics broken down per component."""
    components: List[HealthComponentDetail] = Field(..., description="Detailed component information")
    generated_at: datetime = Field(..., description="Timestamp when the component report was created (UTC)")
    window_minutes: Optional[int] = Field(None, description="Observation window applied to metrics", ge=5)

    @staticmethod
    def test_value() -> "HealthComponentCollection":
        return HealthComponentCollection(
            components=[HealthComponentDetail.test_value()],
            generated_at=datetime(2024, 1, 15, 10, 30, 0),
            window_minutes=60
        )
