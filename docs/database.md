# Database
Named registry and async drivers. Models, migrations, and seeds: see [Models](models.md).

## Register connections
Define the map in `app/config/Database.py` (data only — no registry call at import). Pass it into `Future` in `run.py`; boot calls `Database().set_connection_details(DATABASES)`:

```python
from future.databases.SQLiteDatabase import SQLiteDatabase
from app.config.Settings import DB_DATABASE

DATABASES = {
    "default": "sqlite",
    "sqlite": SQLiteDatabase(database=DB_DATABASE),
}
```

```python
from future.application import Future
from future.database import Database

config = {
    "APP_DOMAIN": APP_DOMAIN,
    "APP_NAME": APP_NAME,
    "DATABASES": DATABASES,
}
app = Future(lifespan=lifespan, config=config)
# same map: Database().get_connection("sqlite")
```

CLI `migrate` / `seed` load `run.py` so registration matches runtime. Env loading (`.env` or Ansible YAML): [Configuration](configuration.md).

## Per-model connection
Models are not locked to one database. Set `__connection__` on the model to a key from `DATABASES` (or `"default"` for `DATABASES["default"]`). Migrations inherit that name; see [Models](models.md#per-model-connection).

## Run migrations and seeds
Generate files **from model annotations** first (`future make:migration` / `make:seed`) — details in [Models](models.md). Then:

```bash
future migrate
future migrate rollback
future seed
future seed StockSeeder
```

Migrations use `async def up` / `async def down`. The first model snapshot uses `Schema.create`; later snapshots use `Schema.update` and carry the previous model shape in `down()` so rollback restores it. Seeders use `async def run` and `await model.save()`. The CLI runs them with `asyncio.run`.

`Schema.update` is database-polymorphic. SQL drivers reconcile the physical table while preserving data in columns shared by both snapshots; ClickHouse applies column alterations; Elasticsearch updates compatible mappings and reindexes for incompatible/removal changes; MongoDB replaces its collection validator; Redis stores the model schema as metadata because its records are schemaless.

## Drivers
Every driver is **async** (`create_async_engine` + aiosqlite / aiomysql / asyncpg; `redis.asyncio`; `AsyncMongoClient`; `AsyncElasticsearch`; ClickHouse `asynch`). `IDatabase` methods are `async def`.

| Driver | Schema / migrate | CRUD |
|--------|------------------|------|
| SQLite | Yes | Yes |
| MySQL | Yes | Yes |
| Postgres | Yes | Yes |
| Elasticsearch | Yes | Yes |
| MongoDB | Yes | Yes |
| ClickHouse | Yes | Yes |
| Redis | Yes (metadata) | Yes |

Scaffold default is **SQLite**. Set `DB_DATABASE` / `sqlite_database` to a bare name; the driver appends `.sqlite`.

Elasticsearch: if `host` has no `://`, the driver uses `http://{host}:{port or 9200}`. A full URL is used as-is. `basic_auth` is set only when `username` is set.

For local MySQL, Postgres, Redis, MongoDB, Elasticsearch, ClickHouse, and RabbitMQ, see the [Docker example](docker.md).
