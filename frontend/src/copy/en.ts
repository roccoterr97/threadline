/**
 * Every word the dashboard shows the owner lives here.
 *
 * House rules for anything added to this file:
 * - Plain English. No jargon, no abbreviations, no product names.
 * - Error messages say what the owner can do next, never what the code did.
 * - Raw error codes are never shown; map them in `runErrors` instead.
 */

import { DraftProblem } from '../domain/categorySettings';
import type { RefreshRefusal, RefreshTarget } from '../domain/refresh';
import type {
  CategoryColour,
  Channel,
  ContactStatus,
  Direction,
  RunStatus,
  RunStep,
  Signal,
  WaitingOn,
} from '../types/database';

export const app = {
  name: 'Threadline',
  skipToContent: 'Skip to the main content',
} as const;

export const nav = {
  home: 'People',
  review: 'To review',
  runs: 'Daily runs',
  settings: 'Settings',
  signOut: 'Sign out',
  headerLabel: 'Main menu',
  bottomBarLabel: 'Main menu at the bottom of the screen',
  reviewCountLabel: (count: number) =>
    count === 1 ? '1 question waiting for you' : `${count} questions waiting for you`,
} as const;

export const login = {
  title: 'Sign in',
  intro:
    'Type your email address and we will send you a sign-in link. There is no password to remember.',
  emailLabel: 'Your email address',
  emailHint: 'Only your own address can open this page.',
  submit: 'Send me the link',
  submitting: 'Sending…',
  sent: (email: string) =>
    `Check your inbox. We sent a sign-in link to ${email}. It may take a minute, and it sometimes lands in the junk folder.`,
  failed: 'We could not send the link just now. Please wait a moment and try again.',
  invalidEmail: 'That does not look like an email address. Please check it and try again.',
  checkingSession: 'Checking whether you are signed in…',
} as const;

export const home = {
  title: 'People',
  subtitle: 'Everyone you are talking to, and what each one is waiting for.',
  counters: {
    actionsForMe: 'Actions for me',
    overdue: 'Overdue replies',
    timeToChase: 'Time to chase',
    waitingOnThem: 'Waiting on them',
    activeConversations: 'Active conversations',
  },
  countersLabel: 'Headline numbers. Choose one to show those people.',
  counterShown: 'Shown below',
  comingUp: {
    title: 'Coming up',
    failed: 'We could not load your meetings for the week. Reload the page to try again.',
    untitled: 'Meeting',
    unknownPerson: 'Someone not on your list',
  },
  filtersLabel: 'Type of contact',
  statusFilterLabel: 'Status',
  waitingFilterLabel: 'Waiting on',
  dueFilterLabel: 'Due',
  sortLabel: 'Sort by',
  tableCaption: 'People you are in contact with',
  columns: {
    person: 'Person',
    organisation: 'Organisation',
    type: 'Type',
    lastContact: 'Last contact',
    status: 'Status',
    waitingOn: 'Waiting on',
    nextAction: 'Next action',
    due: 'Due',
    signal: 'Signal',
  },
  openPerson: (name: string) => `Open ${name}`,
  empty: {
    title: 'Nobody here yet',
    body: 'Once the daily run has read your LinkedIn messages and your mailbox, the people you are talking to will show up here.',
  },
  emptyFiltered: {
    title: 'Nothing matches these filters',
    body: 'Nobody on your list fits everything you picked.',
    action: 'Clear all filters',
  },
  grid: {
    caption: 'How many people of each type are at each stage',
    statusColumn: 'Status',
    total: 'Total',
    cellLabel: (count: number, typeText: string, statusText: string) =>
      `${count}: ${typeText}, ${statusText}`,
  },
} as const;

export const person = {
  backToPeople: 'Back to all people',
  summaryTitle: 'What is going on',
  noSummary: 'The assistant has not written a summary for this person yet.',
  detailsTitle: 'Where this stands',
  stateGroupLabel: 'Where this stands now',
  timelineTitle: 'Every message',
  messageCountLabel: 'Messages saved',
  timelineEmpty: 'No messages have been saved for this person yet.',
  showMore: 'Show more',
  showLess: 'Show less',
  correctHint: 'Change the status, the next step, or hide this person.',
  noBody: 'The text of this message was not kept.',
  noSubject: 'No subject',
  correctedByYou: 'You corrected this',
  notFound: {
    title: 'We could not find that person',
    body: 'They may have been removed from the list. Go back to see everyone.',
  },
  markNoise: {
    button: 'Not relevant',
    confirmTitle: 'Hide this person?',
    confirmBody:
      'They will be taken off your list and the assistant will stop looking at their messages. You can ask for this to be undone later.',
    confirm: 'Yes, hide them',
    cancel: 'No, keep them',
    failed: 'We could not hide this person. Please try again.',
  },
} as const;

