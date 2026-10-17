import { useState, type FormEvent } from 'react';
import type { SupabaseClient } from '@supabase/supabase-js';

export function SignIn({ supabase }: { supabase: SupabaseClient }) {
  const [mode, setMode] = useState<'sign-up' | 'sign-in'>('sign-up');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const { error } =
      mode === 'sign-up'
        ? await supabase.auth.signUp({ email, password })
        : await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) setMessage(error.message);
  }

  return (
    <section className="card" aria-labelledby="signin-title">
      <h1 id="signin-title">{mode === 'sign-up' ? 'Start your sign-up' : 'Welcome back'}</h1>
      <p className="muted">
        Signing up takes about 10 to 15 minutes. Your progress is saved as you go, so you can stop
        and come back at any time.
      </p>
      <form onSubmit={submit} noValidate>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          autoComplete={mode === 'sign-up' ? 'new-password' : 'current-password'}
          required
          minLength={8}
          aria-describedby="password-hint"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <p id="password-hint" className="muted">
          At least 8 characters.
        </p>
        {message && (
          <div className="notice danger" role="alert">
            {message}
          </div>
        )}
        <div className="row">
          <button type="submit" disabled={busy}>
            {mode === 'sign-up' ? 'Create account' : 'Sign in'}
          </button>
          <button
            type="button"
            className="link"
            onClick={() => setMode(mode === 'sign-up' ? 'sign-in' : 'sign-up')}
          >
            {mode === 'sign-up' ? 'I already have an account' : 'Create a new account'}
          </button>
        </div>
      </form>
    </section>
  );
}
