import { describe, expect, it } from 'vitest';
import { peopleListState } from '../lib/peopleListAddress';
import { currentNavPath } from './navItems';

describe('which menu item is the current page', () => {
  it.each([
    ['/', '/'],
    ['/?waiting=me', '/'],
    ['/organisations', '/organisations'],
    ['/organisations/name/Acme', '/organisations'],
    ['/organisations/none', '/organisations'],
    ['/review', '/review'],
    ['/runs', '/runs'],
    ['/settings', '/settings'],
  ])('marks %s as %s', (pathname, expected) => {
    expect(currentNavPath({ pathname: pathname.split('?')[0]!, state: null })).toBe(expected);
  });

  it('marks People on a person opened from the People page, or from nowhere', () => {
    const state = peopleListState('?type=vc');
    expect(currentNavPath({ pathname: '/people/p-01', state })).toBe('/');
    expect(currentNavPath({ pathname: '/people/p-01', state: null })).toBe('/');
  });

  it('marks Organisations on a person opened from an organisation', () => {
    const state = { organisation: { name: 'Acme' } };
    expect(currentNavPath({ pathname: '/people/p-01', state })).toBe('/organisations');
    const none = { organisation: { name: null } };
    expect(currentNavPath({ pathname: '/people/p-01', state: none })).toBe('/organisations');
  });

  it('marks nothing on a page outside the menu', () => {
    expect(currentNavPath({ pathname: '/login', state: null })).toBeNull();
  });
});
