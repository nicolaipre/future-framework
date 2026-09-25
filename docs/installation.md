# Installation
## Requirements
- Python **3.12+**
- [uv](https://docs.astral.sh/uv/)

## Package
PyPI name is **`future-framework`**; import name is always **`future`**.

```bash
uv add future-framework
```

```toml
# pyproject.toml
dependencies = ["future-framework>=3.0.2,<4.0.0"]
```

```python
from future.application import Future
```

## Scaffold an app
```bash
uv run future init myproject
cd myproject
cp .env.example .env
uv sync
uv run future migrate
uv run future seed
uv run python run.py
```

See [Getting started](getting-started.md) and [Configuration](configuration.md).
