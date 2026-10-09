import * as copy from '../copy/en';
import { NotAllowedError, NotConfiguredError, NotSignedInError } from '../lib/errors';
import { Button } from './Button';

interface ErrorStateProps {
  /** Whatever the data layer threw. Never shown to the user directly. */
  error: unknown;
  onRetry: () => void;
}

/** Turns any failure into one sentence the owner can act on. */
function explain(error: unknown): string {
  if (error instanceof NotConfiguredError) return copy.states.notConfigured;
  if (error instanceof NotSignedInError) return copy.states.notSignedIn;
  if (error instanceof NotAllowedError) return copy.states.notAllowed;
  return copy.states.errorBody;
}

/** Shown when a screen could not load. Always offers a way to try again. */
export function ErrorState({ error, onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="rounded-token-lg border border-danger bg-danger-soft p-6 text-center"
    >
      <h2 className="text-lg font-semibold text-danger">{copy.states.errorTitle}</h2>
      <p className="mx-auto mt-2 max-w-prose text-ink">{explain(error)}</p>
      <div className="mt-4 flex justify-center">
        <Button variant="secondary" onClick={onRetry}>
          {copy.states.retry}
        </Button>
      </div>
    </div>
  );
}
