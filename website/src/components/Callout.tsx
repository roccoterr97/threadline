import type { ReactNode } from 'react';
import * as copy from '../copy/en';

export type CalloutTone = 'check' | 'ifNot' | 'note' | 'warning';

const STYLES: Record<CalloutTone, { box: string; label: string; mark: string }> = {
  check: { box: 'border-positive/30 bg-positive-soft', label: 'text-positive', mark: '✓' },
  ifNot: { box: 'border-warn/30 bg-warn-soft', label: 'text-warn', mark: '!' },
  note: { box: 'border-line bg-neutral-soft', label: 'text-neutral', mark: 'i' },
  warning: { box: 'border-danger/30 bg-danger-soft', label: 'text-danger', mark: '!' },
};

const LABELS: Record<CalloutTone, string> = {
  check: copy.callout.check,
  ifNot: copy.callout.ifNot,
  note: copy.callout.note,
  warning: copy.callout.warning,
};

/** A boxed aside: what to check, what to do if not, or something good to know. */
export function Callout({ tone, children }: { tone: CalloutTone; children: ReactNode }) {
  const style = STYLES[tone];
  return (
    <aside className={`rounded-token-md border px-4 py-3 ${style.box}`}>
      <p className={`mb-1 text-sm font-semibold ${style.label}`}>
        <span aria-hidden="true" className="mr-2 inline-block w-4 text-center">
          {style.mark}
        </span>
        {LABELS[tone]}
      </p>
      <div className="text-ink">{children}</div>
    </aside>
  );
}
