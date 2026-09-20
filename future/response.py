import json

from collections.abc import Awaitable
from typing import Any, Callable, Optional, Union


class Response:
    def __init__(self, body: Union[str, bytes] = "", status: int = 200, headers: dict[str, str] | None = None, content_type: Optional[str] = None) -> None:
        self.status = status
        self.context: dict[str, Any] = {}
        self.body = b""
        self.headers: list[list[bytes]] = []
        if body or content_type or headers:
            self._set(body=body, status=status, headers=headers, content_type=content_type)

    def _set(self, body: Union[str, bytes] = "", status: int = 200, headers: dict[str, str] | None = None, content_type: Optional[str] = None) -> "Response":
        self.status = status
        if isinstance(body, str):
            self.body = body.encode("utf-8")
            if content_type is None:
                content_type = "text/plain"
        elif isinstance(body, bytes):
            self.body = body
            if content_type is None and body:
                content_type = "application/octet-stream"
        else:
            raise TypeError(f"Response body must be str or bytes, got {type(body)}")
        header_map = dict(headers) if headers else {}
        if content_type and not any(key.lower() == "content-type" for key in header_map):
            header_map["content-type"] = content_type
        # Preserve Set-Cookie headers already appended via set_cookie
        cookies = [pair for pair in self.headers if pair[0].lower() == b"set-cookie"]
        self.headers = [[key.lower().encode(), value.encode()] for key, value in header_map.items()]
        self.headers.extend(cookies)
        return self

    def json(self, data: Any, status: int = 200, headers: dict[str, str] | None = None) -> "Response":
        return self._set(body=json.dumps(data, default=str, ensure_ascii=False), status=status, headers=headers, content_type="application/json")

    def html(self, html: str, status: int = 200, headers: dict[str, str] | None = None) -> "Response":
        return self._set(body=html, status=status, headers=headers, content_type="text/html")

    def text(self, body: str = "", status: int = 200, headers: dict[str, str] | None = None) -> "Response":
        return self._set(body=body, status=status, headers=headers, content_type="text/plain")

    def empty(self, status: int = 204, headers: dict[str, str] | None = None) -> "Response":
        return self._set(body="", status=status, headers=headers, content_type=None)

    def redirect(self, url: str, status: int = 302, headers: dict[str, str] | None = None) -> "Response":
        final = dict(headers) if headers else {}
        final["location"] = url
        return self._set(body="", status=status, headers=final, content_type=None)

    def file(self, body: bytes = b"", status: int = 200, headers: dict[str, str] | None = None, content_type: str = "application/octet-stream") -> "Response":
        return self._set(body=body, status=status, headers=headers, content_type=content_type)

    def image(self, body: bytes = b"", status: int = 200, headers: dict[str, str] | None = None, content_type: str = "image/png", file_path: str | None = None) -> "Response":
        if file_path:
            with open(file_path, "rb") as f:
                body = f.read()
        return self._set(body=body, status=status, headers=headers, content_type=content_type)

    def set_cookie(self, name: str, value: str, path: str = "/", httponly: bool = True, samesite: str = "Lax", secure: bool = False, max_age: int | None = None, domain: str | None = None, expires: str | None = None) -> "Response":
        cookie = f"{name}={value}; Path={path}"
        if domain:
            cookie += f"; Domain={domain}"
        if max_age is not None:
            cookie += f"; Max-Age={int(max_age)}"
        if expires:
            cookie += f"; Expires={expires}"
        if httponly:
            cookie += "; HttpOnly"
        cookie += f"; SameSite={samesite}"
        if secure:
            cookie += "; Secure"
        self.headers.append([b"set-cookie", cookie.encode("utf-8")])
        return self

    def delete_cookie(self, name: str, path: str = "/") -> "Response":
        self.headers.append([b"set-cookie", f"{name}=; Path={path}; Max-Age=0".encode("utf-8")])
        return self

    async def __call__(self, send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        start_message = {
            "type": "http.response.start",
            "status": self.status,
            "headers": self.headers,
        }
        await send(start_message)
        body_message = {
            "type": "http.response.body",
            "body": self.body,
        }
        await send(body_message)


class WebSocketResponse:
    """ASGI WebSocket session: accept, send/receive loop, then exit on disconnect."""

    def __init__(self, receive: Any, message: str = "") -> None:
        self._asgi_receive = receive
        self.message = message
        self._send: Any = None

    async def accept(self) -> None:
        await self._send({"type": "websocket.accept"})

    async def send_text(self, text: str) -> None:
        await self._send({"type": "websocket.send", "text": text})

    async def send_bytes(self, data: bytes) -> None:
        await self._send({"type": "websocket.send", "bytes": data})

    async def close(self, code: int = 1000, reason: str = "") -> None:
        await self._send({"type": "websocket.close", "code": code, "reason": reason})

    async def receive(self) -> dict[str, Any] | None:
        while True:
            message = await self._asgi_receive()
            if message["type"] == "websocket.disconnect":
                return None
            if message["type"] == "websocket.receive":
                return message

    async def receive_text(self) -> str | None:
        message = await self.receive()
        if message is None:
            return None
        if "text" in message and message["text"] is not None:
            return message["text"]
        if "bytes" in message and message["bytes"] is not None:
            return message["bytes"].decode("utf-8")
        return None

    async def __call__(self, send: Any) -> None:
        self._send = send
        await self.accept()
        if self.message:
            await self.send_text(f"Echo: {self.message}")
        while True:
            text = await self.receive_text()
            if text is None:
                break
            await self.send_text(f"Echo: {text}")


class StreamingResponse(Response):
    def __init__(self, body=(), status: int = 200, headers: dict[str, str] | None = None, content_type: Optional[str] = None) -> None:
        super().__init__(body=b"", status=status, headers=headers, content_type=content_type or "application/octet-stream")
        self._chunks = body

    async def __call__(self, send: Any) -> None:
        await send({"type": "http.response.start", "status": int(self.status), "headers": self.headers})
        chunks = self._chunks
        if isinstance(chunks, (bytes, bytearray, memoryview, str)):
            chunks = [chunks]
        if hasattr(chunks, "__aiter__"):
            async for chunk in chunks:
                if isinstance(chunk, (bytes, bytearray, memoryview)):
                    body = bytes(chunk)
                elif isinstance(chunk, str):
                    body = chunk.encode("utf-8")
                else:
                    raise TypeError(f"stream chunk must be bytes or str, got {type(chunk).__name__}")
                await send({"type": "http.response.body", "body": body, "more_body": True})
        else:
            for chunk in chunks:
                if isinstance(chunk, (bytes, bytearray, memoryview)):
                    body = bytes(chunk)
                elif isinstance(chunk, str):
                    body = chunk.encode("utf-8")
                else:
                    raise TypeError(f"stream chunk must be bytes or str, got {type(chunk).__name__}")
                await send({"type": "http.response.body", "body": body, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

