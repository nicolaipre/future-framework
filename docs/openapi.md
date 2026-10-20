# OpenAPI
Future builds an OpenAPI 3 document from registered routes and serves UIs.

## Mount docs
```python
from future.controllers.OpenAPIController import OpenAPIController
from future.routing import Get, RouteGroup

routes = [
    RouteGroup(
        name="Docs",
        routes=[
            Get("/openapi.json", OpenAPIController.openapi, "openapi"),
            Get("/swagger-config", OpenAPIController.swagger_config, "swagger-config"),
            Get("/docs", OpenAPIController.swagger, "docs"),
            Get("/redoc", OpenAPIController.redoc, "redoc"),
            Get("/scalar", OpenAPIController.scalar, "scalar"),
            Get("/rapidoc", OpenAPIController.rapidoc, "rapidoc"),
        ],
    ),
]
```

## Config
```python
"OPENAPI": {
    "enabled": True,
    "uis": ["swagger", "redoc", "scalar", "rapidoc"],
    "auto_routes": False,
    "path_prefix": "",
}
```

| Path | UI |
|------|-----|
| `/openapi.json` | Schema |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/scalar` | Scalar |
| `/rapidoc` | RapiDoc |

## Docstrings
First line → `summary`; rest → `description`:

```python
async def get_stocks(self) -> Response:
    """List stocks, optionally filtered by instrument_id or ticker.

    Query params: `instrument_id`, `ticker` (symbol).
    """
```
