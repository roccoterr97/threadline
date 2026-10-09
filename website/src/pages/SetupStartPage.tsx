import { Link } from 'react-router-dom';
import { Button } from '../components/Button';
import { ButtonLink } from '../components/ButtonLink';
import { SplitPage, SplitSection } from '../components/SplitPage';
import { ExtrasList } from '../components/setup/ExtrasList';
import * as copy from '../copy/en';
import { usePageTitle } from '../lib/usePageTitle';
import { SETUP_GUIDE } from '../setup/guide';
import { clearProgress, useSetupProgress } from '../setup/progress';
import { resumeScreen, screenPath } from '../setup/wizard';

/** The door into the set-up: what it takes on one side, the button and the extras on the other. */
export function SetupStartPage() {
  usePageTitle(copy.wizard.title);
  const progress = useSetupProgress();
  const started = progress.done.length > 0;
  const target = screenPath(resumeScreen(SETUP_GUIDE, progress));

  return (
    <SplitPage
      title={copy.wizard.title}
      lead={copy.wizard.lead}
      aside={
        <>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
            <ButtonLink to={target} className="px-6 py-3 text-lg">
              {started ? copy.wizard.continue : copy.wizard.start}
            </ButtonLink>
            <Link to="/setup/claude" className="link">
              {copy.wizard.claudeInstead}
            </Link>
          </div>
          {started && (
            <Button
              variant="quiet"
              className="px-0 text-sm"
              onClick={() => {
                if (window.confirm(copy.wizard.confirmStartAgain)) clearProgress();
              }}
            >
              {copy.wizard.startAgain}
            </Button>
          )}
        </>
      }
    >
      <ul className="divide-y divide-line border-y border-line">
        {copy.wizard.needs.map((need, index) => (
          <li key={need} className="flex gap-5 py-4 text-lead text-ink">
            <span className="label-number pt-1 text-sm tabular-nums">{String(index + 1).padStart(2, '0')}</span>
            {need}
          </li>
        ))}
      </ul>
      <div className="mt-14">
        <SplitSection heading={copy.wizard.extrasTitle}>
          <ExtrasList />
        </SplitSection>
      </div>
    </SplitPage>
  );
}
