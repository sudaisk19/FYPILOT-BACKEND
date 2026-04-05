"""Reject oversized PATCH bodies for student whiteboard updates (Excalidraw + embedded images)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Excalidraw scene + base64 files; keep aligned with reverse proxy (e.g. nginx client_max_body_size).
MAX_WHITEBOARD_PATCH_BYTES = 10 * 1024 * 1024


class WhiteboardPatchContentSizeLimitMiddleware(BaseHTTPMiddleware):
    """Return 413 when Content-Length exceeds limit for PATCH /api/students/whiteboards/{id}."""

    async def dispatch(self, request: Request, call_next):
        if request.method == "PATCH" and request.url.path.startswith(
            "/api/students/whiteboards/"
        ):
            cl = request.headers.get("content-length")
            if cl is not None:
                try:
                    if int(cl) > MAX_WHITEBOARD_PATCH_BYTES:
                        return JSONResponse(
                            status_code=413,
                            content={"detail": "Request body too large"},
                        )
                except ValueError:
                    pass
        return await call_next(request)
