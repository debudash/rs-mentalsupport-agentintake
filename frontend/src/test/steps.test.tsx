import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from './axe';
import { describe, expect, it, vi } from 'vitest';
import { ConsentStep } from '../steps/ConsentStep';
import { IntakeStep } from '../steps/IntakeStep';
import { IdentityStep } from '../steps/IdentityStep';
import { SchedulingStep } from '../steps/SchedulingStep';
import { Withdrawal } from '../steps/Withdrawal';
import { CrisisPanel } from '../steps/CrisisPanel';
import { SupportCard } from '../steps/SupportCard';
import type { IntakeReply, ProfileSummary } from '../lib/types';
import { mockFetch } from './fetchMock';

const profile: ProfileSummary = {
  service: { name: 'Riverside Counseling', consultation_minutes: 30, minimum_age: 18 },
  consents: {
    onboarding: {
      version: '1',
      title: 'Onboarding data',
      required: true,
      text: 'We store your answers.',
    },
    id_scan: {
      version: '1',
      title: 'ID scan (optional)',
      required: false,
      text: 'We read a photo.',
    },
  },
  step_guidance: {},
  crisis: {
    resources: [{ label: 'Call or text 988', href: 'tel:988' }],
    pause_message: 'Your safety matters.',
  },
  contact: { phone: '555', email: 'a@b.c', hours: '9-5' },
};

const firstQuestion: IntakeReply = {
  messages: ["What's been bringing you here?"],
  pending_item: 'reason_category',
  input_kind: 'choice',
  quick_replies: [
    { value: 'anxiety', label: 'Anxiety or worry' },
    { value: 'low_mood', label: 'Low mood' },
  ],
  complete: false,
  actions: [],
  crisis: false,
  transcript: [],
};

