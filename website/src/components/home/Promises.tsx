import { needs, promises } from '../../content/home';

const HEADING = 'label';

/** What stays yours, and what the set-up needs: side by side on a wide screen. */
export function Promises() {
  return (
    <section className="rule-node grid gap-14 py-16 lg:grid-cols-2 lg:gap-[clamp(3rem,6vw,8rem)] lg:py-24">
      <div>
        <h2 className={HEADING}>
          <span className="label-number">{promises.number}</span>
          {promises.heading}
        </h2>
        <ul className="mt-6 divide-y divide-line border-y border-line">
          {promises.lines.map((line) => (
            <li key={line} className="py-5 text-lead text-ink">
              {line}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h2 className={HEADING}>
          <span className="label-number">{needs.number}</span>
          {needs.heading}
        </h2>
        <dl className="mt-6 divide-y divide-line border-y border-line">
          {needs.items.map(([what, detail]) => (
            <div key={what} className="gap-6 py-4 sm:grid sm:grid-cols-[12rem_minmax(0,1fr)]">
              <dt className="font-medium text-ink">{what}</dt>
              <dd className="text-ink-muted">{detail}</dd>
            </div>
          ))}
        </dl>
        <p className="label mt-4">{needs.time}</p>
      </div>
    </section>
  );
}
