"""Conservative browser security headers for API, SPA and documentation."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_COMMON_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
)
_API_CSP = b"default-src 'none'; base-uri 'none'; frame-ancestors 'none'"
_APP_CSP = (
    b"default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'self'; "
    b"form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    b"img-src 'self' data: blob:; media-src 'self' blob:; frame-src 'self' blob:; connect-src 'self'"
)
_DOCS_CSP = (
    b"default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
    b"form-action 'none'; script-src 'self' 'unsafe-inline'; "
    b"style-src 'self' 'unsafe-inline'; img-src 'self' data:"
)


class SecurityHeadersMiddleware:
    """Append headers only when the route did not set a stronger value."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _value in headers}
                for name, value in _COMMON_HEADERS:
                    if name not in existing:
                        headers.append((name, value))
                is_api = path.startswith("/api/") or path in (
                    "/healthz",
                    "/readyz",
                    "/openapi.json",
                )
                if is_api and b"cache-control" not in existing:
                    # Login, one-time API keys and signed-link responses must
                    # never be retained by browsers or intermediary caches.
                    headers.append((b"cache-control", b"no-store"))
                # Media routes may already carry a format-specific CSP (SVG)
                # and binary Range delivery must otherwise remain untouched.
                if b"content-security-policy" not in existing and not path.startswith(("/i/", "/v/")):
                    if path == "/docs":
                        csp = _DOCS_CSP
                    elif is_api:
                        csp = _API_CSP
                    else:
                        csp = _APP_CSP
                    headers.append((b"content-security-policy", csp))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
