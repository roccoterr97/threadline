# Threadline website

The public website: what Threadline is, the guided set-up (every step with
what to check and what to do if not, progress remembered in the browser), the
way to your own dashboard, and how to keep a copy up to date. Its words come
from the written guides in `../docs/`; its look comes from the dashboard's
design tokens in `src/theme/tokens.css`, copied from `../frontend`.

```bash
npm ci
npm run dev        # http://localhost:5173
npm run lint && npm run typecheck && npm test && npm run build
```

## Where things are

| Folder | What is in it |
|--------|---------------|
| `src/content/` | The words of the home, dashboard and update pages |
| `src/setup/content/` | The guided set-up, one file per part, in the shape of `src/setup/types.ts` |
| `src/setup/` | How progress is remembered and how the guide is navigated |
| `src/components/` | The frame and the building blocks; `home/`, `setup/`, `dashboard/` per page |
| `src/constants/links.ts` | Every outside address the site points at |

## The look

Every page uses the full width of the screen (`.site-container` in
`src/index.css`). The home page puts the opening line beside the product,
draws "How it works" as one thread across the page with a dot per moment
(`.thread-across`), and starts each new part with a line and a dot
(`.rule-node`). Other pages are two halves (`SplitPage`): the title and what
the page is for on the left, kept in view, the content on the right. The
set-up runs its progress line across the top. Pictures of the product sit in
a thin frame with a numbered caption (`Plate`). No shadows, gradients, badges
or icons; one blue, for links, controls and the thread.

## The icons

`python3 -I scripts/icons.py` draws the favicons and the link-preview picture
from the brand mark (`public/brand/mark.svg`), with nothing beyond Python.
Run it after changing the mark, and commit what it writes.

## Publishing

The site is a static build (`dist/`). On Vercel: a project with **Root
Directory** `website`; `vercel.json` sets the build, the single-page rewrite
and the security headers. Nothing in the site talks to any service: there are
no settings and no keys.
