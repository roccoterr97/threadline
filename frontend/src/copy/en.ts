/**
 * Every word the dashboard shows the owner lives here.
 *
 * House rules for anything added to this file:
 * - Plain English. No jargon, no abbreviations, no product names.
 * - Error messages say what the owner can do next, never what the code did.
 * - Raw error codes are never shown; map them in `runErrors` instead.
 */

import { RUN_HISTORY_LIMIT } from '../constants/dashboard';
import { DraftProblem } from '../domain/categorySettings';
import type { RefreshRefusal, RefreshTarget } from '../domain/refresh';
import type {
  CategoryColour,
  Channel,
  ContactStatus,
  Direction,
  ReviewAnswer,
  ReviewKind,
  RunStatus,
  RunStep,
  Signal,
  WaitingOn,
} from '../types/database';

export const app = {
  name: 'Threadline',
  skipToContent: 'Skip to the main content',
  /** The browser tab's name for one page. */
  pageTitle: (page: string) => `${page} – Threadline`,
} as const;

export const nav = {
  home: 'People',
  organisations: 'Organisations',
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
  unknownAddress:
    'This address cannot sign in. Use the email address you chose for your dashboard login during set-up. It is usually the one you use for Supabase.',
  tooManyLinks: (seconds: number | null) =>
    seconds === null
      ? 'Too many links were asked for. Please wait a while, up to an hour, then try again.'
      : `Too many links were asked for. Please wait ${seconds === 1 ? '1 second' : `${seconds} seconds`}, then try again.`,
  invalidEmail: 'That does not look like an email address. Please check it and try again.',
  checkingSession: 'Checking whether you are signed in…',
} as const;

/** The shared dashboard's way in: the personal link, and switching databases. */
export const connect = {
  title: 'Open your dashboard',
  intro:
    'Open the personal link from your set-up or from your morning e-mail. It tells this page which database is yours.',
  shared:
    'Everyone who uses Threadline opens this same page. Your data stays in your own database, and only you can sign in to it.',
  linkLabel: 'Or paste your personal link here',
  linkHint: 'It starts with https://app.threadlineapp.com/#project=',
  submit: 'Open my dashboard',
  invalidPasted:
    'That is not a complete personal link. Copy the whole link from your set-up or your morning e-mail, then try again.',
  invalidOpened:
    'The link you opened is not complete. Open it again from your morning e-mail, or paste it below.',
  switchTitle: 'Open a different database?',
  switchBody: (incoming: string, current: string) =>
    `This link opens the database at ${incoming}. This browser opens the one at ${current} now.`,
  switchConfirm: 'Switch to the new one',
  switchKeep: 'Keep the current one',
  connectedTo: (address: string) => `This page opens your database at ${address}.`,
  forget: 'Use a different database',
} as const;

/** Said when the owner's database lacks something this dashboard needs. */
export const databaseUpdate = {
  notice:
    "Your database is older than this dashboard, so some parts may not work. Update your copy of Threadline, run 'uv run tracker setup database', then reload this page.",
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
  filtersLabel: 'Category',
  statusFilterLabel: 'Status',
  waitingFilterLabel: 'Waiting on',
  dueFilterLabel: 'Due',
  sortLabel: 'Sort by',
  tableCaption: 'People you are in contact with',
  columns: {
    person: 'Person',
    organisation: 'Organisation',
    type: 'Category',
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
    caption: 'How many people in each category have each status',
    statusColumn: 'Status',
    total: 'Total',
    scrollHint: 'Scroll sideways to see every category.',
    cellLabel: (count: number, typeText: string, statusText: string) =>
      `${count}: ${typeText}, ${statusText}`,
  },
} as const;

export const organisations = {
  title: 'Organisations',
  subtitle: 'The same people, grouped by organisation: where you stand with each one as a whole.',
  loading: 'Loading your organisations…',
  switchLabel: 'See your list by person or by organisation',
  filterHint:
    'An organisation is shown when at least one person there fits everything you pick. Its numbers always count everyone there.',
  tableCaption: 'Organisations you are in contact with',
  columns: {
    people: 'People',
    state: 'Where things stand',
  },
  sortLabels: {
    attention: 'Needs you first',
    people: 'Most people',
  },
  noOrganisation: 'No organisation',
  noOrganisationHint: 'People with no organisation on record.',
  peopleCount: (count: number) => (count === 1 ? '1 person' : `${count} people`),
  inTouch: (count: number) =>
    count === 1 ? '1 person you are in touch with here.' : `${count} people you are in touch with here.`,
  /** One number of the picture, such as "Your turn: 2". */
  stateCount: (label: string, count: number) => `${label}: ${count}`,
  stateGroupLabel: 'Where things stand here',
  emptyFiltered: {
    title: 'Nothing matches these filters',
    body: 'No organisation has someone who fits everything you picked.',
  },
  backToOrganisations: 'Back to organisations',
  backToOrganisation: (name: string) => `Back to ${name}`,
  backToNoOrganisation: 'Back to people with no organisation',
  notFound: {
    title: 'We could not find that organisation',
    body: 'Its people may have been hidden or removed from the list, or its name may be written differently now.',
  },
} as const;

