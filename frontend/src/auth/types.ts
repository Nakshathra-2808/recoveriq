import { User, Session } from '@supabase/supabase-js';

export interface UserProfile {
  user_id: string;
  email: string;
  merchant_id: string;
  merchant_name: string;
  role: 'owner' | 'admin' | 'operator' | 'viewer' | string;
}

export interface AuthState {
  user: User | null;
  session: Session | null;
  profile: UserProfile | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  error: string | null;
}

export interface AuthContextType extends AuthState {
  signInWithPassword: (email: string, password: string) => Promise<{ error: Error | null }>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}
