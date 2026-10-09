import { DEMO_URL } from '../../constants/links';
import { hero } from '../../content/home';
import { ButtonLink } from '../ButtonLink';
import { Showcase } from './Showcase';

/** The opening: the line and the two ways in on one side, the product itself on the other. */
export function Hero() {
  return (
    <section className="grid items-center gap-12 pt-8 pb-16 sm:pt-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] lg:gap-[clamp(3rem,5vw,6rem)] lg:pt-16 lg:pb-28">
      <div>
        <h1 className="text-display text-ink">{hero.title}</h1>
        <p className="mt-6 max-w-[34rem] text-lead text-ink">{hero.lead}</p>
        <div className="mt-8 flex flex-wrap gap-3">
          <ButtonLink to={DEMO_URL} className="px-5 py-3">
            {hero.demo}
          </ButtonLink>
          <ButtonLink to="/setup" variant="secondary" className="px-5 py-3">
            {hero.setup}
          </ButtonLink>
        </div>
        <p className="label mt-5">{hero.small}</p>
      </div>
      <Showcase number={1} />
    </section>
  );
}
