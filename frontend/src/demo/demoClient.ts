import { FunctionsHttpError } from '@supabase/supabase-js';
import { REFRESH_FUNCTION_NAME } from '../api/refresh';
import type { Clock } from '../lib/clock';
import { createDemoData, DEMO_OWNER_EMAIL } from './demoData';
import { DemoDatabase } from './demoDatabase';
import { DemoQuery } from './demoQuery';

/**
 * A stand-in for the Supabase client, holding invented data in memory.
 *
 * It answers the calls the data layer (`src/api/*`) and the sign-in provider
 * make, so every page runs unchanged. The visitor is signed in as the demo
 * owner from the start; signing out and in again needs no e-mail.
 */

interface DemoSession {
  user: { email: string };
}

type AuthListener = (event: string, session: DemoSession | null) => void;

const DEMO_SESSION: DemoSession = { user: { email: DEMO_OWNER_EMAIL } };

function createDemoAuth() {
  let session: DemoSession | null = DEMO_SESSION;
  const listeners = new Set<AuthListener>();
  const announce = (event: string) => {
    listeners.forEach((listener) => {
      listener(event, session);
    });
  };

  return {
    getSession: () => Promise.resolve({ data: { session }, error: null }),
    setSession: () => Promise.resolve({ data: { session }, error: null }),
    onAuthStateChange: (listener: AuthListener) => {
      listeners.add(listener);
      return { data: { subscription: { unsubscribe: () => listeners.delete(listener) } } };
    },
    signInWithOtp: () => {
      session = DEMO_SESSION;
      announce('SIGNED_IN');
      return Promise.resolve({ data: {}, error: null });
    },
    signOut: () => {
      session = null;
      announce('SIGNED_OUT');
      return Promise.resolve({ error: null });
    },
  };
}

const NOT_FOUND_STATUS = 404;

/**
 * The Edge Functions the demo knows: only "Refresh now", which starts a
 * pretend run in the demo database. Answers take the same shape as the real
 * client's: data on success, an HTTP error carrying the response otherwise.
 */
function createDemoFunctions(database: DemoDatabase) {
  return {
    invoke: (name: string) => {
      const answer =
        name === REFRESH_FUNCTION_NAME
          ? database.startRefresh()
          : { status: NOT_FOUND_STATUS, body: { code: 'not_found' } };
      if (answer.status < 300) return Promise.resolve({ data: answer.body, error: null });
      const response = new Response(JSON.stringify(answer.body), { status: answer.status });
      return Promise.resolve({ data: null, error: new FunctionsHttpError(response) });
    },
  };
}

/** The demo's client: invented tables built around the clock's "now". */
export function createDemoClient(clock: Clock) {
  const database = new DemoDatabase(createDemoData(clock.now()), clock);
  return {
    from: (table: string) => new DemoQuery(database, table),
    auth: createDemoAuth(),
    functions: createDemoFunctions(database),
  };
}

export type DemoClient = ReturnType<typeof createDemoClient>;
