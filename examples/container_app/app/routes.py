from future.middleware.AuthenticationMiddleware import AuthenticationMiddleware
from future.middleware.ScopeValidationMiddleware import ScopeValidationMiddleware
from future.routing import Get, RouteGroup

from examples.container_app.app.controllers.HealthController import HealthController
from examples.container_app.app.controllers.UserController import UserController
from examples.container_app.app.middleware.AuditMiddleware import AuditMiddleware


routes = [
    Get("/health", HealthController.show, "health"),
    RouteGroup(
        prefix="/users",
        name="Users",
        middlewares=[AuthenticationMiddleware(provider="basic"), AuditMiddleware, ScopeValidationMiddleware],
        routes=[
            Get("/<str:user_id>", UserController.show, "users.show", scopes=["users:read"]),
            Get("/<str:user_id>/admin", UserController.admin, "users.admin", scopes=["users:read", "users:admin"]),
        ],
    ),
]
