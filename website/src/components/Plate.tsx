import type { ReactNode } from 'react';

interface PlateProps {
  number: number;
  caption: string;
  /** Under the picture, or beside it on a wide screen. */
  layout?: 'below' | 'side';
  className?: string;
  /** The picture or pictures, each already framed. */
  children: ReactNode;
}

const LAYOUTS = {
  below: { figure: '', caption: 'label mt-3 flex gap-1', number: 'label-number shrink-0' },
  side: {
    figure: 'lg:grid lg:grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)] lg:items-end lg:gap-12',
    caption: 'label mt-3 flex gap-1 lg:mt-0 lg:block lg:max-w-[22rem] lg:text-base lg:leading-relaxed',
    number: 'label-number shrink-0 lg:mb-1 lg:block',
  },
} as const;

/** A picture of the real product, set like a plate in a book: framed, numbered, captioned. */
export function Plate({ number, caption, layout = 'below', className = 'mt-6', children }: PlateProps) {
  const style = LAYOUTS[layout];
  return (
    <figure className={`${style.figure} ${className}`.trim()}>
      <div className="min-w-0">{children}</div>
      <figcaption className={style.caption}>
        <span className={style.number}>Fig. {number}</span>
        <span>{caption}</span>
      </figcaption>
    </figure>
  );
}

/** The thin frame every screenshot sits in. */
export const PLATE_FRAME = 'overflow-hidden rounded-token-md border border-line bg-surface';
