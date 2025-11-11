from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


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