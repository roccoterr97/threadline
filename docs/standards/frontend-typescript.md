# Frontend standards — TypeScript / React

Read this before writing frontend code. It extends [CLAUDE.md](../../CLAUDE.md).

## TypeScript

- `strict: true`. No `any` — use `unknown` and narrow. No `@ts-ignore` without a
  comment explaining why and a linked issue.
- Type the boundaries: API responses, form values, route params. Infer the rest.
- Prefer `type` for unions and props, `interface` for extensible object shapes.
- Never assert (`as`) your way out of a type error you could fix properly.
- Validate data crossing the network boundary at runtime (e.g. Zod) — a
  TypeScript type is not a guarantee about what the server sent.

## Components

- One component per file; the filename matches the component name.
- Function components only. Hooks at the top level, never conditionally.
- Keep components under ~150 lines. Extract sub-components and custom hooks
  before a file grows past that.
- Presentational components take data via props and own no fetching.
  Container/route components do the fetching.
- Derive state — do not duplicate it. If a value can be computed from props or
  existing state, compute it.
- Every list needs a stable `key` — never the array index for reorderable lists.
- Clean up in `useEffect`: abort in-flight requests, clear timers, remove
  listeners.

## State

| Kind of state | Where it belongs |
|---------------|------------------|
| Server data | a data-fetching layer with caching (TanStack Query or equivalent) |
| Global UI state | one small store (Zustand/Context) — keep it minimal |
| Local UI state | `useState` in the component |
| URL state | the router — filters, tabs and pagination belong in the URL |

Do not put server data in a global store and hand-manage its freshness.

## Data fetching

- One typed API client module. Components never call `fetch` directly.
- Handle all four states explicitly: loading, empty, error, success. An
  unhandled error state is a bug.
- Show optimistic updates only where you can roll them back.
- Stream long responses rather than blocking the UI on a full payload.

## Styling

- Use the project's design system / component library before hand-rolling a
  component.
- Tailwind: compose utilities in the markup; extract a component (not an
  `@apply` soup) when a pattern repeats.
- Use design tokens for colour, spacing and typography — no hardcoded hex values
  in components.
- Mobile-first. Every screen must work at 375px wide.
- Support light and dark themes from the start if the project has both — never
  define a colour only inside a media query.

## Accessibility (not optional)

- Semantic HTML first; ARIA only when semantics run out.
- Every interactive element is reachable and operable by keyboard, with a
  visible focus state.
- Every input has an associated label. Every image has meaningful `alt` (or
  `alt=""` if decorative).
- Colour contrast ≥ 4.5:1 for body text.
- Never convey information by colour alone.

## Performance

- Code-split at the route level.
- Memoise (`useMemo`/`memo`) only where a measured problem exists — premature
  memoisation adds noise.
- Virtualise lists longer than a few hundred rows.
- Serve responsive, correctly sized images; lazy-load below the fold.

## Copy

- User-facing copy is **English by default**. Additional locales go through an
  explicit locale catalog — never as the only or default string in a component.
- Error messages tell the user what to do next, not what the stack trace said.

## Tooling — required before finishing a task

```bash
npm run lint
npm run typecheck
npm test
```

All three pass on the files you touched before the task is done.
