import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import { AuthProvider } from './auth/AuthProvider';
import { ConnectionGate } from './connect/ConnectionGate';
import {
  restartOnNewLink,
  startConnection,
  type StartupState,
} from './connect/connectionStartup';
import type { DemoParts } from './demo/startDemo';
import './index.css';
import { systemClock } from './lib/clock';
import { createQueryClient } from './lib/queryClient';

const rootElement = document.getElementById('root');
if (rootElement === null) {
  throw new Error('The page is missing its root element');
}

/**
 * Switches to the demo's invented data when the build flag asks for it. The
 * flag is fixed at build time, so a normal build drops this branch and never
 * ships the demo code at all.
 */
async function prepareDemo(): Promise<DemoParts | null> {
  if (import.meta.env.VITE_DEMO !== 'true') return null;
  const { startDemo } = await import('./demo/startDemo');
  return startDemo(systemClock);
}

const demo = await prepareDemo();
// Before anything starts the database client, which also reads the address.
const startup: StartupState = demo === null ? startConnection() : { kind: 'ready' };
if (demo === null) restartOnNewLink();
const queryClient = createQueryClient();

createRoot(rootElement).render(
  <StrictMode>
    <ConnectionGate startup={startup}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BrowserRouter>
            <App banner={demo?.banner} signInPage={demo?.signInPage} />
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ConnectionGate>
  </StrictMode>,
);
