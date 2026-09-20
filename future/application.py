import platform
import sys
import logging
import traceback

from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Optional, Union

import uvicorn

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from future.exceptions import ErrorHandler, HTTPException
from future.logger import log
from future.interfaces.IMiddleware import IMiddleware
from future.openapi import get_openapi_config, is_docs_path, openapi_routes, rebuild_spec_from_routes, set_openapi_config, spec_path
from future.request import Request
from future.response import Response, WebSocketResponse
from future.routing import Route, RouteGroup
from future.types import AsgiEventType, ASGIReceive, ASGIScope, ASGISend, RouteConfig


"""
# ASGI SPEC
async def application(scope, receive, send):
    event = await receive()
    ...
    await send({"type": "websocket.send", ...: ...})

example_http_event = {
    "type": "http.request",
    "body": b"Hello World",
    "more_body": False,
}

example_websocket_event = {
    "type": "websocket.send",
    "text": "Hello world!",
}

example_http_scope = {
    'type': 'http',
    'method': 'POST',
    'path': '/echo',
    'headers': [...],
    ...: ...,
}


...


except BaseException:
    event_type = "lifespan.shutdown.failed" if started else "lifespan.startup.failed"
    await send({"type": event_type, "message": traceback.format_exc()})
    raise
await send({"type": "lifespan.shutdown.complete"})

# Custom openapi path
if path == "/openapi.json":
    await self.serve_openapi(send)
    return
while True:
    message = await receive()
    print(f"Got message:", message)
"""


