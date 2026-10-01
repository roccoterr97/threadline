import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { fieldClassName, LabelledField } from '../components/LabelledField';
import { LoadingState } from '../components/LoadingState';
import * as copy from '../copy/en';
import { useAuth } from './useAuth';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type FormState =
  | { kind: 'idle' }
  | { kind: 'sending' }
  | { kind: 'sent'; email: string }
  | { kind: 'error'; message: string };

/** The only page a signed-out visitor can reach. */
export function LoginPage() {
  const { status, sendSignInLink } = useAuth();
  const [email, setEmail] = useState('');
  const [form, setForm] = useState<FormState>({ kind: 'idle' });

  if (status === 'not-configured') {
    return (
      <main className="mx-auto max-w-prose px-4 py-10">
        <EmptyState title={copy.states.errorTitle} body={copy.states.notConfigured} />
      </main>
    );
  }

  if (status === 'loading') {
    return (
      <main className="mx-auto max-w-prose px-4 py-10">
        <LoadingState label={copy.login.checkingSession} />
      </main>
    );
  }

  if (status === 'signed-in') return <Navigate to="/" replace />;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const address = email.trim();
    if (!EMAIL_PATTERN.test(address)) {
      setForm({ kind: 'error', message: copy.login.invalidEmail });
      return;
    }

    setForm({ kind: 'sending' });
    try {
      await sendSignInLink(address);
      setForm({ kind: 'sent', email: address });
    } catch {
      // The real reason is already logged; the owner only needs to know to retry.
      setForm({ kind: 'error', message: copy.login.failed });
    }
  }

  return (
    <main className="mx-auto max-w-prose px-4 py-10">
      <h1 className="text-2xl font-semibold text-ink">{copy.login.title}</h1>
      <p className="mt-2 text-ink-muted">{copy.login.intro}</p>

      {form.kind === 'sent' ? (
        <p role="status" className="mt-6 rounded-token-lg border border-positive bg-positive-soft p-4 text-positive">
          {copy.login.sent(form.email)}
        </p>
      ) : (
        <form
          // The browser's own validation message is not plain English, so the
          // form checks the address itself and says it in its own words.
          noValidate
          className="mt-6 flex flex-col gap-4"
          onSubmit={(event) => void handleSubmit(event)}
        >
          <LabelledField label={copy.login.emailLabel}>
            {(id) => (
              <>
                <input
                  id={id}
                  type="email"
                  name="email"
                  autoComplete="email"
                  className={fieldClassName}
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                  }}
                  aria-describedby={`${id}-hint`}
                />
                <p id={`${id}-hint`} className="text-sm text-ink-muted">
                  {copy.login.emailHint}
                </p>
              </>
            )}
          </LabelledField>

          {form.kind === 'error' && (
            <p role="alert" className="text-danger">
              {form.message}
            </p>
          )}

          <Button type="submit" variant="primary" disabled={form.kind === 'sending'}>
            {form.kind === 'sending' ? copy.login.submitting : copy.login.submit}
          </Button>
        </form>
      )}
    </main>
  );
}
