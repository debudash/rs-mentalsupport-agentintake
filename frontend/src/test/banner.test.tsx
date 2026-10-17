import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Banner } from '../Banner';
import { axe } from './axe';

describe('banner', () => {
  it('signed out: full banner with name, tagline and the crisis line', async () => {
    const { container } = render(<Banner />);
    expect(screen.getByText('Riverside')).toBeInTheDocument();
    expect(screen.getByText('Counseling')).toBeInTheDocument();
    expect(screen.getByText(/Help is always one tap away/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /988/ })).toHaveAttribute('href', 'tel:988');
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it('signed in: compact banner keeps the crisis line and offers Sign out', async () => {
    const onSignOut = vi.fn();
    const { container } = render(<Banner compact onSignOut={onSignOut} />);
    expect(container.querySelector('header')).toHaveClass('compact');
    expect(screen.queryByText(/Help is always one tap away/)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /988/ })).toHaveAttribute('href', 'tel:988');
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(onSignOut).toHaveBeenCalledOnce();
    expect(await axe(container)).toHaveNoViolations();
  });

  it('the crisis line sits right under the artwork', () => {
    const { container } = render(<Banner />);
    const art = container.querySelector('svg')!;
    const link = screen.getByRole('link', { name: /988/ });
    expect(art.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('matches the page column: the form width for Clients, wide for staff', () => {
    const { container, rerender } = render(<Banner />);
    expect(container.querySelector('header')).not.toHaveClass('wide');
    rerender(<Banner compact wide onSignOut={() => {}} />);
    expect(container.querySelector('header')).toHaveClass('wide');
  });

  it('the artwork is decoration, hidden from assistive technology', () => {
    const { container } = render(<Banner />);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
});
