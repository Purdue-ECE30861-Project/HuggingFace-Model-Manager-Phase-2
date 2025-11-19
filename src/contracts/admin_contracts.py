from pydantic import BaseModel, Field
from typing import List
from enum import Enum


class TrackType(str, Enum):
    """Available implementation tracks."""
    performance = "Performance track"
    access_control = "Access control track"
    high_assurance = "High assurance track"
    other_security = "Other Security track"

    @staticmethod
    def test_value() -> "TrackType":
        return TrackType.performance


class TracksResponse(BaseModel):
    """Response for planned tracks."""
    plannedTracks: List[TrackType] = Field(..., description="List of tracks the student plans to implement")

    @staticmethod
    def test_value() -> "TracksResponse":
        return TracksResponse(plannedTracks=[TrackType.test_value()])