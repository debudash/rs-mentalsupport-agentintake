import { useEffect, useState } from 'react';
import { download, get, timeZone } from '../lib/api';
import type { BookingView } from '../lib/types';

export function DoneStep({ onReschedule }: { onReschedule: () => void }) {
  const [booking, setBooking] = useState<BookingView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<{ booking: BookingView }>(`/api/bookings/current?tz=${encodeURIComponent(timeZone())}`)
      .then((r) => setBooking(r.booking))
      .catch(() => setError('We could not load your booking. Please reload the page.'));
  }, []);

  async function saveCalendar() {
    const blob = await download('/api/bookings/current/ics');
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'initial-consultation.ics';
    link.click();
    URL.revokeObjectURL(url);
  }

  if (error) return <div className="notice danger">{error}</div>;
  if (!booking) return <p role="status">Loading your booking…</p>;

  return (
    <section className="notice ok" aria-labelledby="booked-title">
      <h2 id="booked-title">✓ Your initial consultation is booked</h2>
      <p>
        <strong>
          {booking.local_label} {booking.time_zone}
        </strong>{' '}
        with {booking.clinician}, {booking.format === 'video' ? 'by video' : 'in person'} (
        {booking.minutes} minutes).
      </p>
      <p>
        Booking reference <strong>{booking.reference}</strong>. Your clinician will see your answers
        before you meet, so you won't need to repeat yourself.
      </p>
      <div className="row">
        <button type="button" onClick={saveCalendar}>
          Add to my calendar
        </button>
        <button type="button" className="secondary" onClick={onReschedule}>
          Choose a different time
        </button>
      </div>
    </section>
  );
}
