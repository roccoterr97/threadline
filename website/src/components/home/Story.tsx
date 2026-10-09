import { story } from '../../content/home';
import { PersonPlate } from './PersonPlate';

/** How it works: three moments on one thread drawn across the page, then one person's line as it really looks. */
export function Story() {
  return (
    <section aria-labelledby="story" className="py-16 lg:py-24">
      <h2 id="story" className="label">
        <span className="label-number">{story.number}</span>
        {story.heading}
      </h2>
      <ol className="thread-across mt-10">
        {story.moments.map((moment) => (
          <li key={moment.title}>
            <h3 className="text-2xl text-ink lg:text-3xl">{moment.title}</h3>
            <p className="mt-3 max-w-[30rem] text-lead text-ink-muted">{moment.text}</p>
          </li>
        ))}
      </ol>
      <PersonPlate number={2} />
    </section>
  );
}
