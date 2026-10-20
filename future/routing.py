import re

from typing import Any, Callable, Optional, TypedDict

from future.logger import log
from future.interfaces.IMiddleware import IMiddleware


class RegexConfig(TypedDict):
    paths: list[re.Pattern[str]]


class RouteException(Exception):
    pass


class InvalidValuePatternName(RouteException):
    def __init__(self, pattern_name: str, matched_parameter: str) -> None:
        self.pattern_name = pattern_name
        self.matched_parameter = matched_parameter
        super().__init__(f"Invalid value pattern name: {pattern_name} in {matched_parameter}")


class RouteMatch:
    def __init__(self, route: "Route", params: Optional[dict[str, str]]) -> None:
        self.route = route
        self.params = params


class Route:
    value_patterns = {
        "string": r"[^\/]+",
        "str": r"[^\/]+",
        "path": r".*",
        "int": r"\d+",
        "float": r"\d+(?:\.\d+)?",
        "uuid": r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
    }

    def __init__(
        self,
        methods: list[str],
        path: str,
        endpoint: Callable[..., Any],
        name: str,
        strict_slashes: bool = False,
        middlewares: Optional[list[Any]] = None,
        scopes: Optional[list[str]] = None,
    ) -> None:
        self.methods = methods
        self.path = path
        self.endpoint = endpoint
        self.name = name
        self.strict_slashes = strict_slashes
        self.middlewares = middlewares or []
        self.scopes = scopes or []

    # Huge credits to BlackSheep for the code below.
    def compile_pattern(self) -> None:
        _route_all_rx = re.compile(b"\\*")
        _route_param_rx = re.compile(b"/:([^/]+)")

        _mustache_route_param_rx = re.compile(b"/{([^}]+)}")
        _angle_bracket_route_param_rx = re.compile(b"/<([^>]+)>")

        _named_group_rx = re.compile(b"\\?P<([^>]+)>")
        _escaped_chars = {
            b".",
            b"[",
            b"]",
            b"(",
            b")",
        }

        def _get_parameter_pattern_fragment(name: str, pattern: Optional[str] = None) -> bytes:
            if pattern is None:
                pattern = Route.value_patterns["string"]
            return rb"/(?P<" + name.encode() + rb">" + pattern.encode() + rb")"

        def _handle_rich_parameter(match: re.Match[bytes]) -> bytes:
            matched_parameter = next(iter(match.groups()))
            assert isinstance(matched_parameter, bytes)

            if b":" in matched_parameter:
                raw_pattern_name, parameter_name = matched_parameter.split(b":")
                parameter_pattern_name = raw_pattern_name.decode()
                parameter_pattern = Route.value_patterns.get(parameter_pattern_name)

                if not parameter_pattern:
                    raise InvalidValuePatternName(parameter_pattern_name, matched_parameter.decode("utf8"))

                return _get_parameter_pattern_fragment(parameter_name.decode(), parameter_pattern)

            return _get_parameter_pattern_fragment(matched_parameter.decode())

        pattern = self.path.encode()
        for c in _escaped_chars:
            if c in pattern:
                pattern = pattern.replace(c, b"\\" + c)

        if b"*" in pattern:
            if pattern.count(b"*") > 1:
                raise RouteException("A route pattern cannot contain more than one star sign *.")
            if b"/*" in pattern:
                pattern = _route_all_rx.sub(rb"?(?P<tail>.*)", pattern)
            else:
                pattern = _route_all_rx.sub(rb"(?P<tail>.*)", pattern)

        if b"<" in pattern:
            pattern = _angle_bracket_route_param_rx.sub(_handle_rich_parameter, pattern)

        if b"{" in pattern:
            pattern = _mustache_route_param_rx.sub(_handle_rich_parameter, pattern)

        if b"/:" in pattern:
            pattern = _route_param_rx.sub(rb"/(?P<\1>[^\/]+)", pattern)

        param_names = []
        for p in _named_group_rx.finditer(pattern):
            param_name = p.group(1).decode()

            if param_name in param_names:
                raise ValueError(f"cannot have multiple parameters with name: {param_name}")

            param_names.append(param_name)

        if len(pattern) > 1 and not pattern.endswith(b"*") and not self.strict_slashes:
            pattern = pattern + b"/?"

        self._rx = re.compile(b"^" + pattern + b"$", re.IGNORECASE)

        self.param_names = param_names

    def match(self, request_method: str, request_path: bytes) -> Optional[RouteMatch]:
        log.debug("Matching on request type %s for path: %s using regex: %s", self.methods, request_path, self._rx)
        # Check if the HTTP method matches the allowed methods for this route
        if request_method not in self.methods:
            return None

        # Check if the request path matches the compiled regex pattern for this route
        match = self._rx.match(request_path)
        if not match:
            return None

        # Convert bytes values to strings in groupdict
        params = None
        if self.param_names:
            groupdict = match.groupdict()
            params = {key: value.decode("utf-8") if isinstance(value, bytes) else str(value) for key, value in groupdict.items()}

        route_match = RouteMatch(self, params)
        return route_match