class Future:
    def __init__(self, lifespan: Any, config: dict[str, Any] | None = None) -> None:
        # spawn background tasks in the lifespan startup process... or database connections etc...
        # on shutdown, save shit, send info about shutdown etc...
        self.lifespan = lifespan
        self.routes: dict[str, dict[str, RouteConfig]] = {}
        self.config = config or {}
        self.databases = self.config.get("DATABASES")
        if self.databases:
            from future.database import Database
            Database().set_connection_details(self.databases)

        domain = self.config.get("APP_DOMAIN", "")

        # Domainless mode: if no domain is set, subdomains are ignored, only prefixes work
        # Domain defaults to empty string, so this will always be true
        if domain == "":
            warning_msg = (
                "[WARNING] No domain specified!\n"
                "Subdomains in RouteGroups will be IGNORED.\n"
                "All routes will be accessible regardless of Host header.\n"
                "Prefixes will still work as expected.\n"
                "To enable subdomain routing, set the 'domain' parameter (e.g., domain='example.com')."
            )
            log.warning(warning_msg)
            self.domain = ""
            self.domainless_mode = True
        else:
            # Validate domain format (basic check)
            if not domain.replace(".", "").replace("-", "").isalnum():
                raise ValueError(f"Invalid domain format: {domain}. Domain must be alphanumeric with dots and hyphens only.")
            self.domain = domain
            self.domainless_mode = False

        # Performance monitoring
        self.route_count = 0
        self.max_nesting_depth = 0
        self.registered_domains: set[str] = set()
        
        # Optimization: Cache for domain validation
        self._domain_cache: dict[str, bool] = {}
        set_openapi_config(self.config)
        log.setLevel(logging.DEBUG if bool(self.config.get("APP_DEBUG")) else logging.INFO)

    def set_config(self, config: dict[str, Any]) -> None:
        self.config = config
        set_openapi_config(self.config)
        log.setLevel(logging.DEBUG if bool(self.config.get("APP_DEBUG")) else logging.INFO)

    def _resolve_controller_action(self, endpoint: Any) -> tuple[Any, str | None]:
        qual = getattr(endpoint, "__qualname__", "") or ""
        mod_name = getattr(endpoint, "__module__", None)
        if "." in qual and mod_name:
            cls_name = qual.rsplit(".", 1)[0]
            if "." not in cls_name:
                mod = sys.modules.get(mod_name)
                if mod is not None:
                    cls = getattr(mod, cls_name, None)
                    if cls is not None:
                        return cls, endpoint.__name__
        return None, None

    def _add_route(self, route: Route, subdomain: str = "", parent_middlewares: Optional[list[IMiddleware]] = None, group: Optional[dict[str, str]] = None) -> None:
        """Internal method to add single routes to the application.

        Args:
            route (Route): The actual route object
            subdomain (str): The full domain the route should be available for (e.g., "dev.api.example.com").
        """
        # In domainless mode, always use the empty string key
        key = "" if getattr(self, "domainless_mode", False) else subdomain
        if key not in self.routes:
            self.routes[key] = {}
        self.route_count += 1
        self.registered_domains.add(key)

        middleware_classes: list[Any] = []
        if parent_middlewares:
            middleware_classes.extend(sorted(parent_middlewares, key=lambda m: m.priority))
        middleware_classes.extend(sorted(route.middlewares, key=lambda m: m.priority))

        controller_cls, action = self._resolve_controller_action(route.endpoint)

        route_config = RouteConfig(
            handler=route.endpoint,
            controller=controller_cls,
            action=action,
            middleware={"classes": middleware_classes},
            regex={"paths": [route._rx]} if hasattr(route, "_rx") else None,  # type: ignore[reportGeneralTypeIssues]
            methods=route.methods,
            route=route,  # FIXME: Added in temporarily because of a regression in the regex matching causing /users/123/test to not match /users/123/test/. Not sure when this happened. This shouldnt be needed.
            group=group or {"name": "", "prefix": "", "subdomain": ""},
        )

        self._check_route_conflicts(route, key, group)
        # Path + methods so Get("/x") and Post("/x") can coexist
        self.routes[key][f"{','.join(route.methods)} {route.path}"] = route_config

    def has_path(self, path: str) -> bool:
        for route_map in self.routes.values():
            for route_config in route_map.values():
                route = route_config.get("route")
                if route is not None and getattr(route, "path", None) == path:
                    return True
        return False

    def add_routes(self, routes: Sequence[Union[Route, RouteGroup]]) -> None:
        for r in routes:
            if isinstance(r, Route):
                r.compile_pattern()
                # Use the actual domain for individual routes, just like RouteGroups
                subdomain = self.domain if not getattr(self, "domainless_mode", False) else ""
                self._add_route(route=r, subdomain=subdomain)
            elif isinstance(r, RouteGroup):  # type: ignore[reportUnnecessaryIsInstance]
                self._add_route_group(r, parent_subdomain="", parent_middlewares=[], nesting_depth=0)
            else:
                raise NotImplementedError
        self._maybe_auto_openapi_routes()
        rebuild_spec_from_routes(self.routes, self.config)

    def _maybe_auto_openapi_routes(self) -> None:
        openapi = get_openapi_config(self.config)
        if not openapi.get("auto_routes") or not openapi.get("enabled", True):
            return
        if self.has_path(spec_path()):
            return
        subdomain = self.domain if not getattr(self, "domainless_mode", False) else ""
        prefix = openapi.get("path_prefix") or ""
        for route in openapi_routes(config=self.config):
            if prefix:
                joined = prefix if (not route.path or route.path == "/") else f"{prefix.rstrip('/')}{route.path}"
                route = Route(methods=list(route.methods), path=joined, endpoint=route.endpoint, name=route.name, strict_slashes=route.strict_slashes, middlewares=list(route.middlewares), scopes=list(route.scopes))
            route.compile_pattern()
            self._add_route(route=route, subdomain=subdomain)

    def _add_route_group(
        self,
        route_group: RouteGroup,
        parent_subdomain: str = "",
        parent_prefix: str = "",
        parent_middlewares: Optional[list[IMiddleware]] = None,
        nesting_depth: int = 0,
        parent_group_names: Optional[list[str]] = None,
    ) -> None:
        """Recursively add RouteGroup and its nested RouteGroups."""
        # Validate RouteGroup configuration
        self._validate_route_group(route_group)

        # Track nesting depth for performance monitoring
        self.max_nesting_depth = max(self.max_nesting_depth, nesting_depth)

        # Build the full subdomain path for this group
        current_subdomain = route_group.subdomain
        if parent_subdomain and current_subdomain:
            full_subdomain = f"{current_subdomain}.{parent_subdomain}"
        elif parent_subdomain:
            full_subdomain = parent_subdomain
        elif current_subdomain:
            full_subdomain = current_subdomain
        else:
            full_subdomain = ""

        # Build the full prefix path for this group with validation
        full_prefix = self._build_prefix_path(parent_prefix, route_group.prefix)

        group_names = list(parent_group_names or [])
        if route_group.name:
            group_names.append(route_group.name)
        group_meta = {
            "name": " › ".join(group_names) if group_names else "",
            "prefix": full_prefix,
            "subdomain": full_subdomain,
        }

        # Outer group middleware + this group's (nested groups inherit the full chain)
        accumulated_middlewares = list(parent_middlewares or []) + list(route_group.middlewares)

        # Process all routes in this group
        for r in route_group.routes:
            if isinstance(r, RouteGroup):
                # Nested RouteGroup - recurse with updated parent subdomain and prefix
                self._add_route_group(
                    r,
                    parent_subdomain=full_subdomain,
                    parent_prefix=full_prefix,
                    parent_middlewares=accumulated_middlewares,
                    nesting_depth=nesting_depth + 1,
                    parent_group_names=group_names,
                )
            else:
                # Copy before prefixing — never mutate caller Route objects (reload would stack /api → /api/api).
                # prefix="/indexes" + path="/" must be "/indexes", not "/indexes/" (that broke matching as ^/indexes//?$).
                if not r.path or r.path == "/":
                    joined = full_prefix or "/"
                else:
                    joined = f"{full_prefix.rstrip('/')}{r.path}" if full_prefix else r.path
                prefixed = Route(methods=list(r.methods), path=joined, endpoint=r.endpoint, name=r.name, strict_slashes=r.strict_slashes, middlewares=list(r.middlewares), scopes=list(r.scopes))
                prefixed.compile_pattern()
                if is_docs_path(r.path) or is_docs_path(prefixed.path):
                    set_openapi_config({"OPENAPI": {"path_prefix": full_prefix}})

                # Build full domain path for dictionary lookup
                if getattr(self, "domainless_mode", False):
                    full_domain = ""
                else:
                    full_domain = f"{full_subdomain}.{self.domain}" if full_subdomain else self.domain

                self._add_route(route=prefixed, subdomain=full_domain, parent_middlewares=accumulated_middlewares, group=group_meta)

    def _validate_route_group(self, route_group: RouteGroup) -> None:
        """Validate RouteGroup configuration."""
        # Validate subdomain format
        if route_group.subdomain and not route_group.subdomain.replace(".", "").replace("-", "").isalnum():
            raise ValueError(f"Invalid subdomain format: {route_group.subdomain}. Must be alphanumeric with dots and hyphens only.")

        # Validate prefix format
        if route_group.prefix:
            if not route_group.prefix.startswith("/"):
                raise ValueError(f"Invalid prefix format: {route_group.prefix}. Must start with '/'.")
            if "//" in route_group.prefix:
                raise ValueError(f"Invalid prefix format: {route_group.prefix}. Cannot contain consecutive slashes.")

    def _build_prefix_path(self, parent_prefix: str, current_prefix: str) -> str:
        """Build and validate accumulated prefix path."""
        if parent_prefix and current_prefix:
            full_prefix = f"{parent_prefix}{current_prefix}"
        elif parent_prefix:
            full_prefix = parent_prefix
        elif current_prefix:
            full_prefix = current_prefix
        else:
            full_prefix = ""

        # Validate final prefix
        if full_prefix and not full_prefix.startswith("/"):
            raise ValueError(f"Invalid accumulated prefix: {full_prefix}. Must start with '/'.")

        return full_prefix

    def _check_route_conflicts(self, route: Route, domain: str, group: Optional[dict[str, str]] = None) -> None:
        """Conflict only when the same path shares an HTTP method."""
        existing_routes = self.routes.get(domain, {})
        for existing in existing_routes.values():
            other = existing.get("route")
            if other is None or getattr(other, "path", None) != route.path:
                continue
            overlap = set(other.methods) & set(route.methods)
            if not overlap:
                continue
            methods = ",".join(sorted(overlap))
            incoming_sub = (group or {}).get("subdomain") or ""
            existing_sub = (existing.get("group") or {}).get("subdomain") or ""
            if getattr(self, "domainless_mode", False) and incoming_sub != existing_sub and (incoming_sub or existing_sub):
                raise ValueError(f"Route conflict detected: {methods} {route.path} already exists. In domainless mode (APP_DOMAIN is empty), RouteGroup subdomains are ignored, so {existing_sub!r} and {incoming_sub!r} both register {route.path}. Set APP_DOMAIN to enable subdomain routing, or use different prefixes.")
            raise ValueError(f"Route conflict detected: {methods} {route.path} already exists in domain {domain}")

    def _validate_domain_access(self, host_domain: str) -> bool:
        """Validate if the host domain is allowed to access routes."""
        compare_host = host_domain
        debug = bool(self.config.get("APP_DEBUG")) if self.config else False
        if debug and ":" in compare_host:
            # APP_DEBUG only: Host: localhost:8000 → localhost (explicit Host without port in prod)
            compare_host = compare_host.rsplit(":", 1)[0]
        log.debug(f"Validating domain access for host: '{host_domain}' (compare='{compare_host}') against configured domain: '{self.domain}'")

        # Optimization: Check cache first
        if compare_host in self._domain_cache:
            return self._domain_cache[compare_host]

        # Check if domain matches our configured domain or any subdomain
        if not self.domain:
            self._domain_cache[compare_host] = True
            return True  # No domain restriction

        # Allow exact domain match
        if compare_host == self.domain:
            self._domain_cache[compare_host] = True
            return True

        # Allow subdomains of our domain
        if compare_host.endswith(f".{self.domain}"):
            self._domain_cache[compare_host] = True
            return True

        self._domain_cache[compare_host] = False
        return False

    def get_performance_stats(self) -> dict[str, Any]:
        """Get performance statistics for the application."""
        return {
            "total_routes": self.route_count,
            "registered_domains": len(self.registered_domains),
            "max_nesting_depth": self.max_nesting_depth,
            "domain_list": list(self.registered_domains),
            "memory_usage": {"routes_dict_size": len(self.routes), "total_route_configs": sum(len(configs) for configs in self.routes.values())},
            "domain_cache_size": len(self._domain_cache),
        }

    async def handle_lifespan_request(self, scope: ASGIScope, receive: ASGIReceive, send: ASGISend) -> None:
        # initialize_scheduler for cronjobs
        assert scope["type"] == "lifespan"
        message = await receive()
        assert message["type"] == AsgiEventType.LIFESPAN_STARTUP
        app = scope.get("app")

        started = False
        try:
            # async with self.lifespan(app) as state:
            self.lifespan.app = app
            async with self.lifespan as state:
                if state is not None:
                    scope.setdefault("state", {}).update(state)
                await send({"type": AsgiEventType.LIFESPAN_STARTUP_COMPLETE})
                started = True
                message = await receive()
                assert message["type"] == AsgiEventType.LIFESPAN_SHUTDOWN

        except BaseException:
            event_type = AsgiEventType.LIFESPAN_SHUTDOWN_FAILED if started else AsgiEventType.LIFESPAN_STARTUP_FAILED
            await send({"type": event_type, "message": traceback.format_exc()})
            raise

        await send({"type": AsgiEventType.LIFESPAN_SHUTDOWN_COMPLETE})


    async def handle_http_request(self, scope: ASGIScope, receive: ASGIReceive, send: ASGISend) -> None:
        request = Request(scope, receive)
        response = Response()
        try:
            host_domain = request.host.split("/")[0] if "/" in request.host else request.host
            if not self._validate_domain_access(host_domain):
                raise HTTPException("Not Found", 404)

            debug = bool(self.config.get("APP_DEBUG")) if self.config else False
            route_host = host_domain.rsplit(":", 1)[0] if debug and ":" in host_domain else host_domain
            key = "" if getattr(self, "domainless_mode", False) else route_host
            domain_routes = self.routes.get(key, {})

            matched_route = None
            route_params = None
            allowed_methods: list[str] = []

            for route_path, route_config in domain_routes.items():
                route = route_config.get("route", None)
                if route and hasattr(route, "match"):
                    if getattr(route, "_rx", None) is not None and route._rx.match(request.path.encode()):
                        allowed_methods.extend(route.methods)
                    route_match = route.match(request.method, request.path.encode())
                    if route_match:
                        matched_route = route_config
                        route_params = route_match.params
                        break
                else:
                    cfg_path = route_path.split(" ", 1)[-1] if " " in str(route_path) else route_path
                    if cfg_path == request.path:
                        matched_route = route_config
                        break
            if not matched_route:
                if allowed_methods:
                    if request.method == "OPTIONS":
                        for route_path, route_config in domain_routes.items():
                            route = route_config.get("route", None)
                            if not route or getattr(route, "_rx", None) is None or not route._rx.match(request.path.encode()):
                                continue
                            middleware_classes = route_config.get("middleware", {}).get("classes") or []
                            if any(getattr(middleware, "__name__", "") == "CORSMiddleware" for middleware in middleware_classes):
                                matched_route = route_config
                                break
                    if not matched_route:
                        raise HTTPException("Method Not Allowed", 405, headers={"allow": ", ".join(sorted(set(allowed_methods)))})
                if not matched_route:
                    raise HTTPException("Not Found", 404)

            request.route = matched_route.get("route")
            middleware_classes = matched_route["middleware"].get("classes") or []
            middleware_instances = [m(request, response) for m in middleware_classes]
            for mw in middleware_instances:
                early = await mw.before()
                if early is not None:
                    await early(send)
                    return

            controller_cls = matched_route.get("controller")
            action = matched_route.get("action")
            if controller_cls and action:
                ctrl = controller_cls(request, response)
                method = getattr(ctrl, action)
                if route_params:
                    result = await method(**route_params)
                else:
                    result = await method()
            else:
                handler = matched_route["handler"]
                if route_params:
                    result = await handler(request, response, **route_params)
                else:
                    result = await handler(request, response)
            if result is not None:
                if not isinstance(result, Response):
                    raise TypeError(f"Controller must return a Response or None, got {type(result).__name__}")
                response = result

            for mw in reversed(middleware_instances):
                modified = await mw.after()
                if modified is not None:
                    response = modified
            await response(send)
        except Exception as exc:
            if not isinstance(exc, HTTPException):
                log.exception("Unhandled exception while processing %s %s", request.method, request.path)
            await ErrorHandler(request, response).handle(exc)(send)

    async def handle_websocket_request(self, scope: ASGIScope, receive: ASGIReceive, send: ASGISend) -> None:
        """Handle WebSocket requests following the same pattern as HTTP requests."""
        request_path = scope["path"].encode()
        host_domain = ""

        headers = dict(scope.get("headers", []))
        host_header = headers.get(b"host", b"").decode()
        if host_header:
            host_domain = host_header.split("/")[0] if "/" in host_header else host_header

        if not self._validate_domain_access(host_domain):
            await send({"type": "websocket.close", "code": 1008, "reason": "Forbidden"})
            return

        debug = bool(self.config.get("APP_DEBUG")) if self.config else False
        route_host = host_domain.rsplit(":", 1)[0] if debug and ":" in host_domain else host_domain
        key = "" if getattr(self, "domainless_mode", False) else route_host
        domain_routes = self.routes.get(key, {})
        matched_route = None
        route_params = None

        for route_path, route_config in domain_routes.items():
            route = route_config.get("route")
            if route and hasattr(route, "match"):
                route_match = route.match("WEBSOCKET", request_path)
                if route_match:
                    matched_route = route_config
                    route_params = route_match.params
                    break
            else:
                cfg_path = route_path.split(" ", 1)[-1] if " " in str(route_path) else route_path
                if cfg_path == scope["path"]:
                    matched_route = route_config
                    break

        if not matched_route:
            await send({"type": "websocket.close", "code": 1008, "reason": "Not Found"})
            return

        request = Request(scope, receive)
        response = Response()
        request.route = matched_route.get("route")
        try:
            middleware_classes = matched_route["middleware"].get("classes") or []
            middleware_instances = [m(request, response) for m in middleware_classes]
            for mw in middleware_instances:
                early = await mw.before()
                if early is not None:
                    await send({"type": "websocket.close", "code": 1008, "reason": "Middleware rejected"})
                    return

            controller_cls = matched_route.get("controller")
            action = matched_route.get("action")
            if controller_cls and action:
                ctrl = controller_cls(request, response)
                method = getattr(ctrl, action)
                if route_params:
                    result = await method(**route_params)
                else:
                    result = await method()
            else:
                handler = matched_route["handler"]
                if route_params:
                    result = await handler(request, response, **route_params)
                else:
                    result = await handler(request, response)
            if result is not None:
                if not isinstance(result, (Response, WebSocketResponse)):
                    raise TypeError(f"Controller must return a Response, WebSocketResponse, or None, got {type(result).__name__}")
                response = result

            for mw in reversed(middleware_instances):
                modified = await mw.after()
                if modified is not None:
                    response = modified

            await response(send)
        except Exception:
            log.exception("Unhandled exception while processing websocket %s", scope.get("path", ""))
            await send({"type": "websocket.close", "code": 1011, "reason": "Internal Server Error"})

    async def __call__(self, scope: ASGIScope, receive: ASGIReceive, send: ASGISend) -> None:
        # Inject ourselves into the chain for later convenience
        scope["app"] = self

        # Check scope type and handle accordingly...
        if scope["type"] == "lifespan":
            log.debug("Received scope type: 'lifespan'")
            log.debug("Handling lifespan stuff...")
            await self.handle_lifespan_request(scope, receive, send)
        elif scope["type"] == "http":
            log.debug("Received scope type: 'http' request for path: %s", scope.get("path", ""))
            await self.handle_http_request(scope, receive, send)
        elif scope["type"] == "websocket":
            log.debug("Received scope type: 'websocket' request for path: %s", scope.get("path", ""))
            await self.handle_websocket_request(scope, receive, send)
        else:
            raise NotImplementedError

    # FIXME: should this also be async?
    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        workers: int = 4,
        tls_key: Optional[str] = None,
        tls_cert: Optional[str] = None,
        tls_password: Optional[str] = None,
        access_log: bool = True,
    ) -> None:
        # Dynamically get system information
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        platform_info = platform.platform()
        arch = platform.machine()
        platform_str = f"{platform_info}-{arch}"
        try:
            future_version = version("future-framework")
        except PackageNotFoundError:
            future_version = "not installed"
        except Exception:
            future_version = "unknown"

        debug = self.config.get("APP_DEBUG", False) if self.config else False

        # ASCII-art "F" made with ✨ sparkles
        left = Text()
        left.append("     ✨✨✨✨✨      \n", style="bold yellow")
        left.append("     ✨              \n", style="yellow")
        left.append("     ✨✨✨✨        \n", style="bold yellow")
        left.append("     ✨              \n", style="yellow")
        left.append("     ✨              \n", style="yellow")
        left.append("                     \n", style="yellow")
        left.append(" ASGI based Web API    ", style="bold green")

        # Right info column
        right = Table.grid(padding=(0, 1))
        right.add_column(justify="left", no_wrap=True)
        right.add_column(justify="left")
        right.add_row("[red]app:[/]", f"{ self.config.get('APP_NAME', 'Future') }")
        right.add_row("[red]mode:[/]", f"{ "debug" if debug else "prod"} / { workers } worker(s)")  # FIXME
        right.add_row("[red]domain:[/]", f"{ self.config.get("APP_DOMAIN", "N/A") if self.config else "N/A" }")
        right.add_row("[red]server:[/]", "future, HTTP/1.1")
        right.add_row("[red]python:[/]", f"{ python_version }")
        right.add_row("[red]platform:[/]", f"{ platform_str }")
        right.add_row("[red]packages[/]:", f"future=={ future_version }")
        # right.add_row("[red]docs:[/]", f"http://localhost:{port}/docs")

        # Combined layout
        layout = Table.grid(expand=False)
        layout.add_column(ratio=1)
        layout.add_column(ratio=2)
        layout.add_row(left, right)

        main_panel = Panel(layout, box=ROUNDED, padding=(1, 2), expand=False)
        console = Console()
        # console.print(title_panel)
        console.print(main_panel)

        # uvicorn needs an import string for reload / multiple workers; Future projects use run:app.
        asgi_app: Any = self
        reload = bool(debug)
        if reload or workers > 1:
            asgi_app = (self.config or {}).get("APP_ASGI", "run:app")
        uvicorn.run(
            app=asgi_app,
            host=host,
            port=port,
            workers=workers,
            reload=reload,
            ssl_keyfile=tls_key,
            ssl_certfile=tls_cert,
            ssl_keyfile_password=tls_password,
            timeout_graceful_shutdown=3,
            log_level="info",
            lifespan="on",
            access_log=access_log,
        )
