/** The words of the home page. Few of them, on purpose. */

export const hero = {
  title: 'Every conversation, one clear line.',
  lead: 'Threadline reads your LinkedIn messages and your mailbox once a day and keeps one timeline per person. Each morning you know who is waiting for whom.',
  demo: 'Try the demo',
  setup: 'Set it up',
  small: 'Free. Open source. Runs on accounts you own.',
} as const;

export interface Moment {
  title: string;
  text: string;
}

export const story = {
  number: '01',
  heading: 'How it works',
  moments: [
    {
      title: 'Once a day',
      text: 'It reads your new LinkedIn messages, e-mails and meetings. Nothing is written back.',
    },
    {
      title: 'One line per person',
      text: 'Noise is dropped. What is left becomes one timeline per person, across every channel.',
    },
    {
      title: 'Who is waiting for whom',
      text: 'Claude, on your own plan, says where each conversation stands and what to do next. You see it on your dashboard and in a short morning e-mail.',
    },
  ] satisfies readonly Moment[],
} as const;

export const personFigure = {
  caption: 'One person: every message in order, and where it stands. Made-up names, from the demo.',
  alt: 'A person in the dashboard: their name and status, then every e-mail and meeting with them in order, newest first.',
} as const;

export const showcase = {
  caption: 'The people list, on a laptop and on a phone. Every name here is made up: it is the demo.',
  desktopAlt: 'The dashboard: a list of people, each with a status, who is waiting on whom, the next action and its due date.',
  phoneAlt: 'The same list on a phone, one card per person.',
} as const;

export const promises = {
  number: '02',
  heading: 'Yours alone',
  lines: [
    'Your data stays in your own database and your own GitHub copy. Nothing is sent to us.',
    'It only reads. It never writes to LinkedIn or your mailbox, and never sends anything to anyone but you.',
    'The judging runs on your own Claude plan. No separate AI key, no extra bill.',
  ],
} as const;

export const needs = {
  number: '03',
  heading: 'What you need',
  items: [
    ['A computer', 'Mac, Windows or Linux, for the set-up once'],
    ['A paid Claude plan', 'Pro, Max or Team'],
    ['Three free accounts', 'GitHub, Supabase and Netlify'],
    ['A mailbox', 'Gmail, Outlook, iCloud, Yahoo, Fastmail or any IMAP mailbox'],
    ['LinkedIn, if you want', 'Only for profiles located in the EEA or Switzerland'],
  ] satisfies readonly (readonly [string, string])[],
  time: 'About 40 minutes with the accounts ready, around an hour without.',
} as const;

export const finalCall = {
  heading: 'Ready?',
  text: 'The set-up takes you through it one step at a time.',
  setup: 'Set it up',
  demo: 'Try the demo first',
  guide: 'Prefer the written guide?',
  questions: 'Questions?',
} as const;
