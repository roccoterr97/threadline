import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import * as copy from '../../copy/en';
import { ButtonLink } from '../ButtonLink';
import { Button } from '../Button';

export interface NextAction {
  label: string;
  /** Where "Next" leads; or an action to run first, which then navigates. */
  to: string;
  onBefore?: () => void;
  disabled?: boolean;
}

interface WizardFrameProps {
  /** The small words above the title: the part's name. */
  eyebrow?: string;
  title: string;
  /** Fills the thread at the top: how far along the reader is. */
  progress?: { number: number; total: number } | null;
  back: string | null;
  next: NextAction | null;
  /** A quieter third way on, such as skipping an optional step. */
  aside?: NextAction | null;
  children: ReactNode;
}

/** One screen of the set-up: where the reader is in the margin, one thing to do, the way back and on. */
export function WizardFrame({ eyebrow, title, progress, back, next, aside, children }: WizardFrameProps) {
  const position = progress ?? null;
  const share = position === null ? 0 : position.number / position.total;
  return (
    <div className="site-container pt-6 pb-12 lg:pt-10">
      <div className="h-[var(--site-thread-width)] w-full bg-[var(--site-thread)]" aria-hidden="true">
        {position !== null && (
          <div
            className="progress-done h-full bg-[var(--site-thread-done)]"
            style={{ width: `${Math.round(share * 100)}%` }}
          />
        )}
      </div>

      <div className="mt-8 grid gap-6 lg:mt-14 lg:grid-cols-[minmax(12rem,1fr)_minmax(0,48rem)_minmax(0,1fr)] lg:gap-16">
        <div className="hidden lg:block">
          {position !== null && (
            <p className="label sticky top-10" aria-hidden="true">
              <span className="block font-display text-6xl font-semibold tracking-tight text-ink tabular-nums">
                {String(position.number).padStart(2, '0')}
                <span className="text-2xl text-ink-muted"> / {position.total}</span>
              </span>
              {eyebrow !== undefined && <span className="mt-3 block text-sm">{eyebrow}</span>}
            </p>
          )}
        </div>

        <div className="min-w-0">
          {position !== null && (
            <p className="label mb-4 lg:sr-only">
              {copy.wizard.stepOf(position.number, position.total)}
              {eyebrow !== undefined && <span> · {eyebrow}</span>}
            </p>
          )}
          <h1 className="text-4xl leading-tight tracking-tight text-ink sm:text-5xl">{title}</h1>
          <div className="mt-8 space-y-5 text-lg">{children}</div>

          <div className="mt-12 flex flex-wrap items-center gap-3 border-t border-line pt-6">
            {back !== null && (
              <ButtonLink to={back} variant="secondary" className="px-5 py-3">
                {copy.wizard.back}
              </ButtonLink>
            )}
            {next !== null && <NextButton action={next} />}
            {aside !== undefined && aside !== null && (
              <span className="ml-auto">
                <NextButton action={aside} quiet />
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function NextButton({ action, quiet = false }: { action: NextAction; quiet?: boolean }) {
  if (action.onBefore === undefined && action.disabled === undefined) {
    return (
      <ButtonLink to={action.to} variant={quiet ? 'quiet' : 'primary'} className={quiet ? '' : 'px-5 py-3'}>
        {action.label}
      </ButtonLink>
    );
  }
  return <NextWithAction action={action} quiet={quiet} />;
}

function NextWithAction({ action, quiet }: { action: NextAction; quiet: boolean }) {
  const navigate = useNavigate();
  return (
    <Button
      variant={quiet ? 'quiet' : 'primary'}
      className={quiet ? '' : 'px-5 py-3'}
      disabled={action.disabled}
      onClick={() => {
        action.onBefore?.();
        void navigate(action.to);
      }}
    >
      {action.label}
    </Button>
  );
}
