import type { StepName } from './lib/types';

// A small monochrome lock in the text colour: quieter than an emoji.
function Lock() {
  return (
    <svg className="trust-lock" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path
        d="M4.5 7V5a3.5 3.5 0 0 1 7 0v2h.5A1 1 0 0 1 13 8v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1zm1.5 0h4V5a2 2 0 1 0-4 0z"
        fill="currentColor"
      />
    </svg>
  );
}

// Short, factual privacy reassurance. Every sentence must stay literally true of the system:
// no compliance claims (see README "Privacy and compliance").

export const STEP_TRUST: Partial<Record<StepName, string>> = {
  consent: 'You can delete everything at any time.',
  intake: 'Only you and your clinician see your answers.',
  identity: 'Your ID photo is never stored. Your details are encrypted.',
  scheduling: 'Your clinician sees your answers, not your date of birth or address.',
};

export function StepTrust({ step }: { step: StepName }) {
  const line = STEP_TRUST[step];
  if (!line) return null;
  return (
    <p className="trust-step">
      <Lock />
      {line}
    </p>
  );
}

export function TrustFooter() {
  return (
    <footer className="trust-footer">
      <details>
        <summary>
          <Lock />
          Encrypted and used only to arrange your care.{' '}
          <span className="trust-link">How we protect it</span>
        </summary>
        <ul>
          <li>We keep only what's needed to arrange your first consultation.</li>
          <li>Your ID photo is read once and never stored.</li>
          <li>
            Your name, date of birth, address and anything you write in your own words are
            encrypted.
          </li>
          <li>
            The assistant never sees your name or ID, and phone numbers or emails you type are
            hidden from it.
          </li>
          <li>Only the clinician you book with sees your answers.</li>
          <li>You can withdraw and delete everything at any time.</li>
        </ul>
      </details>
    </footer>
  );
}