class Get(Route):
    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        name: str,
        strict_slashes: bool = False,
        middlewares: Optional[list[Any]] = None,
        scopes: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            methods=["GET"],
            path=path,
            endpoint=endpoint,
            name=name,
            strict_slashes=strict_slashes,
            middlewares=middlewares,
            scopes=scopes,
        )


class Post(Route):
    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        name: str,
        strict_slashes: bool = False,
        middlewares: Optional[list[Any]] = None,
        scopes: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            methods=["POST"],
            path=path,
            endpoint=endpoint,
            name=name,
            strict_slashes=strict_slashes,
            middlewares=middlewares,
            scopes=scopes,
        )


class Put(Route):
    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        name: str,
        strict_slashes: bool = False,
        middlewares: Optional[list[Any]] = None,
        scopes: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            methods=["PUT"],
            path=path,
            endpoint=endpoint,
            name=name,
            strict_slashes=strict_slashes,
            middlewares=middlewares,
            scopes=scopes,
        )


class Head(Route):
    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        name: str,
        strict_slashes: bool = False,
        middlewares: Optional[list[Any]] = None,
        scopes: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            methods=["HEAD"],
            path=path,
            endpoint=endpoint,
            name=name,
            strict_slashes=strict_slashes,
            middlewares=middlewares,
            scopes=scopes,
        )


class Options(Route):
    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        name: str,
        strict_slashes: bool = False,
        middlewares: Optional[list[Any]] = None,
        scopes: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            methods=["OPTIONS"],
            path=path,
            endpoint=endpoint,
            name=name,
            strict_slashes=strict_slashes,
            middlewares=middlewares,
            scopes=scopes,
        )


class Patch(Route):
    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        name: str,
        strict_slashes: bool = False,
        middlewares: Optional[list[Any]] = None,
        scopes: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            methods=["PATCH"],
            path=path,
            endpoint=endpoint,
            name=name,
            strict_slashes=strict_slashes,
            middlewares=middlewares,
            scopes=scopes,
        )


class Delete(Route):
    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        name: str,
        strict_slashes: bool = False,
        middlewares: Optional[list[Any]] = None,
        scopes: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            methods=["DELETE"],
            path=path,
            endpoint=endpoint,
            name=name,
            strict_slashes=strict_slashes,
            middlewares=middlewares,
            scopes=scopes,
        )


class WebSocket(Route):
    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        name: str,
        strict_slashes: bool = False,
        middlewares: Optional[list[Any]] = None,
        scopes: Optional[list[str]] = None,
    ) -> None:
        super().__init__(
            methods=["WEBSOCKET"],
            path=path,
            endpoint=endpoint,
            name=name,
            strict_slashes=strict_slashes,
            middlewares=middlewares,
            scopes=scopes,
        )


class RouteGroup:
    def __init__(
        self,
        routes: list[Route],
        name: str = "",
        prefix: str = "",
        subdomain: str = "",
        middlewares: Optional[list[Any]] = None,
    ) -> None:
        self.name = name
        self.prefix = prefix
        self.routes = routes
        self.subdomain = subdomain
        self.middlewares = middlewares or []


class EndpointConfig(TypedDict):
    middleware_before: list[IMiddleware]
    middleware_after: list[IMiddleware]
    route: Route
