# CLI
```bash
future --help
```

Run from the project directory (where `run.py` lives). Commands that need the DB import `run.py` so `DATABASES` registers.

## Project
```bash
future init myproject
future init .
future run
future run --host 0.0.0.0 --port 8000 --workers 1
future routes
```

With `APP_DEBUG` or `workers>1`, set `config["APP_ASGI"]` (default `run:app`) so uvicorn can import the app.

## Generators
```bash
future make:model Stock
future make:controller Stock
future make:service Stock
future make:repository Stock
future make:interface StockRepository
future make:authentication Company
future make:middleware Auth
future make:plugin Cache
future make:task Cleanup
future make:migration Stock    # from model annotations
future make:migrations
future make:seed Stock         # from model annotations
future make:seeds
```

`make:migration` / `make:seed` (and the plural forms) read annotated fields on `app/models/*` — see [Models](models.md).

## Database
```bash
future migrate
future migrate rollback
future seed
future seed StockSeeder
```

See [Models](models.md), [Database](database.md), and [Configuration](configuration.md).
