import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { clearOverride, fetchOverride, overrideQueryKey, saveOverride } from '../api/overrides';
import { peopleQueryKey } from '../api/people';
import { personQueryKey } from '../api/person';
import { applyOverrideToPerson, type OverrideValues } from '../domain/overrides';
import type { PeopleOverviewRow, PersonOverrideRow } from '../types/database';

/** What is put aside before an optimistic change, so it can be put back. */
interface Snapshot {
  person: PeopleOverviewRow | null | undefined;
  override: PersonOverrideRow | null | undefined;
}

/**
 * Loading and changing one person's hand-made correction.
 *
 * Saving is optimistic: the screen shows the new values immediately and puts
 * the old ones back if the database refuses. Clearing cannot be guessed at —
 * only the database knows the assistant's own values — so it drops the
 * correction from the screen and then refetches the truth.
 */
export function usePersonOverride(personId: string) {
  const queryClient = useQueryClient();

  const override = useQuery({
    queryKey: overrideQueryKey(personId),
    queryFn: () => fetchOverride(personId),
  });

  async function snapshot(): Promise<Snapshot> {
    await queryClient.cancelQueries({ queryKey: personQueryKey(personId) });
    return {
      person: queryClient.getQueryData<PeopleOverviewRow | null>(personQueryKey(personId)),
      override: queryClient.getQueryData<PersonOverrideRow | null>(overrideQueryKey(personId)),
    };
  }

  function rollback(previous: Snapshot | undefined): void {
    if (previous === undefined) return;
    queryClient.setQueryData(personQueryKey(personId), previous.person);
    queryClient.setQueryData(overrideQueryKey(personId), previous.override);
  }

  async function refresh(): Promise<void> {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: personQueryKey(personId) }),
      queryClient.invalidateQueries({ queryKey: overrideQueryKey(personId) }),
      queryClient.invalidateQueries({ queryKey: peopleQueryKey }),
    ]);
  }

  const save = useMutation<void, Error, OverrideValues, Snapshot>({
    mutationFn: (values) => saveOverride({ person_id: personId, ...values }),
    onMutate: async (values) => {
      const previous = await snapshot();
      if (previous.person !== undefined && previous.person !== null) {
        queryClient.setQueryData(
          personQueryKey(personId),
          applyOverrideToPerson(previous.person, values),
        );
      }
      return previous;
    },
    onError: (_error, _values, previous) => {
      rollback(previous);
    },
    onSuccess: refresh,
  });

  const clear = useMutation<void, Error, void, Snapshot>({
    mutationFn: () => clearOverride(personId),
    onMutate: async () => {
      const previous = await snapshot();
      queryClient.setQueryData(overrideQueryKey(personId), null);
      return previous;
    },
    onError: (_error, _values, previous) => {
      rollback(previous);
    },
    onSuccess: refresh,
  });

  return { override, save, clear };
}
