import { z } from 'zod';
import { describe, expect, it } from 'vitest';
import {
  DataUnavailableError,
  NotAllowedError,
  NotSignedInError,
  RefusalReason,
  RefusedError,
  TableMissingError,
  UnexpectedDataError,
} from '../lib/errors';
import { runMutation, runQuery, type SupabaseResult } from './client';

const schema = z.array(z.object({ id: z.string() }));

function answer(result: Partial<SupabaseResult>): () => Promise<SupabaseResult> {
  return () => Promise.resolve({ data: null, error: null, ...result });
}

describe('runQuery', () => {
  it('returns the rows when they match the expected shape', async () => {
    const rows = await runQuery('test', schema, answer({ data: [{ id: 'a' }] }));
    expect(rows).toEqual([{ id: 'a' }]);
  });

  it('raises a "not signed in" error on a 401', async () => {
    await expect(
      runQuery('test', schema, answer({ error: { message: 'no' }, status: 401 })),
    ).rejects.toBeInstanceOf(NotSignedInError);
  });

  it('raises a "not allowed" error on a 403, because the person is signed in', async () => {
    const failure = runQuery('test', schema, answer({ error: { message: 'no' }, status: 403 }));
    await expect(failure).rejects.toBeInstanceOf(NotAllowedError);
    await expect(failure).rejects.not.toBeInstanceOf(NotSignedInError);
  });

  it('raises a "not signed in" error when the token has expired', async () => {
    await expect(
      runQuery('test', schema, answer({ error: { message: 'jwt expired', code: 'PGRST301' } })),
    ).rejects.toBeInstanceOf(NotSignedInError);
  });

  it('raises a "data unavailable" error for any other refusal', async () => {
    await expect(
      runQuery('test', schema, answer({ error: { message: 'boom' }, status: 500 })),
    ).rejects.toBeInstanceOf(DataUnavailableError);
  });

  it('says which kind of unavailable a table the database does not have is', async () => {
    const missing = answer({ error: { message: 'no table', code: 'PGRST205' }, status: 404 });
    const failure = runQuery('test', schema, missing);
    await expect(failure).rejects.toBeInstanceOf(TableMissingError);
    await expect(failure).rejects.toBeInstanceOf(DataUnavailableError);
    await expect(
      runQuery('test', schema, answer({ error: { message: 'no relation', code: '42P01' } })),
    ).rejects.toBeInstanceOf(TableMissingError);
  });

  it('raises a "data unavailable" error when the request itself threw', async () => {
    await expect(
      runQuery('test', schema, () => Promise.reject(new Error('offline'))),
    ).rejects.toBeInstanceOf(DataUnavailableError);
  });

  it('refuses data that does not match the expected shape', async () => {
    await expect(
      runQuery('test', schema, answer({ data: [{ id: 42 }] })),
    ).rejects.toBeInstanceOf(UnexpectedDataError);
  });

  it('never puts the database’s own words in the error it raises', async () => {
    const failure = runQuery(
      'test',
      schema,
      answer({ error: { message: 'relation people does not exist' }, status: 500 }),
    );
    await expect(failure).rejects.toThrow('test');
    await expect(failure).rejects.not.toThrow('relation people does not exist');
  });
});

describe('runMutation', () => {
  it('resolves when the write went through', async () => {
    await expect(runMutation('test', answer({}))).resolves.toBeUndefined();
  });

  it('raises a "not allowed" error, not a "signed out" one, when the write was forbidden', async () => {
    const failure = runMutation('test', answer({ error: { message: 'denied' }, status: 403 }));
    await expect(failure).rejects.toBeInstanceOf(NotAllowedError);
    await expect(failure).rejects.not.toBeInstanceOf(NotSignedInError);
  });

  it('raises a "not signed in" error when the write came without a valid session', async () => {
    await expect(
      runMutation('test', answer({ error: { message: 'no' }, status: 401 })),
    ).rejects.toBeInstanceOf(NotSignedInError);
  });

  it('raises a "data unavailable" error when the write was refused', async () => {
    await expect(
      runMutation('test', answer({ error: { message: 'conflict' }, status: 409 })),
    ).rejects.toBeInstanceOf(DataUnavailableError);
  });

  it.each([
    ['23503', RefusalReason.InUse],
    ['23514', RefusalReason.BreaksRule],
    ['23505', RefusalReason.Duplicate],
  ])('names the reason when Postgres refuses with %s', async (code, reason) => {
    const refusal = runMutation(
      'test',
      answer({ error: { message: 'violates constraint "secret_name"', code }, status: 409 }),
    );
    await expect(refusal).rejects.toBeInstanceOf(RefusedError);
    await expect(refusal).rejects.toMatchObject({ reason, constraint: 'secret_name' });
    await expect(refusal).rejects.not.toHaveProperty('message', expect.stringContaining('secret'));
  });

  it('leaves the rule unnamed when the refusal does not name one', async () => {
    const refusal = runMutation(
      'test',
      answer({ error: { message: 'at most 8 categories', code: '23514' }, status: 400 }),
    );
    await expect(refusal).rejects.toMatchObject({ constraint: null });
  });
});
