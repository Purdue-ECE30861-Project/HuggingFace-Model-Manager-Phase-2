from fastapi import FastAPI, Header, Query, Path, Body, status
from pydantic import BaseModel, Field, field_validator, RootModel
from pydantic import BaseModel, Field, RootModel
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from enum import Enum


class ArtifactType(str, Enum):
    """Artifact category."""
    model = "model"
    dataset = "dataset"
    code = "code"

    @staticmethod
    def test_value() -> "ArtifactType":
        return ArtifactType.model


class AuditAction(str, Enum):
    """Action types for audit entries."""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DOWNLOAD = "DOWNLOAD"
    RATE = "RATE"
    AUDIT = "AUDIT"

    @staticmethod
    def test_value() -> "AuditAction":
        return AuditAction.CREATE


class TrackType(str, Enum):
    """Available implementation tracks."""
    performance = "Performance track"
    access_control = "Access control track"
    high_assurance = "High assurance track"
    other_security = "Other Security track"

    @staticmethod
    def test_value() -> "TrackType":
        return TrackType.performance


class HealthStatus(str, Enum):
    """Aggregate health classification for monitored systems."""
    ok = "ok"
    degraded = "degraded"
    critical = "critical"
    unknown = "unknown"

    @staticmethod
    def test_value() -> "HealthStatus":
        return HealthStatus.ok

# ==================== Schemas ====================

class ArtifactID(BaseModel):
    """Unique identifier for use with artifact endpoints."""
    id: str = Field(..., pattern=r'^[a-zA-Z0-9\-]+$', examples=["48472749248"])

    @staticmethod
    def test_value() -> "ArtifactID":
        return ArtifactID(id="48472749248")

class ArtifactName(BaseModel):
    """Name of an artifact."""
    name: str

    @staticmethod
    def test_value() -> "ArtifactName":
        return ArtifactName(name="Stirlitz")


class ArtifactData(BaseModel):
    """Source location for ingesting an artifact."""
    url: str = Field(..., description="Artifact source url used during ingest")

    @staticmethod
    def test_value() -> "ArtifactData":
        return ArtifactData(url="http://IAmAGoon.com")


class ArtifactMetadata(BaseModel):
    name: str = Field(..., description="Name of the artifact")
    id: str = Field(..., pattern=r'^[a-zA-Z0-9\-]+$', description="Unique identifier")
    type: ArtifactType = Field(..., description="Artifact category")

    @staticmethod
    def test_value() -> "ArtifactMetadata":
        return ArtifactMetadata(
            name="Stirlitz",
            id="48472749248",
            type=ArtifactType.test_value()
        )


class Artifact(BaseModel):
    """Artifact envelope containing metadata and ingest details."""
    metadata: ArtifactMetadata
    data: ArtifactData

    @staticmethod
    def test_value() -> "Artifact":
        return Artifact(
            metadata=ArtifactMetadata.test_value(),
            data=ArtifactData.test_value()
        )


class ArtifactQuery(BaseModel):
    """Query parameters for searching artifacts."""
    name: str = Field(..., description="Name of artifact to query") # if this is * then get all
    types: Optional[List[ArtifactType]] = Field(None, description="Optional list of artifact types to filter results")

    @staticmethod
    def test_value() -> "ArtifactQuery":
        return ArtifactQuery(
            name="Stirlitz",
            types=[ArtifactType.test_value()]
        )


class User(BaseModel):
    """User information."""
    name: str = Field(..., description="User name", examples=["Alfalfa"])
    is_admin: bool = Field(..., description="Is this user an admin?")

    @staticmethod
    def test_value() -> "User":
        return User(
            name="Stirlitz",
            is_admin=True,
        )


class UserAuthenticationInfo(BaseModel):
    """Authentication info for a user."""
    password: str = Field(..., description="Password for a user")

    @staticmethod
    def test_value() -> "UserAuthenticationInfo":
        return UserAuthenticationInfo(
            password="IAmRetepAndIAmEvil",
        )


