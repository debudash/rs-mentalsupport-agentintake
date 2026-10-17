import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { STEP_TRUST, StepTrust, TrustFooter } from '../Trust';
import { axe } from './axe';

describe('privacy reassurance', () => {
  it('each Step has its own short line; Done has none', () => {
    for (const step of ['consent', 'intake', 'identity', 'scheduling'] as const) {
      const { unmount } = render(<StepTrust step={step} />);
      expect(screen.getByText(STEP_TRUST[step]!)).toBeInTheDocument();
      unmount();
    }
    const { container } = render(<StepTrust step="done" />);
    expect(container).toBeEmptyDOMElement();
  });

  // Keyboard toggling of <details> is native browser behaviour (checked in e2e/keyboard.mjs).
  it('footer details stay hidden until asked for', async () => {
    const { container } = render(<TrustFooter />);
    const summary = screen.getByText(/Encrypted and used only to arrange your care/);
    const details = container.querySelector('details')!;
    expect(details.open).toBe(false);
    await userEvent.click(summary);
    expect(details.open).toBe(true);
    expect(await axe(container)).toHaveNoViolations();
  });

  it('never claims compliance or certification', () => {
    const { container } = render(
      <>
        <TrustFooter />
        {(['consent', 'intake', 'identity', 'scheduling'] as const).map((s) => (
          <StepTrust key={s} step={s} />
        ))}
      </>,
    );
    expect(container.textContent).not.toMatch(/HIPAA|complian|certif|guarantee|100%/i);
  });
});
