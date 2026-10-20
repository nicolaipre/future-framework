# Routing
```python
from future.routing import Get, Post, Put, Patch, Delete, Head, Options, RouteGroup, WebSocket
```

Each helper takes `path`, `endpoint`, `name`:

```python
Get("/health", HealthController.ping, "health")
Post("/search", SearchController.search, "search")
```

`endpoint` is normally `SomeController.action` (unbound method). Future instantiates the controller per request. Routes are plain lists — no route decorators.

## Path parameters
```python
Get("/stocks/<str:stock_id>", StockController.get_stock, "stocks.show")
Get("/trades/user/<str:user_id>", TradeController.get_trades_by_user, "trades.by_user")
```

Values are kwargs on the action. Patterns: `<int:name>`, `<str:name>` / `<string:name>`, `<uuid:name>`, plus `/users/:id` and `{id}` forms.

## Groups
```python
from future.controllers.OpenAPIController import OpenAPIController
from future.middleware.CORSMiddleware import CORSMiddleware
from future.routing import RouteGroup, Get
from app.controllers.StockController import StockController
from app.controllers.TradeController import TradeController

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
    RouteGroup(
        prefix="/trades",
        name="Trades",
        middlewares=[CORSMiddleware],
        routes=[
            Get("/", TradeController.get_trades, "trades"),
            Get("/<str:trade_id>", TradeController.get_trade, "trades.show"),
        ],
    ),
]
```

- `prefix` concatenates for nested groups.
- `subdomain` needs a real `APP_DOMAIN`. When `APP_DOMAIN=""`, RouteGroup subdomains are ignored and every group shares one route table. The same path + method on two groups with different subdomains is a conflict — set `APP_DOMAIN` or use different prefixes.
- Middleware: see [applying middleware](middleware.md#applying-middleware).
- Route authorization: declare `scopes=["resource:read"]` and see [Scopes](middleware.md#scopes).

## WebSockets
`WebSocket("/ws/<int:id>", …)` — see [WebSockets](websockets.md).

## List routes
```bash
future routes
```

Expects `app` in `run.py`.
