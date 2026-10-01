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

Open <http://localhost:4173>.

✅ Check: you should now see the dashboard with a notice at the top saying
"Demo — made-up data. Nothing is saved." and a "Set up your own" link.

Press `Ctrl` + `C` in the terminal to stop it.

## 2. Start a new Vercel project

In Vercel, choose **Add New… → Project** and pick the Threadline repository —
the same one your real dashboard uses. This makes a second, separate project.

✅ Check: you should now see the "Configure Project" page.

## 3. Name it and point it at the dashboard folder

- **Project Name:** `threadline-demo` (this becomes the web address, for
  example `threadline-demo.vercel.app`, if nobody else has taken it).
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

Put the address in the "Live demo:" line of the README's "Try the demo"
section, in place of the example address.

---

## Good to know

- **It updates itself.** Every change you push to GitHub rebuilds the demo as
  well as your real dashboard.
- **Nothing is saved.** Each visitor gets a fresh copy of the made-up data;
  reloading the page starts again.
- **Search engines are asked to skip it**, like the real dashboard, because
  both share the same `vercel.json` rules. People can still open it from a link.
- **Keep the two apart.** Never add `VITE_DEMO` to your real dashboard's
  project — it would show the made-up data instead of yours.
- **On a phone** the demo can be added to the home screen like the real
  dashboard: on iPhone, Share → **Add to Home Screen**; on Android, the ⋮ menu
  → **Add to Home screen** (or **Install app**).
