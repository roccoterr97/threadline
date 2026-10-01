import axe from 'axe-core';
import { expect } from 'vitest';

/**
 * Fails the test if axe finds an accessibility violation in `container`.
 *
 * The colour-contrast rule is turned off because jsdom does not lay the page
 * out or resolve CSS variables, so it cannot measure contrast; the two themes
 * are checked against the token values in `theme/tokens.css` instead.
 */
export async function expectNoAxeViolations(container: HTMLElement): Promise<void> {
  const results = await axe.run(container, {
    rules: { 'color-contrast': { enabled: false } },
  });

  const summary = results.violations.map(
    (violation) => `${violation.id}: ${violation.help} (${violation.nodes.length} node(s))`,
  );

  expect(summary).toEqual([]);
}
