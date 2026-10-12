import { useState } from 'react';
import { LINKEDIN_GUIDE_URL } from '../constants/links';
import * as copy from '../copy/en';
import { readLinkedInOfferHidden, rememberLinkedInOfferHidden } from '../lib/linkedInOfferHidden';
import { Button } from './Button';
import { buttonClasses } from './buttonStyles';

const text = copy.linkedInOffer;

/**
 * A small card offering to add LinkedIn, which a full set-up leaves for later.
 *
 * The page decides whether LinkedIn is missing; the card only remembers, on
 * this browser, that the owner hid it.
 */
export function LinkedInOffer() {
  const [hidden, setHidden] = useState(readLinkedInOfferHidden);

  if (hidden) return null;

  return (
    <section
      aria-labelledby="linkedin-offer-title"
      className="flex flex-col gap-3 rounded-token-lg border border-line bg-surface p-4"
    >
      <div>
        <h2 id="linkedin-offer-title" className="font-semibold text-ink">
          {text.title}
        </h2>
        <p className="mt-1 text-sm text-ink-muted">{text.body}</p>
      </div>
      <div className="text-sm text-ink">
        <p>{text.commandIntro}</p>
        <code className="mt-1 block overflow-x-auto rounded-token-md bg-neutral-soft px-3 py-2 font-mono">
          {text.command}
        </code>
      </div>
      <div className="flex flex-wrap gap-3">
        <a
          href={LINKEDIN_GUIDE_URL}
          target="_blank"
          rel="noreferrer"
          className={buttonClasses('primary')}
        >
          {text.guide}
          <span className="sr-only"> {text.guideNewTab}</span>
        </a>
        <Button
          aria-label={text.hideLabel}
          onClick={() => {
            rememberLinkedInOfferHidden();
            setHidden(true);
          }}
        >
          {text.hide}
        </Button>
      </div>
    </section>
  );
}
