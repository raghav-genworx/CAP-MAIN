"""Application entry point for the Core Assessment Platform Service."""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from api.rest.app import create_app  # noqa: E402

app = create_app()
