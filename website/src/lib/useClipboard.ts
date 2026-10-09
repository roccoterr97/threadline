import { useCallback, useEffect, useRef, useState } from 'react';
import { COPIED_SHOWN_MS } from '../constants/site';

export type CopyState = 'idle' | 'copied' | 'failed';

/**
 * Copies text to the clipboard and says for a moment whether it worked. A
 * browser without clipboard access (an old one, or an insecure page) reports
 * "failed" so the reader knows to select the text by hand.
 */
export function useClipboard(): { state: CopyState; copy: (text: string) => Promise<void> } {
  const [state, setState] = useState<CopyState>('idle');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current !== null) clearTimeout(timer.current);
    };
  }, []);

  const copy = useCallback(async (text: string) => {
    let next: CopyState = 'failed';
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard !== undefined) {
        await navigator.clipboard.writeText(text);
        next = 'copied';
      }
    } catch {
      next = 'failed';
    }
    setState(next);
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = setTimeout(() => setState('idle'), COPIED_SHOWN_MS);
  }, []);

  return { state, copy };
}
