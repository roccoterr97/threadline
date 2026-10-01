import type { Category, ContactStatus, StatusLabel } from '../types/database';

/** The on-screen name of every status. */
export type StatusLabels = Record<ContactStatus, string>;

/**
 * The owner's own words for the dashboard: the categories they track and the
 * names they gave the six statuses. Read from the database, never hard-coded.
 */
export interface Vocabulary {
  categories: readonly Category[];
  statusLabels: StatusLabels;
}

/**
 * The owner's status names, with `fallback` for any status the database has
 * no row for (or while there are no rows at all).
 */
export function resolveStatusLabels(
  rows: readonly StatusLabel[] | undefined,
  fallback: StatusLabels,
): StatusLabels {
  const labels = { ...fallback };
  for (const row of rows ?? []) labels[row.status] = row.label;
  return labels;
}
