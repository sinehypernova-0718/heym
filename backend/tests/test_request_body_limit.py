import json
import unittest

from fastapi.middleware.cors import CORSMiddleware

from app.middleware.request_body_limit import RequestBodySizeLimitMiddleware


def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {
        "type": "http",
        "method": "POST",
        "path": "/upload",
        "headers": headers or [],
    }


def _response_status(sent: list[dict]) -> int:
    for message in sent:
        if message["type"] == "http.response.start":
            return message["status"]
    raise AssertionError(f"No response start sent: {sent}")


def _response_json(sent: list[dict]) -> dict:
    body = b"".join(message.get("body", b"") for message in sent)
    return json.loads(body.decode("utf-8"))


def _response_headers(sent: list[dict]) -> dict[bytes, bytes]:
    for message in sent:
        if message["type"] == "http.response.start":
            return dict(message["headers"])
    raise AssertionError(f"No response start sent: {sent}")


class RequestBodySizeLimitMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_content_length_above_limit_without_calling_app(self) -> None:
        called = False

        async def app(scope, receive, send) -> None:
            nonlocal called
            called = True

        middleware = RequestBodySizeLimitMiddleware(app, max_body_size=4)
        sent: list[dict] = []

        async def receive() -> dict:
            raise AssertionError("receive should not be called")

        async def send(message: dict) -> None:
            sent.append(message)

        await middleware(_http_scope([(b"content-length", b"5")]), receive, send)

        self.assertFalse(called)
        self.assertEqual(_response_status(sent), 413)
        self.assertEqual(
            _response_json(sent)["detail"],
            "Request body exceeds the configured size limit.",
        )

    async def test_cors_wrapper_adds_headers_to_rejected_request(self) -> None:
        async def app(scope, receive, send) -> None:
            raise AssertionError("app should not be called")

        middleware = CORSMiddleware(
            RequestBodySizeLimitMiddleware(app, max_body_size=4),
            allow_origins=["https://app.example"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        sent: list[dict] = []

        async def receive() -> dict:
            raise AssertionError("receive should not be called")

        async def send(message: dict) -> None:
            sent.append(message)

        await middleware(
            _http_scope(
                [
                    (b"origin", b"https://app.example"),
                    (b"content-length", b"5"),
                ]
            ),
            receive,
            send,
        )

        self.assertEqual(_response_status(sent), 413)
        self.assertEqual(
            _response_headers(sent).get(b"access-control-allow-origin"),
            b"https://app.example",
        )

    async def test_rejects_streaming_body_once_limit_is_exceeded(self) -> None:
        async def app(scope, receive, send) -> None:
            while True:
                message = await receive()
                if message["type"] == "http.request" and not message.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = RequestBodySizeLimitMiddleware(app, max_body_size=4)
        messages = [
            {"type": "http.request", "body": b"12", "more_body": True},
            {"type": "http.request", "body": b"345", "more_body": False},
        ]
        sent: list[dict] = []

        async def receive() -> dict:
            return messages.pop(0)

        async def send(message: dict) -> None:
            sent.append(message)

        await middleware(_http_scope(), receive, send)

        self.assertEqual(_response_status(sent), 413)
        self.assertEqual(
            _response_json(sent)["detail"],
            "Request body exceeds the configured size limit.",
        )

    async def test_allows_request_body_at_limit(self) -> None:
        async def app(scope, receive, send) -> None:
            body = b""
            while True:
                message = await receive()
                if message["type"] == "http.request":
                    body += message.get("body", b"")
                    if not message.get("more_body", False):
                        break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": body})

        middleware = RequestBodySizeLimitMiddleware(app, max_body_size=4)
        messages = [
            {"type": "http.request", "body": b"12", "more_body": True},
            {"type": "http.request", "body": b"34", "more_body": False},
        ]
        sent: list[dict] = []

        async def receive() -> dict:
            return messages.pop(0)

        async def send(message: dict) -> None:
            sent.append(message)

        await middleware(_http_scope(), receive, send)

        self.assertEqual(_response_status(sent), 200)
        self.assertEqual(b"".join(message.get("body", b"") for message in sent), b"1234")
