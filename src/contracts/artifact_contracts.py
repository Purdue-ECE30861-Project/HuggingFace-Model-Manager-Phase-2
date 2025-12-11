import time

from pydantic import BaseModel, Field, RootModel, model_validator
from typing import List, Optional, Dict, Any, TypeVar, Generic
from enum import Enum
from abc import ABC, abstractmethod
from pathlib import Path


class ArtifactType(str, Enum):
    """Artifact category."""
    model = "model"
    dataset = "dataset"
    code = "code"

    @staticmethod
    def test_value() -> "ArtifactType":
        return ArtifactType.model

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
    download_url: str = Field("", description="The download link provided by server to get preserved artifiact bundle. Present in response only")

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


class ArtifactCost(BaseModel):
    """Artifact Cost aggregates the total download size (in MB)."""
    standalone_cost: float
    total_cost: float

    @staticmethod
    def test_value() -> "ArtifactCost":
        return ArtifactCost(standalone_cost=100.5, total_cost=250.75)


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

    def __lt__(self, other) -> bool:
        if isinstance(other, float):
            for value in self.__dict__.values():
                if value < other:
                    return True
            return False
        else:
            return False

    def __gt__(self, other) -> bool:
        if isinstance(other, float):
            for value in self.__dict__.values():
                if value > other:
                    return True
            return False
        else:
            return False

    def __mul__(self, other):
        if isinstance(other, float):
            values = list(self.__dict__.values())
            avg = sum(values) / len(values)
            return avg * other

    def __rmul__(self, other):
        return self.__mul__(other)