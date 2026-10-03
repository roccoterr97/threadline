import { useEffect, useRef } from 'react';

/**
 * How the last save or clear ended, in one sentence. Only a success can leave
 * the keyboard alone: a failure always takes the focus, so it is never missed.
 */
export type SaveOutcome =
  | {
      tone: 'success';
      text: string;
      /**
       * Leave the keyboard where it is: set when the owner is working through
       * a list (moving a row) and taking focus would throw them out of it. The
       * sentence is still announced.
       */
      keepFocus?: boolean;
    }
  | { tone: 'error'; text: string };

interface SaveFeedbackProps {
  outcome: SaveOutcome;
}

const TONE_CLASS_NAMES: Record<SaveOutcome['tone'], string> = {
  success: 'border-positive bg-positive-soft text-positive',
  error: 'border-danger bg-danger-soft text-danger',
};

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

function scrollBehaviour(): ScrollBehavior {
  return window.matchMedia(REDUCED_MOTION_QUERY).matches ? 'auto' : 'smooth';
}

/**
 * The result of a save, shown so it cannot be missed.
 *
 * The page shows a correction the instant the button is pressed, before the
 * database has answered, so the values on screen say nothing about whether the
 * save worked. On a phone the outcome used to be one small line that was easy
 * to overlook, and a failed save looked exactly like a successful one. The
 * banner is brought on screen and focused whenever its sentence changes, and a
 * failure is announced at once rather than when the screen reader gets to it.
 */
export function SaveFeedback({ outcome }: SaveFeedbackProps) {
  const banner = useRef<HTMLParagraphElement>(null);

  const keepFocus = outcome.tone === 'success' && outcome.keepFocus === true;
  useEffect(() => {
    const element = banner.current;
    if (element === null || keepFocus) return;
    element.focus({ preventScroll: true });
    element.scrollIntoView({ behavior: scrollBehaviour(), block: 'nearest' });
  }, [outcome.text, keepFocus]);

  return (
    <p
      ref={banner}
      tabIndex={-1}
      role={outcome.tone === 'error' ? 'alert' : 'status'}
      className={`rounded-token-lg border p-4 font-medium ${TONE_CLASS_NAMES[outcome.tone]}`}
    >
      {outcome.text}
    </p>
  );
}
