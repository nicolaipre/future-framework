# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]


## [3.0.0] - 2026-09-22
### Added
- Model-based update migrations: generating a migration again after changing a model now emits a full `Schema.update` snapshot, with the preceding snapshot in `down()` for rollback
- Polymorphic `schema_update` support for SQLite, MySQL, Postgres, ClickHouse, Elasticsearch, MongoDB, and Redis; Redis now stores schema snapshots and migration history as metadata

### Fixed
- Running a newly generated migration for an existing model no longer reports success after a `CREATE ... IF NOT EXISTS` no-op


## [2.1.1] - 2026-09-20
### Fixed
- Requests whose `Host` is outside `APP_DOMAIN` now return `404 Not Found`, matching unregistered subdomains without disclosing domain validation behavior


## [2.1.0] - 2026-09-20
### Removed
- `JSONResponse`, `PlainTextResponse`, `EmptyResponse`, `HTMLResponse`, `PNGResponse`, `ImageResponse`, `RedirectResponse`, `FileResponse` — use `self.response.json` / `.text` / `.html` / `.empty` / `.redirect` / `.file` / `.image`
- `Response.stream` — use `StreamingResponse` directly (same module as `WebSocketResponse`)

### Fixed
- Postgres `where … in` uses a single `ANY(:array)` bind so large ID lists no longer hit the ~32767 bind-variable limit
- Elasticsearch `find` / `all` / `get` set model `id` from `_id` when `_source` omits it

### Changed
- Seeder field heuristics for common names (prices, symbols, trade side, timestamps, etc.)
- Response header names are lowercased; streaming chunks must be `bytes` or `str`
Breaking: Active Record / migrations / seeders are async (`await`); `Connections` is `Database`; GraphQL is search terms, not documents.

### Added
- True-async Active Record: `await Model.find()`, `await model.save()`, `await Query.get()` / `.first()`; drivers use async engines/clients (`aiosqlite`, `aiomysql`, `asyncpg`, `redis.asyncio`, `AsyncMongoClient`, `AsyncElasticsearch`, ClickHouse `asynch`)
- Named registry `from future.database import Database` (`set_connection_details` / `get_connection`); `Future` still registers `DATABASES` at boot
- GraphQL search-term `POST` on `GraphQLController.query` (`email`, `name`, `title`, `content`, `author_id`, `id`, optional `limit`)
- Domainless route-conflict error when two RouteGroups with different subdomains register the same path + method while `APP_DOMAIN` is empty
- `Response.stream` / `StreamingResponse` send chunked ASGI bodies (sync or async iterables)

### Changed
- `IDatabase`, migrations (`async with Schema.create`, `await Schema.drop`), and seeders (`async def run`) are awaitable
- `Connections` (`future/databases/Connections.py`) is `Database` in `future/database.py`
- `GraphQLController` no longer runs client GraphQL documents or `config["GRAPHQL_SCHEMA"]`; the in-controller schema only shapes search hits
- `ScopeValidationMiddleware` uses `request.context["scopes"]` instead of a hardcoded grant list

### Fixed
- Scope checks no longer pass every authenticated request
- Pin `elasticsearch` client to `>=8.15,<9` so it matches Elasticsearch 8.x servers (client 9.x sends `compatible-with=9` and breaks migrate/queries against 8.x with `media_type_header_exception`)
- Elasticsearch `connect` builds `http://{host}:{port}` when `host` has no scheme; `table_exists` via `indices.exists`
- `future migrate` rollback body indentation (`SyntaxError` on import)


## [1.1.3] - 2026-07-23
### Changed
- README: Shields.io PyPI badge, clearer badge labels, shorter blurb


## [1.1.2] - 2026-07-23
### Changed
- Package and README description: “ASGI-based framework for web APIs”


## [1.1.1] - 2026-07-23
### Added
- PyPI project links: homepage, repository, documentation, and bug tracker

### Changed
- Docs, badges, and `future init` scaffold point at `nicolaipre/future-framework` and install from PyPI only


