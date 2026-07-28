"""Repository for platform role assignments."""

from data.models.postgres.core.user_role import UserRoleModel
from data.repositories.base_postgres_repository import BaseRepository


class RoleRepository(BaseRepository):
    """Read and persist platform role records."""

    def get(self, uid: str) -> UserRoleModel | None:
        """Return a role assignment by Firebase UID."""

        return self._session.get(UserRoleModel, uid)
