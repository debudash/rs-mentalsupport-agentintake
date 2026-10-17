import { useState, type FormEvent } from 'react';
import { ApiError, post } from '../lib/api';
import type { ProfileSummary } from '../lib/types';

export function ConsentStep({ profile, onDone }: { profile: ProfileSummary; onDone: () => void }) {
  const [onboarding, setOnboarding] = useState(false);
  const [idScan, setIdScan] = useState(false);
  const [adult, setAdult] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { consents, service } = profile;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await post('/api/consent', { onboarding, id_scan: idScan, age_confirmed: adult });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.friendly : 'Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit} aria-describedby="consent-intro">
      <p id="consent-intro">
        Before we start, here's what we collect and why. You're in control: you can withdraw and
        delete everything at any time.
      </p>

      <fieldset>
        <legend>
          <strong>{consents.onboarding.title}</strong> (required)
        </legend>
        <p className="muted">{consents.onboarding.text}</p>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={onboarding}
            onChange={(e) => setOnboarding(e.target.checked)}
          />
          <span>I agree to my onboarding data being stored to arrange my consultation.</span>
        </label>
      </fieldset>

      <fieldset>
        <legend>
          <strong>{consents.id_scan.title}</strong>
        </legend>
        <p className="muted">{consents.id_scan.text}</p>
        <label className="checkbox">
          <input type="checkbox" checked={idScan} onChange={(e) => setIdScan(e.target.checked)} />
          <span>Yes, read a photo of my ID to fill in my details.</span>
        </label>
      </fieldset>

      <fieldset>
        <legend>
          <strong>Age</strong> (required)
        </legend>
        <label className="checkbox">
          <input type="checkbox" checked={adult} onChange={(e) => setAdult(e.target.checked)} />
          <span>I'm {service.minimum_age} or older.</span>
        </label>
      </fieldset>

      {error && (
        <div className="notice danger" role="alert">
          {error}
        </div>
      )}
      <button type="submit" disabled={busy || !onboarding || !adult}>
        Agree and continue
      </button>
      {(!onboarding || !adult) && (
        <p className="muted">To continue, tick the two required boxes.</p>
      )}
    </form>
  );
}
