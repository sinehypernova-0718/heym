from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyLimitExceededError(Exception):
    """Raised when an HTTP request body exceeds the configured ASGI limit."""


class RequestBodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max(0, max_body_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.max_body_size <= 0:
            await self.app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > self.max_body_size:
            await self._send_too_large(scope, receive, send)
            return

        received_size = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_size
            message = await receive()
            if message["type"] == "http.request":
                received_size += len(message.get("body", b""))
                if received_size > self.max_body_size:
                    raise RequestBodyLimitExceededError
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, send_wrapper)
        except RequestBodyLimitExceededError:
            if response_started:
                raise
            await self._send_too_large(scope, receive, send)

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for name, value in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            try:
                return int(value)
            except ValueError:
                return None
        return None

    async def _send_too_large(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": "Request body exceeds the configured size limit."},
        )
        await response(scope, receive, send)
