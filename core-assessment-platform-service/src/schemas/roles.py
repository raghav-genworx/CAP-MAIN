"""Role schemas for platform authorization."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class UserRole(StrEnum):
    """Supported application roles."""

    RECRUITER = "recruiter"


class UserRoleRecord(BaseModel):
    """Role assignment stored in Firebase Firestore."""

    uid: str
    role: UserRole
    is_active: bool = True
    email: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
