import * as copy from '../copy/en';
import type { Vocabulary } from '../domain/vocabulary';
import { usePersonOverride } from '../hooks/usePersonOverride';
import { NotSignedInError } from '../lib/errors';
import { Icon } from './Icon';
import { LoadingState } from './LoadingState';
import { OverrideForm } from './OverrideForm';
import { SaveFeedback, type SaveOutcome } from './SaveFeedback';

interface MutationOutcome {
  isPending: boolean;
  isError: boolean;
  isSuccess: boolean;
  error: Error | null;
  /** When the action was started; 0 if it never was. */
  submittedAt: number;
}

/** A save refused for an expired sign-in needs a different next step from any other failure. */
function saveFailureText(error: Error | null): string {
  return error instanceof NotSignedInError ? copy.override.failedSignedOut : copy.override.failed;
}

function saveFeedback(save: MutationOutcome): SaveOutcome | null {
  if (save.isError) return { tone: 'error', text: saveFailureText(save.error) };
  if (save.isSuccess) return { tone: 'success', text: copy.override.saved };
  return null;
}

function clearFeedback(clear: MutationOutcome): SaveOutcome | null {
  if (clear.isError) return { tone: 'error', text: copy.override.clearFailed };
  if (clear.isSuccess) return { tone: 'success', text: copy.override.cleared };
  return null;
}

/**
 * One sentence about the most recent thing done to the correction.
 *
 * Only the latest action counts, and nothing is shown while it is still
 * waiting for the database: an older "saved" left on screen during a new
 * attempt, or after a later clear failed, would say something untrue.
 */
function feedbackFor(save: MutationOutcome, clear: MutationOutcome): SaveOutcome | null {
  const saveIsLatest = save.submittedAt >= clear.submittedAt;
  const latest = saveIsLatest ? save : clear;
  if (latest.isPending) return null;
  return saveIsLatest ? saveFeedback(save) : clearFeedback(clear);
}

interface PersonCorrectionProps {
  personId: string;
  vocabulary: Vocabulary;
}

/**
 * The "Correct this" form, folded away until the owner opens it: most visits are
 * for reading the history, not for fixing the assistant.
 *
 * A native disclosure keeps it operable by keyboard and announced as
 * expandable. The save outcome sits outside the fold on purpose, so it stays
 * visible — and can still take focus and be announced — even if the form was
 * folded again while the save was on its way.
 */
export function PersonCorrection({ personId, vocabulary }: PersonCorrectionProps) {
  const { override, save, clear } = usePersonOverride(personId);
  const feedback = feedbackFor(save, clear);

  return (
    <section className="rounded-token-lg border border-line bg-surface shadow-card">
      <details className="group">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-token-lg p-4 hover:bg-neutral-soft [&::-webkit-details-marker]:hidden">
          <span>
            <span className="block text-lg font-semibold text-ink">{copy.override.title}</span>
            <span className="block text-sm text-ink-muted">{copy.person.correctHint}</span>
          </span>
          <Icon
            name="chevronDown"
            className="h-5 w-5 text-ink-muted transition-transform group-open:rotate-180"
          />
        </summary>
        <div className="border-t border-line p-4">
          {override.isPending ? (
            <LoadingState label={copy.states.loading} />
          ) : (
            <OverrideForm
              key={override.data?.updated_at ?? 'none'}
              override={override.data ?? null}
              vocabulary={vocabulary}
              onSave={(values) => {
                save.mutate(values);
              }}
              onClear={() => {
                clear.mutate();
              }}
              isSaving={save.isPending}
              isClearing={clear.isPending}
            />
          )}
        </div>
      </details>
      {/* Outside the form as well: the form is rebuilt after every save, and
          the outcome must stay put and keep the focus it was given. */}
      {feedback !== null && (
        <div className="px-4 pb-4">
          <SaveFeedback outcome={feedback} />
        </div>
      )}
    </section>
  );
}
