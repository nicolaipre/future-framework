# Future
Minimal, decorator-free [ASGI](https://asgi.readthedocs.io/) framework for Python web APIs.

Future is built so you can stand up backends for larger applications quickly, with a clean separation between routing, controllers, middleware, models, and configuration. Explicit code over magic: controllers receive `request` / `response` from a base class, routes are plain lists, and there are no annoying decorators that you have to repeatedly add for every route.

## What you get
**Routing for real apps** — Group routes with prefixes, subdomains, and shared middleware. Nest groups when APIs grow. Path parameters land as action kwargs.

**OpenAPI that stays in sync** — Spec and interactive UIs (Swagger, ReDoc, Scalar, RapiDoc) follow your registered routes and docstrings. No parallel hand-maintained catalog of endpoints.

**Active Record, database-agnostic** — One awaitable `IModel` API across SQLite, MySQL, Postgres, Elasticsearch, MongoDB, ClickHouse, and Redis. Point `DATABASES` at another driver, migrate, and seed again — same models and CLI flow.

**Migrations and seeds from models** — Annotate fields on the model; the CLI generates migration and seeder stubs. Run them against whichever connection is configured.

**CLI for day-to-day work** — Scaffold a project (`future init`), generate models / controllers / middleware / migrations / seeds, list routes, migrate, seed, and run the app.

**HTTP and WebSockets** — Familiar request/response builders, middleware `before` / `after`, sessions and CORS when you opt in. WebSocket routes use the same grouping and controller pattern.

**Lifespan and scheduled work** — ASGI [Lifespan](lifespan.md) holds startup / shutdown / cron [Tasks](tasks.md) without a separate worker framework for simple jobs.

## Design
1. **No decorators** on framework or app code we control.
2. **Explicit over magic** — readable dispatch; no hidden IoC by default.
3. **Opt-in features** — sessions, OpenAPI UIs, and DB drivers are chosen in app config.
4. **Agnostic models** — switch underlying store in settings; keep the same Active Record code.

## Quick start
```python
from future.application import Future
from future.interfaces.IController import IController
from future.lifespan import Lifespan
from future.response import Response
from future.routing import Get, RouteGroup

class HomeController(IController):
    async def index(self) -> Response:
        return self.response.json({"ok": True})

routes = [
    RouteGroup(
        name="Main",
        routes=[Get("/", HomeController.index, "home")],
    )
]

lifespan = Lifespan(startup_tasks=[], shutdown_tasks=[], cron_tasks=[])
app = Future(lifespan=lifespan, config={"APP_DOMAIN": "", "APP_NAME": "Demo"})
app.add_routes(routes)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
```

`Future` always needs a `Lifespan` (empty startup / shutdown / cron lists are fine). For a full project layout, see [Getting started](getting-started.md).

## Guides
Published at [nicolaipre.github.io/future-framework](https://nicolaipre.github.io/future-framework/). Local preview: `uv sync --group docs && uv run mkdocs serve`.

| Guide | Package / topic |
|-------|-----------------|
| [Installation](installation.md) | Install + `future init` |
| [Getting started](getting-started.md) | Project layout and boot |
| [Controllers](controllers.md) | `future.controllers` |
| [Request](request.md) | `future.request` |
| [Response](response.md) | `future.response` |
| [Routing](routing.md) | `future.routing` |
| [Middleware](middleware.md) | `future.middleware` |
| [WebSockets](websockets.md) | `WebSocket` + `WebSocketResponse` |
| [Lifespan](lifespan.md) | `future.lifespan` — ASGI startup / cron / shutdown |
| [Tasks](tasks.md) | `future.interfaces.ITask` — scheduled work |
| [Configuration](configuration.md) | Settings, env, `DATABASES` |
| [Models](models.md) | `IModel` — annotations; generate migrate/seed |
| [Database](database.md) | `Database` registry and async drivers |
| [GraphQL](graphql.md) | Search-term `POST` + Strawberry payload |
| [Docker](docker.md) | Local DBs for testing |
| [OpenAPI](openapi.md) | `future.openapi` |
| [CLI](cli.md) | `future` console script |
| [Gaps](gaps.md) | What’s unfinished |
