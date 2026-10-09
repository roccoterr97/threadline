import { remembered } from '../../content/dashboard';
import { buttonClasses } from '../buttonStyles';
import { Button } from '../Button';
import { OutsideMark } from '../OutsideMark';

interface RememberedDashboardProps {
  address: string;
  onForget: () => void;
}

/** The remembered address as one big button to the reader's dashboard, and a quiet way to forget it. */
export function RememberedDashboard({ address, onForget }: RememberedDashboardProps) {
  return (
    <section
      aria-labelledby="remembered-heading"
      className="rounded-token-md border border-line bg-surface p-5 sm:p-6"
    >
      <h2 id="remembered-heading" className="text-xl text-ink">
        {remembered.heading}
      </h2>
      <p className="mt-2 break-all text-sm text-ink-muted">{address}</p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <a
          href={address}
          target="_blank"
          rel="noreferrer"
          className={buttonClasses('primary', 'px-6 py-3 text-lg')}
        >
          {remembered.open}
          <OutsideMark />
        </a>
        <Button variant="quiet" onClick={onForget}>
          {remembered.forget}
        </Button>
      </div>
      <p className="mt-3 text-sm text-ink-muted">{remembered.note}</p>
    </section>
  );
}