describe('ConsentStep', () => {
  it('requires both required boxes and sends the choices', async () => {
    const calls = mockFetch({ 'POST /api/consent': () => ({ json: {} }) });
    const onDone = vi.fn();
    const { container } = render(<ConsentStep profile={profile} onDone={onDone} />);
    const submit = screen.getByRole('button', { name: /agree and continue/i });
    expect(submit).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/onboarding data being stored/i));
    await userEvent.click(screen.getByLabelText(/18 or older/i));
    await userEvent.click(submit);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(calls[0].body).toEqual({ onboarding: true, id_scan: false, age_confirmed: true });
    expect(await axe(container)).toHaveNoViolations();
  });

  it('shows the server reason when consent is rejected', async () => {
    mockFetch({
      'POST /api/consent': () => ({ status: 422, json: { detail: 'This service is for adults.' } }),
    });
    render(<ConsentStep profile={profile} onDone={vi.fn()} />);
    await userEvent.click(screen.getByLabelText(/onboarding data being stored/i));
    await userEvent.click(screen.getByLabelText(/18 or older/i));
    await userEvent.click(screen.getByRole('button', { name: /agree/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('adults');
  });
});

describe('IntakeStep', () => {
  const props = {
    paused: false,
    onSupport: vi.fn(),
    onWithdraw: vi.fn(),
    onDone: vi.fn(),
    onResumed: vi.fn(),
  };

  it('shows the question, sends a quick reply and announces the answer', async () => {
    const calls = mockFetch({
      'GET /api/intake': () => ({ json: firstQuestion }),
      'POST /api/intake/messages': () => ({
        json: {
          ...firstQuestion,
          messages: ['How long has this been going on?'],
          pending_item: 'duration',
        },
      }),
    });
    const { container } = render(<IntakeStep {...props} />);
    expect(await screen.findByText(/bringing you here/)).toBeInTheDocument();
    expect(screen.getByRole('log')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Anxiety or worry' }));
    expect(await screen.findByText(/How long/)).toBeInTheDocument();
    expect(calls.at(-1)?.body).toEqual({ item: 'reason_category', value: 'anxiety' });
    expect(await axe(container)).toHaveNoViolations();
  });

  it('sends free text and surfaces supportive content and withdrawal', async () => {
    const onSupport = vi.fn();
    const onWithdraw = vi.fn();
    mockFetch({
      'GET /api/intake': () => ({ json: firstQuestion }),
      'POST /api/intake/messages': () => ({
        json: {
          ...firstQuestion,
          messages: ['That sounds hard.'],
          actions: ['show_withdrawal'],
          support: { trigger: 'high_stress', title: 'You are doing well', body: 'Take your time.' },
        },
      }),
    });
    render(<IntakeStep {...props} onSupport={onSupport} onWithdraw={onWithdraw} />);
    await userEvent.type(
      await screen.findByLabelText(/type your answer/i),
      "I'm overwhelmed{enter}",
    );
    await waitFor(() =>
      expect(onSupport).toHaveBeenCalledWith(expect.objectContaining({ trigger: 'high_stress' })),
    );
    expect(onWithdraw).toHaveBeenCalled();
  });

  it('collects several choices for a multi-choice question', async () => {
    const calls = mockFetch({
      'GET /api/intake': () => ({
        json: {
          ...firstQuestion,
          pending_item: 'availability',
          input_kind: 'multichoice',
          quick_replies: [
            { value: 'mornings', label: 'Mornings' },
            { value: 'evenings', label: 'Evenings' },
          ],
        },
      }),
      'POST /api/intake/messages': () => ({ json: { ...firstQuestion, messages: ['Thanks'] } }),
    });
    render(<IntakeStep {...props} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Mornings' }));
    await userEvent.click(screen.getByRole('button', { name: 'Evenings' }));
    expect(screen.getByRole('button', { name: 'Mornings' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Done' }));
    await waitFor(() =>
      expect(calls.at(-1)?.body).toEqual({ item: 'availability', value: 'mornings,evenings' }),
    );
  });

  it('shows crisis resources instead of questions when paused, and can resume', async () => {
    const onResumed = vi.fn();
    mockFetch({
      'GET /api/intake': () => ({
        json: {
          ...firstQuestion,
          crisis: true,
          messages: ['Your safety matters.'],
          crisis_resources: profile.crisis.resources,
        },
      }),
      'POST /api/intake/resume': () => ({
        json: { ...firstQuestion, messages: ['Welcome back.'] },
      }),
    });
    const { container } = render(<IntakeStep {...props} paused onResumed={onResumed} />);
    expect(await screen.findByRole('link', { name: /988/ })).toHaveAttribute('href', 'tel:988');
    expect(screen.queryByLabelText(/type your answer/i)).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(screen.getByRole('button', { name: /ready to continue/i }));
    expect(await screen.findByText('Welcome back.')).toBeInTheDocument();
    expect(onResumed).toHaveBeenCalled();
  });

  it('offers to retry the assistant and flags scripted mode', async () => {
    mockFetch({
      'GET /api/intake': () => ({ json: firstQuestion }),
      'POST /api/intake/messages': () => ({
        json: {
          ...firstQuestion,
          messages: ["I'm having trouble right now"],
          actions: ['offer_retry_assistant'],
          scripted_mode: true,
        },
      }),
    });
    render(<IntakeStep {...props} />);
    await userEvent.type(await screen.findByLabelText(/type your answer/i), 'anxiety{enter}');
    expect(
      await screen.findByRole('button', { name: /try the assistant again/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/assistant is unavailable/i)).toBeInTheDocument();
  });
});

describe('IdentityStep', () => {
  it('pre-fills read fields, marks blank ones in words, and confirms with edit flags', async () => {
    const calls = mockFetch({
      'POST /api/identity/scan': () => ({
        json: {
          accepted: true,
          support: null,
          fields: {
            name: { value: 'Jane Q Doe', status: 'read' },
            date_of_birth: { value: '1990-03-14', status: 'read' },
            address: { value: null, status: 'blank' },
          },
        },
      }),
      'POST /api/identity/confirm': () => ({ json: { confirmed: true } }),
    });
    const onDone = vi.fn();
    const { container } = render(
      <IdentityStep idScanAllowed onSupport={vi.fn()} onDone={onDone} />,
    );
    const file = new File(['x'], 'id.jpg', { type: 'image/jpeg' });
    await userEvent.upload(screen.getByLabelText('ID photo'), file);
    expect(await screen.findByDisplayValue('Jane Q Doe')).toBeInTheDocument();
    expect(screen.getAllByText(/Read from your ID — please check/)).toHaveLength(2);
    expect(screen.getByText(/Couldn't read this — please type it/)).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.type(
      screen.getByLabelText('Home address'),
      '123 Main St, Springfield, RS 12345',
    );
    await userEvent.click(screen.getByRole('button', { name: /details are correct/i }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(calls.at(-1)?.body).toMatchObject({
      source: 'scan',
      edited: { legal_name: false, date_of_birth: false, address: true },
    });
  });

  it('rejected upload shows the message and support; manual entry still works', async () => {
    const onSupport = vi.fn();
    mockFetch({
      'POST /api/identity/scan': () => ({
        json: {
          accepted: false,
          message: "That file isn't a photo we can read.",
          fields: null,
          support: {
            trigger: 'upload_problem',
            title: 'Photos can be tricky',
            body: 'Type instead.',
          },
        },
      }),
    });
    render(<IdentityStep idScanAllowed onSupport={onSupport} onDone={vi.fn()} />);
    await userEvent.upload(
      screen.getByLabelText('ID photo'),
      new File(['%PDF'], 'x.pdf', { type: 'image/jpeg' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent("isn't a photo");
    expect(onSupport).toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: /type my details instead/i }));
    expect(screen.getByLabelText('Full legal name')).toBeInTheDocument();
  });

  it('shows field errors from the server, linked to their inputs', async () => {
    mockFetch({
      'POST /api/identity/confirm': () => ({
        status: 422,
        json: { detail: { fields: { date_of_birth: 'Please enter a valid date of birth.' } } },
      }),
    });
    render(<IdentityStep idScanAllowed={false} onSupport={vi.fn()} onDone={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /details are correct/i }));
    const dob = screen.getByLabelText('Date of birth');
    expect(await screen.findByText(/valid date of birth/)).toBeInTheDocument();
    expect(dob).toHaveAttribute('aria-invalid', 'true');
    expect(dob.getAttribute('aria-describedby')).toContain('error-date_of_birth');
  });

  it('adults-only answer shows resources instead of continuing', async () => {
    mockFetch({
      'POST /api/identity/confirm': () => ({
        json: {
          confirmed: false,
          adults_only: true,
          message: 'This service is for adults.',
          crisis_resources: profile.crisis.resources,
        },
      }),
    });
    render(<IdentityStep idScanAllowed={false} onSupport={vi.fn()} onDone={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /details are correct/i }));
    expect(await screen.findByText(/for adults/)).toBeInTheDocument();
  });
});

describe('SchedulingStep', () => {
  const slot = (id: string, label: string) => ({
    id,
    starts_at: '2026-10-20T14:00:00Z',
    local_label: label,
    time_zone: 'EDT',
    format: 'video',
    clinician: 'Ana Rivera',
  });

  it('books a chosen slot', async () => {
    const calls = mockFetch({
      'GET /api/slots': () => ({
        json: { slots: [slot('s1', 'Tue 20 Oct, 10:00 AM')], filtered: true },
      }),
      'POST /api/bookings': () => ({ json: { booking: {} } }),
    });
    const onDone = vi.fn();
    const { container } = render(<SchedulingStep onDone={onDone} />);
    await userEvent.click(await screen.findByRole('button', { name: /Tue 20 Oct, 10:00 AM/ }));
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(screen.getByRole('button', { name: /^Book/ }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(calls.at(-1)?.body).toMatchObject({ slot_id: 's1' });
  });

  it('shows one day at a time with a day picker', async () => {
    mockFetch({
      'GET /api/slots': () => ({
        json: {
          slots: [slot('a', 'Mon 19 Oct, 9:00 AM'), slot('b', 'Tue 20 Oct, 10:00 AM')],
          filtered: true,
        },
      }),
    });
    render(<SchedulingStep onDone={vi.fn()} />);
    expect(await screen.findByRole('button', { name: /Mon 19 Oct, 9:00 AM/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Tue 20 Oct, 10:00 AM/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Tue 20 Oct' }));
    expect(screen.getByRole('button', { name: /Tue 20 Oct, 10:00 AM/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tue 20 Oct' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('shows alternatives when the slot was just taken', async () => {
    mockFetch({
      'GET /api/slots': () => ({
        json: { slots: [slot('s1', 'Tue 20 Oct, 10:00 AM')], filtered: true },
      }),
      'POST /api/bookings': () => ({
        status: 409,
        json: {
          detail: {
            message: 'Someone just took that time.',
            alternatives: [slot('s2', 'Tue 20 Oct, 11:00 AM')],
          },
        },
      }),
    });
    render(<SchedulingStep onDone={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: /10:00 AM/ }));
    await userEvent.click(screen.getByRole('button', { name: /^Book/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('just took');
    expect(screen.getByRole('button', { name: /11:00 AM/ })).toBeInTheDocument();
  });
});

describe('Withdrawal, crisis panel and support card', () => {
  it('requires explicit confirmation and shows a receipt', async () => {
    const calls = mockFetch({
      'POST /api/withdraw': () => ({
        json: {
          reference: 'ABC123',
          deleted_at: '2026-10-16T12:00:00Z',
          deleted: ['Identity details'],
        },
      }),
    });
    const { container } = render(<Withdrawal onCancel={vi.fn()} onDone={vi.fn()} />);
    const remove = screen.getByRole('button', { name: /delete everything/i });
    expect(remove).toBeDisabled();
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(screen.getByLabelText(/I understand/));
    await userEvent.click(remove);
    expect(await screen.findByText('ABC123')).toBeInTheDocument();
    expect(calls[0].body).toEqual({ confirm: true });
  });

  it('crisis panel and support card are accessible', async () => {
    const onDismiss = vi.fn();
    const { container } = render(
      <>
        <CrisisPanel message="Your safety matters." />
        <SupportCard
          card={{ trigger: 'long_pause', title: 'Take your time', body: 'Saved.' }}
          onDismiss={onDismiss}
        />
      </>,
    );
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(screen.getByRole('button', { name: /got it/i }));
    expect(onDismiss).toHaveBeenCalled();
  });
});
