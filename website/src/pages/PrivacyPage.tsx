import { PageContents } from '../components/PageContents';
import { SplitPage } from '../components/SplitPage';
import { InlineText } from '../components/setup/InlineText';
import { ISSUES_URL, SUPPORT_EMAIL } from '../constants/links';
import { PRIVACY } from '../content/privacy';
import * as copy from '../copy/en';
import { usePageTitle } from '../lib/usePageTitle';

const QUESTIONS_ID = 'questions';

/** What this site and the tool do with data: nothing of ours. */
export function PrivacyPage() {
  usePageTitle(copy.privacyPage.title);
  const entries = [
    ...PRIVACY.map((section) => ({ id: section.id, label: section.heading })),
    { id: QUESTIONS_ID, label: copy.questionsPage.title },
  ];
  return (
    <SplitPage
      title={copy.privacyPage.title}
      lead={copy.privacyPage.lead}
      aside={
        <>
          <p className="label">{copy.privacyPage.asOf}</p>
          <PageContents entries={entries} />
        </>
      }
    >
      <div className="divide-y divide-line border-y border-line">
        {PRIVACY.map((section) => (
          <section key={section.id} id={section.id} className="py-8">
            <h2 className="text-2xl text-ink">{section.heading}</h2>
            {section.paragraphs.map((paragraph) => (
              <p key={paragraph} className="mt-3 max-w-[44rem] text-lead text-ink-muted">
                <InlineText text={paragraph} />
              </p>
            ))}
          </section>
        ))}
        <section id={QUESTIONS_ID} className="py-8">
          <h2 className="text-2xl text-ink">{copy.questionsPage.title}</h2>
          <p className="mt-3 max-w-[44rem] text-lead text-ink-muted">
            {copy.questionsPage.missing}{' '}
            <a href={`mailto:${SUPPORT_EMAIL}`} className="link">
              {SUPPORT_EMAIL}
            </a>{' '}
            {copy.questionsPage.orGitHub}:{' '}
            <a href={ISSUES_URL} target="_blank" rel="noreferrer" className="link">
              GitHub
            </a>
            .
          </p>
        </section>
      </div>
    </SplitPage>
  );
}
