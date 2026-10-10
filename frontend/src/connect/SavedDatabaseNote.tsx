import { Button } from '../components/Button';
import * as copy from '../copy/en';
import { readSupabaseSource } from '../lib/runtimeConfig';
import { forgetConnection } from '../lib/savedConnection';

interface SavedDatabaseNoteProps {
  /** Starts the page afresh once the database is forgotten. */
  restart?: () => void;
}

function startAfresh(): void {
  window.location.assign('/');
}

/**
 * On the sign-in page of the shared dashboard: which database this browser
 * opens, and a way to forget it so another personal link can be used. A page
 * whose database is fixed (`config.js`, the build) shows nothing.
 */
export function SavedDatabaseNote({ restart = startAfresh }: SavedDatabaseNoteProps) {
  const resolved = readSupabaseSource();
  if (resolved?.source !== 'saved-link') return null;
  return (
    <section className="mt-10 border-t border-line pt-4 text-sm text-ink-muted">
      <p className="break-words">{copy.connect.connectedTo(resolved.settings.url)}</p>
      <Button
        variant="secondary"
        className="mt-3"
        onClick={() => {
          forgetConnection();
          // The database client and everything loaded belong to the old
          // database, so the page starts again from nothing.
          restart();
        }}
      >
        {copy.connect.forget}
      </Button>
    </section>
  );
}
