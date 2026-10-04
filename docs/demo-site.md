# Publishing the demo website

The demo is the dashboard filled with made-up people. It needs no accounts and
holds no private data, so anyone can look at it. This page puts it online as a
website of its own, next to (not instead of) your real dashboard.

It takes about ten minutes. You need a free [Vercel](https://vercel.com)
account and the Threadline code on your GitHub account.

---

## 1. Try it on your computer first

```bash
cd frontend
npm install
npm run build:demo
npm run preview
```

`npm install` may print warnings about vulnerabilities or install scripts: they
concern developer tools only and can be ignored. Open <http://localhost:4173>.

✅ Check: you should now see the dashboard with a notice at the top saying
"Demo — made-up data. Nothing is saved." and a "Set up your own" link.

Press `Ctrl` + `C` in the terminal to stop it.

## 2. Start a new Vercel project

In Vercel, choose **Add New… → Project** and pick the Threadline repository —
the same one your real dashboard uses. This makes a second, separate project.

✅ Check: you should now see the "Configure Project" page.

## 3. Name it and point it at the dashboard folder

- **Project Name:** a name of your own, such as `my-threadline-demo` (this
  becomes the web address, `my-threadline-demo.vercel.app`, if nobody else has
  taken it; `try-threadline.vercel.app` is the official demo).
- **Root Directory:** click **Edit** and choose `frontend`. If Vercel says
  *"Multiple applications detected"*, click **Import single project** next to
  **frontend** (marked *Vite*) instead: that sets the folder for you.
- Leave **Build and Output Settings** as they are. The file
  `frontend/vercel.json` already sets them, together with the same security
  rules the real dashboard has.

✅ Check: you should now see "Vite" as the Framework Preset and `frontend` as
the Root Directory.

## 4. Switch the demo on

Open **Environment Variables** and add one:

| Name | Value |
|------|-------|
| `VITE_DEMO` | `true` |

Add nothing else. This project must never get your Supabase address or key.

✅ Check: you should now see exactly one variable, `VITE_DEMO`, in the list.

## 5. Publish

Click **Deploy** and wait a minute or two.

✅ Check: you should now see "Congratulations" and a picture of the dashboard
with the demo notice at the top.

## 6. Look at it and share the address

Click the picture to open the site. Copy its address from the browser.

✅ Check: you should now see the demo notice, and "Set up your own" should open
the setup guide on GitHub.

If you forked Threadline and publish your own demo, two places still point at
the original project's demo and guide, so change them to yours: the "Live
demo:" line of the README's "Try the demo" section (replace the official
demo's address, `https://try-threadline.vercel.app`, with yours), and the demo
notice's "Set up your own" link, which is the
`SETUP_GUIDE_URL` in `frontend/src/demo/DemoBanner.tsx`. Leave them as they are
if you would rather keep pointing at the original.

---

## Good to know

- **It updates itself.** Every change you push to GitHub rebuilds the demo as
  well as your real dashboard.
- **Nothing is saved.** Each visitor gets a fresh copy of the made-up data;
  reloading the page starts again.
- **Search engines are asked to skip your demo**, like the real dashboard,
  because both share the same `vercel.json` rules. The one exception is the
  official demo, `try-threadline.vercel.app`, which `frontend/vercel.json` lets
  search engines list; your own demo keeps the rule unless you add its address
  there too. People can still open it from a link.
- **Keep the two apart.** Never add `VITE_DEMO` to your real dashboard's
  project — it would show the made-up data instead of yours.
- **Shared links show a picture.** When someone posts the demo's address in
  a chat or on social media, a preview card with a picture of the dashboard
  appears. On Vercel this works by itself. Elsewhere, set `DEMO_SITE_URL` to
  the demo's full address (for example `https://my-threadline-demo.vercel.app`)
  in `frontend/.env.local` or in your host's settings before
  `npm run build:demo`, because previews need the full address of the picture.
  The picture itself is `frontend/assets/social-card.png`; if you change the
  logo or the colours, run `npm run social-card` in the `frontend` folder to
  draw it again, and commit the new file.
- **On a phone** the demo can be added to the home screen like the real
  dashboard: on iPhone, Share → **Add to Home Screen**; on Android, the ⋮ menu
  → **Add to Home screen** (or **Install app**).
