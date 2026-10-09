import * as copy from '../copy/en';
import { peopleListIsCut } from '../domain/peopleView';
import { InfoNote } from './InfoNote';

interface PeopleCutNoticeProps {
  /** How many people the page has to work with. */
  shown: number;
}

/** Says so when the people list was cut short, because the numbers built from it are then too low. */
export function PeopleCutNotice({ shown }: PeopleCutNoticeProps) {
  if (!peopleListIsCut(shown)) return null;
  return <InfoNote>{copy.states.peopleCut(shown)}</InfoNote>;
}
