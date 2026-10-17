import { useCallback, useEffect, useState } from 'react';
import { ApiError, get, post, timeZone } from '../lib/api';
import type { SlotView } from '../lib/types';

interface SlotsResponse {
  slots: SlotView[];
  filtered: boolean;
}

const FORMAT = { video: 'Video', in_person: 'In person' } as const;

// The server's local label is "Tue 20 Oct, 10:00 AM": the day is everything before the comma.
const dayOf = (s: SlotView) => s.local_label.split(',')[0];

export function SchedulingStep({ onDone }: { onDone: () => void }) {
  const [slots, setSlots] = useState<SlotView[] | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [chosen, setChosen] = useState<SlotView | null>(null);
  const [day, setDay] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (all: boolean) => {
    const tz = encodeURIComponent(timeZone());
    const data = await get<SlotsResponse>(`/api/slots?tz=${tz}&show_all=${all}`);
    setSlots(data.slots);
  }, []);

  useEffect(() => {
    load(showAll).catch(() => setMessage('We could not load available times. Please reload.'));
  }, [load, showAll]);

  async function book() {
    if (!chosen) return;
    setBusy(true);
    setMessage(null);
    try {
      await post('/api/bookings', { slot_id: chosen.id, tz: timeZone() });
      onDone();
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        typeof err.detail === 'object' &&
        err.detail
      ) {
        const detail = err.detail as { message: string; alternatives: SlotView[] };
        setMessage(detail.message);
        setSlots(detail.alternatives);
        setChosen(null);
      } else {
        setMessage(err instanceof ApiError ? err.friendly : 'Please try again.');
      }
    } finally {
      setBusy(false);
    }
  }

  // One day at a time keeps the Book button in view, even on a phone.
  const days = [...new Set((slots ?? []).map(dayOf))];
  const activeDay = day && days.includes(day) ? day : days[0];
  const visible = (slots ?? []).filter((s) => dayOf(s) === activeDay);

  return (
    <section className="card" aria-labelledby="slots-title">
      <h2 id="slots-title">Choose a time for your free initial consultation</h2>
      <p className="muted">
        Times are shown in your time zone ({timeZone()}).{' '}
        {!showAll && 'We matched these to your preferences.'}
      </p>
      {message && (
        <div className="notice warn" role="alert">
          {message}
        </div>
      )}
      {slots === null && <p role="status">Loading available times…</p>}
      {slots && slots.length === 0 && (
        <p>No times match your preferences in the next two weeks. Try showing all times.</p>
      )}
      {slots && slots.length > 0 && (
        <div className="quick-replies" role="group" aria-label="Choose a day">
          {days.map((d) => (
            <button key={d} type="button" aria-pressed={d === activeDay} onClick={() => setDay(d)}>
              {d}
            </button>
          ))}
        </div>
      )}
      {slots && slots.length > 0 && (
        <fieldset>
          <legend className="sr-only">Available times on {activeDay}</legend>
          <ul className="slots">
            {visible.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  aria-pressed={chosen?.id === s.id}
                  onClick={() => setChosen(s)}
                  style={
                    chosen?.id === s.id
                      ? { borderColor: 'var(--brand)', borderWidth: 3 }
                      : undefined
                  }
                >
                  <strong>{s.local_label}</strong> {s.time_zone}
                  <br />
                  <span className="muted">
                    {s.clinician} · {FORMAT[s.format]}
                  </span>
                  {chosen?.id === s.id && <span className="sr-only"> (selected)</span>}
                </button>
              </li>
            ))}
          </ul>
        </fieldset>
      )}
      <div className="row" style={{ marginTop: '1rem' }}>
        <button type="button" disabled={!chosen || busy} onClick={book}>
          {chosen ? `Book ${chosen.local_label}` : 'Choose a time above'}
        </button>
        <button type="button" className="link" onClick={() => setShowAll(!showAll)}>
          {showAll ? 'Show times that match my preferences' : 'Show all times'}
        </button>
      </div>
    </section>
  );
}
