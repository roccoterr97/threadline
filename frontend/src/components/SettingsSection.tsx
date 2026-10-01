import { useId, type ReactNode } from 'react';

interface SettingsSectionProps {
  title: string;
  /** One sentence under the title, if the section needs explaining. */
  intro?: string;
  children: ReactNode;
}

/** A titled block on the settings page, named after its heading for screen readers. */
export function SettingsSection({ title, intro, children }: SettingsSectionProps) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <div>
        <h3 id={headingId} className="text-lg font-semibold text-ink">
          {title}
        </h3>
        {intro !== undefined && <p className="mt-1 text-sm text-ink-muted">{intro}</p>}
      </div>
      {children}
    </section>
  );
}
