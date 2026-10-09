import * as copy from '../copy/en';
import { useClipboard } from '../lib/useClipboard';
import { Button } from './Button';

interface CopyButtonProps {
  text: string;
  /** What is copied, for the accessible name: "Copy the install line". */
  what: string;
}

/** Copies `text` and says so. Pairs with a live region so the result is read out. */
export function CopyButton({ text, what }: CopyButtonProps) {
  const { state, copy: copyText } = useClipboard();
  const label =
    state === 'copied'
      ? copy.copyButton.copied
      : state === 'failed'
        ? copy.copyButton.failed
        : copy.copyButton.copy;
  return (
    <Button
      variant="secondary"
      className="shrink-0 px-3 py-1.5 text-sm"
      aria-label={copy.copyButton.label(what)}
      onClick={() => void copyText(text)}
    >
      <span aria-live="polite">{label}</span>
    </Button>
  );
}
