"""Prometheus collectors.

Splitting one process into four used to give per-service latency attribution for
free -- each service scraped separately. Consolidating loses that, so request
metrics carry the bounded context as a label to recover it.

Cardinality is the thing to watch: labelling by raw URL path would mint a new
series per assessment ID. The templated route path (``/assessments/{id}``) is used
instead, which is bounded by the size of the route table.
"""

from prometheus_client import Counter, Histogram

#: Seconds. Tuned for an API that mixes fast reads with Judge0-bound and
#: LLM-bound requests, which routinely run into tens of seconds.
_LATENCY_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)

REQUEST_DURATION = Histogram(
    "cap_http_request_duration_seconds",
    "HTTP request latency by bounded context.",
    labelnames=("app", "context", "method", "status"),
    buckets=_LATENCY_BUCKETS,
)

REQUEST_TOTAL = Counter(
    "cap_http_requests_total",
    "HTTP requests by bounded context.",
    labelnames=("app", "context", "method", "status"),
)

#: Which bounded context owns a request, derived from the first path segment after
#: the API prefix. Anything unrecognised is bucketed as "other" rather than
#: creating a series, so an unmatched route cannot inflate cardinality.
_CONTEXT_BY_PREFIX = {
    "assessments": "assessments",
    "auth": "auth",
    "candidate": "candidate_portal",
    "notifications": "notifications",
    "question-bank": "question_bank",
    "executions": "execution",
    "evaluations": "evaluation",
    "gateway": "gateway",
    "health": "health",
}


def context_for_path(path: str, api_prefix: str = "/api/v1") -> str:
    """Return the bounded context that owns ``path``."""

    remainder = path.removeprefix(api_prefix).lstrip("/")
    first_segment = remainder.split("/", 1)[0]
    return _CONTEXT_BY_PREFIX.get(first_segment, "other")


def observe_request(
    *,
    app: str,
    path: str,
    method: str,
    status: int,
    duration_seconds: float,
    api_prefix: str = "/api/v1",
) -> None:
    """Record one completed HTTP request."""

    labels = (app, context_for_path(path, api_prefix), method, str(status))
    REQUEST_DURATION.labels(*labels).observe(duration_seconds)
    REQUEST_TOTAL.labels(*labels).inc()
