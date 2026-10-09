import { ButtonLink } from '../components/ButtonLink';
import { SplitPage } from '../components/SplitPage';
import * as copy from '../copy/en';

/** Shown for a set-up address that names no screen. */
export function NoSuchScreen() {
  return (
    <SplitPage
      title={copy.wizard.noSuchScreen}
      lead={copy.wizard.noSuchScreenBody}
      aside={<ButtonLink to="/setup">{copy.wizard.toStart}</ButtonLink>}
    >
      {null}
    </SplitPage>
  );
}
