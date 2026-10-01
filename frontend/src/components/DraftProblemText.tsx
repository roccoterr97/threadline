import * as copy from '../copy/en';
import type { DraftProblem } from '../domain/categorySettings';

interface DraftProblemTextProps {
  problem: DraftProblem | null;
}

/** What is wrong with a category form, announced as soon as it appears. */
export function DraftProblemText({ problem }: DraftProblemTextProps) {
  if (problem === null) return null;
  return (
    <p role="alert" className="font-medium text-danger">
      {copy.categoryDraftProblems[problem]}
    </p>
  );
}
