import { useId, useState, type FormEvent } from 'react';
import { rememberForm } from '../../content/dashboard';
import { rememberDashboardAddress } from '../../lib/dashboardAddress';
import { Button } from '../Button';

interface DashboardAddressFormProps {
  /** Called with the cleaned address once it is remembered. */
  onRemembered: (address: string) => void;
}

/** One field for the reader's own dashboard address, checked before it is remembered. */
export function DashboardAddressForm({ onRemembered }: DashboardAddressFormProps) {
  const inputId = useId();
  const hintId = `${inputId}-hint`;
  const problemId = `${inputId}-problem`;
  const [value, setValue] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = rememberDashboardAddress(value);
    if (!result.ok) {
      setProblem(rememberForm.problems[result.problem]);
      return;
    }
    setProblem(null);
    onRemembered(result.address);
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="rounded-token-md border border-line bg-surface p-5 sm:p-6">
      <h2 className="text-xl text-ink">{rememberForm.heading}</h2>
      <label htmlFor={inputId} className="mt-4 block font-medium text-ink">
        {rememberForm.label}
      </label>
      <p id={hintId} className="mt-1 text-sm text-ink-muted">
        {rememberForm.hint}
      </p>
      <div className="mt-3 flex flex-col gap-3 sm:flex-row lg:flex-col 2xl:flex-row">
        <input
          id={inputId}
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder={rememberForm.placeholder}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-describedby={problem === null ? hintId : `${hintId} ${problemId}`}
          aria-invalid={problem !== null}
          className="min-w-0 flex-1 rounded-token-sm border border-line-strong bg-surface px-3 py-2.5 text-ink placeholder:text-ink-muted"
        />
        <Button type="submit">{rememberForm.save}</Button>
      </div>
      {problem !== null && (
        <p id={problemId} role="alert" className="mt-2 text-sm text-danger">
          {problem}
        </p>
      )}
    </form>
  );
}