## [1.1.0] - 2026-07-23
### Added
- `Query.limit(n)` — portable pagination for `where` / `order_by` chains across all Active Record drivers
- Portable `where(column, "like", pattern)` with SQL-style `%` / `_` on SQLite, MySQL, Postgres, ClickHouse, Elasticsearch, MongoDB, and Redis
- `GraphQLController.query` accepts `POST` `{query, variables?, operationName?}` and runs `config["GRAPHQL_SCHEMA"]` when set (demo schema fallback)

### Changed
- Dependency cleanup: drop unused packages; move pytest/coverage/ruff/mypy/build/twine to `dev`, MkDocs to `docs` group; bump runtime libs (uvicorn 0.51, rich 15, elasticsearch 9, strawberry 0.323, redis 8, faker 40, …)
- Docs CI installs with `poetry install --with docs`
- README GraphQL example uses `Post("/graphql", …)`

### Notes
- `like` naming is SQL-flavored; `docs/gaps.md` tracks a possible rename to a more generic operator later
- Apps that called GraphQL via GET with the old fixed demo query must switch to POST bodies


## [1.0.2] - 2026-07-23
### Fixed
- OpenAPI `servers` built at serve time from `request.scheme` + RouteGroup hosts (no hardcoded `https://APP_DOMAIN`); explicit `OPENAPI.servers` still wins
- Document `servers` prefer non-docs hosts so Scalar Test Request defaults to subdomain APIs; path-level `servers` keep the per-route host
- Docs UIs load the spec via a path-relative URL so the page scheme/host are preserved
- Scalar `onBeforeRequest` sets `baseUrl` from the RouteGroup host map for cross-subdomain Try-it


## [1.0.1] - 2026-07-23
### Fixed
- `RouteGroup` no longer mutates shared `Route.path` in place (reload no longer stacks prefixes, e.g. `/api` → `/api/api`)
- `RouteGroup` prefix + route `path="/"` joins as the prefix alone (`/indexes`, not `/indexes/`)
- `openapi_routes()` returns root-relative paths; mount via `RouteGroup(prefix=...)` (no double `/api` when both were applied)
- Docs `RouteGroup` mount syncs OpenAPI `path_prefix` so UI links point at the mounted spec URL
- `Future.run` passes the app instance when `workers=1` and reload is off; uses `config["APP_ASGI"]` (default `run:app`) for reload / multi-worker so `future run` works
- `BaseAuthentication` alias on `Authentication` so Azure AD / Kerberos stubs import cleanly
- `Database.transaction()` guards missing/`begin`-less clients with `NotImplementedError`
- `strict_slashes=True` no longer appends optional trailing `/`
- Env bools (`APP_ACCESS_LOG`, `APP_SSO`, `APP_REGISTRATION`) parse `"true"`/`"false"` correctly
- CORS no longer sends `Allow-Credentials` with `Allow-Origin: *` (default credentials off)
- OpenAPI paths normalize to `{param}` form; MySQL id-only upsert; Elasticsearch `where(..., "in", ...)`; Postgres URL-encodes credentials
- WebSocket handler errors close with 1011; lifespan tolerates missing `scope["state"]`
- `request.route` set for matched routes (`ScopeValidationMiddleware`); UUID route pattern is hex-only

