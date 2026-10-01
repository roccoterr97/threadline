import { useId, useState } from 'react';
import * as copy from '../copy/en';
import { previewMessage } from '../domain/timeline';

interface MessageBodyProps {
  body: string;
}

const TOGGLE_CLASS_NAME =
  'mt-1 inline-flex min-h-11 items-center font-medium text-accent underline underline-offset-2 hover:text-accent-hover';

/**
 * The text of one message. A long one starts folded to its opening lines, with
 * a "Show more" button that unfolds it; a short one is shown whole, with no
 * button at all.
 */
export function MessageBody({ body }: MessageBodyProps) {
  const textId = useId();
  const [expanded, setExpanded] = useState(false);
  const { preview, isFolded } = previewMessage(body);

  return (
    <div className="mt-2">
      <p id={textId} className="whitespace-pre-line break-words text-ink">
        {expanded || !isFolded ? body : preview}
      </p>
      {isFolded && (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={textId}
          className={TOGGLE_CLASS_NAME}
          onClick={() => {
            setExpanded((current) => !current);
          }}
        >
          {expanded ? copy.person.showLess : copy.person.showMore}
        </button>
      )}
    </div>
  );
}
