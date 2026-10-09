/**
 * The words of the "Keep your copy up to date" page. Facts come from the
 * header of `install.sh` and from docs/operations.md ("Publish a newer
 * dashboard").
 */

export const updatePage = {
  title: 'Keep your copy up to date',
  intro: 'Paste the install line again. It keeps what you have and brings your copy up to date.',
  whatChanged: 'What changed',
  whatChangedLead: 'See what is new first:',
} as const;

export const updateSteps = {
  heading: 'Three steps',
  pasteHeading: 'Paste the install line again',
  pasteBody: 'In a terminal, for your computer:',
  installLineWhat: 'the install line',
  publishHeading: 'Publish the newer dashboard',
  publishBody: 'Two lines publish the newer dashboard to the same address:',
  publishCommand: 'cd ~/threadline/backend\nuv run tracker setup dashboard',
  publishWhat: 'the dashboard lines',
  settingsHeading: 'Only if the change notes say settings changed',
  settingsBody: 'Save your settings on GitHub again:',
  settingsCommand: 'uv run tracker setup github',
  settingsWhat: 'the settings line',
} as const;

export const updateChecks = {
  check: 'Your dashboard opens and shows your data as before.',
  ifNot: 'Follow the line the set-up printed, then run the command again. The details are in setup.log in the backend folder.',
} as const;
