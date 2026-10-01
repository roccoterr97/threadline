import * as copy from '../copy/en';
import type { Clock } from '../lib/clock';
import { formatDate, formatRelative } from '../lib/format';
import type { PeopleOverviewRow } from '../types/database';

interface PersonSummaryProps {
  person: PeopleOverviewRow;
  clock: Clock;
}

/**
 * What the assistant made of this person and what is next, in one compact
 * card that fits the narrow side column on a laptop.
 */
export function PersonSummary({ person, clock }: PersonSummaryProps) {
  return (
    <section className="flex flex-col gap-4 rounded-token-lg border border-line bg-surface p-4 shadow-card">
      <div>
        <h2 className="text-base font-semibold text-ink">{copy.person.summaryTitle}</h2>
        <p className="mt-1 whitespace-pre-line text-ink">
          {person.summary ?? <span className="italic text-ink-muted">{copy.person.noSummary}</span>}
        </p>
      </div>

      <div className="border-t border-line pt-4">
        <h2 className="text-base font-semibold text-ink">{copy.person.detailsTitle}</h2>
        <dl className="mt-2 grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <dt className="text-sm text-ink-muted">{copy.home.columns.nextAction}</dt>
            <dd className="text-ink">{person.next_action ?? copy.values.none}</dd>
          </div>
          <div>
            <dt className="text-sm text-ink-muted">{copy.home.columns.due}</dt>
            <dd className="text-ink">{formatDate(person.due_date)}</dd>
          </div>
          <div>
            <dt className="text-sm text-ink-muted">{copy.home.columns.lastContact}</dt>
            <dd className="text-ink">{formatRelative(person.last_contact_at, clock)}</dd>
          </div>
          <div>
            <dt className="text-sm text-ink-muted">{copy.person.messageCountLabel}</dt>
            <dd className="text-ink">{person.message_count}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
