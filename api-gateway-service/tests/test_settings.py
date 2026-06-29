"""Runtime configuration safety tests."""

import unittest

from pydantic import ValidationError

from config.settings import Settings


class SettingsTests(unittest.TestCase):
    def test_production_rejects_insecure_browser_origins(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                app_env="production",
                cors_allowed_origins="http://cap.example.com",
            )

    def test_production_accepts_explicit_https_origins(self) -> None:
        settings = Settings(
            app_env="production",
            cors_allowed_origins="https://cap.example.com",
            internal_service_token="production-internal-service-token",
            candidate_session_secret="production-candidate-session-secret",
        )

        self.assertEqual(settings.cors_origins, ["https://cap.example.com"])


if __name__ == "__main__":
    unittest.main()
