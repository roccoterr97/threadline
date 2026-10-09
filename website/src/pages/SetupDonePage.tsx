import { ExtrasList } from '../components/setup/ExtrasList';
import { WizardFrame } from '../components/setup/WizardFrame';
import * as copy from '../copy/en';
import { usePageTitle } from '../lib/usePageTitle';

/** The end of the main set-up, and the door to the extras. */
export function SetupDonePage() {
  usePageTitle(copy.wizard.doneTitle);
  return (
    <WizardFrame
      title={copy.wizard.doneTitle}
      back={null}
      next={{ label: copy.wizard.openDashboard, to: '/app' }}
      aside={{ label: copy.wizard.toStart, to: '/setup' }}
    >
      <p className="text-lead text-ink-muted">{copy.wizard.doneBody}</p>
      <h2 className="label pt-6">{copy.wizard.extrasTitle}</h2>
      <ExtrasList />
    </WizardFrame>
  );
}
