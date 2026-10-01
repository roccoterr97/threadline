import { createContext } from 'react';

/** Where the sign-in state can be. */
export type AuthStatus = 'loading' | 'signed-in' | 'signed-out' | 'not-configured';

export interface AuthState {
  status: AuthStatus;
  /** The signed-in address, or null when nobody is signed in. */
  email: string | null;
  /** Asks Supabase to email a one-time sign-in link. */
  sendSignInLink: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);
