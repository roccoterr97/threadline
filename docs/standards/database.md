# Database standards

Read this before designing schema or writing queries. Extends
[CLAUDE.md](../../CLAUDE.md).

## Schema design

- Every table has a primary key and `created_at` / `updated_at` timestamps.
- Store timestamps in UTC, as timestamptz. Convert at the presentation layer.
- Use the database's real types: enums for closed sets, `numeric` for money
  (never floats), `jsonb` only for genuinely unstructured data.
- Enforce invariants in the database — `NOT NULL`, foreign keys, unique
  constraints, check constraints. Application-level validation is a convenience,
  not a guarantee.
- Name things consistently: `snake_case`, plural table names, `{table}_id` for
  foreign keys.
- Index what you filter, join and sort on. Add an index with the query that
  needs it, not speculatively.

## Migrations

- **Every schema change is a migration file**, committed with the code that
  needs it. No manual changes to a shared database.
- Migrations are forward-only in practice — write a `down` if the tool requires
  one, but never rely on it in production.
- Destructive changes go in two deploys: add the new shape, migrate the data and
  the code, then drop the old shape in a later change.
- Test every migration against a copy of realistic data before it reaches
  production.

## Queries

- Use the ORM/query builder by default. Raw SQL only when the ORM genuinely
  cannot express the query — and then always parameterised.
- **Never concatenate user input into SQL.**
- Avoid N+1 access: eager-load or batch related rows.
- Select the columns you need, not `SELECT *`, on hot paths.
- Paginate every list endpoint. Prefer keyset pagination over `OFFSET` for large
  tables.
- Prefer bulk inserts/updates over row-by-row loops.
- Anything running on a large table gets an `EXPLAIN` before it ships.

## Transactions and sessions

- Transaction boundaries belong in the service layer, not in repositories or
  route handlers.
- Keep transactions short — never hold one open across a third-party API call.
- Always close/return sessions, and roll back on failure. Use a context manager.
- Make writes idempotent where a retry is possible (upserts, natural keys).

## Access control

- If the product is multi-tenant, **every query is scoped by tenant/owner**.
  Enforce it at the lowest possible layer — row-level security where the
  database supports it — so a forgotten `WHERE` clause cannot leak data.
- Application database users get the narrowest privileges that work. Migrations
  run under a separate, more privileged user.

## Operations

- Connection pooling configured explicitly — pool size tied to the deployment's
  concurrency, not left at a default.
- Retries on connect are bounded and linear; exhaustion fails fast with one
  clean error (see [backend-python.md](./backend-python.md)).
- Backups exist and have been restored at least once. An untested backup is not
  a backup.
- Never point local development at a production database.
