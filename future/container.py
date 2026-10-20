from __future__ import annotations

import inspect
import types

from collections.abc import Mapping
from typing import Any, Union, get_args, get_origin, get_type_hints

from future.interfacing import Interface


class ResolutionError(TypeError):
    """Raised when the application container cannot build a dependency."""


class Container:
    """Small application container with explicit bindings and typed construction.

    Future owns this container. Application classes opt into injection by adding
    annotated constructor parameters; concrete classes need no registration.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self._bindings: dict[Any, Any] = {}
        self._instances: dict[Any, Any] = {}
        self._components: list[Any] = []
        self._started_components: list[Any] = []

    def bind(self, contract: Any, implementation: Any) -> None:
        self._bindings[contract] = implementation

    def instance(self, key: Any, value: Any) -> Any:
        self._instances[key] = value
        return value

    def component(self, value: Any, key: Any | None = None) -> Any:
        self.instance(key or type(value), value)
        if value not in self._components:
            self._components.append(value)
        return value

    def override(self, key: Any, value: Any) -> None:
        self.instance(key, value)

    def configure_bindings(self, bindings: Mapping[Any, Any] | None) -> None:
        for contract, implementation in (bindings or {}).items():
            self.bind(contract, implementation)

    def get(self, target: Any) -> Any:
        return self.resolve(target)

    def resolve(self, target: Any, provided: Mapping[Any, Any] | None = None, options: Mapping[str, Any] | None = None) -> Any:
        return self._resolve(target, dict(provided or {}), dict(options or {}), [])

    def _resolve(self, target: Any, provided: dict[Any, Any], options: dict[str, Any], stack: list[Any]) -> Any:
        if target in provided:
            return provided[target]
        if target in self._instances:
            return self._instances[target]

        implementation = self._bindings.get(target, target)
        if implementation in self._instances:
            return self._instances[implementation]
        if not inspect.isclass(implementation):
            return implementation

        if implementation in stack:
            chain = " -> ".join(self._name(item) for item in [*stack, implementation])
            raise ResolutionError(f"Circular dependency detected: {chain}")

        if self._is_unbound_interface(implementation):
            chain = " -> ".join(self._name(item) for item in [*stack, implementation])
            raise ResolutionError(f"No binding configured for {self._name(implementation)} while resolving {chain}")

        constructor = implementation.__init__
        if constructor is object.__init__:
            return implementation()

        try:
            hints = get_type_hints(constructor)
        except (NameError, TypeError):
            hints = {}

        kwargs: dict[str, Any] = {}
        next_stack = [*stack, implementation]
        parameters = inspect.signature(constructor).parameters
        accepts_options = any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
        used_options: set[str] = set()
        for name, parameter in parameters.items():
            if name == "self" or parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
                raise ResolutionError(f"Cannot resolve positional-only constructor parameter {self._name(implementation)}.{name}")
            if name in options:
                kwargs[name] = options[name]
                used_options.add(name)
                continue
            annotation = hints.get(name, parameter.annotation)
            if name in provided:
                kwargs[name] = provided[name]
                continue
            if annotation in provided:
                kwargs[name] = provided[annotation]
                continue
            dependency = self._optional_dependency(annotation)
            if dependency is None:
                if parameter.default is not inspect.Parameter.empty:
                    continue
                chain = " -> ".join(self._name(item) for item in next_stack)
                raise ResolutionError(f"Cannot resolve {self._name(implementation)}.{name} while resolving {chain}: add a type annotation or provide a configured option")
            if dependency in (str, int, float, bool, bytes, dict, list, set, tuple, Any):
                if parameter.default is not inspect.Parameter.empty:
                    continue
                chain = " -> ".join(self._name(item) for item in next_stack)
                raise ResolutionError(f"Cannot resolve configured value {self._name(implementation)}.{name}: provide it in the component options (dependency chain: {chain})")
            try:
                kwargs[name] = self._resolve(dependency, provided, {}, next_stack)
            except ResolutionError:
                if parameter.default is not inspect.Parameter.empty:
                    continue
                raise

        unused_options = set(options) - used_options
        if unused_options and accepts_options:
            kwargs.update({name: options[name] for name in unused_options})
        elif unused_options:
            names = ", ".join(sorted(unused_options))
            raise ResolutionError(f"Unknown configured option(s) for {self._name(implementation)}: {names}")

        try:
            return implementation(**kwargs)
        except TypeError as exc:
            chain = " -> ".join(self._name(item) for item in next_stack)
            raise ResolutionError(f"Could not construct {self._name(implementation)} while resolving {chain}: {exc}") from exc

    async def start(self) -> None:
        if self._started_components:
            return
        try:
            for component in self._components:
                start = getattr(component, "start", None)
                if start is not None:
                    result = start()
                    if inspect.isawaitable(result):
                        await result
                self._started_components.append(component)
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        components = list(reversed(self._started_components))
        self._started_components = []
        for component in components:
            stop = getattr(component, "stop", None)
            if stop is not None:
                result = stop()
                if inspect.isawaitable(result):
                    await result

    def _optional_dependency(self, annotation: Any) -> Any | None:
        if annotation is inspect.Parameter.empty:
            return None
        origin = get_origin(annotation)
        if origin in (Union, types.UnionType):
            dependencies = [item for item in get_args(annotation) if item is not type(None)]
            return dependencies[0] if len(dependencies) == 1 else None
        return annotation

    def _is_unbound_interface(self, target: type[Any]) -> bool:
        if not issubclass(target, Interface):
            return False
        for value in target.__dict__.values():
            if callable(value) and Interface._is_stub(value):
                return True
        return False

    def _name(self, value: Any) -> str:
        return getattr(value, "__name__", repr(value))
