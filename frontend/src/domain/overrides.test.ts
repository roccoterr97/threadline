import { describe, expect, it } from 'vitest';
import { samplePerson } from '../test/__fixtures__/sampleData';
import { applyOverrideToPerson, hasAnyOverride, type OverrideValues } from './overrides';

const EMPTY: OverrideValues = {
  status: null,
  waiting_on: null,
  next_action: null,
  due_date: null,
  person_type: null,
  note: null,
};

describe('hasAnyOverride', () => {
  it('is false when nothing was corrected', () => {
    expect(hasAnyOverride(EMPTY)).toBe(false);
  });

  it('is true as soon as one field is set', () => {
    expect(hasAnyOverride({ ...EMPTY, waiting_on: 'them' })).toBe(true);
  });
});

describe('applyOverrideToPerson', () => {
  it('lets a correction win over the assistant', () => {
    const person = samplePerson('p-01');
    const result = applyOverrideToPerson(person, { ...EMPTY, status: 'meeting_planned' });
    expect(result.status).toBe('meeting_planned');
    expect(result.has_override).toBe(true);
  });

  it('leaves untouched fields to the assistant', () => {
    const person = samplePerson('p-01');
    const result = applyOverrideToPerson(person, { ...EMPTY, status: 'closed' });
    expect(result.waiting_on).toBe(person.waiting_on);
    expect(result.next_action).toBe(person.next_action);
  });

  it('marks the person as no longer corrected when every field is cleared', () => {
    const person = { ...samplePerson('p-04'), has_override: true };
    expect(applyOverrideToPerson(person, EMPTY).has_override).toBe(false);
  });

  it('does not change the row it was given', () => {
    const person = samplePerson('p-01');
    const before = { ...person };
    applyOverrideToPerson(person, { ...EMPTY, status: 'closed' });
    expect(person).toEqual(before);
  });
});
