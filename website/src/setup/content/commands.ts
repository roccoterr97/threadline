/**
 * The terminal commands the written guide (docs/setup-your-accounts.md) names,
 * spelt once so every part shows them the same way.
 */

/** Typed first in every new terminal window; works from any folder. */
export const BACKEND_FOLDER_LINE = 'cd ~/threadline/backend';

/** Carries on with the guided set-up where it stopped. */
export const SETUP_COMMAND = 'uv run tracker setup';

/** The same questions on a page in the browser instead of the terminal. */
export const SETUP_BROWSER_COMMAND = `${SETUP_COMMAND} --browser`;

/** Checks every account and setting, one line each. */
export const DOCTOR_COMMAND = 'uv run tracker doctor';

/** Makes the key that lets GitHub use the reader's Claude plan, when it has to be pasted by hand. */
export const CLAUDE_TOKEN_COMMAND = 'claude setup-token';

/** One set-up step on its own, by the name the terminal uses. */
export const STEP_COMMAND = {
  supabase: `${SETUP_COMMAND} supabase`,
  encryption: `${SETUP_COMMAND} encryption`,
  database: `${SETUP_COMMAND} database`,
  login: `${SETUP_COMMAND} login`,
  categories: `${SETUP_COMMAND} categories`,
  timezone: `${SETUP_COMMAND} timezone`,
  mailbox: `${SETUP_COMMAND} mailbox`,
  microsoft: `${SETUP_COMMAND} microsoft`,
  dashboard: `${SETUP_COMMAND} dashboard`,
  schedule: `${SETUP_COMMAND} schedule`,
  github: `${SETUP_COMMAND} github`,
  extras: `${SETUP_COMMAND} extras`,
  linkedin: `${SETUP_COMMAND} linkedin`,
  refresh: `${SETUP_COMMAND} refresh`,
  cloud: `${SETUP_COMMAND} cloud`,
} as const;
