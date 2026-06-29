"""Gateway public-contract privacy tests."""

import unittest
from types import SimpleNamespace

from core.services.gateway_service import GatewayService


class GatewayPrivacyTests(unittest.TestCase):
    """Ensure internal routing details are not returned to browsers."""

    def test_service_catalog_omits_internal_base_urls(self) -> None:
        service = GatewayService(
            SimpleNamespace(
                upstream_services={
                    "core": "http://core-internal:8000",
                    "code-execution": "http://execution-internal:8000",
                    "code-evaluation": "http://evaluation-internal:8000",
                }
            )
        )

        payload = service.get_service_catalog().model_dump()

        self.assertEqual(len(payload["services"]), 3)
        self.assertNotIn("base_url", payload["services"][0])
        self.assertNotIn("core-internal", str(payload))


if __name__ == "__main__":
    unittest.main()
