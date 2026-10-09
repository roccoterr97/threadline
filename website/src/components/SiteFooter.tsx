import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { CHANGELOG_URL, GITHUB_URL, GUIDE_URL, LICENCE_URL, SUPPORT_EMAIL } from '../constants/links';
import * as copy from '../copy/en';
import { Logo } from './Logo';
import { OutsideMark } from './OutsideMark';

const LINK = 'inline-flex items-center gap-1 text-ink hover:text-accent';

function Outside({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a className={LINK} href={href} target="_blank" rel="noreferrer">
      {children}
      <OutsideMark />
    </a>
  );
}

/** The bottom of every page: where to go next, where to write, and the small print. */
export function SiteFooter() {
  return (
    <footer className="mt-20 border-t border-line">
      <div className="site-container margin-grid gap-y-8 py-10 md:py-14">
        <p className="rail flex items-center gap-2 self-start font-display font-semibold text-ink">
          <Logo className="h-4 w-auto" />
          {copy.site.name}
        </p>
        <div className="column text-sm">
          <nav aria-label={copy.footer.label}>
            <ul className="grid grid-cols-2 gap-x-6 gap-y-2.5 sm:grid-cols-3 lg:grid-cols-4">
              <li>
                <Link className={LINK} to="/questions">
                  {copy.nav.questions}
                </Link>
              </li>
              <li>
                <Link className={LINK} to="/privacy">
                  {copy.nav.privacy}
                </Link>
              </li>
              <li>
                <Link className={LINK} to="/update">
                  {copy.nav.update}
                </Link>
              </li>
              <li>
                <Outside href={GUIDE_URL}>{copy.footer.guide}</Outside>
              </li>
              <li>
                <Outside href={CHANGELOG_URL}>{copy.footer.changelog}</Outside>
              </li>
              <li>
                <Outside href={GITHUB_URL}>{copy.nav.github}</Outside>
              </li>
              <li>
                <Outside href={LICENCE_URL}>{copy.footer.licence}</Outside>
              </li>
              <li className="col-span-2 sm:col-span-3 lg:col-span-1">
                <a className={`${LINK} break-all`} href={`mailto:${SUPPORT_EMAIL}`}>
                  {SUPPORT_EMAIL}
                </a>
              </li>
            </ul>
          </nav>
          <div className="mt-10 max-w-[40rem] space-y-1.5 text-ink-muted">
            <p>
              {copy.footer.privacy} {copy.footer.madeWith}
            </p>
            <p>{copy.footer.independent}</p>
          </div>
        </div>
      </div>
    </footer>
  );
}
