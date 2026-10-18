import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Onboarding } from '../Onboarding';
import { SignIn } from '../SignIn';
import { DoneStep } from '../steps/DoneStep';
import { ClinicianView } from '../staff/ClinicianView';
import { Dashboard } from '../staff/Dashboard';
import { ErrorBoundary } from '../ErrorBoundary';
import type { Me, OnboardingState } from '../lib/types';
import { axe } from './axe';
import { mockFetch } from './fetchMock';

const me = (onboarding: OnboardingState): Me => ({
  role: 'client',
  profile: {
    service: { name: 'Riverside Counseling', consultation_minutes: 30, minimum_age: 18 },
    consents: {
      onboarding: { version: '1', title: 'Onboarding data', required: true, text: 'We store.' },
      id_scan: { version: '1', title: 'ID scan', required: false, text: 'We read.' },
    },
    step_guidance: { consent: 'About a minute.' },
    crisis: { resources: [{ label: '988', href: 'tel:988' }], pause_message: 'Safety first.' },
    contact: { phone: '555', email: 'a@b.c', hours: '9-5' },
  },
  onboarding,
  consents: { onboarding: false, id_scan: false, age_confirmed: false },
});

const booking = {
  id: 'b',
  reference: 'REF1',
  starts_at: '',
  local_label: 'Tuesday 20 October, 10:00 AM',
  time_zone: 'EDT',
  format: 'video',
  clinician: 'Ana Rivera',
  minutes: 30,
};

describe('Onboarding shell', () => {
  it('shows progress with the current step marked, guidance, and withdrawal', async () => {
    mockFetch({});
    const { container } = render(
      <Onboarding
        me={me({ step: 'consent', completed: [], crisis_paused: false })}
        refresh={vi.fn()}
        onWithdrawn={vi.fn()}
      />,
    );
    const progress = screen.getByRole('navigation', { name: /sign-up progress/i });
    expect(progress.querySelector('[aria-current="step"]')).toHaveTextContent('Consent');
    expect(screen.getByText('About a minute.')).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(screen.getByRole('button', { name: /withdraw and delete everything/i }));
    expect(
      screen.getByRole('heading', { name: /withdraw and delete everything/i }),
    ).toBeInTheDocument();
  });

  it('done state shows every step as done and the booking', async () => {
    mockFetch({ 'GET /api/bookings/current': () => ({ json: { booking } }) });
    render(
      <Onboarding
        me={me({
          step: 'done',
          completed: ['consent', 'intake', 'identity', 'scheduling'],
          crisis_paused: false,
        })}
        refresh={vi.fn()}
        onWithdrawn={vi.fn()}
      />,
    );
    expect(await screen.findByText('REF1')).toBeInTheDocument();
    expect(screen.getAllByText('(done)')).toHaveLength(4);
  });
});

describe('DoneStep', () => {
  it('offers rescheduling', async () => {
    mockFetch({
      'GET /api/bookings/current': () => ({
        json: { booking: { ...booking, format: 'in_person' } },
      }),
    });
    const onReschedule = vi.fn();
    render(<DoneStep onReschedule={onReschedule} />);
    await userEvent.click(await screen.findByRole('button', { name: /different time/i }));
    expect(onReschedule).toHaveBeenCalled();
    expect(screen.getByText(/in person/)).toBeInTheDocument();
  });
});

describe('SignIn', () => {
  it('signs up, switches to sign-in, and shows auth errors', async () => {
    const signUp = vi.fn().mockResolvedValue({ error: null });
    const signInWithPassword = vi
      .fn()
      .mockResolvedValue({ error: { message: 'Invalid login credentials' } });
    const supabase = { auth: { signUp, signInWithPassword } } as never;
    const { container } = render(<SignIn supabase={supabase} />);
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.type(screen.getByLabelText('Email'), 'a@b.co');
    await userEvent.type(screen.getByLabelText('Password'), 'longenough');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(signUp).toHaveBeenCalledWith({ email: 'a@b.co', password: 'longenough' });
    await userEvent.click(screen.getByRole('button', { name: /already have an account/i }));
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid login credentials');
  });
});

