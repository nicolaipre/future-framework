# Container example application

This runnable application verifies Future's framework-owned container, recursive constructor injection, interface bindings, middleware injection, class-based authentication, identities, scopes, and test overrides. It also demonstrates the application layout: `IUserRepository` lives in `app/interfaces`, `MemoryUserRepository` lives in `app/repositories`, and `TestAuthentication` lives in `app/authentication`.

Run it from the repository root:

```bash
uv run python -m examples.container_app.run
```

Then call its routes:

```bash
curl http://127.0.0.1:8000/health
curl --user reader:secret http://127.0.0.1:8000/users/1
curl --user reader:secret http://127.0.0.1:8000/users/1/admin
curl --user admin:secret http://127.0.0.1:8000/users/1/admin
```

The reader has `users:read`; the admin has both `users:read` and `users:admin`. The reader therefore receives 403 from the admin route. Requests without valid credentials receive 401.