export const person = {
  backToPeople: 'Back to people',
  summaryTitle: 'What is going on',
  noSummary: 'The assistant has not written a summary for this person yet.',
  detailsTitle: 'Where this stands',
  stateGroupLabel: 'Where this stands now',
  timelineTitle: 'Every message',
  timelineCut: (limit: number) =>
    `A very long conversation is shown from its newest ${limit.toLocaleString('en')} messages. Older ones may be left out.`,
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
    body: 'They may have been hidden or removed from the list.',
  },
  markNoise: {
    button: 'Not relevant',
    confirmTitle: 'Hide this person?',
    confirmBody:
      'They will be taken off your list and the assistant will stop looking at their messages. You can undo this straight afterwards.',
    confirm: 'Yes, hide them',
    cancel: 'No, keep them',
    failed: 'We could not hide this person. Please try again.',
  },
  hidden: {
    notice: (name: string) =>
      `${name} is hidden. They are off your list and the assistant will stop looking at their messages.`,
    undo: 'Undo',
    undoLabel: (name: string) => `Undo hiding ${name}`,
    undoing: 'Putting them back…',
    restored: (name: string) => `${name} is back on your list.`,
    undoFailed: (name: string) => `We could not put ${name} back on your list. Please try again.`,
  },
} as const;

export const override = {
  title: 'Correct this',
  intro: 'Anything you set here wins over the assistant, now and on every later run.',
  statusLabel: 'Status',
  waitingOnLabel: 'Waiting on',
  nextActionLabel: 'Next action',
  dueDateLabel: 'Due date',
  personTypeLabel: 'Category',
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
  failedNotAllowed: 'This account is not allowed to make changes here, so nothing was saved.',
  clearFailed: 'We could not clear your correction. Please try again.',
} as const;

/** The notes the owner types on a person's page. */
export const notes = {
  title: 'Your notes',
  intro:
    'Things no message says, kept for you alone. The assistant does not read them and they are not in your morning e-mail.',
  empty: 'No notes yet.',
  add: 'Add a note',
  fieldLabel: 'Your note',
  editFieldLabel: 'Change your note',
  save: 'Save my note',
  saveChanges: 'Save my changes',
  saving: 'Saving… not saved yet',
  cancel: 'Cancel',
  change: 'Change',
  changeLabel: (excerpt: string) => `Change the note “${excerpt}”`,
  remove: 'Delete',
  removeLabel: (excerpt: string) => `Delete the note “${excerpt}”`,
  removeConfirmTitle: 'Delete this note?',
  removeConfirmBody: (excerpt: string) => `“${excerpt}” will be gone for good. This cannot be undone.`,
  removeConfirm: 'Yes, delete it',
  removeCancel: 'No, keep it',
  writtenOn: (dateText: string) => `Written ${dateText}`,
  changedOn: (dateText: string) => `changed ${dateText}`,
  onlyNewestShown: (count: number) => `Only your newest ${count} notes are shown.`,
  problems: {
    empty: 'Please write something before saving the note.',
    tooLong: (most: number) => `A note can be at most ${most.toLocaleString('en-GB')} characters long.`,
  },
  done: {
    added: 'Your note was saved.',
    saved: 'Your changes to the note were saved.',
    removed: 'The note was deleted.',
  },
  failed: {
    add: 'We could not save your note. Please try again.',
    save: 'We could not save your changes. Please try again.',
    remove: 'We could not delete the note. Please try again.',
    signedOut: 'You have been signed out, so nothing was saved. Sign in again and repeat it.',
    notAllowed: 'This account is not allowed to make changes here, so nothing was saved.',
  },
  notSetUp:
    "Notes are not switched on in your database yet. Run 'uv run tracker setup database' in your copy of Threadline, then reload this page.",
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
  length: {
    count: (used: number, most: number) => `${used} of ${most} characters`,
    atLimit: (most: number) => `That is the most it can be: ${most} characters.`,
  },
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
    removeConfirmTitle: (label: string) => `Remove ${label}?`,
    removeConfirmBody:
      'People in it keep their data. If anyone is in it, it will be hidden instead, so they keep it.',
    removeConfirm: 'Yes, remove it',
    removeCancel: 'No, keep it',
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
    notAllowed: 'This account is not allowed to make changes here, so nothing was saved.',
    breaksRule:
      'That change was turned down: at most eight categories can be in use, and “Not known” cannot be changed. Nothing was saved.',
    duplicate: 'There is already a category like that. Reload the page to see it.',
  },
} as const;

