import { useState } from 'react';
import { ApiError, post } from '../lib/api';

// The one post-booking question (Net Promoter Score). One tap, skippable, asked once.
export function Feedback() {
  const [state, setState] = useState<'ask' | 'thanks' | 'skipped'>('ask');
  const [busy, setBusy] = useState(false);

  async function answer(score: number) {
    setBusy(true);
    try {
      await post('/api/feedback', { score });
      setState('thanks');
    } catch (err) {
      // Already answered (e.g. another tab): treat it as done, never as an error.
      setState(err instanceof ApiError && err.status === 409 ? 'thanks' : 'skipped');
    } finally {
      setBusy(false);
    }
  }

  if (state === 'skipped') return null;
  if (state === 'thanks') {
    return (
      <p className="feedback-thanks" role="status">
        Thank you for telling us.
      </p>
    );
  }
  return (
    <fieldset className="feedback">
      <legend>
        How likely are you to recommend signing up with us to someone who needs similar support?
      </legend>
      <div className="feedback-scale" role="group" aria-describedby="feedback-ends">
        {Array.from({ length: 11 }, (_, n) => (
          <button
            key={n}
            type="button"
            className="secondary"
            disabled={busy}
            aria-label={`${n} out of 10`}
            onClick={() => answer(n)}
          >
            {n}
          </button>
        ))}
      </div>
      <p id="feedback-ends" className="muted">
        0 = not at all likely, 10 = extremely likely ·{' '}
        <button type="button" className="link" onClick={() => setState('skipped')}>
          Skip
        </button>
      </p>
    </fieldset>
  );
}
