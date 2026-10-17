import { configureAxe } from 'vitest-axe';

// jsdom has no canvas, so axe cannot compute colour contrast here; contrast.test.ts checks
// every text/background pair of the palette against WCAG AA directly instead.
export const axe = configureAxe({ rules: { 'color-contrast': { enabled: false } } });
