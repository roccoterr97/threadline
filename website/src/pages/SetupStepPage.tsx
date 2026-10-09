import { useParams } from 'react-router-dom';
import { CommandLine } from '../components/CommandLine';
import { BlockList } from '../components/setup/BlockList';
import { Fold } from '../components/setup/Fold';
import { WizardFrame } from '../components/setup/WizardFrame';
import * as copy from '../copy/en';
import { usePageTitle } from '../lib/usePageTitle';
import { markDone } from '../setup/progress';
import { useWizard } from '../setup/useWizard';
import { NoSuchScreen } from './NoSuchScreen';

/** One step: what to do, what you should see, and help folded away until needed. */
export function SetupStepPage() {
  const { stepId } = useParams();
  const place = useWizard('step', stepId);
  const screen = place?.screen.kind === 'step' ? place.screen : null;
  usePageTitle(screen?.step.title ?? copy.wizard.noSuchScreen);
  if (place === null || screen === null) return <NoSuchScreen />;

  const { step, part } = screen;
  const { platform } = place.progress;
  const done = place.progress.done.includes(step.id);
  const next = place.next ?? '/setup/done';
  const optional = step.optional === true;

  return (
    <WizardFrame
      eyebrow={`${part.title}${optional ? ` · ${copy.wizard.optional}` : ''}`}
      title={step.title}
      progress={place.position}
      back={place.back}
      next={{ label: done ? copy.wizard.next : copy.wizard.doneNext, to: next, onBefore: () => markDone(step.id) }}
      aside={optional && !done ? { label: copy.wizard.skip, to: next } : null}
    >
      {step.command !== undefined && (
        <CommandLine command={step.command} what={copy.wizard.commandWhat(step.title)} />
      )}
      <BlockList blocks={step.youDo} platform={platform} />
      <div className="rounded-r-token-sm border-l-2 border-positive bg-positive-soft px-4 py-3">
        <p className="text-sm font-semibold text-positive">{copy.wizard.youShouldSee}</p>
        <BlockList blocks={step.check} platform={platform} className="mt-1 text-ink" />
      </div>
      {step.intro.length > 0 && (
        <Fold label={copy.wizard.why}>
          <BlockList blocks={step.intro} platform={platform} />
        </Fold>
      )}
      {step.ifNot.length > 0 && (
        <Fold label={copy.wizard.didNotWork}>
          <BlockList blocks={step.ifNot} platform={platform} />
        </Fold>
      )}
    </WizardFrame>
  );
}