class AuthenticationRequest(BaseModel):
    """Request for authentication."""
    user: User
    secret: UserAuthenticationInfo

    @staticmethod
    def test_value() -> "AuthenticationRequest":
        return AuthenticationRequest(
            user=User.test_value(),
            secret=UserAuthenticationInfo.test_value()
        )


class ArtifactAuditEntry(BaseModel):
    """One entry in an artifact's audit history."""
    user: User
    date: datetime = Field(..., description="Date of activity using ISO-8601 Datetime standard in UTC format")
    artifact: ArtifactMetadata
    action: AuditAction

    @staticmethod
    def test_value() -> "ArtifactAuditEntry":
        return ArtifactAuditEntry(
            user=User.test_value(),
            date=datetime(2024, 1, 15, 10, 30, 0),
            artifact=ArtifactMetadata.test_value(),
            action=AuditAction.test_value()
        )


class ArtifactCostDetails(BaseModel):
    """Cost details for a single artifact."""
    standalone_cost: Optional[float] = Field(None, description="The standalone cost of this artifact excluding dependencies")
    total_cost: float = Field(..., description="The total cost of the artifact")

    @staticmethod
    def test_value() -> "ArtifactCostDetails":
        return ArtifactCostDetails(
            standalone_cost=100.5,
            total_cost=250.75
        )


class ArtifactCost(RootModel[Dict[str, ArtifactCostDetails]]):
    """Artifact Cost aggregates the total download size (in MB)."""
    pass

    @staticmethod
    def test_value() -> "ArtifactCost":
        return ArtifactCost({"48472749248": ArtifactCostDetails.test_value()})


class ArtifactRegEx(BaseModel):
    """Regular expression query for artifacts."""
    regex: str = Field(..., description="A regular expression over artifact names and READMEs")

    @staticmethod
    def test_value() -> "ArtifactRegEx":
        return ArtifactRegEx(regex="^model.*")


class ArtifactLineageNode(BaseModel):
    """A single node in an artifact lineage graph."""
    artifact_id: str = Field(..., pattern=r'^[a-zA-Z0-9\-]+$', description="Unique identifier for the node")
    name: str = Field(..., description="Human-readable label for the node", examples=["audience-classifier"])
    source: str = Field(..., description="Provenance for how the node was discovered", examples=["config_json"])
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata captured for lineage analysis")

    @staticmethod
    def test_value() -> "ArtifactLineageNode":
        return ArtifactLineageNode(
            artifact_id="48472749248",
            name="audience-classifier",
            source="config_json",
            metadata={"key": "value"}
        )


class ArtifactLineageEdge(BaseModel):
    """Directed relationship between two lineage nodes."""
    from_node_artifact_id: str = Field(..., pattern=r'^[a-zA-Z0-9\-]+$', description="Identifier of the upstream node")
    to_node_artifact_id: str = Field(..., pattern=r'^[a-zA-Z0-9\-]+$', description="Identifier of the downstream node")
    relationship: str = Field(..., description="Qualitative description of the edge", examples=["fine_tuning_dataset"])

    @staticmethod
    def test_value() -> "ArtifactLineageEdge":
        return ArtifactLineageEdge(
            from_node_artifact_id="48472749248",
            to_node_artifact_id="98765432109",
            relationship="fine_tuning_dataset"
        )


class ArtifactLineageGraph(BaseModel):
    """Complete lineage graph for an artifact."""
    nodes: List[ArtifactLineageNode] = Field(..., description="Nodes participating in the lineage graph")
    edges: List[ArtifactLineageEdge] = Field(..., description="Directed edges describing lineage relationships")

    @staticmethod
    def test_value() -> "ArtifactLineageGraph":
        return ArtifactLineageGraph(
            nodes=[ArtifactLineageNode.test_value()],
            edges=[ArtifactLineageEdge.test_value()]
        )


class SimpleLicenseCheckRequest(BaseModel):
    """Request payload for artifact license compatibility analysis."""
    github_url: str = Field(..., description="GitHub repository url to evaluate")

    @staticmethod
    def test_value() -> "SimpleLicenseCheckRequest":
        return SimpleLicenseCheckRequest(github_url="https://github.com/example/repo")


