import * as copy from '../copy/en';
import { refreshIsBusy, type RefreshStatus } from '../domain/refresh';
import { Button } from './Button';
import { Icon } from './Icon';

interface RefreshButtonProps {
  status: RefreshStatus;
  /** The id of the status line that explains what the button is doing. */
  statusId: string;
  onStart: () => void;
}

/**
 * Starts one extra quick update. On a phone the visible label stays "Refresh"
 * to fit next to "Sign out" (the spinning icon and the status line show
 * progress); the spoken name is the full label, which contains that word, so
 * voice control still finds it.
 */
export function RefreshButton({ status, statusId, onStart }: RefreshButtonProps) {
  const busy = refreshIsBusy(status);
  return (
    <Button
      variant="secondary"
      className="shrink-0 px-3"
      disabled={busy}
      aria-label={busy ? copy.refresh.busy : copy.refresh.button}
      aria-describedby={statusId}
      onClick={onStart}
    >
      <Icon name="refresh" className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} />
      <span className="sm:hidden">{copy.refresh.buttonShort}</span>
      <span className="hidden sm:inline">{busy ? copy.refresh.busy : copy.refresh.button}</span>
    </Button>
  );
}
