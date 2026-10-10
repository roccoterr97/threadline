import { describe, expect, it } from 'vitest';
import {
  isPublicKey,
  parseConnectFragment,
  parsePastedLink,
  projectAddress,
  withoutConnectValues,
} from './connectLink';

const REF = 'abcdefghijklmnopqrst';
const KEY = 'sb_publishable_AbC-123_x';
const SETTINGS = { url: `https://${REF}.supabase.co`, anonKey: KEY };

/** A made-up legacy (JWT) key claiming `role`; nothing checks its signature here. */
function legacyKey(role: string): string {
  const claims = btoa(JSON.stringify({ role })).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `eyJhbGciOiJIUzI1NiJ9.${claims}.c2lnbmF0dXJl`;
}

describe('parseConnectFragment', () => {
  it('reads the project and the publishable key', () => {
    expect(parseConnectFragment(`#project=${REF}&key=${KEY}`)).toEqual({
      kind: 'valid',
      settings: SETTINGS,
    });
  });

  it('reads them in any order, %-encoded, next to other values', () => {
    const fragment = `access_token=abc&key=${encodeURIComponent(KEY)}&project=${REF}`;
    expect(parseConnectFragment(fragment)).toEqual({ kind: 'valid', settings: SETTINGS });
  });

  it('accepts a legacy public key with its dots', () => {
    const key = legacyKey('anon');
    expect(parseConnectFragment(`project=${REF}&key=${key}`)).toEqual({
      kind: 'valid',
      settings: { ...SETTINGS, anonKey: key },
    });
  });

  it('is none when the fragment names neither value', () => {
    expect(parseConnectFragment('')).toEqual({ kind: 'none' });
    expect(parseConnectFragment('#access_token=abc&refresh_token=def')).toEqual({ kind: 'none' });
  });

  it.each([
    ['a missing key', `project=${REF}`],
    ['a missing project', `key=${KEY}`],
    ['a project that is not an identifier', `project=Not-A-Ref&key=${KEY}`],
    ['a project naming another host', `project=evil.example%2F&key=${KEY}`],
    ['a secret key', `project=${REF}&key=sb_secret_abc`],
    ['a service-role key', `project=${REF}&key=${legacyKey('service_role')}`],
    ['a key with spaces', `project=${REF}&key=a%20b`],
    ['a broken %-sequence', `project=${REF}&key=%E0%A4%A`],
  ])('is invalid with %s', (_label, fragment) => {
    expect(parseConnectFragment(fragment)).toEqual({ kind: 'invalid' });
  });
});

describe('withoutConnectValues', () => {
  it('leaves everything else exactly as it was', () => {
    expect(withoutConnectValues(`#access_token=a.b%2Bc&project=${REF}&key=${KEY}&type=magiclink`)).toBe(
      'access_token=a.b%2Bc&type=magiclink',
    );
  });

  it('is empty when the link held only its own values', () => {
    expect(withoutConnectValues(`#project=${REF}&key=${KEY}`)).toBe('');
  });
});

describe('parsePastedLink', () => {
  it('reads a whole pasted link, spaces around it included', () => {
    expect(parsePastedLink(`  https://app.threadlineapp.com/#project=${REF}&key=${KEY}\n`)).toEqual(SETTINGS);
  });

  it('reads the part after # on its own', () => {
    expect(parsePastedLink(`project=${REF}&key=${KEY}`)).toEqual(SETTINGS);
  });

  it('refuses anything that is not a complete link', () => {
    expect(parsePastedLink('https://app.threadlineapp.com/')).toBeNull();
    expect(parsePastedLink(`https://app.threadlineapp.com/#project=${REF}`)).toBeNull();
    expect(parsePastedLink('')).toBeNull();
  });
});

describe('isPublicKey', () => {
  it('tells public keys from secret ones', () => {
    expect(isPublicKey(KEY)).toBe(true);
    expect(isPublicKey(legacyKey('anon'))).toBe(true);
    expect(isPublicKey('sb_secret_abc')).toBe(false);
    expect(isPublicKey(legacyKey('supabase_admin'))).toBe(false);
    expect(isPublicKey('')).toBe(false);
  });
});

describe('projectAddress', () => {
  it('builds the project address from its identifier', () => {
    expect(projectAddress(REF)).toBe(SETTINGS.url);
  });
});
