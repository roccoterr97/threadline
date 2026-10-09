import { personFigure } from '../../content/home';
import { Plate, PLATE_FRAME } from '../Plate';

/**
 * One person's page, cropped to the name and the run of messages: the
 * "one line per person" promised above it. The caption sits beside it on a
 * wide screen.
 */
export function PersonPlate({ number }: { number: number }) {
  return (
    <Plate number={number} caption={personFigure.caption} layout="side" className="mt-14 lg:mt-20">
      <div className={`${PLATE_FRAME} aspect-[4/3] sm:aspect-[16/9]`}>
        <img
          src="/images/person.png"
          alt={personFigure.alt}
          width={2400}
          height={2568}
          loading="lazy"
          className="-mt-[12%] block h-auto w-[130%] max-w-none sm:w-[110%]"
        />
      </div>
    </Plate>
  );
}
