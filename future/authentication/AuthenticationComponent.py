from __future__ import annotations

import inspect

from typing import Any

from future.authentication.Identity import Identity
from future.container import Container
from future.request import Request


class AuthenticationComponent:
    """Registry and lifecycle owner for named authentication providers."""

    def __init__(self, container: Container, config: dict[str, Any] | None = None) -> None:
        self._container = container
        self.config = config or {}
        self.default = self.config.get("default")
        self.providers: dict[str, Any] = {}
        for name, definition in self.config.get("providers", {}).items():
            self.register(name, self._build_provider(name, definition))
        if self.default is None and len(self.providers) == 1:
            self.default = next(iter(self.providers))

    def register(self, name: str, provider: Any) -> None:
        if not name:
            raise ValueError("Authentication provider names cannot be empty")
        if not callable(getattr(provider, "authenticate", None)):
            raise TypeError(f"Authentication provider {name!r} must define authenticate(request)")
        self.providers[name] = provider

    def get(self, name: str | None = None) -> Any:
        selected = name or self.default
        if not selected:
            raise LookupError("No default authentication provider is configured")
        try:
            return self.providers[selected]
        except KeyError as exc:
            raise LookupError(f"Authentication provider {selected!r} is not configured") from exc

    async def authenticate(self, request: Request, provider: str | None = None) -> Identity | None:
        selected = provider or self.default
        authenticator = self.get(selected)
        result = authenticator.authenticate(request)
        if inspect.isawaitable(result):
            result = await result
        if result is not None and not isinstance(result, Identity):
            raise TypeError(f"Authentication provider {selected!r} must return Identity or None, got {type(result).__name__}")
        return result

    async def start(self) -> None:
        for provider in self.providers.values():
            start = getattr(provider, "start", None)
            if start is not None:
                result = start()
                if inspect.isawaitable(result):
                    await result

    async def stop(self) -> None:
        for provider in reversed(list(self.providers.values())):
            stop = getattr(provider, "stop", None)
            if stop is not None:
                result = stop()
                if inspect.isawaitable(result):
                    await result

    def _build_provider(self, name: str, definition: Any) -> Any:
        if not isinstance(definition, dict):
            if inspect.isclass(definition):
                return self._container.resolve(definition)
            return definition
        driver = definition.get("driver")
        if driver is None:
            raise ValueError(f"Authentication provider {name!r} is missing its driver")
        options = definition.get("options") or {}
        if not isinstance(options, dict):
            raise TypeError(f"Authentication provider {name!r} options must be a dictionary")
        return self._container.resolve(driver, options=options)
