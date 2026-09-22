from elasticsearch import AsyncElasticsearch

from future.interfaces.IDatabase import IDatabase


class ElasticsearchDatabase(IDatabase):
    def __init__(self, host: str, port: int, username: str, password: str, database: str = ""):
        super().__init__(host, port, username, password, database)
        self.client = None

    async def connect(self):
        host = self.host or "127.0.0.1"
        if "://" not in host:
            host = f"http://{host}:{self.port or 9200}"
        auth = (self.username, self.password) if self.username else None
        self.client = AsyncElasticsearch(host, basic_auth=auth)
        return self.client

    async def disconnect(self):
        if self.client is not None:
            await self.client.close()
            self.client = None

    async def save(self, model):
        if self.client is None:
            await self.connect()
        name = model.tableize()
        document = model.to_dict()
        document_id = getattr(model, "id", None)
        if document_id:
            result = await self.client.index(index=name, id=document_id, document=document, refresh=True)
        else:
            result = await self.client.index(index=name, document=document, refresh=True)
        return {"status": "Document indexed", "result": result}

    async def find(self, model, id):
        if self.client is None:
            await self.connect()
        try:
            result = await self.client.get(index=model.tableize(), id=id)
        except Exception:
            return None
        if not result or "_source" not in result:
            return None
        source = dict(result["_source"] or {})
        if result.get("_id") is not None and not source.get("id"):
            source["id"] = result["_id"]
        return model.__class__(**source)

    async def all(self, model):
        if self.client is None:
            await self.connect()
        try:
            result = await self.client.search(index=model.tableize(), body={"query": {"match_all": {}}, "size": 10000})
        except Exception:
            return []
        rows = []
        for hit in result.get("hits", {}).get("hits", []):
            source = dict(hit.get("_source") or {})
            if hit.get("_id") is not None and not source.get("id"):
                source["id"] = hit["_id"]
            rows.append(model.__class__(**source))
        return rows

    async def get(self, model, wheres, limit=None, orders=None):
        if self.client is None:
            await self.connect()
        must = []
        for column, operator, value in wheres:
            if operator == "=":
                must.append({"match": {column: value}})
            elif operator == ">":
                must.append({"range": {column: {"gt": value}}})
            elif operator == ">=":
                must.append({"range": {column: {"gte": value}}})
            elif operator == "<":
                must.append({"range": {column: {"lt": value}}})
            elif operator == "<=":
                must.append({"range": {column: {"lte": value}}})
            elif operator == "!=":
                must.append({"bool": {"must_not": [{"match": {column: value}}]}})
            elif operator == "in":
                must.append({"terms": {column: list(value)}})
            elif operator == "like":
                pattern = str(value).replace("%", "*").replace("_", "?")
                must.append({"wildcard": {column: pattern}})
            else:
                raise ValueError(f"Unsupported operator: {operator}")
        size = limit if limit is not None else 10000
        body = {"query": {"bool": {"must": must}}, "size": size}
        if orders:
            body["sort"] = [{column: {"order": direction}} for column, direction in orders]
        try:
            result = await self.client.search(index=model.tableize(), body=body)
        except Exception:
            return []
        rows = []
        for hit in result.get("hits", {}).get("hits", []):
            source = dict(hit.get("_source") or {})
            if hit.get("_id") is not None and not source.get("id"):
                source["id"] = hit["_id"]
            rows.append(model.__class__(**source))
        return rows

    async def delete(self, model):
        if self.client is None:
            await self.connect()
        return await self.client.delete(index=model.tableize(), id=getattr(model, "id", None))

    async def update(self, model, changes):
        if self.client is None:
            await self.connect()
        return await self.client.update(index=model.tableize(), id=getattr(model, "id", None), doc=changes)

    async def schema_create(self, blueprint):
        if self.client is None:
            await self.connect()
        properties = self._mapping_properties(blueprint)
        if await self.client.indices.exists(index=blueprint.name):
            return {"status": "exists", "index": blueprint.name}
        result = await self.client.indices.create(index=blueprint.name, mappings={"properties": properties})
        return result

    def _mapping_properties(self, blueprint):
        properties = {}
        for column in blueprint.columns:
            if column.type == "string" and (column.is_primary or column.name == "id"):
                properties[column.name] = {"type": "keyword"}
            elif column.type == "string":
                properties[column.name] = {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}}
            elif column.type == "text":
                properties[column.name] = {"type": "text"}
            elif column.type == "integer":
                properties[column.name] = {"type": "long"}
            elif column.type == "float":
                properties[column.name] = {"type": "double"}
            elif column.type == "boolean":
                properties[column.name] = {"type": "boolean"}
            elif column.type == "datetime":
                properties[column.name] = {"type": "date"}
            else:
                raise ValueError(f"Unsupported column type: {column.type}")
        return properties

    async def schema_update(self, blueprint):
        if self.client is None:
            await self.connect()
        if not await self.client.indices.exists(index=blueprint.name):
            return await self.schema_create(blueprint)
        desired = self._mapping_properties(blueprint)
        mapping = await self.client.indices.get_mapping(index=blueprint.name)
        current = mapping.get(blueprint.name, {}).get("mappings", {}).get("properties", {})
        if current == desired:
            return {"status": "unchanged", "index": blueprint.name}
        additive = set(current).issubset(desired) and all(current[name] == desired[name] for name in current)
        if additive:
            await self.client.indices.put_mapping(index=blueprint.name, properties=desired)
            return {"status": "updated", "index": blueprint.name, "properties": sorted(desired)}

        temporary = f"_future_migrate_{blueprint.name}"
        if await self.client.indices.exists(index=temporary):
            await self.client.indices.delete(index=temporary)
        await self.client.indices.create(index=temporary, mappings={"dynamic": False, "properties": desired})
        keep = list(desired)
        script = {"source": "ctx._source.keySet().removeIf(k -> !params.keep.contains(k))", "params": {"keep": keep}}
        await self.client.reindex(body={"source": {"index": blueprint.name}, "dest": {"index": temporary}, "script": script}, wait_for_completion=True, refresh=True)
        await self.client.indices.delete(index=blueprint.name)
        await self.client.indices.create(index=blueprint.name, mappings={"dynamic": False, "properties": desired})
        await self.client.reindex(body={"source": {"index": temporary}, "dest": {"index": blueprint.name}}, wait_for_completion=True, refresh=True)
        await self.client.indices.delete(index=temporary)
        return {"status": "updated", "index": blueprint.name, "properties": sorted(desired)}

    async def schema_drop(self, name):
        if self.client is None:
            await self.connect()
        if not await self.client.indices.exists(index=name):
            return {"status": "missing", "index": name}
        return await self.client.indices.delete(index=name)

    async def table_exists(self, name):
        if self.client is None:
            await self.connect()
        return bool(await self.client.indices.exists(index=name))

    async def _ensure_migrations_index(self):
        if self.client is None:
            await self.connect()
        if await self.client.indices.exists(index="migrations"):
            return
        await self.client.indices.create(index="migrations", mappings={"properties": {"name": {"type": "keyword"}, "batch": {"type": "integer"}}})

    async def migrations_get(self):
        await self._ensure_migrations_index()
        result = await self.client.search(index="migrations", body={"query": {"match_all": {}}, "size": 10000, "sort": [{"batch": "asc"}, {"name": "asc"}]})
        return [hit["_source"]["name"] for hit in result.get("hits", {}).get("hits", [])]

    async def migrations_put(self, name, batch):
        await self._ensure_migrations_index()
        await self.client.index(index="migrations", id=name, document={"name": name, "batch": batch}, refresh=True)

    async def migrations_delete(self, name):
        await self._ensure_migrations_index()
        await self.client.delete(index="migrations", id=name, refresh=True)

    async def migrations_max_batch(self):
        await self._ensure_migrations_index()
        result = await self.client.search(index="migrations", body={"query": {"match_all": {}}, "size": 0, "aggs": {"max_batch": {"max": {"field": "batch"}}}})
        value = result.get("aggregations", {}).get("max_batch", {}).get("value")
        if value is None:
            return 0
        return int(value)

    async def migrations_batch_for(self, name):
        await self._ensure_migrations_index()
        try:
            result = await self.client.get(index="migrations", id=name)
        except Exception:
            return None
        if not result or "_source" not in result:
            return None
        return int(result["_source"]["batch"])
