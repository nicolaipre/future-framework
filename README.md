# Future
[ASGI](https://asgi.readthedocs.io/)-based framework for web APIs — routing, middleware, Active Record, migrations, seeds, OpenAPI, and interval tasks.

[![Build Status](https://github.com/nicolaipre/future-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/nicolaipre/future-framework/actions)
[![Package Version](https://img.shields.io/pypi/v/future-framework)](https://pypi.org/project/future-framework/)
[![Coverage](https://codecov.io/gh/nicolaipre/future-framework/branch/master/graph/badge.svg)](https://codecov.io/gh/nicolaipre/future-framework)

## Documentation
Published at **[nicolaipre.github.io/future-framework](https://nicolaipre.github.io/future-framework/)**. To preview locally: `uv sync --group docs && uv run mkdocs serve`.

## Install
```bash
uv add future-framework
uv run future init myproject
```

Import name is `future` (`from future.application import Future`).

## Hello
```python
from future.application import Future
from future.interfaces.IController import IController
from future.lifespan import Lifespan
from future.response import Response
from future.routing import Get, RouteGroup

class HomeController(IController):
    async def index(self) -> Response:
        return self.response.json({"ok": True})

app = Future(lifespan=Lifespan([], [], []), config={"APP_DOMAIN": "", "APP_NAME": "Demo"})
app.add_routes([RouteGroup(name="Main", routes=[Get("/", HomeController.index, "home")])])
app.run(host="127.0.0.1", port=8000)
```

## License
See [LICENSE](LICENSE). Versioning: [CHANGELOG.md](CHANGELOG.md).
