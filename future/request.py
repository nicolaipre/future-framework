from __future__ import annotations

from future.types import ASGIReceive, ASGIScope
from urllib.parse import parse_qs
from typing import Any, TYPE_CHECKING
import json

if TYPE_CHECKING:
    from future.authentication.Identity import Identity


class UploadedFile:  # FIXME: should not be a class here
    def __init__(self, filename: str, content_type: str, content: bytes):
        self.filename = filename
        self.content_type = content_type
        self.content = content

    def __repr__(self):
        return f"UploadedFile(filename={self.filename!r}, content_type={self.content_type!r}, size={len(self.content)})"


class Request:
    def __init__(self, scope: ASGIScope, receive: ASGIReceive):
        self.scope = scope
        self.receive = receive
        self.method = scope.get("method") or ("WEBSOCKET" if scope.get("type") == "websocket" else "")
        self.path = scope["path"]
        self.route = None
        self.identity: Identity | None = None
        # ASGI headers are byte pairs; decode once for app code
        self.headers = dict([(key.decode("utf-8"), value.decode("utf-8")) for key, value in scope["headers"]])
        self.host = self.headers.get("host", "")
        # self.host = dict(scope['headers']).get(b'host', b'').decode()
        self.context: dict[str, Any] = {}  # for custom data we inject into the request
        self.scheme = scope["scheme"]
        self.session = {}
        self.cookies: dict[str, str] = {}
        self._body: bytes | None = None
        self._form: dict[str, Any] | None = None
        self._files: dict[str, Any] | None = None
        cookie_header = self.headers.get("cookie", "")
        if cookie_header:
            for part in cookie_header.split(";"):
                part = part.strip()
                if not part or "=" not in part:
                    continue
                name, value = part.split("=", 1)
                self.cookies[name.strip()] = value.strip()
        # Query: single value as str, repeated keys as list[str]
        self.query: dict[str, Any] = {}
        raw_qs = scope.get("query_string", b"") or b""
        if isinstance(raw_qs, bytes):
            raw_qs = raw_qs.decode("utf-8")
        for key, values in parse_qs(raw_qs, keep_blank_values=True).items():
            self.query[key] = values[0] if len(values) == 1 else values

    async def body(self) -> bytes:
        if self._body is not None:
            return self._body
        more_body = True
        body: bytes = b""
        while more_body:
            message = await self.receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)
        self._body = body
        return body

    async def json(self) -> dict[str, Any]:
        body = await self.body()
        return json.loads(body)

    async def form(self) -> dict[str, Any]:
        if self._form is not None:
            return self._form
        content_type = self.headers.get("content-type", "")
        body = await self.body()
        if "multipart/form-data" in content_type.lower():
            fields, files = self._parse_multipart(content_type, body)
            self._form = fields
            self._files = files
            return self._form
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        self._form = {key: (values[0] if len(values) == 1 else values) for key, values in parsed.items()}
        self._files = {}
        return self._form

    async def files(self) -> dict[str, Any]:
        if self._files is None:
            await self.form()
        return self._files or {}

    def _parse_multipart(self, content_type: str, body: bytes):
        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.lower().startswith("boundary="):
                boundary = part.split("=", 1)[1].strip().strip('"')
                break
        if not boundary:
            raise ValueError("multipart/form-data missing boundary")
        delimiter = b"--" + boundary.encode("utf-8")
        fields: dict[str, Any] = {}
        files: dict[str, Any] = {}
        for raw_part in body.split(delimiter):
            if not raw_part or raw_part in (b"--", b"--\r\n", b"\r\n"):
                continue
            if raw_part.startswith(b"--"):
                break
            if raw_part.startswith(b"\r\n"):
                raw_part = raw_part[2:]
            if raw_part.endswith(b"\r\n"):
                raw_part = raw_part[:-2]
            header_blob, _, content = raw_part.partition(b"\r\n\r\n")
            if not header_blob:
                continue
            disposition = ""
            part_type = "text/plain"
            for header_line in header_blob.decode("utf-8", errors="replace").split("\r\n"):
                lower = header_line.lower()
                if lower.startswith("content-disposition:"):
                    disposition = header_line.split(":", 1)[1].strip()
                elif lower.startswith("content-type:"):
                    part_type = header_line.split(":", 1)[1].strip()
            name = None
            filename = None
            for item in disposition.split(";"):
                item = item.strip()
                if item.startswith("name="):
                    name = item.split("=", 1)[1].strip().strip('"')
                elif item.startswith("filename="):
                    filename = item.split("=", 1)[1].strip().strip('"')
            if not name:
                continue
            if filename is not None:
                uploaded = UploadedFile(filename=filename, content_type=part_type, content=content)
                if name in files:
                    existing = files[name]
                    files[name] = existing + [uploaded] if isinstance(existing, list) else [existing, uploaded]
                else:
                    files[name] = uploaded
            else:
                text = content.decode("utf-8", errors="replace")
                if name in fields:
                    existing = fields[name]
                    fields[name] = existing + [text] if isinstance(existing, list) else [existing, text]
                else:
                    fields[name] = text
        return fields, files
