"""Request correlation and logging must never expose signed-link queries."""

import re

import pytest

from app.core import request_logging


class _LogSink:
    def __init__(self):
        self.messages: list[str] = []

    def info(self, template, *args):
        self.messages.append(template % args)


def test_request_log_omits_query_and_echoes_safe_request_id(client, monkeypatch):
    sink = _LogSink()
    monkeypatch.setattr(request_logging, "logger", sink)

    response = client.get(
        "/healthz?sig=never-log-this-signature&expires=9999999999",
        headers={"X-Request-ID": "edge.req-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "edge.req-123"
    assert len(sink.messages) == 1
    message = sink.messages[0]
    assert "request_id=edge.req-123" in message
    assert "method=GET" in message
    assert 'path="/healthz"' in message
    assert "status=200" in message
    assert "duration_ms=" in message
    assert "never-log-this-signature" not in message
    assert "sig=" not in message
    assert "expires=" not in message


def test_unsafe_request_id_is_replaced_and_not_logged(client, monkeypatch):
    sink = _LogSink()
    monkeypatch.setattr(request_logging, "logger", sink)

    response = client.get("/healthz", headers={"X-Request-ID": "unsafe id"})

    generated = response.headers["X-Request-ID"]
    assert generated != "unsafe id"
    assert re.fullmatch(r"[0-9a-f]{32}", generated)
    message = "\n".join(sink.messages)
    assert "unsafe id" not in message
    assert f"request_id={generated}" in message


@pytest.mark.anyio
async def test_failed_asgi_body_send_is_not_counted(monkeypatch):
    recorded = []
    monkeypatch.setattr(request_logging, "record_traffic", lambda **values: recorded.append(values))

    async def downstream(_scope, _receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        await send({"type": "http.response.body", "body": b"second", "more_body": False})

    middleware = request_logging.RequestLogMiddleware(downstream)
    sends = 0

    async def failing_send(_message):
        nonlocal sends
        sends += 1
        if sends == 3:
            raise OSError("client disconnected")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/test",
        "query_string": b"",
        "headers": [],
        "route": type("Route", (), {"path": "/api/test"})(),
    }
    with pytest.raises(OSError, match="client disconnected"):
        await middleware(scope, receive, failing_send)
    assert recorded[-1]["response_bytes"] == len(b"first")
