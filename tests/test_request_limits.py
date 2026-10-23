"""Actual streamed bytes enforce the request limit and clean up multipart files."""

import asyncio
from tempfile import SpooledTemporaryFile

import pytest
from starlette import formparsers
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_limits import RequestBodyLimitMiddleware


@pytest.mark.parametrize("extra_bytes,declared_size", [(0, None), (1, None), (1, b"1")])
def test_streamed_multipart_boundary_and_cleanup(monkeypatch, extra_bytes, declared_size):
    opened = []

    def tracked_file(*args, **kwargs):
        file = SpooledTemporaryFile(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", tracked_file)
    prefix = b'--test\r\nContent-Disposition: form-data; name="file"; filename="a.png"\r\n\r\n'
    suffix = b"\r\n--test--\r\n"
    size = 1024 * 1024 - len(prefix) - len(suffix) + extra_bytes
    messages = iter([
        {"type": "http.request", "body": prefix + b"x", "more_body": True},
        {"type": "http.request", "body": b"x" * (size - 1) + suffix, "more_body": False},
    ])
    headers = [(b"content-type", b"multipart/form-data; boundary=test")]
    if declared_size is not None:
        headers.append((b"content-length", declared_size))
    scope = {"type": "http", "method": "POST", "path": "/api/upload", "headers": headers}
    sent = []

    async def downstream(scope, receive, send):
        async with Request(scope, receive).form() as form:
            assert len(await form["file"].read()) == size
        await Response(status_code=204)(scope, receive, send)

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    asyncio.run(RequestBodyLimitMiddleware(downstream, max_size_mb=1)(scope, receive, send))
    assert sent[0]["status"] == (413 if extra_bytes else 204)
    assert opened and all(file.closed for file in opened)
