import { OptionButtons } from '../components/setup/OptionButtons';
import { WizardFrame } from '../components/setup/WizardFrame';
import * as copy from '../copy/en';
import { usePageTitle } from '../lib/usePageTitle';
import { setWay, SETUP_WAYS, type SetupWay } from '../setup/progress';
import { useWizard } from '../setup/useWizard';
import { NoSuchScreen } from './NoSuchScreen';

function isWay(value: string): value is SetupWay {
  return (SETUP_WAYS as readonly string[]).includes(value);
}

/** The second question: by hand, or let Claude do it. */
export function SetupWayPage() {
  usePageTitle(copy.wizard.wayQuestion);
  const place = useWizard('way');
  if (place === null) return <NoSuchScreen />;
  const claude = place.progress.way === 'claude';
  return (
    <WizardFrame
      title={copy.wizard.wayQuestion}
      back={place.back}
      next={{ label: copy.wizard.next, to: claude ? '/setup/claude' : (place.next ?? '/setup') }}
    >
      <OptionButtons
        question={copy.wizard.wayQuestion}
        options={[
          { id: 'by-hand', label: copy.wizard.wayByHand, hint: copy.wizard.wayByHandHint },
          { id: 'claude', label: copy.wizard.wayClaude, hint: copy.wizard.wayClaudeHint },
        ]}
        value={place.progress.way}
        onChange={(id) => {
          if (isWay(id)) setWay(id);
        }}
      />
    </WizardFrame>
  );
}
