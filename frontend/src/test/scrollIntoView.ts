import { vi } from 'vitest';

/**
 * The `scrollIntoView` calls made on `element`, oldest first.
 *
 * The stand-in for `scrollIntoView` lives on `Element.prototype` (see
 * `vitest.setup.ts`), so every element shares it: asking the stand-in alone
 * whether it was called passes when any element scrolled. This picks out the
 * calls whose `this` was `element`.
 */
export function scrollIntoViewCalls(element: Element): Parameters<Element['scrollIntoView']>[] {
  const { calls, contexts } = vi.mocked(Element.prototype.scrollIntoView).mock;
  return calls.filter((_call, index) => contexts[index] === element);
}
