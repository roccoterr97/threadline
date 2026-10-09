import { showcase } from '../../content/home';
import { Plate, PLATE_FRAME } from '../Plate';

/**
 * The people list on a laptop, with the phone version laid over its corner:
 * the product itself, beside the opening line.
 */
export function Showcase({ number }: { number: number }) {
  return (
    <Plate number={number} caption={showcase.caption} className="lg:mt-0">
      <div className="relative pb-[9%] pl-[15%]">
        <picture className={`${PLATE_FRAME} block`}>
          <source srcSet="/images/people-list-dark.png" media="(prefers-color-scheme: dark)" />
          <img
            src="/images/people-list.png"
            alt={showcase.desktopAlt}
            width={2400}
            height={1516}
            fetchPriority="high"
            className="block h-auto w-full"
          />
        </picture>
        <img
          src="/images/people-list-phone.png"
          alt={showcase.phoneAlt}
          width={780}
          height={1688}
          className={`${PLATE_FRAME} absolute bottom-0 left-0 h-auto w-[24%] rounded-[1rem] shadow-[0_0_0_6px_var(--tracker-bg)]`}
        />
      </div>
    </Plate>
  );
}
