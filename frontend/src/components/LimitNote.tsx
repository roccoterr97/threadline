import * as copy from '../copy/en';
import { InfoNote } from './InfoNote';

/** Why adding is switched off: eight categories are already in use. */
export function LimitNote() {
  return <InfoNote>{copy.categorySettings.limitReached}</InfoNote>;
}
