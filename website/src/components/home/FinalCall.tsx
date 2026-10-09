import { Link } from 'react-router-dom';
import { DEMO_URL, GUIDE_URL } from '../../constants/links';
import { finalCall } from '../../content/home';
import { ButtonLink } from '../ButtonLink';
import { OutsideMark } from '../OutsideMark';

/** The last word, across the full width: the question on one side, the two ways in on the other. */
export function FinalCall() {
  return (
    <section
      aria-labelledby="ready"
      className="rule-node grid items-end gap-8 pt-14 pb-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:gap-16 lg:pt-20"
    >
      <div>
        <h2 id="ready" className="text-title text-ink">
          {finalCall.heading}
        </h2>
        <p className="mt-3 text-lead text-ink-muted">{finalCall.text}</p>
      </div>
      <div className="lg:text-right">
        <div className="flex flex-wrap items-center gap-3 lg:justify-end">
          <ButtonLink to="/setup" className="px-5 py-3">
            {finalCall.setup}
          </ButtonLink>
          <ButtonLink to={DEMO_URL} variant="secondary" className="px-5 py-3">
            {finalCall.demo}
          </ButtonLink>
        </div>
        <p className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-sm lg:justify-end">
          <Link to="/questions" className="link">
            {finalCall.questions}
          </Link>
          <a href={GUIDE_URL} target="_blank" rel="noreferrer" className="link inline-flex items-center gap-1">
            {finalCall.guide}
            <OutsideMark />
          </a>
        </p>
      </div>
    </section>
  );
}
