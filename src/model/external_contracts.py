from pydantic import BaseModel, Field, RootModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ArtifactType(str, Enum):
    """Artifact category."""
    model = "model"
    dataset = "dataset"
    code = "code"


class AuditAction(str, Enum):
    """Action types for audit entries."""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DOWNLOAD = "DOWNLOAD"
    RATE = "RATE"
    AUDIT = "AUDIT"


class TrackType(str, Enum):
    """Available implementation tracks."""
    performance = "Performance track"
    access_control = "Access control track"
    high_assurance = "High assurance track"
    other_security = "Other Security track"


# ==================== Schemas ====================

class ArtifactID(BaseModel):
    """Unique identifier for use with artifact endpoints."""
    id: str = Field(..., pattern=r'^[a-zA-Z0-9\-]+$', examples=["48472749248"])


class ArtifactName(BaseModel):
    """Name of an artifact."""
    name: str


class ArtifactData(BaseModel):
    """Source location for ingesting an artifact."""
    url: str = Field(..., description="Artifact source url used during ingest")


class ArtifactMetadata(BaseModel):
    """The name and version are used as a unique identifier pair when uploading an artifact."""
    name: str = Field(..., description="Name of the artifact")
    version: str = Field(..., description="Artifact version", pattern=r"^(?:\d+\.\d+\.\d+-\d+\.\d+\.\d+|(?:\^|~)\d+\.\d+\.\d+|\d+\.\d+\.\d+)$", examples=["1.2.3"])
    id: str = Field(..., pattern=r'^[a-zA-Z0-9\-]+$', description="Unique identifier")
    type: ArtifactType = Field(..., description="Artifact category")


class Artifact(BaseModel):
    """Artifact envelope containing metadata and ingest details."""
    metadata: ArtifactMetadata
    data: ArtifactData


class ArtifactQuery(BaseModel):
    """Query parameters for searching artifacts."""
    name: str = Field(..., description="Name of artifact to query")
    version: Optional[str] = Field(None, description="Semver range (Exact, Bounded range, Carat, Tilde)")
    types: Optional[List[ArtifactType]] = Field(None, description="Optional list of artifact types to filter results")


class User(BaseModel):
    """User information."""
    name: str = Field(..., description="User name", examples=["Alfalfa"])
    is_admin: bool = Field(..., description="Is this user an admin?")


class UserAuthenticationInfo(BaseModel):
    """Authentication info for a user."""
    password: str = Field(..., description="Password for a user")


class AuthenticationRequest(BaseModel):
    """Request for authentication."""
    user: User
    secret: UserAuthenticationInfo


class ArtifactAuditEntry(BaseModel):
    """One entry in an artifact's audit history."""
    user: User
    date: datetime = Field(..., description="Date of activity using ISO-8601 Datetime standard in UTC format")
    artifact: ArtifactMetadata
    action: AuditAction


class ArtifactCostDetails(BaseModel):
    """Cost details for a single artifact."""
    standalone_cost: Optional[float] = Field(None, description="The standalone cost of this artifact excluding dependencies")
    total_cost: float = Field(..., description="The total cost of the artifact")


class ArtifactCost(RootModel[Dict[str, ArtifactCostDetails]]):
    """Artifact Cost aggregates the total download size (in MB)."""
    pass


class ArtifactRegEx(BaseModel):
    """Regular expression query for artifacts."""
    regex: str = Field(..., description="A regular expression over artifact names and READMEs")


class ArtifactLineageNode(BaseModel):
    """A single node in an artifact lineage graph."""
    artifact_id: str = Field(..., pattern=r'^[a-zA-Z0-9\-]+$', description="Unique identifier for the node")
    name: str = Field(..., description="Human-readable label for the node", examples=["audience-classifier"])
    version: str = Field(..., description="Version string associated with the node", examples=["0.3.0"])
    source: str = Field(..., description="Provenance for how the node was discovered", examples=["config_json"])
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata captured for lineage analysis")


class ArtifactLineageEdge(BaseModel):
    """Directed relationship between two lineage nodes."""
    from_node_artifact_id: str = Field(..., pattern=r'^[a-zA-Z0-9\-]+$', description="Identifier of the upstream node")
    to_node_artifact_id: str = Field(..., pattern=r'^[a-zA-Z0-9\-]+$', description="Identifier of the downstream node")
    relationship: str = Field(..., description="Qualitative description of the edge", examples=["fine_tuning_dataset"])


class ArtifactLineageGraph(BaseModel):
    """Complete lineage graph for an artifact."""
    nodes: List[ArtifactLineageNode] = Field(..., description="Nodes participating in the lineage graph")
    edges: List[ArtifactLineageEdge] = Field(..., description="Directed edges describing lineage relationships")


class SimpleLicenseCheckRequest(BaseModel):
    """Request payload for artifact license compatibility analysis."""
    github_url: str = Field(..., description="GitHub repository url to evaluate")


class SizeScore(BaseModel):
    """Size suitability scores for common deployment targets."""
    raspberry_pi: float = Field(..., description="Size score for Raspberry Pi class devices")
    jetson_nano: float = Field(..., description="Size score for Jetson Nano deployments")
    desktop_pc: float = Field(..., description="Size score for desktop deployments")
    aws_server: float = Field(..., description="Size score for cloud server deployments")


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


class TracksResponse(BaseModel):
    """Response for planned tracks."""
    plannedTracks: List[TrackType] = Field(..., description="List of tracks the student plans to implement")
