"""Service configuration smoke tests."""

from config.settings import Settings


def test_local_defaults_define_the_evaluation_contract() -> None:
    settings = Settings(_env_file=None)

    assert settings.api_prefix == "/api/v1"
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.evaluation_worker_batch_size > 0
    assert settings.evaluation_retention_days >= 30
