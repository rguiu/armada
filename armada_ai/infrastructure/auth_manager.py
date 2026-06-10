"""Authentication token management.

Extracts token logic (generation, persistence, validation, extraction from
requests/websockets) from server.py into a single, testable module.
"""
import os
import secrets
from pathlib import Path

from fastapi import Request, WebSocket

from .. import constants


class TokenManager:
    """Manages the Armada auth token lifecycle."""

    def __init__(self, token_file: str = constants.TOKEN_FILE):
        self._token_file = token_file
        self._token: str = ""

    @property
    def token(self) -> str:
        return self._token

    @property
    def is_set(self) -> bool:
        return bool(self._token)

    def ensure(self, keep: bool = True) -> str:
        """Load existing token or generate a new one. Returns the token."""
        if self._token:
            return self._token

        if keep and os.path.exists(self._token_file):
            loaded = Path(self._token_file).read_text().strip()
            if loaded:
                self._token = loaded
                return self._token

        self._token = secrets.token_hex(16)
        os.makedirs(os.path.dirname(self._token_file), exist_ok=True)
        Path(self._token_file).write_text(self._token)
        return self._token

    def validate(self, candidate: str) -> bool:
        return bool(self._token and candidate == self._token)

    @staticmethod
    def extract_from_request(request: Request) -> str:
        """Extract token from query param or Authorization Bearer header."""
        token = request.query_params.get("token", "")
        if token:
            return token
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return ""

    @staticmethod
    def extract_from_websocket(websocket: WebSocket) -> str:
        """Extract token from query param or sec-websocket-protocol / headers."""
        token = websocket.query_params.get("token", "")
        if token:
            return token
        auth = websocket.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return ""


class AuthExemptPaths:
    """Central registry of paths exempt from auth requirements."""

    EXEMPT = frozenset({
        "/api/report",
        "/api/auth/status",
        "/favicon.ico",
        "/manifest.json",
        "/health",
        "/metrics",
        "/icon.svg",
        "/api/qr",
    })

    @classmethod
    def is_exempt(cls, path: str) -> bool:
        return path in cls.EXEMPT
