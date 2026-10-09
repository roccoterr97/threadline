import { ButtonLink } from '../components/ButtonLink';
import { SplitPage } from '../components/SplitPage';
import * as copy from '../copy/en';
import { usePageTitle } from '../lib/usePageTitle';

/** Shown for an address that names no page. */
export function NotFoundPage() {
  usePageTitle(copy.notFound.title);
  return (
    <SplitPage title={copy.notFound.title} lead={copy.notFound.body} aside={<ButtonLink to="/">{copy.notFound.home}</ButtonLink>}>
      {null}
    </SplitPage>
  );
}
