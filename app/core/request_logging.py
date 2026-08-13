"""Minimal HTTP request logging without credentials or signed-link queries."""

import json
import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..services.traffic import record_traffic

logger = logging.getLogger("uvicorn.error")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _request_id(scope: Scope) -> str:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() != b"x-request-id":
            continue
        try:
            candidate = raw_value.decode("ascii")
        except UnicodeDecodeError:
            break
        if _REQUEST_ID_PATTERN.fullmatch(candidate):
            return candidate
        break
    return uuid.uuid4().hex


class RequestLogMiddleware:
    """Add a correlation ID and log only a small, non-sensitive request summary."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(scope)
        status_code = 500
        request_bytes = 0
        response_bytes = 0
        started = time.perf_counter()

        async def receive_with_count() -> Message:
            nonlocal request_bytes
            message = await receive()
            if message["type"] == "http.request":
                request_bytes += len(message.get("body", b""))
            return message

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_bytes
            body_size = 0
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            elif message["type"] == "http.response.body":
                body_size = len(message.get("body", b""))
            await send(message)
            # Count only chunks accepted by the ASGI server. This still cannot
            # prove the remote peer consumed every byte, but a failed send no
            # longer inflates management traffic statistics.
            response_bytes += body_size

        try:
            await self.app(scope, receive_with_count, send_with_request_id)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            # ASGI exposes the decoded path separately from query_string. Never
            # log the latter: signed media URLs carry secrets in that field.
            path = json.dumps(scope.get("path", ""), ensure_ascii=True)
            logger.info(
                "http_request request_id=%s method=%s path=%s status=%d duration_ms=%.3f",
                request_id,
                scope.get("method", ""),
                path,
                status_code,
                duration_ms,
            )
            raw_path = scope.get("path", "")
            if raw_path.startswith(("/api/", "/i/", "/v/")):
                matched_route = scope.get("route")
                route = getattr(matched_route, "path", None)
                if not route:
                    if raw_path.startswith("/api/"):
                        route = "/api/{unmatched}"
                    elif raw_path.startswith("/i/"):
                        route = "/i/{unmatched}"
                    else:
                        route = "/v/{unmatched}"
                state = scope.get("state", {})
                record_traffic(
                    user_id=state.get("traffic_user_id"),
                    api_key_id=state.get("traffic_api_key_id"),
                    user_created_at=state.get("traffic_user_created_at"),
                    api_key_created_at=state.get("traffic_api_key_created_at"),
                    route=route,
                    method=scope.get("method", ""),
                    status_code=status_code,
                    request_bytes=request_bytes,
                    response_bytes=response_bytes,
                )
