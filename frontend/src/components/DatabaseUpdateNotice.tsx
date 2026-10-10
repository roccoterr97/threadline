import { useQuery } from '@tanstack/react-query';
import { databaseVersionQueryKey, isDatabaseOlder } from '../api/databaseVersion';
import * as copy from '../copy/en';

/**
 * A strip under the header when the owner's database is older than this
 * dashboard, saying how to update it. Asked once per visit; when the question
 * itself fails, nothing is shown, since the pages already say so.
 */
export function DatabaseUpdateNotice() {
  const older = useQuery({
    queryKey: databaseVersionQueryKey,
    queryFn: isDatabaseOlder,
    staleTime: Infinity,
    retry: false,
  });
  if (older.data !== true) return null;
  return (
    <div className="mx-auto max-w-6xl px-4 pt-4">
      <p role="status" className="rounded-token-lg border border-warn bg-warn-soft p-4 text-warn">
        {copy.databaseUpdate.notice}
      </p>
    </div>
  );
}
