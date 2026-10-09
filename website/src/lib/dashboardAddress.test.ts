import { DASHBOARD_ADDRESS_KEY } from '../constants/site';
import {
  forgetDashboardAddress,
  parseDashboardAddress,
  readDashboardAddress,
  rememberDashboardAddress,
} from './dashboardAddress';

const ADDRESS = 'https://something-123abc.netlify.app';

beforeEach(() => {
  window.localStorage.clear();
});

describe('parseDashboardAddress', () => {
  it('accepts a whole https address and trims it', () => {
    expect(parseDashboardAddress(`  ${ADDRESS}  `)).toEqual({ ok: true, address: ADDRESS });
  });

  it('turns down an empty address', () => {
    expect(parseDashboardAddress('   ')).toEqual({ ok: false, problem: 'empty' });
  });

  it('turns down an address with spaces in it', () => {
    expect(parseDashboardAddress('https://my site.netlify.app')).toEqual({
      ok: false,
      problem: 'has-spaces',
    });
  });

  it('turns down an address that is not https', () => {
    expect(parseDashboardAddress('http://something.netlify.app')).toEqual({
      ok: false,
      problem: 'not-https',
    });
    expect(parseDashboardAddress('something.netlify.app')).toEqual({
      ok: false,
      problem: 'not-https',
    });
  });

  it('turns down something that is not an address at all', () => {
    expect(parseDashboardAddress('https://')).toEqual({ ok: false, problem: 'not-an-address' });
  });
});

describe('remembering the address', () => {
  it('is empty until something is remembered', () => {
    expect(readDashboardAddress()).toBeNull();
  });

  it('remembers a good address and reads it back', () => {
    expect(rememberDashboardAddress(ADDRESS)).toEqual({ ok: true, address: ADDRESS });
    expect(readDashboardAddress()).toBe(ADDRESS);
    expect(window.localStorage.getItem(DASHBOARD_ADDRESS_KEY)).toBe(JSON.stringify(ADDRESS));
  });

  it('remembers nothing when the address is turned down', () => {
    expect(rememberDashboardAddress('ftp://x').ok).toBe(false);
    expect(readDashboardAddress()).toBeNull();
  });

  it('says so when the browser refuses to store it', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota');
    });
    expect(rememberDashboardAddress(ADDRESS)).toEqual({ ok: false, problem: 'not-saved' });
  });

  it('ignores rubbish left by an older version', () => {
    window.localStorage.setItem(DASHBOARD_ADDRESS_KEY, JSON.stringify({ url: ADDRESS }));
    expect(readDashboardAddress()).toBeNull();
    window.localStorage.setItem(DASHBOARD_ADDRESS_KEY, 'not json');
    expect(readDashboardAddress()).toBeNull();
  });

  it('forgets the address', () => {
    rememberDashboardAddress(ADDRESS);
    forgetDashboardAddress();
    expect(readDashboardAddress()).toBeNull();
  });
});
