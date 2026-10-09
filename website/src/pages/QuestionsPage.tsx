import { OutsideMark } from '../components/OutsideMark';
import { PageContents } from '../components/PageContents';
import { SplitPage } from '../components/SplitPage';
import { InlineText } from '../components/setup/InlineText';
import { DEMO_URL, ISSUES_URL, SUPPORT_EMAIL } from '../constants/links';
import { QUESTIONS } from '../content/questions';
import * as copy from '../copy/en';
import { usePageTitle } from '../lib/usePageTitle';

/** Short answers to what people ask most, with the questions listed beside them. */
export function QuestionsPage() {
  usePageTitle(copy.questionsPage.title);
  return (
    <SplitPage
      title={copy.questionsPage.title}
      lead={
        <>
          {copy.questionsPage.lead} {copy.questionsPage.missing}{' '}
          <a href={`mailto:${SUPPORT_EMAIL}`} className="link">
            {SUPPORT_EMAIL}
          </a>{' '}
          {copy.questionsPage.orGitHub}:{' '}
          <a href={ISSUES_URL} target="_blank" rel="noreferrer" className="link">
            GitHub
          </a>
          .
        </>
      }
      aside={<PageContents entries={QUESTIONS.map((item) => ({ id: item.id, label: item.question }))} />}
    >
      <dl className="divide-y divide-line border-y border-line">
        {QUESTIONS.map((item) => (
          <div key={item.id} id={item.id} className="py-8">
            <dt className="font-display text-2xl font-semibold text-ink">{item.question}</dt>
            {item.answer.map((paragraph) => (
              <dd key={paragraph} className="mt-3 max-w-[44rem] text-lead text-ink-muted">
                <InlineText text={paragraph} />
              </dd>
            ))}
          </div>
        ))}
      </dl>
      <p className="mt-10 text-lead">
        <a href={DEMO_URL} target="_blank" rel="noreferrer" className="link">
          {copy.questionsPage.stillDeciding} <OutsideMark />
        </a>
      </p>
    </SplitPage>
  );
}
