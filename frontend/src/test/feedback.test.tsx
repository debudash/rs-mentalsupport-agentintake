import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { Feedback } from '../steps/Feedback';
import { axe } from './axe';
import { mockFetch } from './fetchMock';

describe('post-booking question (NPS)', () => {
  it('records one tap and thanks the client', async () => {
    const calls = mockFetch({ 'POST /api/feedback': () => ({ json: { thanks: true } }) });
    const { container } = render(<Feedback />);
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(screen.getByRole('button', { name: '9 out of 10' }));
    expect(await screen.findByText('Thank you for telling us.')).toBeInTheDocument();
    expect(calls).toEqual([{ key: 'POST /api/feedback', body: { score: 9 } }]);
  });

  it('can be skipped without sending anything', async () => {
    const calls = mockFetch({});
    const { container } = render(<Feedback />);
    await userEvent.click(screen.getByRole('button', { name: 'Skip' }));
    expect(container).toBeEmptyDOMElement();
    expect(calls).toHaveLength(0);
  });

  it('an earlier answer counts as done, not as an error', async () => {
    mockFetch({ 'POST /api/feedback': () => ({ status: 409, json: { detail: 'already' } }) });
    render(<Feedback />);
    await userEvent.click(screen.getByRole('button', { name: '10 out of 10' }));
    expect(await screen.findByText('Thank you for telling us.')).toBeInTheDocument();
  });
});
