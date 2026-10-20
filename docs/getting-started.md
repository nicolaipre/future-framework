# Getting started
Scaffold with `future init`, then work in the layout below. Examples match how a real app (controllers, models, `run.py`) uses Future.

## Project layout
```text
myproject/
  run.py                 # Future(...), add_routes, app.run
  .env                   # from .env.example (or use environment.yml — see Configuration)
  app/
    config/
      Settings.py        # load env → APP_*, DB_*
      Database.py        # DATABASES map
    controllers/
    authentication/
    interfaces/          # I-prefixed contracts only
    models/
    middleware/
    plugins/
    repositories/
    services/
    tasks/
    routes.py
  database/
    migrations/
    seeds/
```

## Application naming

Application components are classes named for their role and stored in the matching folder:

- Interfaces are the only classes with an `I` prefix and live in `app/interfaces`, for example `IUserRepository`.
- Authentication classes end in `Authentication` and live in `app/authentication`.
- Controllers end in `Controller` and live in `app/controllers`.
- Middleware ends in `Middleware` and lives in `app/middleware`.
- Plugins end in `Plugin` and live in `app/plugins`.
- Repositories end in `Repository` and live in `app/repositories`.
- Services end in `Service` and live in `app/services`.
- Tasks end in `Task` and live in `app/tasks`.

The CLI applies role suffixes to the component types it generates. For example, `future make:repository User` creates `app/repositories/UserRepository.py`. Interfaces express application-specific contracts, so they are authored directly in `app/interfaces` rather than generated.

## Boot (`run.py`)
```python
from app.config.Settings import APP_HOST, APP_PORT, APP_WORKERS, APP_NAME, APP_DOMAIN, APP_DEBUG
from app.config.Database import DATABASES
from app.routes import routes
from future.application import Future
from future.lifespan import Lifespan

config = {
    "APP_DOMAIN": APP_DOMAIN,
    "APP_NAME": APP_NAME,
    "APP_DEBUG": APP_DEBUG,
    "DATABASES": DATABASES,
    "OPENAPI": {
        "enabled": True,
        "uis": ["swagger", "redoc", "scalar", "rapidoc"],
        "auto_routes": False,
    },
}

lifespan = Lifespan(startup_tasks=[], shutdown_tasks=[], cron_tasks=[])
app = Future(lifespan=lifespan, config=config)
app.add_routes(routes)

if __name__ == "__main__":
    app.run(host=APP_HOST, port=APP_PORT, workers=APP_WORKERS)
```

CLI `migrate` / `seed` / `routes` import this `app` so `DATABASES` registers the same way as at runtime.

## Controllers
See [Controllers](controllers.md). Short version: inherit `IController`, use `self.request` / `self.response`, register class methods on routes.

## Routes (`app/routes.py`)
```python
from future.controllers.OpenAPIController import OpenAPIController
from future.routing import RouteGroup, Get
from app.controllers.StockController import StockController

routes = [
    RouteGroup(
        name="Docs",
        routes=[
            Get("/openapi.json", OpenAPIController.openapi, "openapi"),
            Get("/docs", OpenAPIController.swagger, "docs"),
            Get("/redoc", OpenAPIController.redoc, "redoc"),
            Get("/scalar", OpenAPIController.scalar, "scalar"),
            Get("/rapidoc", OpenAPIController.rapidoc, "rapidoc"),
        ],
    ),
    RouteGroup(
        prefix="/stocks",
        name="Stocks",
        routes=[
            Get("/", StockController.get_stocks, "stocks"),
            Get("/<str:stock_id>", StockController.get_stock, "stocks.show"),
        ],
    ),
]
```

## First database cycle
```bash
cp .env.example .env          # DB_DATABASE=database → database.sqlite
future make:model Stock
# edit annotations on app/models/Stock.py — migrations/seeds are generated from these
future make:migration Stock
future make:seed Stock
future migrate
future seed
future run
```

Details: [Models](models.md), [Configuration](configuration.md), [Database](database.md), [CLI](cli.md).