### Changed
- CLI `migrate` / `rollback` / `make:migration` use Orator-style colored output (`✓ Migrated` / `✓ Rolled back` + blue filename)
- Moved Lifespan to `future.lifespan` (ASGI lifecycle; tasks stay in `future.tasks`)
- Removed the unused per-status exception subclasses (`NotFoundException`, …)
- 404 / 403 / 405 from the router now return the same JSON error shape as raised `HTTPException`s
- Package layout: `controllers/`, `tasks/`, `testing/`, `cli/`, `models/`, `graphql/`; HTTP primitives stay top-level modules
- Imports: `future.tasks` (was `lifespan`/`scheduler`), `future.testing` (was `testclient`); removed `__main__.py` (`future` console script only)
- Folded `TODO.md` into `docs/gaps.md`; demo from `example.py` moved into README; deleted both files
- `APP_DEBUG` strips `:port` from `Host` for domain checks and route lookup; prod stays explicit
- WebSocket dispatch uses `Route.match("WEBSOCKET", path)`; `Request` tolerates websocket scopes; test client drives real ASGI
- Dropped debug `print` in `Route.match`
- Nested `RouteGroup` middleware accumulates outer → inner → route (was dropping parent group middleware)
- `future` logger level follows `APP_DEBUG`; no root `basicConfig`; library HTTP client noise is not wired into the framework
- CLI `migrate` / `seed` import `future.migrations` / `future.seeds` (package layout fix)
- `future make:migration <Model>` / `make:migrations`; `future make:seed <Model>` / `make:seeds` (singular requires a model; plural generates all)
- `future seed` with no name runs every seeder in `database/seeds/` (no `DatabaseSeeder` orchestrator)
- Controllers must return `Response` or `None` (bare `dict` raises `TypeError` → 500)
- Empty session clears the session cookie (`Max-Age=0`); `set_cookie` supports `max_age` / `domain` / `expires`
- `DATABASES` register on `Future` boot from config (no import-time `Connections` side effect); CLI migrate/seed load `run.py`
- Session cookies are HMAC-signed with `APP_KEY` (legacy unsigned cookies still readable once)

### Added
- OpenAPI model schemas via `OPENAPI.models` + `Model.openapi_schema()`, and typed path params (`<int:id>`, `<uuid:…>`, …)
- WebSocket duplex receive loop
- MongoDB / ClickHouse / Redis Active Record CRUD
- MkDocs Material theme; redis dependency
- SQLite driver (`future.databases.SQLite`) with schema, migrations tracking, and Active Record CRUD; scaffold defaults to SQLite
- Postgres Active Record CRUD (aligned with SQLite/MySQL); `where(..., "in", [...])`; `Model.transaction()` / `connection.transaction()`
- `belongs_to` / `has_many` / `eager_load` on models
- Multipart `form()` / `files()` with `UploadedFile`; CSRF + RateLimit middleware (exported)
- OpenAPI path parameters, servers (from `APP_DOMAIN` or config), security schemes / security
- `CORSMiddleware` and `GZipMiddleware` implementations; OpenAPI `tags` from `RouteGroup.name`
- `future run` CLI
- Same path with different HTTP methods (`Get("/x")` + `Post("/x")`); registration conflicts only on overlapping methods
- **405 Method Not Allowed** with `Allow` when the path matches but the method does not
- Route configs store `group` metadata (`name`, `prefix`, `subdomain`) for nested RouteGroups
- `future routes` lists routes in rich tables grouped by domain / group / prefix / middleware (includes path param **Args**)
- Single `HTTPException` + `ErrorHandler(request, response)` wired into HTTP dispatch (`self.response.json(...)`)
- Mocked tests for Model / Elasticsearch / MySQL; path-param styles; HTTPException / multi-method; ASGI websocket smoke tests
- Middleware tests for nested `RouteGroup` accumulation, before/after order, and before short-circuit

## [1.0.0] - 2026-07-22
First major release. The HTTP stack (controllers, middleware, request/response) is intentionally redesigned; apps written against 0.3.x need updates. See [docs/](docs/index.md) and [gaps.md](docs/gaps.md).

### Breaking
- **Controller DI** — Controllers are no longer static-only. Base `Controller.__init__(request, response)` injects `self.request` / `self.response`. Actions are instance methods.
- **Middleware API** — Base `Middleware` uses the same DI plus async `before()` / `after()` (no `attach_to` / class-level `intercept`). Returning a `Response` from `before` short-circuits; `after` runs in reverse on the same instances.
- **Module renames** — Use `future.request` and `future.response` only. Plural shims (`future.requests` / `future.responses`) are gone.
- **Sessions** — Cookie session load/save is opt-in via `SessionMiddleware`, not implicit on every request.
- **Wrong HTTP method** — Matching lives in `Route.match(method, path)`. Wrong method on an existing path currently returns **404** (no match), not **405**.

