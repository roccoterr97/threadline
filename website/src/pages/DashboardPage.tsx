import { useState } from 'react';
import { ButtonLink } from '../components/ButtonLink';
import { DashboardAddressForm } from '../components/dashboard/DashboardAddressForm';
import { RememberedDashboard } from '../components/dashboard/RememberedDashboard';
import { SplitPage, SplitSection } from '../components/SplitPage';
import { DEMO_URL } from '../constants/links';
import { dashboardPage, notSetUp, onYourPhone, whereToFind } from '../content/dashboard';
import { forgetDashboardAddress, readDashboardAddress } from '../lib/dashboardAddress';
import { usePageTitle } from '../lib/usePageTitle';

/** The way to the reader's own dashboard: the address on one side, where to find it and more on the other. */
export function DashboardPage() {
  usePageTitle(dashboardPage.title);
  const [address, setAddress] = useState<string | null>(readDashboardAddress);

  function forget() {
    forgetDashboardAddress();
    setAddress(null);
  }

  return (
    <SplitPage
      title={dashboardPage.title}
      lead={dashboardPage.intro.join(' ')}
      aside={
        address === null ? (
          <DashboardAddressForm onRemembered={setAddress} />
        ) : (
          <RememberedDashboard address={address} onForget={forget} />
        )
      }
    >
      <SplitSection heading={whereToFind.heading}>
        <p className="text-ink-muted">{whereToFind.intro}</p>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-lead text-ink marker:text-ink-muted">
          {whereToFind.places.map((place) => (
            <li key={place}>{place}</li>
          ))}
        </ol>
      </SplitSection>

      <SplitSection heading={onYourPhone.heading}>
        <p className="text-lead text-ink-muted">{onYourPhone.intro}</p>
        <dl className="mt-4 divide-y divide-line border-y border-line">
          {onYourPhone.steps.map((step) => (
            <div key={step.device} className="gap-6 py-3.5 sm:grid sm:grid-cols-[10rem_minmax(0,1fr)]">
              <dt className="font-medium text-ink">{step.device}</dt>
              <dd className="text-ink-muted">{step.how}</dd>
            </div>
          ))}
        </dl>
      </SplitSection>

      <SplitSection heading={notSetUp.heading}>
        <p className="text-lead text-ink-muted">{notSetUp.body}</p>
        <div className="mt-5 flex flex-wrap gap-3">
          <ButtonLink to="/setup">{notSetUp.setup}</ButtonLink>
          <ButtonLink to={DEMO_URL} variant="secondary">
            {notSetUp.demo}
          </ButtonLink>
        </div>
      </SplitSection>
    </SplitPage>
  );
}
