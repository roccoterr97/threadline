import { useEffect, useRef, useState } from 'react';

/**
 * Moves the keyboard to the first field marked `aria-invalid` after a form was
 * turned down, so the owner lands where the problem is instead of on a
 * button far below it.
 *
 * Call `afterCheck()` each time the form is checked; the focus moves once the
 * marks from that check are on screen.
 */
export function useFocusFirstInvalid<T extends HTMLElement>() {
  const container = useRef<T>(null);
  const [checks, setChecks] = useState(0);

  useEffect(() => {
    if (checks === 0) return;
    container.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
  }, [checks]);

  return {
    container,
    afterCheck: () => {
      setChecks((count) => count + 1);
    },
  };
}