### Added
- **`Request.query`** — Query string parsed at construction (single value → `str`, repeated keys → `list`).
- **Cached request body** — First `body()` caches bytes; `json()` / `form()` reuse that cache.
- **Task jitter** — Optional `Task(..., jitter=60)` adds `random.uniform(0, jitter)` seconds to each `next_run` (default off).
- **`SessionMiddleware`** — Cookie ↔ `request.session` (unsigned base64 JSON) under `future.middleware`.
- **Unified `Response` builder** — `json()`, `html()`, `text()`, `empty()`, `redirect()`, `file()`, `image()`, plus `set_cookie` / `delete_cookie`.
- **OpenAPI UIs** — Swagger, Scalar, RapiDoc, and ReDoc; optional `redocly_license_key` for paid Redocly Reference Docs CDN.
- **Handler docstrings → OpenAPI** — First line → `summary`, remainder → `description`.
- **Path params on all verbs** — `Get` / `Post` / `Put` / … share `Route` + `match` → `await method(**route_params)`.
- **MkDocs guides** — Rewritten `docs/` (HTTP, routing, database, OpenAPI, lifespan/tasks, CLI, examples, gaps) plus a slim README landing page.

### Changed
- Middleware and controllers are instantiated once per request; path params still pass as action kwargs.
- Interval scheduler remains fixed-interval (not crontab); jitter is the only spread control.
- Documentation no longer claims unfinished features (auth, full WS, GraphQL HTTP endpoint, etc.); gaps are listed explicitly.

### Fixed
- Duplicate HTTP method checks consolidated into `Route.match` only (post-match 405 path removed).
- Session cookie plumbing cleaned up (no nested helpers inside the ASGI handler).

### Migration notes (0.3 → 1.0)
```python
# Controllers
class TradeController(Controller):
    async def index(self) -> Response:
        return self.response.json({"ok": True})

# Middleware
class Auth(Middleware):
    async def before(self) -> Optional[Response]:
        if not self.request.headers.get("authorization"):
            return self.response.json({"error": "unauthorized"}, status=401)
        return None

# Imports
from future.request import Request
from future.response import Response
from future.middleware.SessionMiddleware import SessionMiddleware

# Query / body
q = self.request.query.get("q")
data = await self.request.json()  # safe after body()

# Tasks
Task("scrape", interval=1, unit=Unit.HOURS, func=scraper, jitter=60)
```

## [0.3.1] - 2025-01-06
### Added
- Initial release of the Future framework
- Basic ASGI application structure
- Core routing and middleware systems
- GraphQL support with Strawberry
- WebSocket support
- CLI tool for project management

### Changed
- Complete architectural overhaul
- Removed all decorators for minimal design
- Implemented static method patterns
- Centralized configuration management

### Removed
- Legacy database integration
- Complex dependency chains
- Decorator-based patterns
- Boilerplate files

## [0.3.0] - 2025-01-06
### Added
- Foundation of the Future framework
- Basic routing system
- Middleware infrastructure
- Type safety throughout

## [0.2.0] - 2025-01-06
### Added
- Initial project structure
- Core ASGI application
- Basic routing capabilities

## [0.1.0] - 2025-01-06
### Added
- Project initialization
- Basic framework structure
- Development environment setup

---

## Versioning
This project uses [Semantic Versioning](https://semver.org/) for version numbers.

### Version Increment Rules:
- **Patch releases** (1.0.0 → 1.0.1): Bug fixes and minor improvements
- **Minor releases** (1.0.0 → 1.1.0): New features, backward compatible
- **Major releases** (1.0.0 → 2.0.0): Breaking changes

### GitHub Workflows
All releases and publishing are handled automatically by GitHub workflows:
- **CI**: Runs on every push/PR (linting, type checking, tests, building)
- **Publish**: Automatically publishes to PyPI when tags are pushed
- **Versioning**: Uses `poetry-dynamic-versioning` for automatic version management

The version is automatically incremented based on git commit messages:
- `feat:` → minor version bump
- `BREAKING CHANGE:` → major version bump
- Default → patch version bump
