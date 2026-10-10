/**
 * Every outside address the website points at, in one place. Change the
 * template, the demo or the guide here and nowhere else.
 */

/** The site's own address, and where to write. */
export const SITE_URL = 'https://threadlineapp.com';
export const SUPPORT_EMAIL = 'support@threadlineapp.com';

/** The public template every private copy is made from. */
export const TEMPLATE_REPOSITORY = 'roccoterr97/threadline';
export const GITHUB_URL = `https://github.com/${TEMPLATE_REPOSITORY}`;
const RAW_URL = `https://raw.githubusercontent.com/${TEMPLATE_REPOSITORY}/main`;
const DOCS_URL = `${GITHUB_URL}/blob/main/docs`;

/** The dashboard filled with made-up people; nothing is saved. */
export const DEMO_URL = 'https://demo.threadlineapp.com';

/** The shared dashboard every copy uses unless its owner publishes their own. */
export const SHARED_DASHBOARD_URL = 'https://app.threadlineapp.com';

/** The one line that installs Threadline, per kind of computer. */
export const INSTALL_LINE_MAC_LINUX = `curl -LsSf ${RAW_URL}/install.sh | sh`;
export const INSTALL_LINE_WINDOWS = `irm ${RAW_URL}/install.ps1 | iex`;

/**
 * The written guides on GitHub, for whoever wants every detail. Pages the
 * guided set-up alone points at (Supabase, LinkedIn, the mail providers)
 * live in `src/setup/content/addresses.ts`.
 */
export const GUIDE_URL = `${DOCS_URL}/setup-your-accounts.md`;
export const REFRESH_NOW_URL = `${DOCS_URL}/refresh-now.md`;
export const CLAUDE_WAY_URL = `${DOCS_URL}/setup-with-claude.md`;
export const OPERATIONS_URL = `${DOCS_URL}/operations.md`;
export const CUSTOMISING_URL = `${DOCS_URL}/customising.md`;
export const SECURITY_URL = `${GITHUB_URL}/blob/main/SECURITY.md`;
export const LICENCE_URL = `${GITHUB_URL}/blob/main/LICENSE`;
export const CHANGELOG_URL = `${GITHUB_URL}/blob/main/CHANGELOG.md`;
export const ISSUES_URL = `${GITHUB_URL}/issues`;

/** Where the accounts the set-up needs are created. */
export const CLAUDE_DOWNLOAD_URL = 'https://claude.ai/download';
export const CLAUDE_CODE_SETUP_URL = 'https://code.claude.com/docs/en/setup';
export const GITHUB_SIGNUP_URL = 'https://github.com/signup';
export const SUPABASE_URL = 'https://supabase.com';
export const NETLIFY_URL = 'https://www.netlify.com';
