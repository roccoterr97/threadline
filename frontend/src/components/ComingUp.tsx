import { useId } from 'react';
import * as copy from '../copy/en';
import { formatClockTime, formatWeekday } from '../lib/format';
import type { UpcomingMeetingRow } from '../types/database';
import { PersonLink } from './PersonLink';

interface ComingUpProps {
  /** This week's meetings, soonest first, as the query returns them. */
  meetings: readonly UpcomingMeetingRow[];
}

const CARD = 'flex h-full min-h-11 flex-col rounded-token-lg border bg-surface p-3 text-sm shadow-card';

/** What one meeting card says: when, who, where they work, and the title. */
function MeetingDetails({ meeting }: { meeting: UpcomingMeetingRow }) {
  const organisation = meeting.people?.organisations?.name ?? null;
  return (
    <>
      <time dateTime={meeting.meeting_at} className="font-semibold text-ink">
        {formatWeekday(meeting.meeting_at)} · {formatClockTime(meeting.meeting_at)}
      </time>
      <span className="mt-1 font-medium text-ink">
        {meeting.people?.full_name ?? copy.home.comingUp.unknownPerson}
      </span>
      {organisation !== null && <span className="text-ink-muted">{organisation}</span>}
      <span className="mt-1 break-words text-ink-muted">
        {meeting.subject ?? copy.home.comingUp.untitled}
      </span>
    </>
  );
}

/** One meeting; it opens the person page when the meeting is linked to someone. */
function MeetingItem({ meeting }: { meeting: UpcomingMeetingRow }) {
  if (meeting.person_id === null) {
    return (
      <div className={`${CARD} border-line`}>
        <MeetingDetails meeting={meeting} />
      </div>
    );
  }
  return (
    <PersonLink
      personId={meeting.person_id}
      className={`${CARD} border-line transition-colors hover:border-accent`}
    >
      <MeetingDetails meeting={meeting} />
    </PersonLink>
  );
}

/**
 * The strip of meetings in the coming week, shown under the run banner.
 *
 * It hides itself when there is nothing coming up. On a phone the cards scroll
 * sideways inside the strip, never the page, and a long title wraps inside
 * its card; on wider screens the cards wrap, and a card widens for a long
 * title before the title wraps.
 */
export function ComingUp({ meetings }: ComingUpProps) {
  const headingId = useId();
  if (meetings.length === 0) return null;

  return (
    <section aria-labelledby={headingId} className="min-w-0">
      <h2 id={headingId} className="text-base font-semibold text-ink">
        {copy.home.comingUp.title}
      </h2>
      <ol className="mt-2 flex list-none gap-3 overflow-x-auto p-0 pb-1 sm:flex-wrap sm:overflow-visible">
        {meetings.map((meeting) => (
          <li key={meeting.id} className="w-60 shrink-0 sm:w-auto sm:min-w-60 sm:max-w-sm">
            <MeetingItem meeting={meeting} />
          </li>
        ))}
      </ol>
    </section>
  );
}
