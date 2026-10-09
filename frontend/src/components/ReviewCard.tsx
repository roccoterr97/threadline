import { useEffect, useId, useRef } from 'react';
import { Link } from 'react-router-dom';
import * as copy from '../copy/en';
import type { ReviewAnswer, ReviewItemRow } from '../types/database';
import { Button } from './Button';
import { TAP_LINK } from './linkStyles';
import { SaveFeedback } from './SaveFeedback';

/** Someone a question is about who is on the people list, so their page can be opened. */
export interface ReviewPerson {
  id: string;
  name: string;
}

interface ReviewCardProps {
  item: ReviewItemRow;
  /** The people the question names who have a page to open; may be empty. */
  people: readonly ReviewPerson[];
  onAnswer: (answer: ReviewAnswer) => void;
  isAnswering: boolean;
  /** Set when the last attempt on this card failed. */
  errorText: string | null;
  /** Set on the question that is next once another has been answered: it takes the keyboard. */
  takesFocus: boolean;
  onFocused: () => void;
}

/**
 * One open question, with the two answers the owner can give it. Neither
 * answer is styled as the expected one, and each button carries the question
 * so a screen reader user moving between buttons knows what "Yes" answers.
 *
 * When another question has just been answered and left the list, this one
 * can take the keyboard: the question itself is focused, not "Yes", so a
 * repeated key press can never answer it by accident. A failed answer is
 * shown on the card and takes the keyboard, so it cannot be missed.
 */
export function ReviewCard({
  item,
  people,
  onAnswer,
  isAnswering,
  errorText,
  takesFocus,
  onFocused,
}: ReviewCardProps) {
  const questionId = useId();
  const question = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (!takesFocus) return;
    question.current?.focus();
    onFocused();
  }, [takesFocus, onFocused]);

  const answerButton = (answer: ReviewAnswer, label: string) => (
    <Button
      aria-describedby={questionId}
      disabled={isAnswering}
      onClick={() => {
        onAnswer(answer);
      }}
    >
      {label}
    </Button>
  );

  return (
    <li className="rounded-token-lg border border-line bg-surface p-4 shadow-card">
      <p className="text-sm font-medium text-ink-muted">{copy.review.kind[item.kind]}</p>
      <p ref={question} id={questionId} tabIndex={-1} className="mt-1 text-lg break-words text-ink">
        {item.question}
      </p>
      {people.length > 0 && (
        <p className="mt-1 flex flex-wrap gap-x-4 text-sm">
          {people.map((person) => (
            <Link key={person.id} to={`/people/${person.id}`} className={`font-medium ${TAP_LINK}`}>
              {copy.home.openPerson(person.name)}
            </Link>
          ))}
        </p>
      )}

      {errorText !== null && (
        <div className="mt-2">
          <SaveFeedback outcome={{ tone: 'error', text: errorText }} />
        </div>
      )}

      <div className="mt-4 flex gap-3">
        {answerButton('yes', copy.review.yes)}
        {answerButton('no', copy.review.no)}
      </div>

      {isAnswering && (
        <p role="status" className="mt-2 text-sm text-ink-muted">
          {copy.review.answering}
        </p>
      )}
    </li>
  );
}
