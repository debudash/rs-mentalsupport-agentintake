import { useEffect, useRef, useState } from 'react';
import { get } from '../lib/api';

interface BookingRow {
  id: string;
  starts_at: string;
  format: 'video' | 'in_person';
  reference: string;
}

interface Detail {
  booking_id: string;
  starts_at: string;
  format: string;
  reference: string;
  client_first_name: string | null;
  safety_flag?: boolean;
  assessment: Record<string, { question: string; answer: string }>;
}

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  });

export function ClinicianView() {
  const [rows, setRows] = useState<BookingRow[] | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const detailHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    get<{ clinician: string | null; bookings: BookingRow[] }>('/api/clinician/bookings')
      .then((r) => {
        setRows(r.bookings);
        setName(r.clinician);
      })
      .catch(() => setError('We could not load your consultations.'));
  }, []);

  useEffect(() => {
    detailHeading.current?.focus(); // ISSUE-003: block body, see IntakeStep
  }, [detail]);

  async function open(id: string) {
    try {
      setDetail(await get<Detail>(`/api/clinician/bookings/${id}`));
    } catch {
      setError('You do not have access to that consultation.');
    }
  }

  return (
    <>
      <h1>Upcoming initial consultations{name ? ` — ${name}` : ''}</h1>
      <p className="muted">
        You can see only clients booked with you. Every time you open a client's answers, the view
        is recorded in the access log.
      </p>
      {error && (
        <div className="notice danger" role="alert">
          {error}
        </div>
      )}
      <div className="grid">
        <section className="card" aria-labelledby="list-title">
          <h2 id="list-title">Consultations</h2>
          {rows === null && <p role="status">Loading…</p>}
          {rows?.length === 0 && <p>No consultations booked yet.</p>}
          <ul>
            {rows?.map((r) => (
              <li key={r.id}>
                <button type="button" className="link" onClick={() => open(r.id)}>
                  {when(r.starts_at)} · {r.format === 'video' ? 'Video' : 'In person'} ·{' '}
                  {r.reference}
                </button>
              </li>
            ))}
          </ul>
        </section>
        {detail && (
          <section className="card" aria-labelledby="detail-title">
            <h2 id="detail-title" ref={detailHeading} tabIndex={-1}>
              {detail.client_first_name ?? 'Client'} · {when(detail.starts_at)}
            </h2>
            {detail.safety_flag && (
              <p className="notice danger" role="alert">
                ⚠ <strong>Safety:</strong> this Client answered yes to the safety question (thoughts
                of harming themselves or someone else). They were shown crisis resources and chose
                to continue. Follow your risk protocol before the consultation.
              </p>
            )}
            <dl>
              {Object.entries(detail.assessment).map(([key, qa]) => (
                <div key={key} style={{ marginBottom: '0.6rem' }}>
                  <dt className="muted">{qa.question}</dt>
                  <dd style={{ margin: 0 }}>
                    <strong>
                      {qa.answer === 'prefer_not_to_say' ? 'Prefer not to say' : qa.answer}
                    </strong>
                  </dd>
                </div>
              ))}
            </dl>
            <p className="muted">
              Date of birth and address are not shown here; you only see what you need.
            </p>
          </section>
        )}
      </div>
    </>
  );
}
