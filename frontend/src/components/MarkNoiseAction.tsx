import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { markPersonAsNoise } from '../api/overrides';
import { peopleQueryKey } from '../api/people';
import { personQueryKey } from '../api/person';
import * as copy from '../copy/en';
import { hiddenPersonState } from '../lib/hiddenPerson';
import { Button } from './Button';
import { ConfirmPanel } from './ConfirmPanel';

interface MarkNoiseActionProps {
  personId: string;
  personName: string;
}

/**
 * "Not relevant": hides a person from the list, but only after an
 * "are you sure?" step, because it also stops the assistant reading them.
 * Once hidden, the page goes back to the list, which says so and offers to undo.
 */
export function MarkNoiseAction({ personId, personName }: MarkNoiseActionProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);

  const markNoise = useMutation({
    mutationFn: () => markPersonAsNoise(personId),
    onSuccess: async () => {
      // Leave first: refetching this person now would flash "not found".
      void navigate('/', { state: hiddenPersonState({ id: personId, name: personName }) });
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
