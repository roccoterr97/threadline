import { Button } from '../components/Button';
import * as copy from '../copy/en';
import { usePageTitle } from '../hooks/usePageTitle';
import type { SupabaseSettings } from '../lib/runtimeConfig';

interface SwitchDatabasePageProps {
  current: SupabaseSettings;
  incoming: SupabaseSettings;
  onSwitch: () => void;
  onKeep: () => void;
}

/**
 * Asked when a personal link names a different database than the one this
 * browser opens, so a link from somebody else never quietly replaces it.
 */
export function SwitchDatabasePage({ current, incoming, onSwitch, onKeep }: SwitchDatabasePageProps) {
  usePageTitle(copy.connect.switchTitle);
  return (
    <main className="mx-auto max-w-prose px-4 py-10">
      <h1 className="text-2xl font-semibold text-ink">{copy.connect.switchTitle}</h1>
      <p className="mt-2 break-words text-ink">
        {copy.connect.switchBody(incoming.url, current.url)}
      </p>
      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <Button variant="primary" onClick={onSwitch}>
          {copy.connect.switchConfirm}
        </Button>
        <Button variant="secondary" onClick={onKeep}>
          {copy.connect.switchKeep}
        </Button>
      </div>
    </main>
  );
}
