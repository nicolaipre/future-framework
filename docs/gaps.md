# Gaps and roadmap
Honest inventory of what Future still lacks or only partially implements. Use this when deciding what to build next.

## Won’t do unless requested
| Item | Notes |
|------|-------|
| **Query / form → action kwargs** | Path params and `request.query` / cached `body()` / `json()` / `form()` / `files()` are enough. Auto-inject into action kwargs fights explicit style. |

## Database / ORM
MongoDB, ClickHouse, and Redis Active Record CRUD are usable and async (Redis has no schema/migrate). Remaining ORM gaps are driver-specific edge cases rather than stubs.

- **`where(..., "like", ...)` naming** — Pattern matching works on all drivers (`%` / `_`, mapped per backend), but the operator name is SQL-flavored. Later: review a more generic, cross-store name (e.g. `match` / `pattern` / `contains`-style) that stays understandable for SQL, Elasticsearch, MongoDB, etc., without breaking the agnostic Model API. Keep one portable pattern language; avoid driver-specific wording in app code.
- **Elasticsearch 9** — Client is pinned to `>=8.15,<9` so migrate/queries work against Elasticsearch 8.x (client 9.x sends `compatible-with=9` and 8.x servers reject it with `media_type_header_exception`). Later: support ES 9 (bump `elasticsearch` to 9.x and align Docker/docs), ideally without breaking ES 8 apps — or document a clear major-version split.

## Middleware stock library
CORS, GZip, CSRF, and RateLimit are usable and exported. Confuser classes remain unfinished and are **not** exported from `future.middleware`.

- **Configured middleware on routes** — Today `middlewares=[CORSMiddleware]` is a class list; Future constructs each with `(request, response)`. Consider allowing per-route / per-group options without subclasses, e.g. `middlewares=[CORSMiddleware(opt=opt)]` (or an equivalent factory / options object), so apps can set CORS origins, rate limits, etc. in `routes.py`. Design carefully: keep no-decorator style, and do not break the current class + `(request, response)` injection.

## Authentication
`future.authentication.*` are stubs (`auth_type` only) extending `future.interfaces.IAuthentication`. No JWT / OIDC / session-login middleware ships yet.

## WebSockets
Usable duplex echo — see [WebSockets](websockets.md). `handle_websocket_request` mirrors HTTP for middleware, controller DI, and path params; errors close with 1011. HTTP chunked bodies: `StreamingResponse` (same module as `WebSocketResponse`) — see [Response](response.md). Later: whether streaming belongs on `Response` itself.

## HTTP/2 / ASGI server
- Outbound: prefer httpx (already used by the test client).
- Inbound HTTP/2: reverse proxy (nginx / Hypercorn in front) is fine.
- **`Future.run` stays on uvicorn.** Hypercorn is **not** a drop-in for `uvicorn.run(...)` (different API: `Config` + `asyncio.run(serve(app, config))`, different workers/reload). An optional Hypercorn backend can be a later feature, not a silent swap.

## GraphQL
`GraphQLController.query` accepts `POST` JSON search terms (`email`, `name`, `title`, `content`, `author_id`, `id`, optional `limit`). Each term is its own query; hits are unioned by id. GraphQL only shapes the result (`GetEverything`). Register the route yourself (`Post("/graphql", GraphQLController.query, …)`). There is no `GRAPHQL_SCHEMA` config key and no `app.add_graphql_route`. See [GraphQL](graphql.md).

- **`strawberry.type(Model)` vs Active Record** — The demo uses `UserType = strawberry.type(UserModel)`. Nested `Query` field annotations still use `list[UserModel]` because `UserType` is not in that class scope. Strawberry’s `type(...)` wraps the class in place; if that starts breaking `IModel` lookups, apps should keep separate GraphQL types. Later: see if one class can serve ORM + GraphQL without decorator hacks.

## Plugins
`IPlugin` is a marker interface in `future.interfaces`. Only `ElasticsearchPlugin` is substantial. No lifecycle hooks into `Future` boot.

## Testing
Most HTTP / middleware / path-syntax / DB coverage lives under `tests/`. Remaining gaps:

| Gap | Notes |
|-----|-------|
| `FutureTestClient` sync API | Prefer `from future.testclient import FutureTestClient` (async). |

## Exploring (needs design — keep Future simple)
| Idea | Notes |
|------|-------|
| **Thin service container** | Optional Masonite-like `bind` / `singleton` / `make` for app services (mail, clients, `TradeService`), while controllers keep explicit `request` / `response` DI. Not a full auto-wire IoC for every dependency. Must stay optional and obvious — no hidden constructor magic by default. Compare Masonite’s container; design carefully before shipping. |
| **C#-style interface naming + `Interface` base** | Shipped. `future/interfacing.py` = core validation. `future/interfaces/` = I* types (`IModel`, `IController`, `IMiddleware`, `IDatabase`, `IPlugin`). App code extends those. Concrete classes stay in domain folders. |

Accepted validation behavior:

- **Always** — every stub method on an `Interface` ancestor must be implemented; signatures must match exactly; `_`-prefixed helpers ignored.
- **`__strict__ = True` on the interface** — no extra public methods on implementors (drop-in drivers). Default `False` (C#/PHP allow extra methods on the class).
- Interface stub declarations (`raise NotImplementedError`) are not valid inherited implementations; real methods on implementors (including `raise NotImplementedError("reason")`) count.

Example:

```python
class Interface:
    __strict__ = False

class IDatabase(Interface):
    async def connect(self) -> None: raise NotImplementedError
    async def save(self, model) -> None: raise NotImplementedError
    async def transaction(self): ...  # default implementation, not required on subclasses

class PostgresDatabase(IDatabase):
    async def connect(self) -> None: ...
    async def save(self, model) -> None: ...

class IModel(Interface):  # real methods — TradeModel(IModel) inherits without re-validation
    async def save(self): ...
```

## Explicitly out of scope (for now)
- Full IoC / auto-wiring every constructor argument (Laravel/Spring-style for the whole app)
- Shipping Redocly paid JS without a customer license
- Revel / Reef portal products (not embeddable OpenAPI UIs)
- Replacing uvicorn with Hypercorn as a silent default

---

When closing a gap, update the relevant guide and delete the row here.
