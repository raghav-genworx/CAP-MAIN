"""PostgreSQL-backed platform role authorization."""

from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config.settings import Settings
from core.exceptions.auth import AuthorizationError, RoleStoreUnavailableError
from data.models.postgres.core.user_role import UserRoleModel
from data.repositories.auth.role_repository import RoleRepository
from schemas.auth import AuthenticatedUser, FirebaseIdentity
from schemas.roles import SubscriptionStatus, UserRole, UserRoleRecord


class RoleService:
    """Read and manage application role assignments from PostgreSQL."""

    def __init__(self, settings: Settings, session: Session) -> None:
        """Initialize the service with runtime settings and a DB session."""

        self._settings = settings
        self._repository = RoleRepository(session)

    def resolve_user(self, identity: FirebaseIdentity) -> AuthenticatedUser:
        """Attach an active role assignment to a verified Firebase identity."""

        role_record = self.get_role_for_uid(identity.uid, identity.email)

        return AuthenticatedUser(
            uid=identity.uid,
            email=identity.email,
            name=identity.name,
            picture=identity.picture,
            email_verified=identity.email_verified,
            role=role_record.role,
            subscription_status=role_record.subscription_status,
            trial_started_at=role_record.trial_started_at,
        )

    def get_role_for_uid(
        self,
        uid: str,
        email: str | None = None,
    ) -> UserRoleRecord:
        """Return the user's active role assignment."""

        try:
            role_model = self._repository.get(uid)
        except SQLAlchemyError as exc:
            raise RoleStoreUnavailableError("Unable to read role table") from exc

        if role_model is None:
            if not self._settings.auto_create_recruiter_role:
                raise AuthorizationError("No platform role is assigned to this user")

            return self._create_default_recruiter_role(uid, email)

        role_record = self._record_from_model(role_model)

        if not role_record.is_active:
            raise AuthorizationError("This platform role is inactive")

        return role_record

    def _create_default_recruiter_role(
        self,
        uid: str,
        email: str | None,
    ) -> UserRoleRecord:
        """Create the initial recruiter role for local development bootstrap."""

        now = datetime.now(UTC)
        role_model = UserRoleModel(
            uid=uid,
            role=UserRole.RECRUITER.value,
            is_active=True,
            email=email,
            subscription_status=SubscriptionStatus.PENDING.value,
            created_at=now,
            updated_at=now,
        )

        try:
            self._repository.add(role_model)
            self._repository.commit()
            self._repository.refresh(role_model)
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise RoleStoreUnavailableError("Unable to create role assignment") from exc

        return self._record_from_model(role_model)

    def start_free_trial(self, uid: str) -> UserRoleRecord:
        """Activate the no-charge trial for a recruiter account."""

        try:
            role_model = self._repository.get(uid)
        except SQLAlchemyError as exc:
            raise RoleStoreUnavailableError("Unable to read role table") from exc
        if role_model is None:
            raise AuthorizationError("No platform role is assigned to this user")
        if not role_model.is_active:
            raise AuthorizationError("This platform role is inactive")

        if role_model.subscription_status != SubscriptionStatus.FREE_TRIAL.value:
            role_model.subscription_status = SubscriptionStatus.FREE_TRIAL.value
            role_model.trial_started_at = datetime.now(UTC)
            try:
                self._repository.commit()
                self._repository.refresh(role_model)
            except SQLAlchemyError as exc:
                self._repository.rollback()
                raise RoleStoreUnavailableError(
                    "Unable to activate the free trial"
                ) from exc

        return self._record_from_model(role_model)

    @staticmethod
    def _record_from_model(role_model: UserRoleModel) -> UserRoleRecord:
        """Build a role record from a database model."""

        try:
            return UserRoleRecord(
                uid=role_model.uid,
                role=UserRole(role_model.role),
                is_active=role_model.is_active,
                email=role_model.email,
                subscription_status=SubscriptionStatus(role_model.subscription_status),
                trial_started_at=role_model.trial_started_at,
                created_at=role_model.created_at,
                updated_at=role_model.updated_at,
            )
        except ValueError as exc:
            raise AuthorizationError("Invalid platform role assignment") from exc
