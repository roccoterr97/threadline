import { describe, expect, it } from 'vitest';
import * as copy from '../copy/en';
import { peopleListState } from './peopleListAddress';
import { personLinkState, personOrigin } from './personOrigin';

describe('what a link to a person takes along', () => {
  it('takes the People page filters from the People page', () => {
    const state = personLinkState({ pathname: '/', search: '?type=vc', state: null });
    expect(state).toEqual(peopleListState('?type=vc'));
  });

  it('takes the organisation, and its own way back, from an organisation page', () => {
    const state = personLinkState({
      pathname: '/organisations/name/Slate%20%26%20Sons',
      search: '',
      state: { organisationsSearch: '?sort=name' },
    });
    expect(state).toEqual({
      organisation: { name: 'Slate & Sons' },
      organisationsSearch: '?sort=name',
    });
  });

  it('takes the page of the people with no organisation along too', () => {
    const state = personLinkState({ pathname: '/organisations/none', search: '', state: null });
    expect(state).toEqual({ organisation: { name: null } });
  });

  it('takes nothing from any other page', () => {
    expect(personLinkState({ pathname: '/review', search: '?type=vc', state: null })).toBeUndefined();
  });
});

describe('where a person goes back to', () => {
  it('is the organisation page it was opened from, by name, with that page\'s way back', () => {
    const origin = personOrigin({
      organisation: { name: 'Slate & Sons' },
      organisationsSearch: '?sort=name',
    });
    expect(origin).toEqual({
      address: '/organisations/name/Slate%20%26%20Sons',
      state: { organisationsSearch: '?sort=name' },
      label: copy.organisations.backToOrganisation('Slate & Sons'),
    });
  });

  it('is the page of the people with no organisation when opened from there', () => {
    expect(personOrigin({ organisation: { name: null } })).toEqual({
      address: '/organisations/none',
      state: undefined,
      label: copy.organisations.backToNoOrganisation,
    });
  });

  it('is the People page with its filters when opened from there', () => {
    expect(personOrigin(peopleListState('?type=vc'))).toEqual({
      address: '/?type=vc',
      state: undefined,
      label: copy.person.backToPeople,
    });
  });

  it.each([null, undefined, {}, { organisation: { name: '' } }, { organisation: 'Acme' }])(
    'is the plain People page for any other state (%j)',
    (state) => {
      expect(personOrigin(state)).toEqual({
        address: '/',
        state: undefined,
        label: copy.person.backToPeople,
      });
    },
  );
});
