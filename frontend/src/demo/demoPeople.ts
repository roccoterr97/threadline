import type {
  CategoryKey,
  Channel,
  ContactStatus,
  Direction,
  Signal,
  WaitingOn,
} from '../types/database';

/**
 * The invented people of the demo: a small business doing sales outreach.
 * Every name, company and address is made up; mail domains all end in
 * `.example`, which can never belong to anyone.
 *
 * Days are counted from "today" so the demo always looks current: negative
 * numbers are in the past, positive ones in the future.
 */

/** One message: how many days ago, who wrote it, and what it said. */
export type MessageSeed = readonly [daysAgo: number, direction: Direction, body: string];

/** A meeting's start, counted from today. */
export interface MeetingSeed {
  inDays: number;
  hour: number;
  minute: number;
}

export interface ThreadSeed {
  channel: Channel;
  subject: string | null;
  messages: readonly MessageSeed[];
  meeting?: MeetingSeed;
}

export interface PersonSeed {
  id: string;
  fullName: string;
  role: string | null;
  organisation: string | null;
  type: CategoryKey;
  status: ContactStatus;
  waitingOn: WaitingOn;
  signal: Signal;
  dueInDays: number | null;
  nextAction: string;
  summary: string;
  threads: readonly ThreadSeed[];
}

