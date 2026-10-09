import * as copy from '../copy/en';
import { useActiveSection } from '../lib/useActiveSection';

interface PageContentsProps {
  entries: readonly { id: string; label: string }[];
}

/**
 * The list of the page's sections, with the one being read marked. Shown on
 * a wide screen only, where it stays in view; a phone scrolls the page.
 */
export function PageContents({ entries }: PageContentsProps) {
  const active = useActiveSection(entries.map((entry) => entry.id));
  return (
    <nav aria-label={copy.onThisPage} className="hidden lg:block">
      <ol className="space-y-2 border-l border-line">
        {entries.map((entry) => {
          const current = entry.id === active;
          return (
            <li key={entry.id}>
              <a
                href={`#${entry.id}`}
                aria-current={current ? 'location' : undefined}
                className={`-ml-px block border-l-2 py-0.5 pl-4 text-sm transition-colors hover:text-accent ${
                  current ? 'border-accent text-ink' : 'border-transparent text-ink-muted'
                }`}
              >
                {entry.label}
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
