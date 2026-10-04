import { describe, expect, it } from 'vitest';
import {
  NO_ORGANISATION_PATH,
  organisationPath,
  organisationsListAddress,
  organisationsListState,
  readOrganisationPath,
  readOrganisationsListState,
} from './organisationAddress';

describe('the address of an organisation page', () => {
  it('carries the name, with anything unsafe escaped', () => {
    expect(organisationPath('Slate & Sons')).toBe('/organisations/name/Slate%20%26%20Sons');
    expect(organisationPath('A/B Testing')).toBe('/organisations/name/A%2FB%20Testing');
    expect(organisationPath('100% Design')).toBe('/organisations/name/100%25%20Design');
  });

  it('has a page of its own for the people with no organisation', () => {
    expect(organisationPath(null)).toBe(NO_ORGANISATION_PATH);
  });

  it.each(['Slate & Sons', 'A/B Testing', '100% Design', 'Ærø Søfart', 'none'])(
    'reads back the name "%s" from its own address',
    (name) => {
      expect(readOrganisationPath(organisationPath(name))).toEqual({ name });
    },
  );

  it('reads the page of the people with no organisation', () => {
    expect(readOrganisationPath(NO_ORGANISATION_PATH)).toEqual({ name: null });
    expect(readOrganisationPath(`${NO_ORGANISATION_PATH}/`)).toEqual({ name: null });
  });

  it.each([
    '/',
    '/organisations',
    '/organisations/name',
    '/organisations/name/',
    '/organisations/name/Acme/people',
    '/organisations/name/100%',
    '/people/p-01',
  ])('is nothing for %s', (pathname) => {
    expect(readOrganisationPath(pathname)).toBeNull();
  });
});

describe('the organisations view an organisation was opened from', () => {
  it('leads back to the same filters and order', () => {
    const state = organisationsListState('?waiting=me&sort=name');
    expect(readOrganisationsListState(state)).toEqual(state);
    expect(organisationsListAddress(state)).toBe('/organisations?waiting=me&sort=name');
  });

  it.each([
    null,
    undefined,
    'text',
    {},
    { organisationsSearch: '' },
    { organisationsSearch: 42 },
    { organisationsSearch: '//elsewhere.example' },
    { peopleSearch: '?type=vc' },
  ])('leads to the plain list for any other state (%j)', (state) => {
    expect(readOrganisationsListState(state)).toBeUndefined();
    expect(organisationsListAddress(state)).toBe('/organisations');
  });
});
