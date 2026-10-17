import { useEffect, useRef, useState } from 'react';
import { post } from '../lib/api';

interface Receipt {
  reference: string;
  deleted_at: string;
  deleted: string[];
}

export function Withdrawal({ onCancel, onDone }: { onCancel: () => void; onDone: () => void }) {
  const [confirmed, setConfirmed] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    heading.current?.focus(); // ISSUE-003: block body, see IntakeStep
  }, [receipt]);

  async function withdraw() {
    setBusy(true);
    try {
      setReceipt(await post<Receipt>('/api/withdraw', { confirm: true }));
    } catch {
      setError('We could not complete the deletion. Please try again in a moment.');
    } finally {
      setBusy(false);
    }
  }

  if (receipt) {
    return (
      <section className="card" aria-labelledby="receipt-title">
        <h1 id="receipt-title" ref={heading} tabIndex={-1}>
          Everything has been deleted
        </h1>
        <p>
          Deletion reference <strong>{receipt.reference}</strong>, completed{' '}
          {new Date(receipt.deleted_at).toLocaleString()}.
        </p>
        <ul>
          {receipt.deleted.map((item) => (
            <li key={item}>✓ {item}</li>
          ))}
        </ul>
        <p className="muted">
          We keep only a record that you withdrew consent, with this reference and no personal
          details. If you need help in the future, you're always welcome back.
        </p>
        <button type="button" onClick={onDone}>
          Finish
        </button>
      </section>
    );
  }

  return (
    <section className="card" aria-labelledby="withdraw-title">
      <h1 id="withdraw-title" ref={heading} tabIndex={-1}>
        Withdraw and delete everything
      </h1>
      <p>This permanently deletes:</p>
      <ul>
        <li>Your answers to the intake questions and the conversation</li>
        <li>Your name, date of birth and address</li>
        <li>Your booking (the time is released for someone else)</li>
        <li>Your sign-up progress and your account</li>
      </ul>
      <p className="muted">This can't be undone. Your ID photo was never stored.</p>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        <span>I understand everything above will be deleted.</span>
      </label>
      {error && (
        <div className="notice danger" role="alert">
          {error}
        </div>
      )}
      <div className="row" style={{ marginTop: '1rem' }}>
        <button type="button" className="danger" disabled={!confirmed || busy} onClick={withdraw}>
          Delete everything
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Keep my sign-up
        </button>
      </div>
    </section>
  );
}
