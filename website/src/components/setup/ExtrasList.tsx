import { Link } from 'react-router-dom';
import { SETUP_GUIDE } from '../../setup/guide';

/** The optional parts of the set-up, one row each, each row one link. */
export function ExtrasList() {
  return (
    <ul className="divide-y divide-line border-y border-line">
      {SETUP_GUIDE.extras.map((part) => (
        <li key={part.id}>
          <Link
            to={`/setup/extra/${part.id}`}
            className="group flex items-start justify-between gap-6 py-4 hover:text-accent"
          >
            <span>
              <span className="block font-display text-lg font-semibold text-ink group-hover:text-accent">
                {part.title}
              </span>
              <span className="mt-0.5 block text-sm text-ink-muted">{part.summary}</span>
            </span>
            <span
              aria-hidden="true"
              className="mt-1 text-accent transition-transform duration-200 group-hover:translate-x-1"
            >
              →
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
