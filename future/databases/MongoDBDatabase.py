from future.interfaces.IDatabase import IDatabase
import re


class MongoDBDatabase(IDatabase):
    def __init__(self, host: str, port: int, username: str, password: str, database: str):
        super().__init__(host, port, username, password, database)
        self.client = None
        self.db = None

    async def connect(self):
        from pymongo import AsyncMongoClient
        if self.username:
            uri = f"mongodb://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        else:
            uri = f"mongodb://{self.host}:{self.port}/{self.database}"
        self.client = AsyncMongoClient(uri)
        self.db = self.client[self.database]
        return self.client

    async def disconnect(self):
        if self.client is not None:
            await self.client.close()
            self.client = None
            self.db = None

    async def save(self, model):
        if self.db is None:
            await self.connect()
        name = model.tableize()
        data = model.to_dict()
        doc_id = data.get("id")
        if doc_id is not None:
            await self.db[name].replace_one({"id": doc_id}, data, upsert=True)
        else:
            await self.db[name].insert_one(data)
        return {"status": "saved", "collection": name, "id": doc_id}

    async def find(self, model, id):
        if self.db is None:
            await self.connect()
        doc = await self.db[model.tableize()].find_one({"id": id}, {"_id": 0})
        if doc is None:
            return None
        return model.__class__(**doc)

    async def all(self, model):
        if self.db is None:
            await self.connect()
        return [model.__class__(**doc) async for doc in self.db[model.tableize()].find({}, {"_id": 0})]

    async def get(self, model, wheres, limit=None, orders=None):
        if self.db is None:
            await self.connect()
        query = {}
        for column, operator, value in wheres:
            if operator == "=":
                query[column] = value
            elif operator == "in":
                query[column] = {"$in": list(value)}
            elif operator == ">":
                query[column] = {"$gt": value}
            elif operator == ">=":
                query[column] = {"$gte": value}
            elif operator == "<":
                query[column] = {"$lt": value}
            elif operator == "<=":
                query[column] = {"$lte": value}
            elif operator == "!=":
                query[column] = {"$ne": value}
            elif operator == "like":
                parts = []
                for char in str(value):
                    if char == "%":
                        parts.append(".*")
                    elif char == "_":
                        parts.append(".")
                    else:
                        parts.append(re.escape(char))
                query[column] = {"$regex": "^" + "".join(parts) + "$"}
            else:
                raise ValueError(f"Unsupported operator: {operator}")
        cursor = self.db[model.tableize()].find(query, {"_id": 0})
        if orders:
            cursor = cursor.sort([(column, 1 if str(direction).upper() == "ASC" else -1) for column, direction in orders])
        if limit is not None:
            cursor = cursor.limit(int(limit))
        return [model.__class__(**doc) async for doc in cursor]

    async def delete(self, model):
        if self.db is None:
            await self.connect()
        name = model.tableize()
        doc_id = getattr(model, "id", None)
        await self.db[name].delete_one({"id": doc_id})
        return {"status": "deleted", "collection": name, "id": doc_id}

    async def update(self, model, changes):
        if self.db is None:
            await self.connect()
        name = model.tableize()
        doc_id = getattr(model, "id", None)
        if not changes:
            return {"status": "noop", "collection": name, "id": doc_id}
        await self.db[name].update_one({"id": doc_id}, {"$set": changes})
        return {"status": "updated", "collection": name, "id": doc_id}

    async def schema_create(self, blueprint):
        if self.db is None:
            await self.connect()
        validator = self._validator(blueprint)
        if blueprint.name in await self.db.list_collection_names():
            return {"status": "exists", "collection": blueprint.name}
        await self.db.create_collection(blueprint.name, validator=validator)
        await self._ensure_indexes(blueprint)
        return {"status": "created", "collection": blueprint.name}

    def _validator(self, blueprint):
        properties = {}
        required = []
        for column in blueprint.columns:
            if column.type == "string" or column.type == "text":
                bson_type = "string"
            elif column.type == "integer":
                bson_type = "long"
            elif column.type == "float":
                bson_type = "double"
            elif column.type == "boolean":
                bson_type = "bool"
            elif column.type == "datetime":
                bson_type = "date"
            else:
                raise ValueError(f"Unsupported column type: {column.type}")
            properties[column.name] = {"bsonType": bson_type}
            if not column.is_nullable and not column.is_primary:
                required.append(column.name)
        validator = {"$jsonSchema": {"bsonType": "object", "properties": properties}}
        if required:
            validator["$jsonSchema"]["required"] = required
        return validator

    async def _ensure_indexes(self, blueprint):
        for column in blueprint.columns:
            if column.is_unique or column.is_primary:
                await self.db[blueprint.name].create_index(column.name, unique=True)
            elif column.is_index:
                await self.db[blueprint.name].create_index(column.name)

    async def table_exists(self, name):
        if self.db is None:
            await self.connect()
        return name in await self.db.list_collection_names()

    async def schema_update(self, blueprint):
        if self.db is None:
            await self.connect()
        if not await self.table_exists(blueprint.name):
            return await self.schema_create(blueprint)
        validator = self._validator(blueprint)
        await self.db.command({"collMod": blueprint.name, "validator": validator})
        await self._ensure_indexes(blueprint)
        return {"status": "updated", "collection": blueprint.name, "properties": sorted(column.name for column in blueprint.columns)}

    async def schema_drop(self, name):
        if self.db is None:
            await self.connect()
        await self.db.drop_collection(name)
        return {"status": "dropped", "collection": name}

    async def migrations_get(self):
        if self.db is None:
            await self.connect()
        return [doc["name"] async for doc in self.db["_migrations"].find().sort([("batch", 1), ("name", 1)])]

    async def migrations_put(self, name, batch):
        if self.db is None:
            await self.connect()
        await self.db["_migrations"].update_one({"name": name}, {"$set": {"name": name, "batch": batch}}, upsert=True)

    async def migrations_delete(self, name):
        if self.db is None:
            await self.connect()
        await self.db["_migrations"].delete_one({"name": name})

    async def migrations_max_batch(self):
        if self.db is None:
            await self.connect()
        doc = await self.db["_migrations"].find_one(sort=[("batch", -1)])
        if doc is None:
            return 0
        return int(doc["batch"])

    async def migrations_batch_for(self, name):
        if self.db is None:
            await self.connect()
        doc = await self.db["_migrations"].find_one({"name": name})
        if doc is None:
            return None
        return int(doc["batch"])
