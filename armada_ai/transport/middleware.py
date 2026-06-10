"""FastAPI middleware: auth token validation and Content-Security-Policy."""
from fastapi import Request
from fastapi.responses import JSONResponse

from ..infrastructure.auth_manager import AuthExemptPaths, TokenManager
from .. import logs


def create_auth_middleware(token_manager: TokenManager):
    """Build the auth middleware closure with injected TokenManager."""

    async def auth_middleware(request: Request, call_next):
        path = request.url.path

        if path.startswith("/api/logs"):
            token = TokenManager.extract_from_request(request)
            if not token_manager.validate(token) and not AuthExemptPaths.is_exempt(path):
                logs.log_http_error(request.method, path, 401, "missing or invalid token")
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
            return await call_next(request)

        if (path.startswith("/api/") and not AuthExemptPaths.is_exempt(path)
                and not path.endswith("/ws")):
            token = TokenManager.extract_from_request(request)
            if not token_manager.validate(token):
                logs.log_http_error(request.method, path, 401, "missing or invalid token")
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        return await call_next(request)

    return auth_middleware


_CSP_HEADER = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'self' ws: wss:; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "base-uri 'self'; "
    "form-action 'self'"
)


def create_csp_middleware():
    """Build the CSP middleware. Use as a singleton: applied once per app."""

    async def csp_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = _CSP_HEADER
        return response

    return csp_middleware
