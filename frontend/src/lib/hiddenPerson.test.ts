import { describe, expect, it } from 'vitest';
import { hiddenPersonState, readHiddenPerson, withoutHiddenPerson } from './hiddenPerson';

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

  it('comes off a state leaving the rest, or nothing when it was alone', () => {
    const note = hiddenPersonState({ id: 'p-01', name: 'Ada Lovelace' });
    expect(withoutHiddenPerson({ ...note, organisationsSearch: '?sort=name' })).toEqual({
      organisationsSearch: '?sort=name',
    });
    expect(withoutHiddenPerson(note)).toBeNull();
    expect(withoutHiddenPerson(null)).toBeNull();
  });
});
