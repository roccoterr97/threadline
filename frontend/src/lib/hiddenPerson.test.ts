import { describe, expect, it } from 'vitest';
import { hiddenPersonState, readHiddenPerson } from './hiddenPerson';

describe('the "just hidden" note', () => {
  it('reads back the person it was made for', () => {
    const person = { id: 'p-01', name: 'Ada Lovelace' };
    expect(readHiddenPerson(hiddenPersonState(person))).toEqual(person);
  });

  it.each([null, undefined, 'text', {}, { hiddenPerson: { id: 1, name: 'x' } }])(
    'ignores any other state (%j)',
    (state) => {
      expect(readHiddenPerson(state)).toBeNull();
    },
  );
});
