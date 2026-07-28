"""Repository for AI execution run logs."""

from data.models.postgres.core.ai_run_log import AIRunLogModel
from data.repositories.base_postgres_repository import BaseRepository


class AIRunLogRepository(BaseRepository):
    """Persist AI gateway trace records."""

    def add_run_log(self, run_log: AIRunLogModel) -> None:
        """Stage and flush an AI run log."""

        self.add(run_log)
        self.flush()
