"""Backward-compatible imports for the Firebase authentication adapter."""

from typing import Any

from handlers.http_clients import firebase as _implementation

FIREBASE_CERTS_URL = _implementation.FIREBASE_CERTS_URL
FirebaseAuthService = _implementation.FirebaseAuthService
_compat: Any = _implementation
google_requests = _compat.google_requests
id_token = _compat.id_token

__all__ = [
    "FIREBASE_CERTS_URL",
    "FirebaseAuthService",
    "google_requests",
    "id_token",
]
