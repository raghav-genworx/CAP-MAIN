"""Application entry point for the Code Execution Service."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api.rest.app import create_app

app = create_app()
