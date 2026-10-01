import { useContext } from 'react';
import { AuthContext, type AuthState } from './AuthContext';

/**
 * The sign-in state.
 *
 * @throws {Error} when used outside `AuthProvider` — a programming mistake, not
 *   something a user can cause.
 */
export function useAuth(): AuthState {
  const state = useContext(AuthContext);
  if (state === null) {
    throw new Error('useAuth was used outside AuthProvider');
  }
  return state;
}
