/**
 * The words of the "Your dashboard" page. This page never asks for keys,
 * passwords or e-mail addresses: only the address of the reader's own
 * dashboard, remembered in this browser.
 */

import type { AddressProblem } from '../lib/dashboardAddress';

export const dashboardPage = {
  title: 'Your dashboard',
  intro: [
    'Your dashboard lives at your own address, the one the set-up created for you. Only the e-mail you chose during the set-up can sign in, with a link by e-mail. No password.',
  ],
} as const;

export const rememberForm = {
  heading: 'Remember my dashboard address',
  label: 'Your dashboard address',
  placeholder: 'https://something-123abc.netlify.app',
  hint: 'Remembered in this browser only.',
  save: 'Remember this address',
  problems: {
    empty: 'Type your dashboard address first.',
    'has-spaces': 'An address has no spaces in it. Check what you typed.',
    'not-https': 'The address must start with https://.',
    'not-an-address': 'That does not look like a whole address. It should look like the example.',
    'not-saved': 'This browser refused to remember it. You can still open the address by hand.',
  } satisfies Record<AddressProblem | 'not-saved', string>,
} as const;

export const remembered = {
  heading: 'Your dashboard',
  open: 'Open my dashboard',
  forget: 'Forget this address',
  note: 'Remembered in this browser only. Opens in a new tab.',
} as const;

export const whereToFind = {
  heading: 'Where do I find my address?',
  intro: 'In one of three places:',
  places: [
    'On the last screen of the set-up, after "Set-up done."',
    'In the file ~/threadline/backend/.env, on the line DASHBOARD_URL.',
    'In your Netlify account, under your sites.',
  ],
} as const;

export const onYourPhone = {
  heading: 'On your phone',
  intro: 'Open the address on your phone and add it to the home screen. It then opens like an app.',
  steps: [
    { device: 'iPhone and iPad', how: 'In Safari, tap Share, then "Add to Home Screen".' },
    { device: 'Android', how: 'In Chrome, tap the three-dot menu, then "Add to Home screen" or "Install app".' },
  ],
} as const;

export const notSetUp = {
  heading: 'Not set up yet?',
  body: 'The set-up takes thirty to forty minutes. Or look at the demo first: it is the dashboard filled with made-up people.',
  setup: 'Set it up',
  demo: 'Try the demo',
} as const;
