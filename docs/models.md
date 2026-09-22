# Models
Active Record models live in `app/models/` and inherit `IModel`. **Class annotations are the source of truth** for columns — migrations and seeders are generated from them.

Reads and writes are **awaitable**: `find` / `all` / `save` / `delete` / `update` / `Query.get` / `Query.first`. `where` / `order_by` / `limit` only build the query.

## Define a model
```bash
future make:model Stock
```

```python
from future.interfaces.IModel import IModel

class Stock(IModel):
    # __table__ = "stocks"        # optional; default is tableized class name (Stock → stocks)
    # __connection__ = "default"  # name from DATABASES / Database()

    id: str
    name: str
    symbol: str
    instrument_id: str
    price: float | None
```

Register connections in [Configuration](configuration.md) / [Database](database.md) before using the model at runtime or in CLI.

## Per-model connection
`__connection__` selects which entry in `DATABASES` the model uses. Default is `"default"`, which resolves to the name in `DATABASES["default"]` (e.g. `"sqlite"`). Set it to any other registered key to put a model on a different store:

```python
from future.interfaces.IModel import IModel

class Stock(IModel):
    __connection__ = "default"   # → DATABASES["default"] → e.g. sqlite

class Trade(IModel):
    __connection__ = "mysql"     # → DATABASES["mysql"]

class Event(IModel):
    __connection__ = "postgres"  # → DATABASES["postgres"]
```

`future make:migration` copies the model’s `__connection__` onto the migration class. `future migrate` / `rollback` apply each migration on that connection (migration history is tracked per connection). Seeders call the model’s own `save()` / queries, so they follow the model connection automatically.

Register every named connection in `DATABASES` before use — see [Database](database.md).

## Annotations drive generators
After annotations are set:

```bash
future make:migration Stock   # → database/migrations/…_create_stocks.py from annotations
future make:seed Stock        # → database/seeds/StockSeeder.py from annotations

# or every annotated model under app/models/:
future make:migrations
future make:seeds             # skips seed files that already exist
```

The first migration generated for a model is a create snapshot. After changing the model annotations, run `make:migration` again: Future detects the earlier snapshot and generates an update migration. Its `up()` contains the new model shape and its `down()` contains the preceding shape, so both migrate and rollback remain model-driven.

When adding a column to a table that already contains rows, make the annotation optional or edit the generated column to supply `.default(...)`; a new required column without a value cannot preserve those rows and the database will reject the migration.

Then apply / run:

```bash
future migrate
future seed                   # all seeders
future seed StockSeeder       # one class name
```

Prefer either `make:migration Stock` **or** `make:migrations` for the same model in one session — not both (duplicate files).

Generated migration (from the `Stock` annotations above):

```python
from future.migrations import Migration, Schema

class CreateStocks(Migration):
    __connection__ = "default"

    async def up(self):
        async with Schema.create("stocks") as table:
            table.id()
            table.string("name")
            table.string("symbol")
            table.string("instrument_id")
            table.float("price").nullable()

    async def down(self):
        await Schema.drop("stocks")
```

Generated seeder uses the model fields (Faker stubs):

```python
from faker import Faker
from future.seeder import Seeder
from app.models.Stock import Stock

class StockSeeder(Seeder):
    async def run(self):
        fake = Faker()
        for _ in range(10):
            await Stock(
                id=fake.uuid4(),
                name=fake.company(),
                symbol=fake.unique.lexify(text="????").upper(),
                instrument_id=str(fake.random_int(10000, 99999)),
                price=float(fake.pyfloat(min_value=1, max_value=100)),
            ).save()
```

Edit generated files if you need indexes, extras, or richer seed data. Re-running generators does not replace hand-edited migrations; seeds skip existing files on `make:seeds`.

For example, adding `market: str | None` to `Stock` and generating again produces:

```python
class UpdateStocks(Migration):
    __connection__ = "default"

    async def up(self):
        async with Schema.update("stocks") as table:
            table.id()
            table.string("name")
            table.string("symbol")
            table.string("instrument_id")
            table.float("price").nullable()
            table.string("market").nullable()

    async def down(self):
        async with Schema.update("stocks") as table:
            table.id()
            table.string("name")
            table.string("symbol")
            table.string("instrument_id")
            table.float("price").nullable()
```

## CRUD
```python
stock = Stock(id="1", name="Equinor", symbol="EQNR", instrument_id="16105067", price=250.0)
await stock.save()

stock = await Stock.find("1")
stocks = await Stock.all()
stock.price = 251.0
await stock.save()
await stock.delete()
```

## Query
`where` / `order_by` / `limit` return a **Query** — `await` `.get()` or `.first()` to hit the DB:

```python
await Stock.where("symbol", "EQNR").first()
await Stock.where("price", ">", 100).order_by("price", "desc").get()
await Stock.where("name", "like", "%Equinor%").limit(20).get()
```

In a controller:

```python
async def get_stocks(self) -> Response:
    ticker = self.request.query.get("ticker")
    if ticker:
        stocks = await Stock.where("symbol", ticker).get()
    else:
        stocks = await Stock.all()
    return self.response.json([s.to_dict() for s in stocks], status=200)
```

See [CLI](cli.md) for the full command list and [Database](database.md) for drivers and connection registration.
