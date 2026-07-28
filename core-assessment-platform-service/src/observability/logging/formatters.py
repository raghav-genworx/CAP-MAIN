"""Log record formatters.

COE requires structured logging. Plain text is fine for a developer tailing
Compose, but Cloud Logging parses JSON on stdout into queryable fields, so the
formatter is selectable and the deployed default is JSON.
"""

import json
import logging
from typing import Any

from utils.context import get_request_id

TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

#: Attributes ``logging`` puts on every record. Anything outside this set was
#: attached by the caller via ``extra=`` and is worth emitting.
_STANDARD_RECORD_FIELDS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Render records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        """Return the record as a compact JSON line."""

        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Correlate a log line with the request that produced it even when the
        # emitting code is far from the route -- a service, a repository, or a
        # background task.
        request_id = get_request_id()
        if request_id is not None:
            payload["request_id"] = request_id

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS:
                payload[key] = value

        return json.dumps(payload, default=str)
