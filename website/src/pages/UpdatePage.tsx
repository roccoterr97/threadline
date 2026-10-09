import { useState } from 'react';
import { Callout } from '../components/Callout';
import { CommandLine } from '../components/CommandLine';
import { OutsideMark } from '../components/OutsideMark';
import { PlatformSwitcher } from '../components/PlatformSwitcher';
import { SplitPage } from '../components/SplitPage';
import { Thread } from '../components/Thread';
import { CHANGELOG_URL, INSTALL_LINE_MAC_LINUX, INSTALL_LINE_WINDOWS } from '../constants/links';
import { updateChecks, updatePage, updateSteps } from '../content/update';
import { detectPlatform, type Platform } from '../lib/platform';
import { usePageTitle } from '../lib/usePageTitle';

/** How to bring an existing copy of Threadline up to date: the same install line, then two commands. */
export function UpdatePage() {
  usePageTitle(updatePage.title);
  const [platform, setPlatform] = useState<Platform>(() => detectPlatform(navigator.userAgent));
  const installLine = platform === 'windows' ? INSTALL_LINE_WINDOWS : INSTALL_LINE_MAC_LINUX;

  return (
    <SplitPage
      title={updatePage.title}
      lead={updatePage.intro}
      aside={
        <p className="text-ink-muted">
          {updatePage.whatChangedLead}{' '}
          <a href={CHANGELOG_URL} target="_blank" rel="noreferrer" className="link inline-flex items-center gap-1">
            {updatePage.whatChanged}
            <OutsideMark />
          </a>
        </p>
      }
    >
      <h2 className="label mb-8">{updateSteps.heading}</h2>
      <Thread
        items={[
          {
            id: 'paste',
            title: updateSteps.pasteHeading,
            text: (
              <>
                <p>{updateSteps.pasteBody}</p>
                <PlatformSwitcher value={platform} onChange={setPlatform} />
                <CommandLine command={installLine} what={updateSteps.installLineWhat} />
              </>
            ),
          },
          {
            id: 'publish',
            title: updateSteps.publishHeading,
            text: (
              <>
                <p>{updateSteps.publishBody}</p>
                <CommandLine command={updateSteps.publishCommand} what={updateSteps.publishWhat} />
              </>
            ),
          },
          {
            id: 'settings',
            title: updateSteps.settingsHeading,
            text: (
              <>
                <p>{updateSteps.settingsBody}</p>
                <CommandLine command={updateSteps.settingsCommand} what={updateSteps.settingsWhat} />
              </>
            ),
          },
        ]}
      />
      <div className="mt-12 flex flex-col gap-3">
        <Callout tone="check">{updateChecks.check}</Callout>
        <Callout tone="ifNot">{updateChecks.ifNot}</Callout>
      </div>
    </SplitPage>
  );
}
