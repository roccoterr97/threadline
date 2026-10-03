import { describe, expect, it } from 'vitest';
import { peopleListAddress, peopleListState } from './peopleListAddress';

describe('the People view a person was opened from', () => {
  it('leads back to the same filters and order', () => {
    expect(peopleListAddress(peopleListState('?type=startup&sort=name'))).toBe(
      '/?type=startup&sort=name',
    );
  });

  it.each([
    null,
    undefined,
    'text',
    {},
    { peopleSearch: '' },
    { peopleSearch: 42 },
    { peopleSearch: '//elsewhere.example' },
    { hiddenPerson: { id: 'p-01', name: 'Someone' } },
  ])('leads to the plain People page for any other state (%j)', (state) => {
    expect(peopleListAddress(state)).toBe('/');
  });
});
