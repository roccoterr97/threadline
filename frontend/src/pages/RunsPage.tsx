import { useQuery } from '@tanstack/react-query';
import { fetchRecentRuns, runsQueryKey } from '../api/runs';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { RunRow } from '../components/RunRow';
import * as copy from '../copy/en';
import { usePageTitle } from '../hooks/usePageTitle';

/** The history of automatic updates, with plain-English problems. */
export function RunsPage() {
  usePageTitle(copy.runs.title);
  const runs = useQuery({ queryKey: runsQueryKey, queryFn: fetchRecentRuns });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">{copy.runs.title}</h1>
        <p className="mt-1 text-ink-muted">{copy.runs.subtitle}</p>
      </div>

      {runs.isPending && <LoadingState label={copy.states.loadingRuns} />}

      {runs.isError && (
        <ErrorState
          error={runs.error}
          onRetry={() => {
            void runs.refetch();
          }}
        />
      )}

      {runs.isSuccess && runs.data.length === 0 && (
        <EmptyState title={copy.runs.empty.title} body={copy.runs.empty.body} />
      )}

      {runs.isSuccess && runs.data.length > 0 && (
        <ul className="flex list-none flex-col gap-3 p-0">
          {runs.data.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </ul>
      )}
    </div>
  );
}
