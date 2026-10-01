import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { markPersonAsNoise } from '../api/overrides';
import { peopleQueryKey } from '../api/people';
import { personQueryKey } from '../api/person';
import * as copy from '../copy/en';
import { Button } from './Button';
import { ConfirmPanel } from './ConfirmPanel';

interface MarkNoiseActionProps {
  personId: string;
}

/**
 * "Not relevant": hides a person from the list, but only after an
 * "are you sure?" step, because it also stops the assistant reading them.
 */
export function MarkNoiseAction({ personId }: MarkNoiseActionProps) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const markNoise = useMutation({
    mutationFn: () => markPersonAsNoise(personId),
    onSuccess: async () => {
      setConfirming(false);
      await queryClient.invalidateQueries({ queryKey: peopleQueryKey });
      await queryClient.invalidateQueries({ queryKey: personQueryKey(personId) });
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
