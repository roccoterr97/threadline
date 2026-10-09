import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { DASHBOARD_ADDRESS_KEY } from '../constants/site';
import { DEMO_URL } from '../constants/links';
import { dashboardPage, rememberForm, remembered } from '../content/dashboard';
import { DashboardPage } from './DashboardPage';

const ADDRESS = 'https://something-123abc.netlify.app';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/app']}>
      <DashboardPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
});

describe('DashboardPage', () => {
  it('explains where the dashboard lives and offers the set-up and the demo', () => {
    renderPage();
    expect(screen.getByRole('heading', { level: 1, name: dashboardPage.title })).toBeInTheDocument();
    expect(document.title).toBe(`${dashboardPage.title} – Threadline`);
    expect(screen.getByRole('link', { name: 'Set it up' })).toHaveAttribute('href', '/setup');
    expect(screen.getByRole('link', { name: 'Try the demo' })).toHaveAttribute('href', DEMO_URL);
    expect(screen.getByRole('heading', { name: 'Where do I find my address?' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'On your phone' })).toBeInTheDocument();
  });

  it('asks for nothing but a dashboard address', () => {
    renderPage();
    const fields = screen.getAllByRole('textbox');
    expect(fields).toHaveLength(1);
    expect(fields[0]).toHaveAttribute('type', 'url');
    expect(screen.getByLabelText(rememberForm.label)).toBe(fields[0]);
    expect(document.querySelector('input[type="password"], input[type="email"]')).toBeNull();
  });

  it('turns down an address that is not https and remembers nothing', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText(rememberForm.label), 'http://something.netlify.app');
    await user.click(screen.getByRole('button', { name: rememberForm.save }));
    expect(screen.getByRole('alert')).toHaveTextContent(rememberForm.problems['not-https']);
    expect(window.localStorage.getItem(DASHBOARD_ADDRESS_KEY)).toBeNull();
    expect(screen.queryByRole('link', { name: remembered.open })).not.toBeInTheDocument();
  });

  it('remembers a good address and turns it into a button', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText(rememberForm.label), ` ${ADDRESS} `);
    await user.click(screen.getByRole('button', { name: rememberForm.save }));
    const open = screen.getByRole('link', { name: remembered.open });
    expect(open).toHaveAttribute('href', ADDRESS);
    expect(open).toHaveAttribute('target', '_blank');
    expect(open).toHaveAttribute('rel', 'noreferrer');
    expect(window.localStorage.getItem(DASHBOARD_ADDRESS_KEY)).toBe(JSON.stringify(ADDRESS));
    expect(screen.queryByLabelText(rememberForm.label)).not.toBeInTheDocument();
  });

  it('shows the remembered address straight away on a later visit', () => {
    window.localStorage.setItem(DASHBOARD_ADDRESS_KEY, JSON.stringify(ADDRESS));
    renderPage();
    expect(screen.getByRole('link', { name: remembered.open })).toHaveAttribute('href', ADDRESS);
    expect(screen.getByText(ADDRESS)).toBeInTheDocument();
  });

  it('forgets the address and shows the form again', async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(DASHBOARD_ADDRESS_KEY, JSON.stringify(ADDRESS));
    renderPage();
    await user.click(screen.getByRole('button', { name: remembered.forget }));
    expect(window.localStorage.getItem(DASHBOARD_ADDRESS_KEY)).toBeNull();
    expect(screen.getByLabelText(rememberForm.label)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: remembered.open })).not.toBeInTheDocument();
  });
});
