import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { markPersonAsRelevant } from '../api/overrides';
import { peopleQueryKey } from '../api/people';
import * as copy from '../copy/en';
import { readHiddenPerson, type HiddenPerson } from '../lib/hiddenPerson';
import { Button } from './Button';

const text = copy.person.hidden;

/**
 * Says who was just hidden from the list, with a way to undo it.
 *
 * The person page hands the name over in the location state. It is read once
 * and then cleared from the browser history, so going back or reloading does
 * not bring the message back. The note takes focus when it appears, so a
 * screen reader hears it and the keyboard is one Tab away from "Undo".
 */
export function HiddenPersonNotice() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [person] = useState<HiddenPerson | null>(() => readHiddenPerson(location.state));
  const note = useRef<HTMLDivElement>(null);

  const undo = useMutation({
    mutationFn: (id: string) => markPersonAsRelevant(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: peopleQueryKey }),
  });

  const hasState = readHiddenPerson(location.state) !== null;
  useEffect(() => {
    if (!hasState) return;
    void navigate(`${location.pathname}${location.search}`, { replace: true, state: null });
  }, [hasState, location.pathname, location.search, navigate]);

  useEffect(() => {
    note.current?.focus();
  }, []);

  if (person === null) return null;

  return (
    <div
      ref={note}
      tabIndex={-1}
      role={undo.isError ? 'alert' : 'status'}
      className="flex flex-wrap items-center gap-3 rounded-token-lg border border-positive bg-positive-soft p-4 font-medium text-positive"
    >
      <p className="m-0 flex-1 basis-60">{message(person.name, undo)}</p>
      {!undo.isSuccess && (
        <Button
          aria-label={text.undoLabel(person.name)}
          disabled={undo.isPending}
          onClick={() => {
            undo.mutate(person.id);
          }}
        >
          {undo.isPending ? text.undoing : text.undo}
        </Button>
      )}
    </div>
  );
}

function message(name: string, undo: { isSuccess: boolean; isError: boolean }): string {
  if (undo.isSuccess) return text.restored(name);
  if (undo.isError) return text.undoFailed(name);
  return text.notice(name);
}
