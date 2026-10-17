import { useCallback, useEffect, useState } from 'react';
import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js';
import { ApiError, get, setTokenProvider } from './lib/api';
import type { Me } from './lib/types';
import { Banner } from './Banner';
import { SignIn } from './SignIn';
import { TrustFooter } from './Trust';
import { Onboarding } from './Onboarding';
import { ClinicianView } from './staff/ClinicianView';
import { Dashboard } from './staff/Dashboard';

export default function App() {
  const [supabase, setSupabase] = useState<SupabaseClient | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<{ supabase_url: string; supabase_anon_key: string }>('/api/config')
      .then(({ supabase_url, supabase_anon_key }) => {
        if (!supabase_url || !supabase_anon_key) {
          setError('Sign-in is not configured yet. Please try again later.');
          return;
        }
        const client = createClient(supabase_url, supabase_anon_key);
        setTokenProvider(
          async () => (await client.auth.getSession()).data.session?.access_token ?? null,
        );
        client.auth.getSession().then(({ data }) => setSession(data.session));
        client.auth.onAuthStateChange((_event, next) => setSession(next));
        setSupabase(client);
      })
      .catch(() => setError('We could not reach the service. Please check your connection.'));
  }, []);

  const signOut = useCallback(async () => {
    await supabase?.auth.signOut();
    setMe(null);
  }, [supabase]);

  const refresh = useCallback(async () => {
    try {
      setMe(await get<Me>('/api/me'));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) await signOut();
      else setError('We could not load your progress. Please reload the page.');
    }
  }, [signOut]);

  useEffect(() => {
    if (session) refresh();
    else setMe(null);
  }, [session, refresh]);

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Banner compact={!!session} onSignOut={session ? signOut : undefined} />
      <main id="main" className={me && me.role !== 'client' ? 'wide' : undefined}>
        {error && (
          <div className="notice danger" role="alert">
            {error}
          </div>
        )}
        {!error && supabase && !session && <SignIn supabase={supabase} />}
        {me?.role === 'client' && <Onboarding me={me} refresh={refresh} onWithdrawn={signOut} />}
        {me?.role === 'clinician' && <ClinicianView />}
        {me?.role === 'operator' && <Dashboard />}
        {session && !me && !error && <p aria-live="polite">Loading your progress…</p>}
      </main>
      {/* Clients and people signing up; staff screens don't need it. */}
      {(!me || me.role === 'client') && <TrustFooter />}
    </>
  );
}
