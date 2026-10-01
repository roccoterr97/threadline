import type { SupabaseClient } from '@supabase/supabase-js';
import type { ReactElement } from 'react';
import type { Clock } from '../lib/clock';
import { installSupabaseClient } from '../lib/supabaseClient';
import { createDemoClient, type DemoClient } from './demoClient';
import { DemoBanner } from './DemoBanner';

/**
 * The demo client stands in for the real one. It implements only the calls
 * the data layer and the sign-in provider make — a small, tested slice of the
 * Supabase interface — so it cannot be typed as the whole client; this is
 * the single place that says "treat it as one".
 */
function asSupabaseClient(demo: DemoClient): SupabaseClient {
  return demo as unknown as SupabaseClient;
}

/**
 * Switches the dashboard to invented data for this page load and returns the
 * banner to show above every page. Loaded only when the build flag is on.
 */
export function startDemo(clock: Clock): ReactElement {
  installSupabaseClient(asSupabaseClient(createDemoClient(clock)));
  return <DemoBanner />;
}
