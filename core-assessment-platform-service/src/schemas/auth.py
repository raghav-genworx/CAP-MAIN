"""Authentication and identity schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from schemas.roles import SubscriptionStatus, UserRole


class FirebaseIdentity(BaseModel):
    """Identity claims verified from a Firebase ID token."""

    uid: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    email_verified: bool = False


class AuthenticatedUser(FirebaseIdentity):
    """Authenticated application user with an assigned platform role."""

    role: UserRole
    subscription_status: SubscriptionStatus
    trial_started_at: datetime | None = None


class FirebaseWebConfig(BaseModel):
    """Firebase web config returned to the frontend."""

    api_key: str = Field(alias="apiKey")
    auth_domain: str = Field(alias="authDomain")
    project_id: str = Field(alias="projectId")
    app_id: str = Field(alias="appId")
    storage_bucket: str | None = Field(default=None, alias="storageBucket")
    messaging_sender_id: str | None = Field(default=None, alias="messagingSenderId")
    measurement_id: str | None = Field(default=None, alias="measurementId")

    model_config = {"populate_by_name": True}
