import { useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { ApiError, post, upload } from '../lib/api';
import { prepareImage } from '../lib/imagePrep';
import type { CrisisResource, FieldName, ScanResult, SupportCardData } from '../lib/types';
import { CrisisPanel } from './CrisisPanel';

const FIELDS: { id: FieldName; api: string; label: string; hint: string }[] = [
  { id: 'name', api: 'legal_name', label: 'Full legal name', hint: 'As it appears on your ID.' },
  {
    id: 'date_of_birth',
    api: 'date_of_birth',
    label: 'Date of birth',
    hint: 'For example 1990-03-14.',
  },
  { id: 'address', api: 'address', label: 'Home address', hint: 'Street, city, state and ZIP.' },
];

type Values = Record<FieldName, string>;
type Status = Record<FieldName, 'read' | 'blank' | 'manual'>;

interface Props {
  idScanAllowed: boolean;
  onSupport: (card: SupportCardData) => void;
  onDone: () => void;
}

export function IdentityStep({ idScanAllowed, onSupport, onDone }: Props) {
  const [scanAllowed, setScanAllowed] = useState(idScanAllowed);
  const [mode, setMode] = useState<'choose' | 'review'>(idScanAllowed ? 'choose' : 'review');
  const [values, setValues] = useState<Values>({ name: '', date_of_birth: '', address: '' });
  const [original, setOriginal] = useState<Values>({ name: '', date_of_birth: '', address: '' });
  const [status, setStatus] = useState<Status>({
    name: 'manual',
    date_of_birth: 'manual',
    address: 'manual',
  });
  const [source, setSource] = useState<'scan' | 'manual'>('manual');
  const [notice, setNotice] = useState<string | null>(null);
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({});
  const [busy, setBusy] = useState(false);
  const [adultsOnly, setAdultsOnly] = useState<{
    message: string;
    resources: CrisisResource[];
  } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setBusy(true);
    setNotice(null);
    try {
      const prepared = await prepareImage(file);
      const result = await upload<ScanResult>('/api/identity/scan', prepared, 'id.jpg');
      if (result.support) onSupport(result.support);
      if (!result.accepted || !result.fields) {
        setNotice(result.message ?? 'That photo could not be used.');
        return;
      }
      const next = { ...values };
      const nextStatus = { ...status };
      for (const f of FIELDS) {
        const read = result.fields[f.id];
        next[f.id] = read.value ?? '';
        nextStatus[f.id] = read.status;
      }
      setValues(next);
      setOriginal(next);
      setStatus(nextStatus);
      setSource('scan');
      setMode('review');
      if (!Object.values(result.fields).some((f) => f.value)) {
        setNotice("We couldn't read your ID clearly, so please type your details below.");
      }
    } catch (err) {
      setNotice(
        err instanceof ApiError
          ? err.friendly
          : 'The upload failed. Please try again or type your details.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function enableScan() {
    await post('/api/consent/id-scan', { allowed: true });
    setScanAllowed(true);
    setMode('choose');
  }

  async function confirm(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      const result = await post<{
        confirmed: boolean;
        message?: string;
        crisis_resources?: CrisisResource[];
      }>('/api/identity/confirm', {
        legal_name: values.name,
        date_of_birth: values.date_of_birth,
        address: values.address,
        source,
        edited: {
          legal_name: values.name !== original.name,
          date_of_birth: values.date_of_birth !== original.date_of_birth,
          address: values.address !== original.address,
        },
      });
      if (result.confirmed) onDone();
      else
        setAdultsOnly({ message: result.message ?? '', resources: result.crisis_resources ?? [] });
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.detail &&
        typeof err.detail === 'object' &&
        'fields' in err.detail
      ) {
        setErrors((err.detail as { fields: Record<string, string> }).fields);
      } else {
        setNotice(err instanceof ApiError ? err.friendly : 'Please try again.');
      }
    } finally {
      setBusy(false);
    }
  }

  if (adultsOnly)
    return <CrisisPanel message={adultsOnly.message} resources={adultsOnly.resources} />;

  return (
    <section className="card">
      {notice && (
        <div className="notice warn" role="alert">
          {notice}
        </div>
      )}

      {mode === 'choose' && scanAllowed && (
        <>
          <h2>Use a photo of your ID</h2>
          <p className="muted">
            Lay your ID flat in good light with all four corners visible. The photo is read once and
            never stored.
          </p>
          <button type="button" disabled={busy} onClick={() => fileInput.current?.click()}>
            {busy ? 'Reading your ID…' : 'Take or choose a photo'}
          </button>
          <input
            ref={fileInput}
            id="id-photo"
            aria-label="ID photo"
            className="sr-only"
            tabIndex={-1}
            type="file"
            accept="image/*"
            capture="environment"
            onChange={onFile}
            disabled={busy}
          />
          <p style={{ marginTop: '1rem' }}>
            <button type="button" className="link" onClick={() => setMode('review')}>
              Type my details instead
            </button>
          </p>
          {busy && <p role="status">Reading your ID…</p>}
        </>
      )}

      {mode === 'review' && (
        <form onSubmit={confirm} noValidate>
          <h2>{source === 'scan' ? 'Check your details' : 'Your details'}</h2>
          <p className="muted">
            {source === 'scan'
              ? "We've filled in what we could read. Please check each field and fix anything that's wrong."
              : 'Please enter your details as they appear on your ID.'}
          </p>
          {FIELDS.map((f) => {
            const err = errors[f.api];
            const s = status[f.id];
            return (
              <div key={f.id}>
                <label htmlFor={`field-${f.id}`}>{f.label}</label>
                <input
                  id={`field-${f.id}`}
                  type="text"
                  value={values[f.id]}
                  onChange={(e) => setValues({ ...values, [f.id]: e.target.value })}
                  aria-invalid={err ? true : undefined}
                  aria-describedby={`hint-${f.id}${err ? ` error-${f.id}` : ''}`}
                  autoComplete={
                    f.id === 'name' ? 'name' : f.id === 'date_of_birth' ? 'bday' : 'street-address'
                  }
                />
                <p
                  id={`hint-${f.id}`}
                  className={`field-status ${s === 'read' ? 'read' : s === 'blank' ? 'blank' : 'muted'}`}
                >
                  {s === 'read' && '✓ Read from your ID — please check. '}
                  {s === 'blank' && "⚠ Couldn't read this — please type it. "}
                  {f.hint}
                </p>
                {err && (
                  <p id={`error-${f.id}`} className="field-error">
                    {err}
                  </p>
                )}
              </div>
            );
          })}
          <div className="row" style={{ marginTop: '1rem' }}>
            <button type="submit" disabled={busy}>
              These details are correct
            </button>
            {scanAllowed ? (
              <button type="button" className="secondary" onClick={() => setMode('choose')}>
                Use a photo instead
              </button>
            ) : (
              <button type="button" className="link" onClick={enableScan}>
                Use a photo of my ID instead
              </button>
            )}
          </div>
        </form>
      )}
    </section>
  );
}
