# Request
`future.request.Request` wraps one ASGI HTTP (or WebSocket) connection. Controllers and middleware use `self.request`.

## Attributes
| Attribute | Meaning |
|-----------|---------|
| `method` | `GET`, `POST`, … (or `WEBSOCKET`) |
| `path` | URL path |
| `scheme` | `http` / `https` / `ws` / `wss` |
| `host` | From the `Host` header |
| `headers` | `dict[str, str]` (decoded from ASGI byte pairs) |
| `cookies` | Parsed from `Cookie` |
| `query` | Query string: single values are `str`, repeated keys are `list[str]` |
| `session` | Plain `dict` (persist with `SessionMiddleware`) |
| `identity` | Authenticated `Identity`, or `None` on public/unauthenticated requests |
| `context` | Scratch `dict` for middleware → controller |
| `scope` | Raw ASGI scope |
| `receive` | ASGI receive callable |

## Body helpers
Cached after the first read:

```python
await self.request.body()    # bytes
await self.request.json()    # dict
await self.request.form()    # urlencoded or multipart fields
await self.request.files()   # multipart UploadedFile values (after form())
```

```python
self.request.query.get("ticker")
self.request.headers.get("authorization")
self.request.cookies.get("session")
self.request.session["user"] = "alice"
```

## Uploads
`files()` returns `UploadedFile` instances (`filename`, `content_type`, `content`).
