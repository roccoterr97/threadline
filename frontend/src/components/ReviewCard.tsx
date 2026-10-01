import { useId } from 'react';
import { Link } from 'react-router-dom';
import * as copy from '../copy/en';
import type { ReviewAnswer, ReviewItemRow } from '../types/database';
import { Button } from './Button';

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
}

/**
 * One open question, with the two answers the owner can give it. Neither
 * answer is styled as the expected one, and each button carries the question
 * so a screen reader user moving between buttons knows what "Yes" answers.
 */
export function ReviewCard({ item, people, onAnswer, isAnswering, errorText }: ReviewCardProps) {
  const questionId = useId();
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
      <p id={questionId} className="mt-1 text-lg text-ink">
        {item.question}
      </p>
      {people.length > 0 && (
        <p className="mt-1 flex flex-wrap gap-x-4 text-sm">
          {people.map((person) => (
            <Link
              key={person.id}
              to={`/people/${person.id}`}
              className="font-medium text-accent underline underline-offset-2"
            >
              {copy.home.openPerson(person.name)}
            </Link>
          ))}
        </p>
      )}

      {errorText !== null && (
        <p role="alert" className="mt-2 text-danger">
          {errorText}
        </p>
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
