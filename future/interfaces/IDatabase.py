# Interface for all database types (MySQL, Elasticsearch, Clickhouse, Redis, etc.).
# Concrete databases implement these with their own storage primitives
# (tables, indices, keys, ...). Model only calls these names.

from future.interfacing import Interface


class IDatabase(Interface):
    def __init__(self, host: str, port: int, username: str, password: str, database: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database

    async def connect(self):
        raise NotImplementedError

    async def disconnect(self):
        raise NotImplementedError

    async def save(self, model):
        raise NotImplementedError

    async def find(self, model, id):
        raise NotImplementedError

    async def all(self, model):
        raise NotImplementedError

    async def get(self, model, wheres, limit=None, orders=None):
        raise NotImplementedError

    async def delete(self, model):
        raise NotImplementedError

    async def update(self, model, changes):
        raise NotImplementedError

    async def schema_create(self, blueprint):
        raise NotImplementedError

    async def schema_update(self, blueprint):
        raise NotImplementedError

    async def schema_drop(self, name):
        raise NotImplementedError

    async def migrations_get(self):
        raise NotImplementedError

    async def migrations_put(self, name, batch):
        raise NotImplementedError

    async def migrations_delete(self, name):
        raise NotImplementedError

    async def migrations_max_batch(self):
        raise NotImplementedError

    async def migrations_batch_for(self, name):
        raise NotImplementedError

    async def transaction(self):
        client = getattr(self, "client", None)
        if client is None:
            await self.connect()
            client = getattr(self, "client", None)
        if client is None or not hasattr(client, "begin"):
            raise NotImplementedError(f"{type(self).__name__} does not support transactions")
        return client.begin()