describe('ClinicianView', () => {
  it('lists own consultations and opens one without DOB or address', async () => {
    mockFetch({
      'GET /api/clinician/bookings': () => ({
        json: {
          clinician: 'Ana Rivera',
          bookings: [
            { id: 'b1', starts_at: '2026-10-20T14:00:00Z', format: 'video', reference: 'R1' },
          ],
        },
      }),
      'GET /api/clinician/bookings/b1': () => ({
        json: {
          booking_id: 'b1',
          starts_at: '2026-10-20T14:00:00Z',
          format: 'video',
          reference: 'R1',
          client_first_name: 'Jane',
          assessment: {
            reason_category: { question: 'What brings you here?', answer: 'Anxiety or worry' },
          },
        },
      }),
    });
    const { container } = render(<ClinicianView />);
    await userEvent.click(await screen.findByRole('button', { name: /R1/ }));
    expect(await screen.findByText('Anxiety or worry')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Jane/ })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('flags a Client who answered yes to the Safety question', async () => {
    // ISSUE-015 — found by the whole-codebase review: the Safety answer never reached the
    // Clinician.
    mockFetch({
      'GET /api/clinician/bookings': () => ({
        json: {
          clinician: 'Ana Rivera',
          bookings: [
            { id: 'b1', starts_at: '2026-10-20T14:00:00Z', format: 'video', reference: 'R1' },
          ],
        },
      }),
      'GET /api/clinician/bookings/b1': () => ({
        json: {
          booking_id: 'b1',
          starts_at: '2026-10-20T14:00:00Z',
          format: 'video',
          reference: 'R1',
          client_first_name: 'Jane',
          safety_flag: true,
          assessment: { safety: { question: 'Any thoughts of harming yourself?', answer: 'Yes' } },
        },
      }),
    });
    const { container } = render(<ClinicianView />);
    await userEvent.click(await screen.findByRole('button', { name: /R1/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/answered yes to the safety/i);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe('Dashboard', () => {
  it('shows performance verdicts, AI health and eval quality', async () => {
    mockFetch({
      'GET /api/operator/dashboard': () => ({
        json: {
          window_hours: 24,
          generated_at: '2026-10-16T12:00:00Z',
          performance: {
            targets: [
              {
                name: 'chat',
                target_p95_ms: 3000,
                count: 50,
                p50_ms: 900,
                p95_ms: 1800,
                meets_target: true,
              },
              {
                name: 'ocr',
                target_p95_ms: 8000,
                count: 0,
                p50_ms: null,
                p95_ms: null,
                meets_target: null,
              },
              {
                name: 'booking',
                target_p95_ms: 1000,
                count: 5,
                p50_ms: 80,
                p95_ms: 1200,
                meets_target: false,
              },
            ],
            endpoints: [
              { endpoint: 'POST /api/intake/messages', count: 50, p50_ms: 900, p95_ms: 1800 },
            ],
            requests: 60,
            server_errors: 0,
          },
          llm_health: {
            messages: 50,
            llm_calls: 40,
            failures: 2,
            failure_rate: 0.05,
            outcomes: { llm_ok: 38, 'llm_failure:timeout': 2 },
            fallback_to_scripted: 2,
            output_check_trips: 1,
            llm_p50_ms: 800,
            llm_p95_ms: 1500,
            providers: { 'anthropic/claude-opus-5-5': 40 },
            intents: { 'provide-details': 30 },
          },
          ai_quality: {
            ocr: {
              golden: { overall_accuracy: 0.989 },
              held_out: { overall_accuracy: 0.933 },
              fabricated_fields: 0,
              engine: 'tesseract 5.5.0',
            },
          },
          safety_and_privacy: { crisis_pauses: '<5', withdrawals: 0 },
          funnel: [
            {
              event: 'signed_up',
              reached: 20,
              drop_off_pct: null,
              median_minutes_from_previous: null,
            },
            {
              event: 'consent_completed',
              reached: 18,
              drop_off_pct: 10,
              median_minutes_from_previous: 1.5,
            },
            {
              event: 'intake_completed',
              reached: 12,
              drop_off_pct: 33.3,
              median_minutes_from_previous: 6,
            },
            {
              event: 'identity_completed',
              reached: 10,
              drop_off_pct: 16.7,
              median_minutes_from_previous: 2,
            },
            {
              event: 'booked',
              reached: '<5',
              drop_off_pct: null,
              median_minutes_from_previous: null,
            },
          ],
          nps: {
            responses: 12,
            promoters_pct: 58.3,
            passives_pct: 25,
            detractors_pct: 16.7,
            nps: 42,
          },
          friction_by_step: [
            { step: 'intake', kind: 'long_pause', count: 7 },
            { step: 'identity', kind: 'upload_problem', count: '<5' },
          ],
          ocr_corrections: [
            { field: 'legal_name', reviews: 8, prefilled_pct: 100, blank_pct: 0, edited_pct: 12.5 },
            {
              field: 'date_of_birth',
              reviews: 8,
              prefilled_pct: 87.5,
              blank_pct: 12.5,
              edited_pct: 0,
            },
            {
              field: 'address',
              reviews: '<5',
              prefilled_pct: null,
              blank_pct: null,
              edited_pct: null,
            },
          ],
        },
      }),
    });
    const { container } = render(<Dashboard />);
    expect(await screen.findByText('98.9%')).toBeInTheDocument();
    expect(screen.getAllByText('✓ Meets target')).toHaveLength(2); // chat + OCR eval
    expect(screen.getByText('✗ Misses target')).toBeInTheDocument();
    expect(screen.getByText('No data')).toBeInTheDocument();
    expect(screen.getAllByText('<5').length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText('About you (intake)')).toHaveLength(2); // funnel + friction
    expect(screen.getByText('33.3%')).toBeInTheDocument();
    expect(screen.getByText('6 min')).toBeInTheDocument();
    expect(screen.getAllByText('12.5%', { selector: 'td' })).toHaveLength(2); // edited name, blank DOB
    expect(screen.getByText('Corrected by the client')).toBeInTheDocument();
    expect(screen.getByText('+42')).toBeInTheDocument();
    expect(screen.getByText('Long pause')).toBeInTheDocument();
    expect(screen.getByText('Photo could not be read')).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe('ErrorBoundary', () => {
  it('shows a friendly message instead of a crash', () => {
    const Boom = () => {
      throw new Error('secret detail');
    };
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/progress is saved/);
    expect(screen.queryByText(/secret detail/)).not.toBeInTheDocument();
  });
});
