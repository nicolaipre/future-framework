# Container example application

This runnable application verifies Future's framework-owned container, recursive constructor injection, interface bindings, middleware injection, configured authentication middleware, identities, scopes, and test overrides.

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
