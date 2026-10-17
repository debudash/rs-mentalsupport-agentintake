import { useEffect, useRef, useState, type FormEvent } from 'react';
import { post, get } from '../lib/api';
import type { IntakeReply, QuickReply, SupportCardData } from '../lib/types';
import { CrisisPanel } from './CrisisPanel';

interface Bubble {
  role: 'client' | 'assistant';
  text: string;
}

interface Props {
  paused: boolean;
  onSupport: (card: SupportCardData) => void;
  onWithdraw: () => void;
  onDone: () => void;
  onResumed: () => void;
}

// Gentle mode's "Take a break" option: handled here, never sent as an answer.
const BREAK_VALUE = '__break__';

const PAUSE_FALLBACK =
  "Your safety matters more than finishing this. Please reach out to one of these now — they're free, confidential and available 24/7.";

export function IntakeStep({ paused, onSupport, onWithdraw, onDone, onResumed }: Props) {
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [reply, setReply] = useState<IntakeReply | null>(null);
  const [text, setText] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [crisis, setCrisis] = useState(paused);
  const [error, setError] = useState<string | null>(null);
  const [onBreak, setOnBreak] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    get<IntakeReply>('/api/intake')
      .then((first) => {
        const history = (first.transcript ?? []).map((t) => ({ role: t.role, text: t.text }));
        setBubbles([
          ...history,
          ...first.messages.map((m) => ({ role: 'assistant' as const, text: m })),
        ]);
        setReply(first);
        setCrisis(first.crisis || paused);
      })
      .catch(() => setError('We could not load the conversation. Please reload the page.'));
  }, [paused]);

  // ISSUE-003: effects must not return a value. Current Chromium's scrollIntoView() and
  // focus() return Promises, so an expression-bodied effect handed React a Promise as its
  // "cleanup" and the Step crashed. Block bodies return nothing.
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'nearest' });
  }, [bubbles]);

  async function send(body: Record<string, unknown>, shown: string | null) {
    setBusy(true);
    setError(null);
    if (shown) setBubbles((b) => [...b, { role: 'client', text: shown }]);
    try {
      const next = await post<IntakeReply>('/api/intake/messages', body);
      setBubbles((b) => [
        ...b,
        ...next.messages.map((m) => ({ role: 'assistant' as const, text: m })),
      ]);
      setReply(next);
      setSelected([]);
      if (next.support) onSupport(next.support);
      if (next.crisis) setCrisis(true);
      if (next.actions.includes('show_withdrawal')) onWithdraw();
      if (next.complete) window.setTimeout(onDone, 1200);
    } catch {
      setError("Sorry, that didn't go through. Your progress is saved — please try again.");
    } finally {
      setBusy(false);
    }
  }

  function submitText(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value) return;
    setText('');
    send({ text: value }, value);
  }

  function choose(option: QuickReply) {
    if (option.value === BREAK_VALUE) {
      setOnBreak(true);
      return;
    }
    if (reply?.input_kind === 'multichoice') {
      setSelected((s) =>
        s.includes(option.value) ? s.filter((v) => v !== option.value) : [...s, option.value],
      );
      return;
    }
    send({ item: reply?.pending_item, value: option.value }, option.label);
  }

  async function resume() {
    const resumed = await post<IntakeReply>('/api/intake/resume');
    setCrisis(false);
    setBubbles((b) => [
      ...b,
      ...resumed.messages.map((m) => ({ role: 'assistant' as const, text: m })),
    ]);
    setReply(resumed);
    onResumed();
  }

  if (onBreak) {
    return (
      <section className="notice info" aria-labelledby="break-title">
        <h2 id="break-title">Take all the time you need</h2>
        <p>
          Your progress is saved. You can stay here, step away, or close this page and come back
          later — we'll pick up where you left off.
        </p>
        <button type="button" onClick={() => setOnBreak(false)}>
          I'm ready to continue
        </button>
      </section>
    );
  }

  if (crisis) {
    return (
      <CrisisPanel
        message={reply?.messages?.[0] ?? PAUSE_FALLBACK}
        resources={reply?.crisis_resources}
        onResume={resume}
      />
    );
  }

  const multi = reply?.input_kind === 'multichoice';
  // Gentle mode's break offer arrives with the options; show it apart from the answers.
  const answers = (reply?.quick_replies ?? []).filter((q) => q.value !== BREAK_VALUE);
  const offersBreak = (reply?.quick_replies ?? []).some((q) => q.value === BREAK_VALUE);
  const labels = Object.fromEntries((reply?.quick_replies ?? []).map((q) => [q.value, q.label]));

  return (
    <section className="card" aria-label="Intake conversation">
      {reply?.scripted_mode && (
        <div className="notice warn" role="status">
          The assistant is unavailable right now, so we're using simple questions. Your answers are
          saved the same way.
        </div>
      )}
      <div className="chat" role="log" aria-live="polite" aria-label="Conversation">
        {bubbles.map((b, i) => (
          <div key={i} className={`bubble ${b.role}`}>
            <span className="sr-only">{b.role === 'assistant' ? 'Assistant: ' : 'You: '}</span>
            {b.text}
          </div>
        ))}
        <div ref={end} />
      </div>

      {reply && answers.length > 0 && !reply.complete && (
        <div
          className="quick-replies"
          role="group"
          aria-label={multi ? 'Choose any that apply' : 'Quick answers'}
        >
          {answers.map((q) => (
            <button
              key={q.value}
              type="button"
              disabled={busy}
              aria-pressed={multi ? selected.includes(q.value) : undefined}
              onClick={() => choose(q)}
            >
              {q.label}
            </button>
          ))}
          {multi && (
            <button
              type="button"
              className="secondary"
              disabled={busy || selected.length === 0}
              onClick={() =>
                send(
                  { item: reply.pending_item, value: selected.join(',') },
                  selected.map((v) => labels[v]).join(', '),
                )
              }
            >
              Done
            </button>
          )}
        </div>
      )}

      {offersBreak && !reply?.complete && (
        <p className="break-offer">
          <button type="button" className="link" onClick={() => setOnBreak(true)}>
            Take a break
          </button>
        </p>
      )}

      {reply?.actions.includes('offer_retry_assistant') && (
        <button
          type="button"
          className="link"
          disabled={busy}
          onClick={() => send({ retry_assistant: true }, null)}
        >
          Try the assistant again
        </button>
      )}

      {error && (
        <div className="notice danger" role="alert">
          {error}
        </div>
      )}

      {!reply?.complete && (
        <form className="composer" onSubmit={submitText}>
          <label htmlFor="intake-text" className="sr-only">
            Type your answer
          </label>
          <input
            id="intake-text"
            type="text"
            autoComplete="off"
            maxLength={2000}
            placeholder="Type your answer, or tap an option above"
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={busy}
          />
          <button type="submit" disabled={busy || !text.trim()}>
            Send
          </button>
        </form>
      )}
      {busy && (
        <p className="muted" role="status">
          The assistant is thinking…
        </p>
      )}
    </section>
  );
}
