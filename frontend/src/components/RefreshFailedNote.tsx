import * as copy from '../copy/en';
import { InfoNote } from './InfoNote';

interface RefreshFailedNoteProps {
  /** True when what is on screen is older than intended because an update failed. */
  show: boolean;
}

/**
 * Says an update did not work while the earlier data stays on screen. It is
 * read out politely and never takes the place of the page.
 */
export function RefreshFailedNote({ show }: RefreshFailedNoteProps) {
  if (!show) return null;
  return (
    <div role="status">
      <InfoNote>{copy.states.refreshFailed}</InfoNote>
    </div>
  );
}
