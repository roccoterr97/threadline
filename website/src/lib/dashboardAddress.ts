import { z } from 'zod';
import { DASHBOARD_ADDRESS_KEY } from '../constants/site';
import { clearStored, readStored, writeStored } from './storage';

/**
 * The reader's own dashboard address, remembered in this browser only.
 *
 * Threadline has no central server, so the website cannot know where a
 * reader's dashboard is. The reader types it once; it is kept in local
 * storage under `DASHBOARD_ADDRESS_KEY` and offered back as a button.
 */

/** Why an address was turned down. The page turns each one into a sentence. */
export type AddressProblem = 'empty' | 'has-spaces' | 'not-https' | 'not-an-address';

const HTTPS_PREFIX = 'https://';

/** Whether the browser can make sense of the address at all (older phones lack `URL.canParse`). */
function isWholeAddress(value: string): boolean {
  try {
    new URL(value);
    return true;
  } catch {
    return false;
  }
}

/** A dashboard address: a whole `https://` address with no spaces in it. */
export const dashboardAddressSchema = z
  .string()
  .trim()
  .min(1, { message: 'empty' satisfies AddressProblem })
  .refine((value) => !/\s/.test(value), { message: 'has-spaces' satisfies AddressProblem })
  .refine((value) => value.toLowerCase().startsWith(HTTPS_PREFIX), {
    message: 'not-https' satisfies AddressProblem,
  })
  .refine(isWholeAddress, {
    message: 'not-an-address' satisfies AddressProblem,
  });

export type ParsedAddress = { ok: true; address: string } | { ok: false; problem: AddressProblem };

function isAddressProblem(value: string): value is AddressProblem {
  return ['empty', 'has-spaces', 'not-https', 'not-an-address'].includes(value);
}

/** Checks what the reader typed and returns the cleaned address, or why it was turned down. */
export function parseDashboardAddress(input: string): ParsedAddress {
  const result = dashboardAddressSchema.safeParse(input);
  if (result.success) return { ok: true, address: result.data };
  const message = result.error.issues[0]?.message ?? '';
  return { ok: false, problem: isAddressProblem(message) ? message : 'not-an-address' };
}

/** The remembered address, or `null` when none is remembered or storage is unavailable. */
export function readDashboardAddress(): string | null {
  return readStored(DASHBOARD_ADDRESS_KEY, dashboardAddressSchema);
}

export type RememberResult = ParsedAddress | { ok: false; problem: 'not-saved' };

/** Checks the address and remembers it; says why when it could not. */
export function rememberDashboardAddress(input: string): RememberResult {
  const parsed = parseDashboardAddress(input);
  if (!parsed.ok) return parsed;
  if (!writeStored(DASHBOARD_ADDRESS_KEY, parsed.address)) {
    return { ok: false, problem: 'not-saved' };
  }
  return parsed;
}

/** Forgets the remembered address. */
export function forgetDashboardAddress(): void {
  clearStored(DASHBOARD_ADDRESS_KEY);
}
