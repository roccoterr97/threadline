# Contributing to Threadline

Thank you for helping. Bug reports, fixes and small improvements are all
welcome. For anything larger, open an issue first so the approach can be agreed
before you spend time on it.

## Development setup

You need [uv](https://docs.astral.sh/uv/) for the backend (it installs Python
3.12 itself) and Node.js 22 or newer for the dashboard. No accounts are needed:
the tests never touch the network.

```bash
# Backend
cd backend
uv sync

# Dashboard
cd frontend
npm ci
```

To try the dashboard against your own Supabase project, copy
`frontend/.env.example` to `frontend/.env.local`, fill in the two `VITE_`
values and run `npm run dev`. To look around without a database, run
`npm run demo` instead: it uses made-up data kept in the browser tab.

To publish your changed dashboard on your own Netlify site, the way the set-up
does, build it from your copy instead of downloading the ready-made one:

```bash
cd backend
uv run tracker setup dashboard --build-here
```

It needs Node.js 22 or newer and the `frontend` folder. Without the option,
the set-up publishes the ready-made dashboard from the template's release.

## The checks

Every change must pass all of these; CI runs the same list on every push and
pull request.

```bash
cd backend
uv run ruff check .
uv run pyright
uv run pytest -q

cd ../frontend
npm run lint
npm run typecheck
npm test
npm run build
```

## Standards

The engineering standards are in [`CLAUDE.md`](./CLAUDE.md), with the
stack-specific rules under [`docs/standards/`](./docs/standards/). How the
pieces fit together is in [`docs/architecture.md`](./docs/architecture.md). In
short: keep the layers apart, add tests for the happy path and the failure
cases, remove unused code, and add every new environment variable to
`.env.example` with a comment. A database change is always a new file under
`supabase/migrations/`, never an edit to an existing one.

## Personal data

**Never put real personal data in tests, fixtures, examples, issues or pull
requests.** No real names paired with real addresses, no real messages, no keys
or tokens. Use made-up people and the reserved `.example` domains, for example
`anna@company.example`. If you need a realistic message, write one.

## Commits and pull requests

- One logical change per commit.
- The subject line is in the imperative ("Add", "Fix", not "Added"), under
  about 70 characters, followed by a blank line and a short explanation of why.
- Fill in the pull request template, and say how you checked the change.

## Security issues

Do not open a public issue for a vulnerability. See [`SECURITY.md`](./SECURITY.md).

## Code of conduct

This project follows the [Code of Conduct](./CODE_OF_CONDUCT.md).
