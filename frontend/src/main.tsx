import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode, type ReactElement } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import { AuthProvider } from './auth/AuthProvider';
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
async function prepareDemo(): Promise<ReactElement | null> {
  if (import.meta.env.VITE_DEMO !== 'true') return null;
  const { startDemo } = await import('./demo/startDemo');
  return startDemo(systemClock);
}

const demoBanner = await prepareDemo();
const queryClient = createQueryClient();

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          {demoBanner}
          <App />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
