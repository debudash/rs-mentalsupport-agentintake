import { useCallback, useEffect, useRef, useState } from 'react';
import { post } from './lib/api';
import type { Me, StepName, SupportCardData } from './lib/types';
import { useIdle } from './lib/useIdle';
import { SupportCard } from './steps/SupportCard';
import { ConsentStep } from './steps/ConsentStep';
import { IntakeStep } from './steps/IntakeStep';
import { IdentityStep } from './steps/IdentityStep';
import { SchedulingStep } from './steps/SchedulingStep';
import { DoneStep } from './steps/DoneStep';
import { Withdrawal } from './steps/Withdrawal';

const STEPS: { id: Exclude<StepName, 'done'>; label: string }[] = [
  { id: 'consent', label: 'Consent' },
  { id: 'intake', label: 'About you' },
  { id: 'identity', label: 'Your details' },
  { id: 'scheduling', label: 'Book' },
];

interface Props {
  me: Me;
  refresh: () => Promise<void>;
  onWithdrawn: () => void;
}

export function Onboarding({ me, refresh, onWithdrawn }: Props) {
  const onboarding = me.onboarding!;
  const [support, setSupport] = useState<SupportCardData | null>(null);
  const [withdrawing, setWithdrawing] = useState(false);
  const [rescheduling, setRescheduling] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const step: StepName = rescheduling ? 'scheduling' : onboarding.step;

  // Move focus to the new Step's heading so keyboard and screen-reader users follow along.
  useEffect(() => {
    heading.current?.focus();
    setSupport(null);
  }, [step]);

  const reportIdle = useCallback(
    async (seconds: number) => {
      const result = await post<{ support: SupportCardData | null }>('/api/support/events', {
        kind: 'idle',
        step,
        idle_seconds: seconds,
      }).catch(() => ({ support: null }));
      if (result.support) setSupport(result.support);
    },
    [step],
  );
  useIdle(reportIdle, step !== 'done' && !onboarding.crisis_paused && !withdrawing, step);

  const advance = useCallback(async () => {
    setRescheduling(false);
    await refresh();
  }, [refresh]);

  if (withdrawing) {
    return <Withdrawal onCancel={() => setWithdrawing(false)} onDone={onWithdrawn} />;
  }

  const index = STEPS.findIndex((s) => s.id === step);
  const guidance = me.profile.step_guidance[step];

  return (
    <>
      <nav aria-label="Sign-up progress">
        <ol className="progress">
          {STEPS.map((s, i) => {
            const state =
              step === 'done' || onboarding.completed.includes(s.id) || i < index
                ? 'done'
                : s.id === step
                  ? 'current'
                  : 'todo';
            return (
              <li
                key={s.id}
                data-state={state}
                aria-current={state === 'current' ? 'step' : undefined}
              >
                <span aria-hidden="true">{state === 'done' ? '✓ ' : `${i + 1}. `}</span>
                {s.label}
                <span className="sr-only">
                  {state === 'done' ? ' (done)' : state === 'current' ? ' (current step)' : ''}
                </span>
              </li>
            );
          })}
        </ol>
      </nav>

      <h1 ref={heading} tabIndex={-1}>
        {step === 'done' ? "You're all set" : STEPS[index]?.label}
      </h1>
      {guidance && <p className="muted">{guidance}</p>}

      <div aria-live="polite">
        {support && <SupportCard card={support} onDismiss={() => setSupport(null)} />}
      </div>

      {step === 'consent' && <ConsentStep profile={me.profile} onDone={advance} />}
      {step === 'intake' && (
        <IntakeStep
          paused={onboarding.crisis_paused}
          onSupport={setSupport}
          onWithdraw={() => setWithdrawing(true)}
          onDone={advance}
          onResumed={refresh}
        />
      )}
      {step === 'identity' && (
        <IdentityStep
          idScanAllowed={!!me.consents?.id_scan}
          onSupport={setSupport}
          onDone={advance}
        />
      )}
      {step === 'scheduling' && <SchedulingStep onDone={advance} />}
      {step === 'done' && <DoneStep onReschedule={() => setRescheduling(true)} />}

      <p className="muted" style={{ marginTop: '2rem' }}>
        Changed your mind?{' '}
        <button type="button" className="link" onClick={() => setWithdrawing(true)}>
          Withdraw and delete everything
        </button>
      </p>
    </>
  );
}