export const DEMO_PEOPLE: readonly PersonSeed[] = [
  {
    id: 'demo-p01',
    fullName: 'Maya Lindqvist',
    role: 'Operations Lead',
    organisation: 'Harbourline Logistics',
    type: 'prospect',
    status: 'meeting_planned',
    waitingOn: 'nobody',
    signal: 'positive',
    dueInDays: 2,
    nextAction: 'Run the demo and send the pricing sheet afterwards',
    summary:
      'Operations lead at Harbourline. Answered the first e-mail within a day and booked a demo for her team of twelve.',
    threads: [
      {
        channel: 'email',
        subject: 'Route planning for Harbourline',
        messages: [
          [9, 'outbound', 'Hello Maya, I saw Harbourline is opening a second depot. We help teams plan routes in half the time — worth a short look?'],
          [8, 'inbound', 'Timing is good, we are drowning in spreadsheets. Could you show the team?'],
          [7, 'outbound', 'Of course. I have sent an invitation for a 30-minute demo.'],
        ],
      },
      {
        channel: 'calendar',
        subject: 'Demo for Harbourline Logistics',
        messages: [[7, 'inbound', 'Meeting organised by you. Maya Lindqvist accepted.']],
        meeting: { inDays: 2, hour: 10, minute: 0 },
      },
    ],
  },
  {
    id: 'demo-p02',
    fullName: 'Tomás Ferreira',
    role: 'Head of Procurement',
    organisation: 'Quillstone Foods',
    type: 'prospect',
    status: 'in_process',
    waitingOn: 'me',
    signal: 'positive',
    dueInDays: -2,
    nextAction: 'Send the revised quote with the annual discount',
    summary:
      'Trial finished well. Tomás asked for a revised quote before his finance meeting; it is late.',
    threads: [
      {
        channel: 'email',
        subject: 'Quote for Quillstone Foods',
        messages: [
          [21, 'outbound', 'Hi Tomás, following our call, here is the trial account for your planners.'],
          [12, 'inbound', 'The planners like it. Can you send a quote for 25 seats?'],
          [11, 'outbound', 'Quote attached. Happy to walk through it.'],
          [5, 'inbound', 'Finance wants an annual price. Could you revise it before Thursday?'],
        ],
      },
    ],
  },
  {
    id: 'demo-p03',
    fullName: 'Priya Natarajan',
    role: 'IT Director',
    organisation: 'Bellwether Clinics',
    type: 'prospect',
    status: 'contacted_no_reply',
    waitingOn: 'them',
    signal: 'neutral',
    dueInDays: -3,
    nextAction: 'Send a short follow-up with the clinic case study',
    summary: 'Contacted on LinkedIn after the health-tech meetup. No answer yet.',
    threads: [
      {
        channel: 'linkedin',
        subject: null,
        messages: [
          [10, 'outbound', 'Hello Priya, good to meet you at the meetup. Would a 20-minute call about scheduling for your clinics be useful?'],
        ],
      },
    ],
  },
  {
    id: 'demo-p04',
    fullName: 'Owen Achterberg',
    role: 'Founder',
    organisation: 'Tidewater Studio',
    type: 'prospect',
    status: 'gone_quiet',
    waitingOn: 'them',
    signal: 'cold',
    dueInDays: -6,
    nextAction: 'One last nudge, then close it',
    summary: 'Was keen at first, then stopped answering after the price came up.',
    threads: [
      {
        channel: 'email',
        subject: 'Tidewater and route planning',
        messages: [
          [30, 'inbound', 'A friend recommended you. What would it cost for a studio of six?'],
          [29, 'outbound', 'Hi Owen, for six people it is the starter plan. Details attached.'],
          [25, 'inbound', 'Thanks, I will look this week.'],
          [18, 'outbound', 'Any questions I can answer?'],
        ],
      },
    ],
  },
  {
    id: 'demo-p05',
    fullName: 'Sofia Marchetti',
    role: 'Finance Manager',
    organisation: 'Cobalt & Pine',
    type: 'customer',
    status: 'in_conversation',
    waitingOn: 'me',
    signal: 'positive',
    dueInDays: 1,
    nextAction: 'Answer her question about moving to yearly billing',
    summary: 'Customer for a year. Asking whether they can switch to yearly billing at renewal.',
    threads: [
      {
        channel: 'email',
        subject: 'Renewal and billing',
        messages: [
          [4, 'inbound', 'Hi, our renewal is next month. Can we move to yearly billing, and is there a discount?'],
        ],
      },
    ],
  },
  {
    id: 'demo-p06',
    fullName: 'Kwame Mensah',
    role: 'Customer Success Lead',
    organisation: 'Lumen Freight',
    type: 'customer',
    status: 'meeting_planned',
    waitingOn: 'nobody',
    signal: 'positive',
    dueInDays: 5,
    nextAction: 'Prepare the usage numbers for the quarterly review',
    summary: 'Happy customer. Quarterly review booked; they may add a second team.',
    threads: [
      {
        channel: 'email',
        subject: 'Quarterly review',
        messages: [
          [6, 'outbound', 'Hi Kwame, time for our quarterly review. Does next week suit you?'],
          [5, 'inbound', 'Yes — and I would like to talk about adding the warehouse team.'],
        ],
      },
      {
        channel: 'calendar',
        subject: 'Quarterly review with Lumen Freight',
        messages: [[5, 'inbound', 'Meeting organised by Kwame Mensah. You accepted.']],
        meeting: { inDays: 5, hour: 9, minute: 30 },
      },
    ],
  },
  {
    id: 'demo-p07',
    fullName: 'Hannah Kowalski',
    role: 'Office Manager',
    organisation: 'Brightmoor Dental',
    type: 'customer',
    status: 'closed',
    waitingOn: 'nobody',
    signal: 'positive',
    dueInDays: null,
    nextAction: 'Nothing to do — check in at renewal',
    summary: 'Signed the yearly plan last week. Onboarding is done.',
    threads: [
      {
        channel: 'email',
        subject: 'Welcome aboard',
        messages: [
          [9, 'inbound', 'Contract signed and returned. Looking forward to it!'],
          [8, 'outbound', 'Wonderful, welcome aboard. Your accounts are ready.'],
        ],
      },
    ],
  },
  {
    id: 'demo-p08',
    fullName: 'Rafael Ortega',
    role: 'Partnerships Manager',
    organisation: 'Stackbridge Integrations',
    type: 'partner',
    status: 'in_process',
    waitingOn: 'me',
    signal: 'positive',
    dueInDays: -1,
    nextAction: 'Send back the signed partner agreement',
    summary: 'Agreed to resell to their clients. The partner agreement is waiting for your signature.',
    threads: [
      {
        channel: 'linkedin',
        subject: null,
        messages: [
          [20, 'inbound', 'We integrate with tools like yours. Interested in a reseller deal?'],
          [19, 'outbound', 'Very. Shall we talk this week?'],
        ],
      },
      {
        channel: 'email',
        subject: 'Partner agreement',
        messages: [
          [6, 'inbound', 'Agreement attached as discussed. Please sign and send it back.'],
        ],
      },
    ],
  },
  {
    id: 'demo-p09',
    fullName: 'Daniel Novak',
    role: 'Sales Engineer',
    organisation: 'Stackbridge Integrations',
    type: 'partner',
    status: 'meeting_planned',
    waitingOn: 'nobody',
    signal: 'neutral',
    dueInDays: 1,
    nextAction: 'Agree who presents which part of the joint pitch',
    summary: 'Works with Rafael. Preparing a joint pitch for one of their clients.',
    threads: [
      {
        channel: 'calendar',
        subject: 'Joint pitch preparation',
        messages: [[3, 'inbound', 'Meeting organised by Daniel Novak. You accepted.']],
        meeting: { inDays: 1, hour: 15, minute: 30 },
      },
    ],
  },
  {
    id: 'demo-p10',
    fullName: 'Aisha Rahman',
    role: 'Agency Director',
    organisation: 'Fernhill Digital',
    type: 'partner',
    status: 'in_conversation',
    waitingOn: 'them',
    signal: 'neutral',
    dueInDays: 4,
    nextAction: 'Wait for her list of clients who could use it',
    summary: 'Runs an agency. Thinking about recommending you to her clients.',
    threads: [
      {
        channel: 'linkedin',
        subject: null,
        messages: [
          [8, 'outbound', 'Hello Aisha, several agencies recommend us to their clients. Could that work for Fernhill?'],
          [6, 'inbound', 'Possibly. Let me check which clients would fit and come back to you.'],
        ],
      },
    ],
  },
  {
    id: 'demo-p11',
    fullName: 'Jonah Whitfield',
    role: 'Former colleague',
    organisation: null,
    type: 'partner',
    status: 'in_conversation',
    waitingOn: 'me',
    signal: 'positive',
    dueInDays: 0,
    nextAction: 'Thank him and ask for an introduction to the logistics contact',
    summary: 'Old colleague who knows people in logistics. Offered two introductions.',
    threads: [
      {
        channel: 'linkedin',
        subject: null,
        messages: [
          [3, 'inbound', 'I know two people in logistics who would love this. Want an introduction?'],
        ],
      },
    ],
  },
  {
    id: 'demo-p12',
    fullName: 'Leila Haddad',
    role: 'Consultant',
    organisation: 'Haddad Advisory',
    type: 'partner',
    status: 'contacted_no_reply',
    waitingOn: 'them',
    signal: 'neutral',
    dueInDays: 6,
    nextAction: 'Wait a week, then follow up',
    summary: 'Advises small shipping firms. Asked whether she would refer clients.',
    threads: [
      {
        channel: 'email',
        subject: 'Working together?',
        messages: [
          [2, 'outbound', 'Hi Leila, would you be open to recommending us to your clients? Happy to share a referral fee.'],
        ],
      },
    ],
  },
  {
    id: 'demo-p13',
    fullName: 'Grace Oyelaran',
    role: 'Chief Operating Officer',
    organisation: 'Bellwether Clinics',
    type: 'prospect',
    status: 'closed',
    waitingOn: 'nobody',
    signal: 'cold',
    dueInDays: null,
    nextAction: 'Try again next year',
    summary: 'Chose another supplier. Open to talking again next year.',
    threads: [
      {
        channel: 'email',
        subject: 'Your proposal',
        messages: [
          [16, 'outbound', 'Hi Grace, here is the proposal we discussed.'],
          [12, 'inbound', 'Thank you, but we have gone with another supplier this year.'],
        ],
      },
    ],
  },
  {
    id: 'demo-p14',
    fullName: 'Marcus Bell',
    role: null,
    organisation: null,
    type: 'unknown',
    status: 'in_conversation',
    waitingOn: 'me',
    signal: 'neutral',
    dueInDays: null,
    nextAction: 'Find out what he needs',
    summary: 'Wrote in asking about "the tool". Not yet clear who he is.',
    threads: [
      {
        channel: 'email',
        subject: 'Question about your tool',
        messages: [[2, 'inbound', 'Hello, a friend mentioned your tool. Can you tell me more?']],
      },
    ],
  },
];
