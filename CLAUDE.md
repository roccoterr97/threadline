# CLAUDE.md — Engineering Standards

Coding standards for this repository. These apply to every change, in every
language, unless a rule below says otherwise.

Stack-specific rules live in `docs/standards/` and are **not** auto-loaded.
Read the relevant file before writing code in that stack:

| File | Covers |
|------|--------|
| `docs/standards/backend-python.md` | Python style, FastAPI layering, async, background jobs |
| `docs/standards/frontend-typescript.md` | TypeScript, React, state, styling, accessibility |
| `docs/standards/database.md` | Schema design, migrations, queries, transactions |

---

## 1. General principles

- Always write production-ready code. No placeholders, no `TODO`s left behind.
- Prefer readability over cleverness.
- Follow SOLID, DRY and KISS.
- Follow Clean Architecture: domain logic must not depend on frameworks, HTTP,
  or the database driver.
- Use dependency injection where appropriate. Avoid global mutable state.
- Every function has a single responsibility. Keep functions under ~40 lines.
- Use meaningful names. A name that needs a comment to be understood is the
  wrong name.
- Write modular code — small units, clear boundaries, no circular imports.
- **Explain assumptions before coding.** If information is missing, state the
  assumption explicitly rather than guessing silently.

## 2. Reuse before building

Search the codebase for an existing capability before adding a new one.
Duplicating an abstraction that already exists (a second HTTP client, a second
storage wrapper, a second auth helper) is the most expensive mistake available
in any codebase.

Order of preference: extend existing code → compose existing code → write new
code → add a dependency.

## 3. Code hygiene (mandatory on every change)

Remove before finishing:

- Unused imports
- Unused variables and assignments
- Unused function/method parameters (delete them, or prefix with `_` only when a
  protocol/callback signature requires the parameter)
- Dead branches and commented-out code
- Debug prints and leftover scaffolding

Verify with the project's linter and type checker on **every file you touched**.
Do not leave hygiene failures for a follow-up pass.

## 4. Code quality

- Avoid nested `if` statements — use early returns / guard clauses.
- Avoid magic numbers and magic strings.
- Use enums for closed sets of values.
- Prefer composition over inheritance.
- Keep files focused; split when a file starts serving two purposes.
- Match the surrounding code's style, naming and idiom before introducing your
  own.

## 5. Constants vs configuration

| Kind | Where it goes | Examples |
|------|---------------|----------|
| **Secrets / deployment** | environment variables, read through one config module | API keys, DB URL, base URLs |
| **Operational tuning** | a `constants/` module, one file per concern | timeouts, batch sizes, retry caps, page sizes |
| **Domain policy** | the domain layer | code that *interprets* constants (eligibility rules, pricing tiers) |

Do not scatter tunable numbers across feature modules. Do not put non-deployment
constants in `.env`. Every new env var must be added to `.env.example` with a
comment.

## 6. Error handling

- Catch only expected exceptions. Never use a bare `except` / `catch {}`.
- Never suppress an exception silently.
- Raise meaningful, typed, domain-specific errors — not generic ones.
- Never leak internal exception messages or stack traces to users or API
  responses. Map them to stable error codes.
- Log unexpected exceptions with enough context to debug (IDs, inputs, not
  secrets).
- Treat dependency outages (DB, cache, third-party API) as *operational*
  failures: one clean error log line, not a stack dump.

## 7. Logging

- Use structured logging. Never use `print()` / `console.log` in committed code.
- Log important business events, not every line of execution.
- Include a request/correlation ID where one is available.
- Never log secrets, tokens, passwords, or full payloads containing personal
  data.

## 8. Security

- Validate and sanitize all user input at the boundary.
- Use parameterised queries. Never build SQL by string concatenation.
- Escape output where the sink requires it.
- Never hardcode secrets. Read them from environment variables.
- Never commit `.env`, credentials, keys, or tokens.
- Enforce authentication *and* authorization on every non-public endpoint —
  check that the caller owns the resource, not just that they are logged in.
- Follow OWASP Top 10 recommendations.

## 9. Testing

- Write unit tests for business logic.
- Cover the happy path *and* the failure cases.
- Mock external dependencies; tests must not hit the network.
- Tests must be deterministic — no reliance on wall-clock time, ordering, or
  live data.
- Every change ships with at least one concrete validation step.

## 10. Performance

- Optimise queries before optimising code.
- Avoid N+1 access patterns.
- Paginate anything that can grow unbounded.
- Cache expensive, stable computations — with an explicit invalidation story.
- Stream large payloads and files instead of buffering them.
- Prefer async/concurrent execution for I/O-bound work.

## 11. Documentation

- Every public function, class and module has a docstring / JSDoc.
- Comments explain **why**, not **what**.
- Keep comments minimal and truthful — a stale comment is worse than none.
- Update `README.md` when setup, commands or architecture change.

## 12. Git

- One logical change per commit. Imperative subject line ("Add", not "Added").
- Never commit generated artifacts, `node_modules`, virtualenvs, or `.env`.
- Do not commit or push unless the engineer asks.
- Never force-push a shared branch.

## 13. Definition of done

A task is not done until all of these hold:

1. The code works and has been run — not just written.
2. Linter and type checker pass on every touched file.
3. Tests for the change pass, and the existing suite still passes.
4. Unused code removed, no `TODO`s, no commented-out blocks.
5. `.env.example` and docs updated if the change affects them.
