# Controllers
Controllers get `request` / `response` from a base class. Routes are plain lists. No route decorators.

`future.interfaces.IController` injects them in `__init__`:

```python
from future.interfaces.IController import IController
from future.response import Response

class StockController(IController):
    async def get_stock(self, stock_id: str) -> Response:
        return self.response.json({"id": stock_id})
```

Do not add your own `__init__` unless you need dependencies — Future constructs controllers per request and resolves annotated constructor dependencies automatically.

```python
class StockController(IController):
    def __init__(self, request: Request, response: Response, stocks: StockService) -> None:
        super().__init__(request, response)
        self.stocks = stocks

    async def get_stock(self, stock_id: str) -> Response:
        stock = await self.stocks.find(stock_id)
        return self.response.json(stock.to_dict())
```

Concrete dependencies need no registration. An interface with multiple implementations needs one `BINDINGS` choice in application config. See [Dependencies](dependencies.md).

## Example
```python
from future.interfaces.IController import IController
from future.response import Response
from app.models.Stock import Stock

class StockController(IController):
    async def get_stocks(self) -> Response:
        instrument_id = self.request.query.get("instrument_id")
        if instrument_id:
            stocks = await Stock.where("instrument_id", instrument_id).get()
        else:
            stocks = await Stock.all()
        return self.response.json([stock.to_dict() for stock in stocks], status=200)

    async def get_stock(self, stock_id: str) -> Response:
        stock = await Stock.find(stock_id)
        if stock is None:
            return self.response.json({"error": "Not found"}, status=404)
        return self.response.json(stock.to_dict(), status=200)
```

Register **class method references**, not instances:

```python
from future.routing import Get

Get("/stocks", StockController.get_stocks, "stocks")
Get("/stocks/<str:stock_id>", StockController.get_stock, "stocks.show")
```

Path params become action kwargs. See [Routing](routing.md), [Request](request.md), [Response](response.md). Search over the demo user/post models: [GraphQL](graphql.md).