export const override = {
  title: 'Correct this',
  intro: 'Anything you set here wins over the assistant, now and on every later run.',
  statusLabel: 'Status',
  waitingOnLabel: 'Waiting on',
  nextActionLabel: 'Next action',
  dueDateLabel: 'Due date',
  personTypeLabel: 'Type of contact',
  noteLabel: 'Note for yourself',
  keepAssistantValue: 'Leave it to the assistant',
  save: 'Save my correction',
  saving: 'Saving… not saved yet',
  clear: 'Clear my correction',
  clearing: 'Clearing…',
  saved: 'Your correction was saved.',
  cleared: 'Your correction was removed. The assistant’s own view is back.',
  failed: 'We could not save your correction, so we put the old values back. Please try again.',
  failedSignedOut:
    'You have been signed out, so your correction was not saved. Sign in again and repeat it.',
  clearFailed: 'We could not clear your correction. Please try again.',
} as const;

export const settings = {
  title: 'Settings',
  subtitle: 'Make the dashboard fit what you are keeping track of.',
  loading: 'Loading your settings…',
} as const;

export const categorySettings = {
  title: 'Categories',
  intro:
    'Categories say who someone is to you — a customer, an investor, a friend. The assistant uses them to sort everyone it finds. A change here reaches the assistant the next morning.',
  yours: 'Your categories',
  none: 'You have no categories of your own yet. Add one below.',
  reservedNote: 'Always there, for people who cannot be placed yet. It cannot be changed.',
  hidden: 'Hidden categories',
  hiddenIntro:
    'Some people still have these, so they keep them. They are no longer offered as a choice.',
  suggestions: 'Suggestions',
  suggestionsIntro: 'One tap adds a category with its description already written.',
  suggestionsFailed: 'We could not load the suggestions. Reload the page to try again.',
  addOwn: 'Add your own',
  limitReached:
    'You already use eight categories, the most there can be. Remove or hide one before adding another.',
  fields: {
    name: 'Name',
    groupName: 'Name for a group',
    groupNameHint: 'Used on the filter buttons and the table, for example “Customers”.',
    description: 'Who belongs here (the assistant reads this)',
    colour: 'Colour',
  },
  actions: {
    change: 'Change',
    changeLabel: (label: string) => `Change ${label}`,
    moveUp: 'Move up',
    moveUpLabel: (label: string) => `Move ${label} up`,
    moveDown: 'Move down',
    moveDownLabel: (label: string) => `Move ${label} down`,
    remove: 'Remove',
    removeLabel: (label: string) => `Remove ${label}`,
    showAgain: 'Show again',
    showAgainLabel: (label: string) => `Show ${label} again`,
    addSuggestion: (label: string) => `Add ${label}`,
    add: 'Add category',
    save: 'Save',
    cancel: 'Cancel',
    working: 'Saving…',
  },
  done: {
    added: (label: string) => `“${label}” was added.`,
    saved: (label: string) => `Your changes to “${label}” were saved.`,
    moved: (label: string) => `“${label}” was moved. The new order is saved.`,
    removed: (label: string) => `“${label}” was removed.`,
    hiddenInstead: (label: string) =>
      `“${label}” is hidden instead, because some people still have it. It is no longer offered as a choice.`,
    shownAgain: (label: string) => `“${label}” is back among your categories.`,
  },
  failed: {
    generic: 'We could not save that change. Please try again.',
    signedOut: 'You have been signed out, so nothing was saved. Sign in again and repeat it.',
    breaksRule:
      'That change was turned down: at most eight categories can be in use, and “Not known” cannot be changed. Nothing was saved.',
    duplicate: 'There is already a category like that. Reload the page to see it.',
  },
} as const;

/** One sentence for each thing that can be wrong with a category form. */
export const categoryDraftProblems: Record<DraftProblem, string> = {
  [DraftProblem.MissingName]: 'Please give the category a name.',
  [DraftProblem.NameTooLong]: 'The name can be at most 40 characters long.',
  [DraftProblem.MissingGroupName]: 'Please give a name for a group of them.',
  [DraftProblem.GroupNameTooLong]: 'The name for a group can be at most 40 characters long.',
  [DraftProblem.MissingDescription]:
    'Please say who belongs here, so the assistant can place people.',
  [DraftProblem.DescriptionTooLong]: 'The description can be at most 1,000 characters long.',
};

/** The name of each palette colour, shown next to its swatch. */
export const categoryColourNames: Record<CategoryColour, string> = {
  violet: 'Violet',
  cyan: 'Cyan',
  orange: 'Orange',
  pink: 'Pink',
  indigo: 'Indigo',
  teal: 'Teal',
  olive: 'Olive',
  brown: 'Brown',
  grey: 'Grey',
};

