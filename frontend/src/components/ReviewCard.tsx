import * as copy from '../copy/en';
import type { ReviewAnswer, ReviewItemRow } from '../types/database';
import { Button } from './Button';

interface ReviewCardProps {
  item: ReviewItemRow;
  onAnswer: (answer: ReviewAnswer) => void;
  isAnswering: boolean;
  /** Set when the last attempt on this card failed. */
  errorText: string | null;
}

/** One open question, with the two answers the owner can give it. */
export function ReviewCard({ item, onAnswer, isAnswering, errorText }: ReviewCardProps) {
  return (
    <li className="rounded-token-lg border border-line bg-surface p-4 shadow-card">
      <p className="text-sm font-medium text-ink-muted">{copy.review.kind[item.kind]}</p>
      <p className="mt-1 text-lg text-ink">{item.question}</p>

      {errorText !== null && (
        <p role="alert" className="mt-2 text-danger">
          {errorText}
        </p>
      )}

      <div className="mt-4 flex gap-3">
        <Button
          variant="primary"
          disabled={isAnswering}
          onClick={() => {
            onAnswer('yes');
          }}
        >
          {copy.review.yes}
        </Button>
        <Button
          variant="secondary"
          disabled={isAnswering}
          onClick={() => {
            onAnswer('no');
          }}
        >
          {copy.review.no}
        </Button>
      </div>

      {isAnswering && (
        <p role="status" className="mt-2 text-sm text-ink-muted">
          {copy.review.answering}
        </p>
      )}
    </li>
  );
}
