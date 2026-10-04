/** Every small line icon the dashboard draws. */
export type IconName =
  | 'people'
  | 'organisations'
  | 'review'
  | 'runs'
  | 'settings'
  | 'signOut'
  | 'chevronDown'
  | 'refresh';

/** The strokes of each icon, on a 24x24 grid. */
const ICON_PATHS: Record<IconName, readonly string[]> = {
  people: [
    'M16 20v-1.5a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4V20',
    'M12.5 7a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0Z',
    'M22 20v-1.5a4 4 0 0 0-3-3.87',
    'M16 3.13a4 4 0 0 1 0 7.75',
  ],
  organisations: [
    'M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z',
    'M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2',
    'M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2',
    'M10 6h4',
    'M10 10h4',
    'M10 14h4',
    'M10 18h4',
  ],
  review: [
    'M22 12h-6l-2 3h-4l-2-3H2',
    'M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z',
  ],
  runs: ['M3 12a9 9 0 1 0 2.64-6.36L3 8.3', 'M3 3v5.3h5.3', 'M12 7v5l3.5 2'],
  settings: [
    'M4 6h9',
    'M17 6h3',
    'M15 4v4',
    'M4 12h3',
    'M11 12h9',
    'M9 10v4',
    'M4 18h11',
    'M19 18h1',
    'M17 16v4',
  ],
  signOut: ['M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4', 'm16 17 5-5-5-5', 'M21 12H9'],
  chevronDown: ['m6 9 6 6 6-6'],
  refresh: ['M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8', 'M21 3v5h-5'],
};

interface IconProps {
  name: IconName;
  /** Extra classes, e.g. a size or a rotation. Defaults to a 20px icon. */
  className?: string;
}

/**
 * A small line drawing in the current text colour.
 *
 * Purely decorative: every place that uses one also prints its meaning in
 * words, so the icon is hidden from screen readers.
 */
export function Icon({ name, className = 'h-5 w-5' }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className}`}
    >
      {ICON_PATHS[name].map((path) => (
        <path key={path} d={path} />
      ))}
    </svg>
  );
}