/** One sentence for each thing that can be wrong with a category form. */
export const categoryDraftProblems: Record<DraftProblem, string> = {
  [DraftProblem.MissingName]: 'Please give the category a name.',
  [DraftProblem.NameTooLong]: 'The name can be at most 40 characters long.',
  [DraftProblem.DuplicateName]:
    'You already have a category with this name (perhaps a hidden one). Please pick another name.',
  [DraftProblem.MissingGroupName]: 'Please give a name for a group of them.',
  [DraftProblem.GroupNameTooLong]: 'The name for a group can be at most 40 characters long.',
  [DraftProblem.DuplicateGroupName]:
    'Another category already uses this name for a group (perhaps a hidden one). Please pick another one.',
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
  /** What happens after each answer, said once it is saved. */
  answered: {
    relevance: {
      yes: 'Answer saved. The assistant will count this as part of what you track.',
      no: 'Answer saved. The assistant will leave this out from now on.',
    },
    same_person: {
      yes: 'Answer saved. The two will be joined into one person on the next daily run.',
      no: 'Answer saved. They will stay two separate people.',
    },
  } satisfies Record<ReviewKind, Record<ReviewAnswer, string>>,
} as const;

export const runs = {
  title: 'Daily runs',
  subtitle: `The ${RUN_HISTORY_LIMIT} most recent automatic updates, newest first.`,
  startedAt: 'Started',
  duration: 'Took',
  trigger: 'Started by',
  stepsTitle: 'Steps',
  found: 'found',
  new: 'new',
  emailSent: 'sent',
  emailSkipped: 'not sent: today’s email had already gone out',
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
  "Refresh now is not switched on yet. Run 'uv run tracker setup refresh' in your copy of Threadline (the guide, part 8b, explains).";

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
  refreshFailed: "Couldn't update just now. Showing what was loaded earlier.",
  peopleCut: (shown: number) =>
    `Only the ${shown.toLocaleString('en')} people you were in touch with most recently are shown. Older ones are left out, so the numbers on this page may be too low.`,
  notSignedIn: 'Your session has ended. Please sign in again.',
  notAllowed:
    'You are signed in, but this account is not allowed to see this dashboard. Sign in with the address that owns it, or ask whoever set it up.',
  notConfigured:
    'This page has not been connected to its database yet. Whoever set it up needs to publish it again with its database settings (uv run tracker setup dashboard).',
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

/** Who owes the next message, as the filter and the correction form offer it. */
export const waitingOnLabels: Record<WaitingOn, string> = {
  me: 'You',
  them: 'Them',
  nobody: 'Nobody',
};

/** The same, as a chip next to other chips, where it has to make sense on its own. */
export const waitingOnBadges: Record<WaitingOn, string> = {
  me: 'Your turn',
  them: 'Waiting on them',
  nobody: 'Nobody waiting',
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
  mailbox_window_capped:
    'Your mailbox had more new mail than is read in one go. The newest was read; older mail in that folder from this stretch was skipped. Nothing to do: a skipped conversation is read in full as soon as somebody writes in it again.',
  tracker_error: 'Something went wrong in this step.',
};

export const runErrorFallback = 'Something went wrong in this step.';

/** What set a run going, as stored in `run_logs.trigger`. */
export const runTriggerLabels: Record<string, string> = {
  cloud: 'the daily schedule',
  github: 'the daily schedule',
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
  signedOut: {
    title: 'You are signed out of the demo',
    body: 'The demo has no accounts and no e-mail sign-in. One tap takes you back to the made-up data.',
    signIn: 'Sign back into the demo',
    signingIn: 'Signing in…',
    failed: 'That did not work. Reload the page to start the demo again.',
  },
} as const;
