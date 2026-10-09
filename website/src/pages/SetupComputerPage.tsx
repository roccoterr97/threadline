import { OptionButtons } from '../components/setup/OptionButtons';
import { WizardFrame } from '../components/setup/WizardFrame';
import * as copy from '../copy/en';
import { isPlatform, PLATFORM_LABELS, PLATFORMS } from '../lib/platform';
import { usePageTitle } from '../lib/usePageTitle';
import { setPlatform } from '../setup/progress';
import { useWizard } from '../setup/useWizard';
import { NoSuchScreen } from './NoSuchScreen';

/** The first question: which computer. */
export function SetupComputerPage() {
  usePageTitle(copy.wizard.computerQuestion);
  const place = useWizard('computer');
  if (place === null) return <NoSuchScreen />;
  return (
    <WizardFrame
      title={copy.wizard.computerQuestion}
      back="/setup"
      next={place.next === null ? null : { label: copy.wizard.next, to: place.next }}
    >
      <OptionButtons
        question={copy.wizard.computerQuestion}
        options={PLATFORMS.map((platform) => ({ id: platform, label: PLATFORM_LABELS[platform] }))}
        value={place.progress.platform}
        onChange={(id) => {
          if (isPlatform(id)) setPlatform(id);
        }}
      />
    </WizardFrame>
  );
}
