"""Service configuration smoke tests."""

from config.settings import Settings


def test_local_defaults_define_the_gateway_contract() -> None:
    settings = Settings(_env_file=None)

    assert settings.api_prefix == "/api/v1"
    assert settings.core_service_base_url.startswith("http://")
    assert settings.code_execution_service_base_url.startswith("http://")
    assert settings.code_evaluation_service_base_url.startswith("http://")