class SizeScore(BaseModel):
    """Size suitability scores for common deployment targets."""
    raspberry_pi: float = Field(..., description="Size score for Raspberry Pi class devices")
    jetson_nano: float = Field(..., description="Size score for Jetson Nano deployments")
    desktop_pc: float = Field(..., description="Size score for desktop deployments")
    aws_server: float = Field(..., description="Size score for cloud server deployments")

    @staticmethod
    def test_value() -> "SizeScore":
        return SizeScore(
            raspberry_pi=0.5,
            jetson_nano=0.7,
            desktop_pc=0.9,
            aws_server=1.0
        )


class ModelRating(BaseModel):
    """Model rating summary generated by the evaluation service."""
    name: str = Field(..., description="Human-friendly label for the evaluated model")
    category: str = Field(..., description="Model category assigned during evaluation")
    net_score: float = Field(..., description="Overall score synthesizing all metrics")
    net_score_latency: float = Field(..., description="Time (seconds) required to compute net_score")
    ramp_up_time: float = Field(..., description="Ease-of-adoption rating for the model")
    ramp_up_time_latency: float = Field(..., description="Time (seconds) required to compute ramp_up_time")
    bus_factor: float = Field(..., description="Team redundancy score for the upstream project")
    bus_factor_latency: float = Field(..., description="Time (seconds) required to compute bus_factor")
    performance_claims: float = Field(..., description="Alignment between stated and observed performance")
    performance_claims_latency: float = Field(..., description="Time (seconds) required to compute performance_claims")
    license: float = Field(..., description="Licensing suitability score")
    license_latency: float = Field(..., description="Time (seconds) required to compute license")
    dataset_and_code_score: float = Field(..., description="Availability and quality of accompanying datasets and code")
    dataset_and_code_score_latency: float = Field(..., description="Time (seconds) required to compute dataset_and_code_score")
    dataset_quality: float = Field(..., description="Quality rating for associated datasets")
    dataset_quality_latency: float = Field(..., description="Time (seconds) required to compute dataset_quality")
    code_quality: float = Field(..., description="Quality rating for provided code artifacts")
    code_quality_latency: float = Field(..., description="Time (seconds) required to compute code_quality")
    reproducibility: float = Field(..., description="Likelihood that reported results can be reproduced")
    reproducibility_latency: float = Field(..., description="Time (seconds) required to compute reproducibility")
    reviewedness: float = Field(..., description="Measure of peer or community review coverage")
    reviewedness_latency: float = Field(..., description="Time (seconds) required to compute reviewedness")
    tree_score: float = Field(..., description="Supply-chain health score for model dependencies")
    tree_score_latency: float = Field(..., description="Time (seconds) required to compute tree_score")
    size_score: SizeScore = Field(..., description="Size suitability scores for common deployment targets")
    size_score_latency: float = Field(..., description="Time (seconds) required to compute size_score")

    @staticmethod
    def test_value() -> "ModelRating":
        return ModelRating(
            name="Stirlitz",
            category="text-generation",
            net_score=0.85,
            net_score_latency=1.2,
            ramp_up_time=0.75,
            ramp_up_time_latency=0.5,
            bus_factor=0.65,
            bus_factor_latency=0.8,
            performance_claims=0.90,
            performance_claims_latency=1.5,
            license=1.0,
            license_latency=0.3,
            dataset_and_code_score=0.80,
            dataset_and_code_score_latency=1.0,
            dataset_quality=0.85,
            dataset_quality_latency=0.9,
            code_quality=0.75,
            code_quality_latency=0.7,
            reproducibility=0.70,
            reproducibility_latency=2.0,
            reviewedness=0.60,
            reviewedness_latency=0.6,
            tree_score=0.88,
            tree_score_latency=1.1,
            size_score=SizeScore.test_value(),
            size_score_latency=0.4
        )


class TracksResponse(BaseModel):
    """Response for planned tracks."""
    plannedTracks: List[TrackType] = Field(..., description="List of tracks the student plans to implement")

    @staticmethod
    def test_value() -> "TracksResponse":
        return TracksResponse(plannedTracks=[TrackType.test_value()])


# ==================== Health-Related Schemas ====================

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
