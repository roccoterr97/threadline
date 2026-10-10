import type { SetupGuide } from './types';
import { BEFORE_YOU_START } from './content/before-you-start';
import { INSTALL } from './content/install';
import { SUPABASE } from './content/supabase';
import { LOGIN_CATEGORIES_TIME_ZONE } from './content/login-categories-time-zone';
import { MAILBOX } from './content/mailbox';
import { DASHBOARD } from './content/dashboard';
import { GITHUB } from './content/github';
import { FINAL_CHECK } from './content/final-check';
import { LINKEDIN } from './content/linkedin';
import { REFRESH_NOW } from './content/refresh-now';
import { CLOUD_ROUTE } from './content/cloud-route';
import { OWN_DASHBOARD } from './content/own-dashboard';

export { CLAUDE_WAY } from './content/claude-way';

/**
 * The guided set-up's content, assembled from the files under `./content/`
 * in the order of docs/setup-your-accounts.md. The screens read this value
 * and `CLAUDE_WAY`, and nothing else.
 */
export const SETUP_GUIDE: SetupGuide = {
  core: [
    BEFORE_YOU_START,
    INSTALL,
    SUPABASE,
    LOGIN_CATEGORIES_TIME_ZONE,
    MAILBOX,
    DASHBOARD,
    GITHUB,
    FINAL_CHECK,
  ],
  extras: [LINKEDIN, REFRESH_NOW, CLOUD_ROUTE, OWN_DASHBOARD],
};
