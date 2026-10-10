import { OPERATIONS_URL } from '../constants/links';

/** The questions people ask, and short answers. Facts from the README and the live set-up test. */
export interface Question {
  id: string;
  question: string;
  /** Paragraphs; a little inline markup is allowed, as in the set-up. */
  answer: readonly string[];
}

export const QUESTIONS: readonly Question[] = [
  {
    id: 'data',
    question: 'Is my data sent anywhere?',
    answer: [
      'Only to accounts you own. Your own copy reads your messages on GitHub, Claude judges them on your own Claude plan, and the results live in your own Supabase database. Your dashboard is a shared page that shows only what your own database sends it, after you sign in.',
      'Nothing is sent to the people who make Threadline. There is no Threadline server.',
    ],
  },
  {
    id: 'why-claude',
    question: 'Why Claude?',
    answer: [
      'Working out who is waiting on whom takes judgement that simple rules cannot give. Threadline uses Claude through Claude Code, on the plan you already have, so there is no API key to buy and no bill per message. The daily run uses part of your plan\'s usage limits.',
    ],
  },
  {
    id: 'outside-europe',
    question: 'Can I use it outside Europe?',
    answer: [
      'Yes. Only LinkedIn is limited to the European Economic Area and Switzerland, because LinkedIn only lets members there export their messages. Mail and calendar work anywhere.',
    ],
  },
  {
    id: 'outlook-only',
    question: 'What if I only use Outlook?',
    answer: [
      'Outlook.com and Hotmail work, and so does the Outlook calendar. Outlook alone cannot send you the morning summary, though. Add a second mailbox with an app password, such as Gmail, or use the Claude cloud route. The set-up explains both.',
    ],
  },
  {
    id: 'sends',
    question: 'Does it send messages for me?',
    answer: [
      'No. Threadline only reads. It never writes to LinkedIn or your mailbox, never replies to anyone, and does not even mark mail as read. The one e-mail it sends is your own morning summary, to you.',
    ],
  },
  {
    id: 'cost',
    question: 'What does it cost?',
    answer: [
      'Threadline itself is free. GitHub and Supabase are used on their free plans, and Claude runs on the paid plan you already have (Pro, Max or Team). Free plans change from time to time, so check the providers\' pages if in doubt.',
    ],
  },
  {
    id: 'time',
    question: 'How long does the set-up take?',
    answer: [
      'About 20 minutes with GitHub and Supabase ready, about 30 without. The first summary e-mail arrives about ten minutes after you finish.',
    ],
  },
  {
    id: 'windows',
    question: 'Does it work on Windows?',
    answer: [
      'Yes, on Windows 10 and 11, with the PowerShell line from the set-up. Letting Claude run the set-up for you works on a Mac or Linux only for now.',
    ],
  },
  {
    id: 'phone',
    question: 'Does it work on my phone?',
    answer: [
      'The dashboard does: it opens in your phone\'s browser and can be added to the home screen like an app. The set-up itself needs a computer.',
    ],
  },
  {
    id: 'team',
    question: 'Can my team share one copy?',
    answer: [
      'No. One copy is for one person: the database has a single owner and keeps nobody else\'s data apart. Each person sets up their own copy, on their own accounts.',
    ],
  },
  {
    id: 'update',
    question: 'How do I update to a new version?',
    answer: ['Paste the install line again. The shared dashboard is kept up to date for you. [How to update](/update) shows the line.'],
  },
  {
    id: 'pause-remove',
    question: 'How do I pause it, or remove it completely?',
    answer: [
      `To pause, open your copy on GitHub, go to **Actions**, then **Threadline run**, and choose **Disable workflow**. Nothing is lost while it is off. [Step by step](${OPERATIONS_URL}#pause-and-resume).`,
      'To remove it completely, delete your threadline copy on GitHub and your project on Supabase (and your own dashboard site on Netlify, if you made one), and remove the app password from your mailbox. Everything was on your accounts, so that is all there is.',
    ],
  },
];
