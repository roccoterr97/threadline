import * as copy from '../copy/en';
import type { TimelineEntry } from '../domain/timeline';
import { formatDateTime } from '../lib/format';
import { Badge } from './Badge';
import { ChannelIcon } from './ChannelIcon';
import { MessageBody } from './MessageBody';

interface TimelineProps {
  entries: readonly TimelineEntry[];
}

/** Every message with this person, across every channel, newest first. */
export function Timeline({ entries }: TimelineProps) {
  return (
    <ol className="flex list-none flex-col gap-3 p-0">
      {entries.map((entry) => (
        <li
          key={entry.id}
          className="rounded-token-lg border border-line bg-surface p-4 shadow-card"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-muted">
              <ChannelIcon channel={entry.channel} />
              {copy.channelLabels[entry.channel]}
            </span>
            <Badge
              tone={entry.direction === 'inbound' ? 'calm' : 'neutral'}
              label={copy.directionLabels[entry.direction]}
            />
            <time dateTime={entry.sentAt} className="text-sm text-ink-muted">
              {formatDateTime(entry.sentAt)}
            </time>
          </div>

          {entry.channel !== 'linkedin' && (
            <p className="mt-2 font-medium break-words text-ink">{entry.subject ?? copy.person.noSubject}</p>
          )}

          {entry.body === null ? (
            <p className="mt-2 italic text-ink-muted">{copy.person.noBody}</p>
          ) : (
            <MessageBody body={entry.body} />
          )}
        </li>
      ))}
    </ol>
  );
}
