import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';
import { Button } from '../components/Button';
import { LoadingState } from '../components/LoadingState';
import * as copy from '../copy/en';
import { usePageTitle } from '../hooks/usePageTitle';
import { DemoBanner } from './DemoBanner';
import { DEMO_OWNER_EMAIL } from './demoData';

const text = copy.demo.signedOut;

/**
 * The demo's sign-in page, in place of the real "e-mail me a link" form.
 *
 * Asking the demo stand-in for a link signs the visitor in at once (see
 * `demoClient.ts`), so one button is all it takes and no address is typed.
 */
export function DemoSignIn() {
  usePageTitle(copy.login.title);
  const { status, sendSignInLink } = useAuth();
  const [state, setState] = useState<'idle' | 'signing-in' | 'failed'>('idle');

  if (status === 'signed-in') return <Navigate to="/" replace />;

  const signIn = async () => {
    setState('signing-in');
    try {
      await sendSignInLink(DEMO_OWNER_EMAIL);
    } catch {
      // The stand-in never refuses; this only guards against a broken build.
      setState('failed');
    }
  };

  return (
    <>
      <DemoBanner />
      <main className="mx-auto max-w-prose px-4 py-10">
        {status === 'loading' ? (
          <LoadingState label={copy.login.checkingSession} />
        ) : (
          <>
            <h1 className="text-2xl font-semibold text-ink">{text.title}</h1>
            <p className="mt-2 text-ink-muted">{text.body}</p>
            {state === 'failed' && (
              <p role="alert" className="mt-4 text-danger">
                {text.failed}
              </p>
            )}
            <Button
              variant="primary"
              className="mt-6"
              disabled={state === 'signing-in'}
              onClick={() => {
                void signIn();
              }}
            >
              {state === 'signing-in' ? text.signingIn : text.signIn}
            </Button>
          </>
        )}
      </main>
    </>
  );
}
