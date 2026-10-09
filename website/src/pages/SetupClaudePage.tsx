import { BlockList } from '../components/setup/BlockList';
import { WizardFrame } from '../components/setup/WizardFrame';
import { CopyButton } from '../components/CopyButton';
import * as copy from '../copy/en';
import { usePageTitle } from '../lib/usePageTitle';
import { CLAUDE_WAY } from '../setup/guide';
import { useSetupProgress } from '../setup/progress';

/** The other way in: one sentence pasted into the Claude app. */
export function SetupClaudePage() {
  usePageTitle(CLAUDE_WAY.title);
  const progress = useSetupProgress();
  return (
    <WizardFrame
      title={CLAUDE_WAY.title}
      back="/setup/way"
      next={{ label: copy.wizard.toStart, to: '/setup' }}
    >
      <BlockList blocks={CLAUDE_WAY.intro} platform={progress.platform} />
      <figure className="rounded-token-md border border-line bg-surface p-4">
        <figcaption className="mb-2 flex items-center justify-between gap-3 text-sm font-medium text-ink">
          {copy.wizard.promptLabel}
          <CopyButton text={CLAUDE_WAY.prompt} what={copy.wizard.promptWhat} />
        </figcaption>
        <pre className="font-mono text-sm whitespace-pre-wrap text-ink [overflow-wrap:anywhere]">{CLAUDE_WAY.prompt}</pre>
      </figure>
      <h2 className="pt-4 text-xl text-ink">{copy.wizard.afterwards}</h2>
      <BlockList blocks={CLAUDE_WAY.afterwards} platform={progress.platform} />
    </WizardFrame>
  );
}
