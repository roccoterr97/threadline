import { DEMO_URL, SECURITY_URL } from '../constants/links';

/** The privacy page, in sections of a few sentences. A little inline markup is allowed. */
export interface PrivacySection {
  id: string;
  heading: string;
  paragraphs: readonly string[];
}

export const PRIVACY: readonly PrivacySection[] = [
  {
    id: 'website',
    heading: 'This website',
    paragraphs: [
      'No cookies, no analytics, no trackers and no advertising. The pages load no fonts or scripts from other companies.',
      'The site is hosted on Vercel. Like any web host, Vercel keeps short technical logs, such as IP addresses, to run and protect its service. We do not use them to follow anyone.',
      'Links to GitHub, the demo and the sign-up pages take you to other websites, which have their own privacy policies.',
    ],
  },
  {
    id: 'tool',
    heading: 'Threadline, the tool',
    paragraphs: [
      'You run your own copy, on your own GitHub and Supabase accounts and your own Claude plan. Your messages, your list of people and your notes are stored in your own database.',
      'The dashboard at app.threadlineapp.com is one page shared by everyone. It holds no data: after you sign in, your browser reads your data straight from your own database.',
      'The people who make Threadline have no database of their own and no access to yours. We cannot see, recover or delete your data: only you can.',
    ],
  },
  {
    id: 'reads',
    heading: 'What it reads and keeps',
    paragraphs: [
      'It reads your mailbox and calendar with read-only permission, and never writes to LinkedIn or your mailbox.',
      'Claude reads the messages to judge each conversation, on your own Claude plan and under the same terms as the rest of your Claude use.',
      'Mail judged to be noise keeps no subject and no text. The files that carry message text to Claude are deleted once its answers are saved. The notes you write about someone are never sent to Claude and never put in the summary e-mail.',
      `The full details are in the [security notes on GitHub](${SECURITY_URL}).`,
    ],
  },
  {
    id: 'demo',
    heading: 'The demo',
    paragraphs: [`The [demo](${DEMO_URL}) shows made-up people and saves nothing: reloading it starts again from the same made-up data.`],
  },
];
