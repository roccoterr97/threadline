import { useEffect, useRef, useState, type ReactNode } from 'react';

/** Whether the frame hides content, and whether some is still past its end. */
interface Edges {
  /** True when the content is wider than the frame at all. */
  overflows: boolean;
  atEnd: boolean;
}

const NO_OVERFLOW: Edges = { overflows: false, atEnd: true };

/** A scroll position within this many pixels of an edge counts as touching it. */
const EDGE_SLACK = 1;

function measureEdges(frame: HTMLElement): Edges {
  const hidden = frame.scrollWidth - frame.clientWidth;
  if (hidden <= EDGE_SLACK) return NO_OVERFLOW;
  return { overflows: true, atEnd: frame.scrollLeft >= hidden - EDGE_SLACK };
}

const END_FADE =
  'pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-surface to-transparent';

interface SidewaysScrollProps {
  /** Said under the content while it is wider than the screen, e.g. "Scroll sideways…". */
  hint: string;
  children: ReactNode;
}

/**
 * A frame for content wider than a phone screen, such as a table with many
 * columns. The content scrolls sideways inside it (the page itself never
 * does). While some of it is still past the frame's end, that edge fades out
 * and a line of text under it says to scroll sideways, so a cut-off column
 * never looks like the end. Only the end fades: the start may hold a column
 * pinned in place, which must stay readable. On a screen wide enough,
 * nothing extra is drawn.
 */
export function SidewaysScroll({ hint, children }: SidewaysScrollProps) {
  const frame = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState<Edges>(NO_OVERFLOW);

  useEffect(() => {
    const element = frame.current;
    if (element === null) return;
    const measure = () => {
      setEdges(measureEdges(element));
    };
    measure();
    const resized = new ResizeObserver(measure);
    resized.observe(element);
    for (const child of element.children) resized.observe(child);
    element.addEventListener('scroll', measure, { passive: true });
    return () => {
      resized.disconnect();
      element.removeEventListener('scroll', measure);
    };
  }, []);

  return (
    <div>
      <div className="relative">
        <div ref={frame} className="overflow-x-auto">
          {children}
        </div>
        {!edges.atEnd && <div aria-hidden="true" className={END_FADE} />}
      </div>
      {edges.overflows && <p className="px-3 py-2 text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}
