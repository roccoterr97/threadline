import { describe, expect, it } from 'vitest';
import * as copy from '../copy/en';
import { DataUnavailableError, NotSignedInError, RefusalReason, RefusedError } from '../lib/errors';
import { categoryEditFailureText } from './useCategoryEditor';

describe('categoryEditFailureText', () => {
  it.each([
    [new RefusedError(RefusalReason.BreaksRule, 'x'), copy.categorySettings.failed.breaksRule],
    [new RefusedError(RefusalReason.Duplicate, 'x'), copy.categorySettings.failed.duplicate],
    [new RefusedError(RefusalReason.InUse, 'x'), copy.categorySettings.failed.generic],
    [new NotSignedInError('x'), copy.categorySettings.failed.signedOut],
    [new DataUnavailableError('x'), copy.categorySettings.failed.generic],
  ])('explains %o in plain words', (error, text) => {
    expect(categoryEditFailureText(error)).toBe(text);
  });
});