export const review = {
  title: 'To review',
  subtitle: 'The assistant is unsure about these. Your answers are remembered.',
  yes: 'Yes',
  no: 'No',
  answering: 'Saving your answer…',
  empty: {
    title: 'Nothing to review',
    body: 'The assistant has no open questions for you right now.',
  },
  failed: 'We could not save your answer. Please try again.',
  kind: {
    relevance: 'Is this relevant to what you are tracking?',
    same_person: 'Is this the same person?',
  },
} as const;

export const runs = {
  title: 'Daily runs',
  subtitle: 'The last two weeks of automatic updates.',
  startedAt: 'Started',
  duration: 'Took',
  trigger: 'Started by',
  stepsTitle: 'Steps',
  found: 'found',
  new: 'new',
  stillRunning: 'Still running',
  empty: {
    title: 'No runs yet',
    body: 'The first automatic update has not happened yet. It will show up here once it does.',
  },
} as const;

export const banner = {
  lastRunFailed:
    'The last automatic update did not finish, so what you see below may be out of date.',
  lastRunStale: 'There has been no successful update for more than a day. This list may be stale.',
  noRunYet: 'No automatic update has run yet, so this list is empty for now.',
  seeRuns: 'See the run history',
  updatedAt: (whenText: string) => `Last updated ${whenText}`,
} as const;

/** Where the switch-on guide lives; the dashboard cannot know the address of the owner's copy. */
const REFRESH_GUIDE = 'the guide docs/refresh-now.md in your copy of Threadline';

/** What to do when Refresh now is not there yet: one command switches it on. */
const SWITCH_ON =
  "Refresh now is not switched on yet. Run 'uv run tracker setup refresh' in your copy of Threadline (the guide, part 8f, explains).";

/** Who runs the extra update, as the owner knows it. */
function runnerName(target: RefreshTarget | null): string {
  if (target === 'github') return 'GitHub';
  if (target === 'claude_routine') return 'Claude';
  return 'The service that runs your updates';
}

/** The "Refresh now" button and the one-line status under the header. */
export const refresh = {
  button: 'Refresh now',
  buttonShort: 'Refresh',
  busy: 'Refreshing…',
  sending: 'Asking for a refresh…',
  waiting: 'Refreshing… new messages will appear in a few minutes.',
  finished: {
    success: 'Refresh finished. Everything is up to date.',
    partial: 'Refresh finished, but part of it did not work. The run history says which part.',
    failed: 'The refresh did not work. The run history says what went wrong.',
    running: 'Refreshing… new messages will appear in a few minutes.',
  } satisfies Record<RunStatus, string>,
  timedOut:
    'The refresh has not finished after 15 minutes. It may still be going; check the run history later.',
  seeRuns: 'See the run history',
  refusals: {
    not_deployed: () => SWITCH_ON,
    unanswered: () => SWITCH_ON,
    not_set_up: () =>
      `Refresh now is only half set up: a setting is missing or mistyped. Follow ${REFRESH_GUIDE}.`,
    unreachable: () => 'You seem to be offline. Check your internet connection, then try again.',
    already_running: () =>
      'An update is already running. New messages will appear when it finishes.',
    too_soon: (_target, minutes) =>
      minutes === null
        ? 'A refresh was started a few minutes ago. Please wait a little before the next one.'
        : `A refresh was started a few minutes ago. You can start the next one in ${minutes === 1 ? '1 minute' : `${minutes} minutes`}.`,
    runner_auth_failed: (target) =>
      `${runnerName(target)} turned down the key Refresh now uses. It has probably expired. Make a new one and save it in Supabase, as ${REFRESH_GUIDE} explains under "Renew the key".`,
    runner_not_found: (target) =>
      `${runnerName(target)} could not find what Refresh now should start. Check the names you saved in Supabase against ${REFRESH_GUIDE}.`,
    runner_rejected: (target) =>
      `${runnerName(target)} turned the request down. The update may be paused or not set up yet. See ${REFRESH_GUIDE}.`,
    runner_rate_limited: (target) =>
      `${runnerName(target)} has had too many requests in the last hour. Please try again later.`,
    runner_unavailable: (target) =>
      `${runnerName(target)} did not answer. It usually works again by itself; try again in a few minutes.`,
    database_unavailable: () =>
      'The database could not be reached just now. Try again in a few minutes.',
    not_owner: () => 'Only the owner of this dashboard can start a refresh.',
    not_signed_in: () => 'Your sign-in has expired. Sign out, sign in again, then try once more.',
    origin_not_allowed: () =>
      `Refresh now does not recognise this web address. Check the dashboard address you saved in Supabase, as ${REFRESH_GUIDE} explains.`,
    method_not_allowed: () => 'Something went wrong starting the refresh. Please try again.',
    unexpected: () => 'Something went wrong starting the refresh. Please try again.',
  } satisfies Record<
    RefreshRefusal,
    (target: RefreshTarget | null, retryAfterMinutes: number | null) => string
  >,
} as const;

