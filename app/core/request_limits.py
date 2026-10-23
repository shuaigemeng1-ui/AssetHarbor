"""Bound HTTP request bodies without buffering or changing uploaded bytes."""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _RequestBodyTooLarge(HTTPException, OSError):
    # Starlette's multipart parser closes temporary files on OSError. Keeping
    # HTTPException as well lets FastAPI preserve the 413 instead of returning
    # a generic body-parsing error for multipart and JSON requests.
    pass


class RequestBodyLimitMiddleware:
    """Check declared size early and count actual bytes, including chunked bodies."""

    def __init__(self, app: ASGIApp, max_size_mb: int) -> None:
        self.app = app
        self.max_bytes = max_size_mb * 1024 * 1024
        self.detail = f"request body exceeds the {max_size_mb} MB limit"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    declared_size = int(value)
                except ValueError:
                    continue  # The server validates framing; still count bytes below.
                if declared_size > self.max_bytes:
                    await JSONResponse({"detail": self.detail}, status_code=413)(scope, receive, send)
                    return

        received = 0
        response_started = False

        async def receive_with_limit() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestBodyTooLarge(status_code=413, detail=self.detail)
            return message

        async def track_response(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive_with_limit, track_response)
        except _RequestBodyTooLarge:
            if response_started:
                raise
            await JSONResponse({"detail": self.detail}, status_code=413)(scope, receive, send)
