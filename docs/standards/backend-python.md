# Backend standards — Python / FastAPI

Read this before writing Python. It extends [CLAUDE.md](../../CLAUDE.md); where
they overlap, the stricter rule wins.

## Environment

- Always work inside a virtual environment (`venv`, `uv`, or `poetry`) — never
  install into the system interpreter.
- Pin the interpreter version in `.python-version` or `pyproject.toml`.
- Target Python 3.12+.

## Style

- Follow PEP 8. Format with `ruff format` (or `black`).
- **Type hints everywhere** — parameters, returns, class attributes. `Any` is a
  last resort and needs a comment justifying it.
- Docstrings on every class, method and public function.
- Use `dataclasses` or Pydantic models for structured data; do not pass around
  bare dicts between layers.
- Prefer `pathlib` over `os.path`.
- Use context managers for anything that must be released.
- Use `async`/`await` for I/O-bound work; keep CPU-bound work off the event
  loop.
- No global mutable state.

## Tooling — required before finishing a task

Run the linter and the type checker on every file you changed:

```bash
ruff check path/to/file.py
pyright path/to/file.py
```

Fix every error *you introduced*, including the unused-code family
(`unused-import`, `unused-variable`, `unused-argument`, `reportUnused*`).
A task with lint failures on touched files is not done.

## Layering (FastAPI)

```
api/routes/      HTTP only — parse, validate, delegate, shape the response
services/        business logic, orchestration, transactions
repositories/    data access only — one place that knows about the DB
domain/          entities, value objects, policy; no framework imports
schemas/         Pydantic request/response models
infrastructure/  external capabilities: storage, messaging, jobs, third-party APIs
shared/          config, constants, errors, logging
```

Rules:

- **Business logic must never live in a route handler.** Handlers validate input
  and call a service. If a handler is longer than ~15 lines, it is doing too
  much.
- Repositories only touch the database. Services only touch repositories and
  other services. Domain code imports nothing from `api/` or `infrastructure/`.
- Use FastAPI's dependency injection for shared resources; make clients
  singletons.
- Always declare `response_model`. Always return the correct HTTP status code.
- Validate every request payload with a Pydantic schema.
- Never let an internal exception message reach the client — map it to a stable
  error code and log the detail server-side.

### Backend package is self-contained

The backend must not import from outside its own package. If a module is needed
by two apps, move it into a shared package with its own dependency boundary.

## Configuration and constants

| Kind | Location |
|------|----------|
| Secrets / deployment values | `shared/config.py`, read from env via a single `get_settings()` |
| Operational tuning | `shared/constants/` — one module per concern (`retry.py`, `pagination.py`, …) |
| Domain policy | `domain/` — code that interprets the constants |

`get_settings()` is the only place that reads `os.environ`. Every new env var
goes into `.env.example` with a comment.

## Background jobs and scheduling

- Keep application startup wiring thin: start/stop the scheduler, nothing else.
- Keep job implementations in one module per concern under
  `infrastructure/scheduling/`.
- **Every job must be idempotent and safe to re-run.**
- In multi-instance deployments, guard job execution with a distributed lock
  (DB advisory lock or Redis lock) — otherwise every replica runs every job.
- Keep startup catch-up logic explicit and separate from job registration.

## External dependencies (DB, cache, third-party APIs)

Mirror one pattern for every new client:

1. Singleton client, created once at startup.
2. Bounded **linear** retries on connect (e.g. 10 attempts, 5s apart).
3. A typed unavailability error (`DatabaseUnavailableError`,
   `CacheUnavailableError`) — do not chain the driver exception into the
   operator-facing raise.
4. A boot-time `ensure_*_or_exit()` check: fail fast with **one clean ERROR log
   line**, never a framework traceback dump.
5. At request time, map the typed error to a stable JSON error response.

Treat outages as operational failures: one clean log line, not `log.exception`.

## Errors

- Define custom exception types in `shared/errors.py`, one hierarchy.
- Never `except:` or `except Exception:` without re-raising or handling
  specifically.
- Never swallow an exception to "keep things running" without logging why.

## Testing

```bash
pytest -q
```

- Unit-test services and domain logic; mock repositories and external clients.
- Use FastAPI's `TestClient` for route contract tests.
- No network access in tests. No dependence on wall-clock time — inject a clock.
