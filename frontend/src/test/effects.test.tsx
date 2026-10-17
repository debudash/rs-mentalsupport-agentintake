import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { IntakeStep } from '../steps/IntakeStep';
import { Withdrawal } from '../steps/Withdrawal';
import { mockFetch } from './fetchMock';

// ISSUE-003 regression. Found by: walking the real UI in headless Chromium — the Intake step
// crashed into the error boundary right after consent ("C is not a function").
describe('effects tolerate DOM methods that return promises (current Chromium)', () => {
  const original = {
    scroll: Element.prototype.scrollIntoView,
    focus: HTMLElement.prototype.focus,
  };

  afterEach(() => {
    Element.prototype.scrollIntoView = original.scroll;
    HTMLElement.prototype.focus = original.focus;
    vi.restoreAllMocks();
  });

  it('Intake keeps working when scrollIntoView returns a Promise', async () => {
    Element.prototype.scrollIntoView = vi.fn(() => Promise.resolve()) as never;
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
    const first = {
      messages: ['First question?'],
      pending_item: 'reason_category',
      input_kind: 'choice',
      quick_replies: [{ value: 'anxiety', label: 'Anxiety or worry' }],
      complete: false,
      actions: [],
      crisis: false,
      transcript: [],
    };
    mockFetch({
      'GET /api/intake': () => ({ json: first }),
      'POST /api/intake/messages': () => ({ json: { ...first, messages: ['Second question?'] } }),
    });
    render(
      <IntakeStep
        paused={false}
        onSupport={vi.fn()}
        onWithdraw={vi.fn()}
        onDone={vi.fn()}
        onResumed={vi.fn()}
      />,
    );
    await userEvent.click(await screen.findByRole('button', { name: 'Anxiety or worry' }));
    expect(await screen.findByText('Second question?')).toBeInTheDocument();
    expect(errors).not.toHaveBeenCalledWith(
      expect.stringContaining('must not return anything besides a function'),
      expect.anything(),
      expect.anything(),
    );
  });

  it('Withdrawal keeps working when focus returns a Promise', async () => {
    HTMLElement.prototype.focus = vi.fn(() => Promise.resolve()) as never;
    mockFetch({
      'POST /api/withdraw': () => ({
        json: { reference: 'R1', deleted_at: '2026-10-16T12:00:00Z', deleted: [] },
      }),
    });
    render(<Withdrawal onCancel={vi.fn()} onDone={vi.fn()} />);
    await userEvent.click(screen.getByLabelText(/I understand/));
    await userEvent.click(screen.getByRole('button', { name: /delete everything/i }));
    expect(await screen.findByText('R1')).toBeInTheDocument();
  });
});
