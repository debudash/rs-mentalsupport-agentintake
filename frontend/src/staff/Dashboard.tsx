import { useCallback, useEffect, useState } from 'react';
import { get } from '../lib/api';

interface Target {
  name: string;
  target_p95_ms: number;
  count: number;
  p50_ms: number | null;
  p95_ms: number | null;
  meets_target: boolean | null;
}

interface DashboardData {
  window_hours: number;
  generated_at: string;
  performance: {
    targets: Target[];
    endpoints: { endpoint: string; count: number; p50_ms: number | null; p95_ms: number | null }[];
    requests: number;
    server_errors: number;
  };
  llm_health: {
    messages: number;
    llm_calls: number;
    failures: number;
    failure_rate: number | null;
    outcomes: Record<string, number>;
    fallback_to_scripted: number;
    output_check_trips: number;
    llm_p50_ms: number | null;
    llm_p95_ms: number | null;
    providers: Record<string, number>;
    intents: Record<string, number | string>;
  };
  ai_quality: Record<string, Record<string, unknown>>;
  safety_and_privacy: { crisis_pauses: number | string; withdrawals: number | string };
}

const NAMES: Record<string, string> = { chat: 'Chat reply', ocr: 'ID reading', booking: 'Booking' };
const ms = (v: number | null) =>
  v === null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`;
const pct = (v: unknown) => (typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : '—');

function Verdict({ ok }: { ok: boolean | null | undefined }) {
  if (ok === null || ok === undefined) return <span className="badge na">No data</span>;
  return ok ? (
    <span className="badge ok">✓ Meets target</span>
  ) : (
    <span className="badge bad">✗ Misses target</span>
  );
}

export function Dashboard() {
  const [hours, setHours] = useState(24);
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await get<DashboardData>(`/api/operator/dashboard?hours=${hours}`));
      setError(null);
    } catch {
      setError('We could not load the dashboard.');
    }
  }, [hours]);

  useEffect(() => {
    load();
  }, [load]);

  const ocr = data?.ai_quality.ocr as
    | {
        golden?: { overall_accuracy: number };
        held_out?: { overall_accuracy: number };
        fabricated_fields?: number;
        engine?: string;
        created_at?: string;
      }
    | undefined;
  const intent = data?.ai_quality.intent as
    | {
        overall_pass_rate?: number;
        per_intent?: Record<string, number>;
        model?: string;
        provider?: string;
        unambiguous_crisis_always_pauses?: boolean;
        created_at?: string;
      }
    | undefined;

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h1>Onboarding operations</h1>
        <div className="row">
          <label htmlFor="window" style={{ margin: 0 }}>
            Window
          </label>
          <select id="window" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            <option value={1}>Last hour</option>
            <option value={24}>Last 24 hours</option>
            <option value={168}>Last 7 days</option>
          </select>
          <button type="button" className="secondary" onClick={load}>
            Refresh
          </button>
        </div>
      </div>
      <p className="muted">
        Aggregate figures only. No individual client's data appears here; counts under 5 are shown
        as "&lt;5".
      </p>
      {error && (
        <div className="notice danger" role="alert">
          {error}
        </div>
      )}
      {!data && !error && <p role="status">Loading…</p>}
      {data && (
        <>
          <h2>Performance</h2>
          <div className="grid">
            {data.performance.targets.map((t) => (
              <section className="card" key={t.name} aria-label={`${NAMES[t.name]} performance`}>
                <h3>{NAMES[t.name]}</h3>
                <div className="stat">{ms(t.p95_ms)}</div>
                <p className="muted">
                  p95 · target under {ms(t.target_p95_ms)} · p50 {ms(t.p50_ms)} · {t.count} requests
                </p>
                <Verdict ok={t.meets_target} />
              </section>
            ))}
          </div>

          <h2>AI health</h2>
          <div className="grid">
            <section className="card" aria-label="LLM calls">
              <h3>LLM calls</h3>
              <div className="stat">{data.llm_health.llm_calls}</div>
              <p className="muted">
                {data.llm_health.failures} failures ({pct(data.llm_health.failure_rate)}) · LLM p95{' '}
                {ms(data.llm_health.llm_p95_ms)}
              </p>
            </section>
            <section className="card" aria-label="Safety nets">
              <h3>Safety nets</h3>
              <p>
                Fell back to scripted questions:{' '}
                <strong>{data.llm_health.fallback_to_scripted}</strong>
                <br />
                Unsafe replies replaced: <strong>{data.llm_health.output_check_trips}</strong>
                <br />
                Crisis pauses: <strong>{data.safety_and_privacy.crisis_pauses}</strong>
                <br />
                Withdrawals: <strong>{data.safety_and_privacy.withdrawals}</strong>
              </p>
            </section>
            <section className="card" aria-label="Model in use">
              <h3>Model in use</h3>
              {Object.keys(data.llm_health.providers).length === 0 && (
                <p className="muted">No LLM calls yet.</p>
              )}
              <ul>
                {Object.entries(data.llm_health.providers).map(([p, n]) => (
                  <li key={p}>
                    {p}: {n}
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <section className="card" aria-labelledby="outcomes-title">
            <h3 id="outcomes-title">Intake message outcomes</h3>
            <table>
              <thead>
                <tr>
                  <th scope="col">Outcome</th>
                  <th scope="col">Count</th>
                  <th scope="col">Share</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.llm_health.outcomes).map(([k, v]) => (
                  <tr key={k}>
                    <td>{k}</td>
                    <td>{v}</td>
                    <td style={{ width: '40%' }}>
                      <div className="bar-track" aria-hidden="true">
                        <div
                          className="bar"
                          style={{ width: `${(100 * v) / Math.max(1, data.llm_health.messages)}%` }}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <h2>AI quality (latest eval)</h2>
          <div className="grid">
            <section className="card" aria-label="OCR accuracy">
              <h3>ID reading accuracy</h3>
              {ocr ? (
                <>
                  <div className="stat">{pct(ocr.golden?.overall_accuracy)}</div>
                  <p className="muted">
                    golden set · held-out {pct(ocr.held_out?.overall_accuracy)} · fabricated fields{' '}
                    {ocr.fabricated_fields ?? '—'} · {ocr.engine}
                  </p>
                  <Verdict ok={(ocr.golden?.overall_accuracy ?? 0) >= 0.9} />
                </>
              ) : (
                <p className="muted">No eval recorded yet. Run make eval-record.</p>
              )}
            </section>
            <section className="card" aria-label="Intent handling">
              <h3>Intent handling</h3>
              {intent ? (
                <>
                  <div className="stat">{pct(intent.overall_pass_rate)}</div>
                  <p className="muted">
                    {intent.provider}/{intent.model} · crisis always pauses:{' '}
                    {intent.unambiguous_crisis_always_pauses ? 'yes' : 'no'}
                  </p>
                  <ul>
                    {Object.entries(intent.per_intent ?? {}).map(([k, v]) => (
                      <li key={k}>
                        {k}: {pct(v)}
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="muted">No eval recorded yet.</p>
              )}
            </section>
          </div>

          <section className="card" aria-labelledby="endpoints-title">
            <h3 id="endpoints-title">All endpoints</h3>
            <table>
              <thead>
                <tr>
                  <th scope="col">Endpoint</th>
                  <th scope="col">Requests</th>
                  <th scope="col">p50</th>
                  <th scope="col">p95</th>
                </tr>
              </thead>
              <tbody>
                {data.performance.endpoints.map((e) => (
                  <tr key={e.endpoint}>
                    <td>{e.endpoint}</td>
                    <td>{e.count}</td>
                    <td>{ms(e.p50_ms)}</td>
                    <td>{ms(e.p95_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted">
              {data.performance.requests} requests · {data.performance.server_errors} server errors
              · updated {new Date(data.generated_at).toLocaleTimeString()}
            </p>
          </section>
        </>
      )}
    </>
  );
}
