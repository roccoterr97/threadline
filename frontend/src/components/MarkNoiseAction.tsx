import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { markPersonAsNoise } from '../api/overrides';
import { peopleQueryKey } from '../api/people';
import { personQueryKey } from '../api/person';
import * as copy from '../copy/en';
import { hiddenPersonState } from '../lib/hiddenPerson';
import { personOrigin } from '../lib/personOrigin';
import type { PeopleOverviewRow } from '../types/database';
import { Button } from './Button';
import { ConfirmPanel } from './ConfirmPanel';

interface MarkNoiseActionProps {
  personId: string;
  personName: string;
}

/**
 * "Not relevant": hides a person from the list, but only after an
 * "are you sure?" step, because it also stops the assistant reading them.
 * Once hidden, the page goes back to the list the person was opened from (the
 * People page or an organisation's page) as the owner left it, without the
 * person, and that list says so and offers to undo.
 */
export function MarkNoiseAction({ personId, personName }: MarkNoiseActionProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const origin = personOrigin(useLocation().state);
  const [confirming, setConfirming] = useState(false);

  const markNoise = useMutation({
    mutationFn: () => markPersonAsNoise(personId),
    onSuccess: async () => {
      // Off the kept list now: the list page would otherwise show them until its refetch ends.
      await queryClient.cancelQueries({ queryKey: peopleQueryKey });
      queryClient.setQueryData<PeopleOverviewRow[]>(peopleQueryKey, (people) =>
        people?.filter((person) => person.person_id !== personId),
      );
      // Leave first: refetching this person now would flash "not found".
      void navigate(origin.address, {
        state: { ...origin.state, ...hiddenPersonState({ id: personId, name: personName }) },
      });
      queryClient.removeQueries({ queryKey: personQueryKey(personId) });
      await queryClient.invalidateQueries({ queryKey: peopleQueryKey });
    },
  });

  if (!confirming) {
    return (
      <div>
        <Button
          variant="danger"
          onClick={() => {
            setConfirming(true);
          }}
        >
          {copy.person.markNoise.button}
        </Button>
      </div>
    );
  }

  return (
    <ConfirmPanel
      title={copy.person.markNoise.confirmTitle}
      body={copy.person.markNoise.confirmBody}
      confirmLabel={copy.person.markNoise.confirm}
      cancelLabel={copy.person.markNoise.cancel}
      isBusy={markNoise.isPending}
      errorText={markNoise.isError ? copy.person.markNoise.failed : null}
      onConfirm={() => {
        markNoise.mutate();
      }}
      onCancel={() => {
        setConfirming(false);
      }}
    />
  );
}
