import { Link } from 'react-router-dom';
import * as copy from '../copy/en';
import type { RefreshStatus as Status } from '../domain/refresh';

interface RefreshStatusProps {
  id: string;
  status: Status;
}

type Tone = 'quiet' | 'warn';

interface Message {
  text: string;
  tone: Tone;
  linksToRuns: boolean;
}

function messageFor(status: Status): Message | null {
  switch (status.kind) {
    case 'idle':
      return null;
    case 'sending':
      return { text: copy.refresh.sending, tone: 'quiet', linksToRuns: false };
    case 'waiting':
      return { text: copy.refresh.waiting, tone: 'quiet', linksToRuns: false };
    case 'finished':
      return {
        text: copy.refresh.finished[status.runStatus],
        tone: status.runStatus === 'success' ? 'quiet' : 'warn',
        linksToRuns: status.runStatus !== 'success',
      };
    case 'timed_out':
      return { text: copy.refresh.timedOut, tone: 'warn', linksToRuns: true };
    case 'refused':
      return {
        text: copy.refresh.refusals[status.code](status.target, status.retryAfterMinutes),
        tone: 'warn',
        linksToRuns: false,
      };
  }
}

const TONE_CLASSES: Record<Tone, string> = {
  quiet: 'text-ink-muted',
  warn: 'text-warn',
};

/**
 * The one line under the header that says what "Refresh now" is doing. The
 * region is always in the page, so screen readers announce each change.
 */
export function RefreshStatus({ id, status }: RefreshStatusProps) {
  const message = messageFor(status);
  return (
    <div id={id} role="status" className="mx-auto max-w-6xl px-4">
      {message !== null && (
        <p className={`pb-3 text-sm ${TONE_CLASSES[message.tone]}`}>
          {message.text}
          {message.linksToRuns && (
            <>
              {' '}
              <Link to="/runs" className="font-medium text-accent underline underline-offset-2">
                {copy.refresh.seeRuns}
              </Link>
            </>
          )}
        </p>
      )}
    </div>
  );
}
