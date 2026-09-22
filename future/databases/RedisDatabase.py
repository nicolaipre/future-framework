import json
import re

from future.interfaces.IDatabase import IDatabase


class RedisDatabase(IDatabase):
    def __init__(self, host: str, port: int, username: str, password: str, database: str):
        super().__init__(host, port, username, password, database)
        self.client = None

    async def connect(self):
        from redis.asyncio import Redis
        db_index = int(self.database) if str(self.database).isdigit() else 0
        self.client = Redis(host=self.host or "127.0.0.1", port=self.port or 6379, username=self.username or None, password=self.password or None, db=db_index, decode_responses=True)
        await self.client.ping()
        return self.client

    async def disconnect(self):
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    def _key(self, table, id):
        return f"{table}:{id}"

    def _ids_key(self, table):
        return f"{table}:ids"

    def _schema_key(self, table):
        return f"future:schema:{table}"

    def _migrations_key(self):
        return "future:migrations"

    async def save(self, model):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        data = model.to_dict()
        doc_id = data.get("id")
        if doc_id is None:
            raise ValueError("Redis models require an id for save()")
        await self.client.set(self._key(table, doc_id), json.dumps(data))
        await self.client.sadd(self._ids_key(table), str(doc_id))
        return {"status": "saved", "key": self._key(table, doc_id), "id": doc_id}

    async def find(self, model, id):
        if self.client is None:
            await self.connect()
        raw = await self.client.get(self._key(model.tableize(), id))
        if raw is None:
            return None
        return model.__class__(**json.loads(raw))

    async def all(self, model):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        ids = await self.client.smembers(self._ids_key(table))
        rows = []
        for doc_id in ids:
            raw = await self.client.get(self._key(table, doc_id))
            if raw is not None:
                rows.append(model.__class__(**json.loads(raw)))
        return rows

    async def get(self, model, wheres, limit=None, orders=None):
        rows = await self.all(model)
        for column, operator, value in wheres:
            filtered = []
            for row in rows:
                current = getattr(row, column, None)
                if operator == "=" and current == value:
                    filtered.append(row)
                elif operator == "!=" and current != value:
                    filtered.append(row)
                elif operator == ">" and current is not None and current > value:
                    filtered.append(row)
                elif operator == ">=" and current is not None and current >= value:
                    filtered.append(row)
                elif operator == "<" and current is not None and current < value:
                    filtered.append(row)
                elif operator == "<=" and current is not None and current <= value:
                    filtered.append(row)
                elif operator == "in" and current in list(value):
                    filtered.append(row)
                elif operator == "like" and current is not None:
                    parts = []
                    for char in str(value):
                        if char == "%":
                            parts.append(".*")
                        elif char == "_":
                            parts.append(".")
                        else:
                            parts.append(re.escape(char))
                    if re.search("^" + "".join(parts) + "$", str(current)):
                        filtered.append(row)
                elif operator not in ("=", "!=", ">", ">=", "<", "<=", "in", "like"):
                    raise ValueError(f"Unsupported operator: {operator}")
            rows = filtered
        if orders:
            for column, direction in reversed(orders):
                rows.sort(key=lambda row: getattr(row, column, None), reverse=str(direction).upper() == "DESC")
        if limit is not None:
            rows = rows[: int(limit)]
        return rows

    async def delete(self, model):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        doc_id = getattr(model, "id", None)
        await self.client.delete(self._key(table, doc_id))
        await self.client.srem(self._ids_key(table), str(doc_id))
        return {"status": "deleted", "key": self._key(table, doc_id), "id": doc_id}

    async def update(self, model, changes):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        doc_id = getattr(model, "id", None)
        if not changes:
            return {"status": "noop", "id": doc_id}
        raw = await self.client.get(self._key(table, doc_id))
        if raw is None:
            return {"status": "missing", "id": doc_id}
        data = json.loads(raw)
        data.update(changes)
        await self.client.set(self._key(table, doc_id), json.dumps(data))
        return {"status": "updated", "id": doc_id}

    async def schema_create(self, blueprint):
        if self.client is None:
            await self.connect()
        schema = self._schema_document(blueprint)
        created = await self.client.set(self._schema_key(blueprint.name), json.dumps(schema, sort_keys=True, default=str), nx=True)
        return {"status": "created" if created else "exists", "table": blueprint.name}

    def _schema_document(self, blueprint):
        return {
            "name": blueprint.name,
            "columns": [
                {
                    "name": column.name,
                    "type": column.type,
                    "length": column.length,
                    "nullable": column.is_nullable,
                    "unique": column.is_unique,
                    "primary": column.is_primary,
                    "index": column.is_index,
                    "default": column.default_value,
                }
                for column in blueprint.columns
            ],
        }

    async def table_exists(self, name):
        if self.client is None:
            await self.connect()
        return bool(await self.client.exists(self._schema_key(name)))

    async def schema_update(self, blueprint):
        if self.client is None:
            await self.connect()
        await self.client.set(self._schema_key(blueprint.name), json.dumps(self._schema_document(blueprint), sort_keys=True, default=str))
        return {"status": "updated", "table": blueprint.name, "columns": sorted(column.name for column in blueprint.columns)}

    async def schema_drop(self, name):
        if self.client is None:
            await self.connect()
        ids = await self.client.smembers(self._ids_key(name))
        keys = [self._key(name, doc_id) for doc_id in ids]
        keys.extend([self._ids_key(name), self._schema_key(name)])
        if keys:
            await self.client.delete(*keys)
        return {"status": "dropped", "table": name}

    async def migrations_get(self):
        if self.client is None:
            await self.connect()
        return list(await self.client.zrange(self._migrations_key(), 0, -1))

    async def migrations_put(self, name, batch):
        if self.client is None:
            await self.connect()
        await self.client.zadd(self._migrations_key(), {name: int(batch)})

    async def migrations_delete(self, name):
        if self.client is None:
            await self.connect()
        await self.client.zrem(self._migrations_key(), name)

    async def migrations_max_batch(self):
        if self.client is None:
            await self.connect()
        rows = await self.client.zrevrange(self._migrations_key(), 0, 0, withscores=True)
        if not rows:
            return 0
        return int(rows[0][1])

    async def migrations_batch_for(self, name):
        if self.client is None:
            await self.connect()
        score = await self.client.zscore(self._migrations_key(), name)
        return None if score is None else int(score)
