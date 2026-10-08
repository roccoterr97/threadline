import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { upcomingMeetingsQueryKey } from '../api/meetings';
import { markPersonAsRelevant } from '../api/overrides';
import { peopleQueryKey } from '../api/people';
import * as copy from '../copy/en';
import { readHiddenPerson, withoutHiddenPerson, type HiddenPerson } from '../lib/hiddenPerson';
import { Button } from './Button';
import { SaveFeedback } from './SaveFeedback';

const text = copy.person.hidden;

/**
 * Says who was just hidden from the list, with a way to undo it.
 *
 * The person page hands the name over in the location state. It is read once
 * and then cleared from the browser history (anything else the page was opened
 * with stays), so going back or reloading does not bring the message back. The note takes focus when it appears, so a
 * screen reader hears it and the keyboard is one Tab away from "Undo", and
 * takes it back once the undo has worked. An undo that fails says so the way
 * every failed save does: its message takes the focus and comes on screen,
 * and "Undo" stays for another try.
 */
export function HiddenPersonNotice() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [person] = useState<HiddenPerson | null>(() => readHiddenPerson(location.state));
  const note = useRef<HTMLDivElement>(null);

  const undo = useMutation({
    mutationFn: (id: string) => markPersonAsRelevant(id),
    // Back on the list, so their meetings in "Coming up" open their page again.
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: peopleQueryKey }),
        queryClient.invalidateQueries({ queryKey: upcomingMeetingsQueryKey }),
      ]),
  });

  const hasState = readHiddenPerson(location.state) !== null;
  useEffect(() => {
    if (!hasState) return;
    void navigate(`${location.pathname}${location.search}`, {
      replace: true,
      state: withoutHiddenPerson(location.state),
    });
  }, [hasState, location.pathname, location.search, location.state, navigate]);

  // Again once undone: "Undo" leaves the page while it has the keyboard, which
  // would otherwise drop back to the top, and the note now says who is back.
  useEffect(() => {
    note.current?.focus();
  }, [undo.isSuccess]);

  if (person === null) return null;

  return (
    <div className="flex flex-col gap-3">
      <div
        ref={note}
        tabIndex={-1}
        role="status"
        className="flex flex-wrap items-center gap-3 rounded-token-lg border border-positive bg-positive-soft p-4 font-medium text-positive"
      >
        <p className="m-0 flex-1 basis-60">
          {undo.isSuccess ? text.restored(person.name) : text.notice(person.name)}
        </p>
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
      {undo.isError && (
        // One message per try, so a second failure takes the focus again too.
        <SaveFeedback
          key={undo.submittedAt}
          outcome={{ tone: 'error', text: text.undoFailed(person.name) }}
        />
      )}
    </div>
  );
}
