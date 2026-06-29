"""Tests for Groq-backed code-quality evaluation."""

import json
import unittest

import httpx

from core.services.code_quality_evaluator import GroqCodeQualityEvaluator


def _quality_payload(score: float = 82) -> dict[str, object]:
    return {
        "score": score,
        "approach": "Uses a clear single-pass approach.",
        "time_complexity": "O(n)",
        "space_complexity": "O(1)",
        "readability": "Names and control flow are clear.",
        "maintainability": "The implementation is compact and modular.",
        "strengths": ["Clear control flow"],
        "weaknesses": ["Limited input validation"],
        "improvements": ["Validate malformed input"],
    }


class GroqCodeQualityEvaluatorTest(unittest.TestCase):
    def test_returns_schema_validated_groq_review(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["authorization"], "Bearer test-key")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "test-model")
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            self.assertIn("def solve", payload["messages"][1]["content"])
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": json.dumps(_quality_payload())}}
                    ]
                },
            )

        client = httpx.Client(
            base_url="https://api.groq.test/openai/v1",
            transport=httpx.MockTransport(handler),
            headers={"Authorization": "Bearer test-key"},
        )
        evaluator = GroqCodeQualityEvaluator(
            api_key="test-key",
            base_url="https://api.groq.test/openai/v1",
            model="test-model",
            timeout_seconds=5,
            retry_count=1,
            max_source_chars=10_000,
            client=client,
        )

        result = evaluator.evaluate(
            language="Python 3",
            source_code="def solve(values):\n    return sum(values)\n",
        )

        self.assertEqual(result.score, 82)
        self.assertEqual(result.time_complexity, "O(n)")

    def test_retries_invalid_model_output(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            content = "not-json" if calls == 1 else json.dumps(_quality_payload(76))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": content}}]},
            )

        evaluator = GroqCodeQualityEvaluator(
            api_key="test-key",
            base_url="https://api.groq.test/openai/v1",
            model="test-model",
            timeout_seconds=5,
            retry_count=2,
            max_source_chars=10_000,
            client=httpx.Client(
                base_url="https://api.groq.test/openai/v1",
                transport=httpx.MockTransport(handler),
            ),
        )

        result = evaluator.evaluate(language="Python", source_code="return 1")

        self.assertEqual(calls, 2)
        self.assertEqual(result.score, 76)


if __name__ == "__main__":
    unittest.main()
