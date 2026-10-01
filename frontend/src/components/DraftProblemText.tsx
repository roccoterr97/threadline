import * as copy from '../copy/en';
import type { DraftProblem } from '../domain/categorySettings';

interface DraftProblemTextProps {
  /** The field at fault points here with `aria-describedby`. */
  id: string;
  problem: DraftProblem | null;
}

/** What is wrong with a category form, announced as soon as it appears. */
export function DraftProblemText({ id, problem }: DraftProblemTextProps) {
  if (problem === null) return null;
  return (
    <p id={id} role="alert" className="font-medium text-danger">
      {copy.categoryDraftProblems[problem]}
    </p>
  );
}
