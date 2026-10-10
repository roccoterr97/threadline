import { useId, useState } from 'react';
import { Button } from '../components/Button';
import { fieldClassName, LabelledField } from '../components/LabelledField';
import * as copy from '../copy/en';
import { usePageTitle } from '../hooks/usePageTitle';
import { parsePastedLink } from '../lib/connectLink';
import type { SupabaseSettings } from '../lib/runtimeConfig';

interface ConnectPageProps {
  /** The page was opened with a link that is not complete. */
  openedWithBrokenLink: boolean;
  /** Called with the database a pasted link names. */
  onConnected: (settings: SupabaseSettings) => void;
}

/**
 * The shared dashboard's first page in a browser that has never opened a
 * personal link: it says where the link is, and takes a pasted one.
 */
export function ConnectPage({ openedWithBrokenLink, onConnected }: ConnectPageProps) {
  usePageTitle(copy.connect.title);
  const [pasted, setPasted] = useState('');
  const [invalid, setInvalid] = useState(false);
  const errorId = useId();

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const settings = parsePastedLink(pasted);
    if (settings === null) {
      setInvalid(true);
      return;
    }
    onConnected(settings);
  }

  return (
    <main className="mx-auto max-w-prose px-4 py-10">
      <h1 className="text-2xl font-semibold text-ink">{copy.connect.title}</h1>
      <p className="mt-2 text-ink">{copy.connect.intro}</p>
      <p className="mt-2 text-ink-muted">{copy.connect.shared}</p>
      {openedWithBrokenLink && (
        <p role="alert" className="mt-4 text-danger">
          {copy.connect.invalidOpened}
        </p>
      )}
      <form noValidate className="mt-6 flex flex-col gap-4" onSubmit={handleSubmit}>
        <LabelledField label={copy.connect.linkLabel}>
          {(id) => (
            <>
              <input
                id={id}
                type="url"
                name="personal-link"
                autoComplete="off"
                spellCheck={false}
                className={fieldClassName}
                value={pasted}
                onChange={(event) => {
                  setPasted(event.target.value);
                  setInvalid(false);
                }}
                aria-invalid={invalid || undefined}
                aria-describedby={invalid ? `${errorId} ${id}-hint` : `${id}-hint`}
              />
              <p id={`${id}-hint`} className="text-sm text-ink-muted">
                {copy.connect.linkHint}
              </p>
            </>
          )}
        </LabelledField>
        {invalid && (
          <p id={errorId} role="alert" className="text-danger">
            {copy.connect.invalidPasted}
          </p>
        )}
        <Button type="submit" variant="primary">
          {copy.connect.submit}
        </Button>
      </form>
    </main>
  );
}