export const states = {
  loading: 'Loading…',
  loadingPeople: 'Loading your people…',
  loadingPerson: 'Loading this person…',
  loadingReview: 'Loading your questions…',
  loadingRuns: 'Loading the run history…',
  errorTitle: 'We could not load this',
  errorBody:
    'This usually means the connection dropped. Check that you are online and try again.',
  retry: 'Try again',
  notSignedIn: 'Your session has ended. Please sign in again.',
  notConfigured:
    'This page has not been connected to its database yet. Whoever set it up needs to add the two settings and publish again.',
} as const;

export const values = {
  none: 'Not set',
  unknown: 'Not known',
  never: 'Never',
  notAssessed: 'Not looked at yet',
} as const;

/**
 * Neutral status names, used only where the owner's own names (the
 * `status_labels` table) are missing or could not be loaded.
 */
export const defaultStatusLabels: Record<ContactStatus, string> = {
  contacted_no_reply: 'Contacted, no reply yet',
  in_conversation: 'In conversation',
  meeting_planned: 'Meeting planned',
  in_process: 'In process',
  gone_quiet: 'Gone quiet',
  closed: 'Closed',
};

export const waitingOnLabels: Record<WaitingOn, string> = {
  me: 'You',
  them: 'Them',
  nobody: 'Nobody',
};

export const signalLabels: Record<Signal, string> = {
  positive: 'Positive',
  neutral: 'Neutral',
  cold: 'Cold',
};

export const channelLabels: Record<Channel, string> = {
  linkedin: 'LinkedIn',
  email: 'Email',
  calendar: 'Calendar',
};

export const directionLabels: Record<Direction, string> = {
  inbound: 'They wrote',
  outbound: 'You wrote',
};

export const runStatusLabels: Record<RunStatus, string> = {
  running: 'Running',
  success: 'Worked',
  partial: 'Partly worked',
  failed: 'Did not work',
};

export const runStepLabels: Record<RunStep, string> = {
  collect_linkedin: 'Reading LinkedIn messages',
  collect_email: 'Reading your mailbox',
  collect_calendar: 'Reading your calendar',
  assess: 'Working out where each person stands',
  summary_email: 'Sending your morning email',
};

/**
 * Plain-English meaning for the error codes the daily run writes to
 * `run_step_logs.error_code`. Anything not listed falls back to
 * `runErrorFallback` — a raw code is never shown.
 */
export const runErrors: Record<string, string> = {
  source_auth_failed: 'The sign-in for this source has expired. It needs to be renewed.',
  source_unavailable: 'The other service did not answer. It usually works again by itself.',
  database_unavailable: 'The database could not be reached during this step.',
  database_request_failed: 'The database refused part of this step. The next run will try again.',
  database_probe_failed: 'The database could not be reached when the run started.',
  configuration_invalid: 'A setting is missing or wrong, so this step could not start.',
  validation_failed: 'Some of the data that came back did not look right and was skipped.',
  command_failed: 'This step stopped before it finished.',
  run_interrupted:
    'The run stopped here and never finished (for example, GitHub stopped it). It was closed when the next run started.',
  tracker_error: 'Something went wrong in this step.',
};

export const runErrorFallback = 'Something went wrong in this step.';

/** What set a run going, as stored in `run_logs.trigger`. */
export const runTriggerLabels: Record<string, string> = {
  cloud: 'the daily schedule (Claude)',
  github: 'the daily schedule (GitHub)',
  mac: 'your Mac',
  manual: 'you, by hand',
  refresh: 'the Refresh now button',
};

export const runTriggerFallback = 'something else';

export const time = {
  justNow: 'just now',
  minutesAgo: (n: number) => (n === 1 ? '1 minute ago' : `${n} minutes ago`),
  hoursAgo: (n: number) => (n === 1 ? '1 hour ago' : `${n} hours ago`),
  daysAgo: (n: number) => (n === 1 ? 'yesterday' : `${n} days ago`),
} as const;

export const filterLabels = {
  everyone: 'Everyone',
  anyStatus: 'Any status',
  anyone: 'Anyone',
  anyDate: 'Any date',
  active: 'Active — talking, meeting or in process',
  overdue: 'Overdue — replies you owe',
  chase: 'Time to chase — they have not answered',
} as const;

/** Short flags shown next to a person's due date. */
export const dueBadgeLabels = {
  overdue: 'Overdue',
  chase: 'Time to chase',
  description: 'Follow-up:',
} as const;

export const sortLabels = {
  lastContact: 'Most recent contact',
  dueDate: 'Due date',
  name: 'Name',
} as const;

/** The strip across the top of the demo. */
export const demo = {
  notice: 'Demo — made-up data. Nothing is saved.',
  setupLink: 'Set up your own',
} as const;
