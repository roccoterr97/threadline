import { useState, type ReactNode } from 'react';
import { saveConnection } from '../lib/savedConnection';
import { isConfigured } from '../lib/supabaseClient';
import { ConnectPage } from './ConnectPage';
import type { StartupState } from './connectionStartup';
import { SwitchDatabasePage } from './SwitchDatabasePage';

interface ConnectionGateProps {
  /** How the page started (`startConnection`). */
  startup: StartupState;
  /** The dashboard, shown once the page knows its database. */
  children: ReactNode;
}

/**
 * Shows the dashboard only once the page knows which database to open: it
 * first asks before switching databases, and on the shared dashboard with no
 * database yet it asks for the personal link. A dashboard with `config.js`,
 * a build with its settings compiled in, and the demo go straight through.
 */
export function ConnectionGate({ startup, children }: ConnectionGateProps) {
  const [state, setState] = useState<StartupState>(startup);
  const ready = () => {
    setState({ kind: 'ready' });
  };

  if (state.kind === 'confirm-switch') {
    return (
      <SwitchDatabasePage
        current={state.current}
        incoming={state.incoming}
        onSwitch={() => {
          saveConnection(state.incoming);
          ready();
        }}
        onKeep={ready}
      />
    );
  }

  if (!isConfigured()) {
    return (
      <ConnectPage
        openedWithBrokenLink={state.kind === 'invalid-link'}
        onConnected={(settings) => {
          saveConnection(settings);
          ready();
        }}
      />
    );
  }

  return <>{children}</>;
}
