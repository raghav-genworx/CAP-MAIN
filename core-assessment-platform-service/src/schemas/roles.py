"""Role schemas for platform authorization."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class UserRole(StrEnum):
    """Supported application roles."""

    RECRUITER = "recruiter"


class SubscriptionStatus(StrEnum):
    """Recruiter onboarding and subscription states."""

    PENDING = "pending"
    FREE_TRIAL = "free_trial"


class UserRoleRecord(BaseModel):
    """Role assignment stored in Firebase Firestore."""

    uid: str
    role: UserRole
    is_active: bool = True
    email: str | None = None
    subscription_status: SubscriptionStatus = SubscriptionStatus.PENDING
    trial_started_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
