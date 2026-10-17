// @vitest-environment node
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

// WCAG 2.1 contrast ratio between two hex colours.
function luminance(hex: string) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
function ratio(a: string, b: string) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const css = readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8');
const token = (name: string) => css.match(new RegExp(`--${name}:[ ]*(#[0-9a-fA-F]{6})`))![1];

// Every text colour used on every background it appears on.
const PAIRS: [string, string][] = [
  ['ink', 'bg'],
  ['ink', 'surface'],
  ['ink-soft', 'surface'],
  ['ink-soft', 'bg'],
  ['brand', 'surface'],
  ['brand', 'bg'],
  ['brand-ink', 'brand'],
  ['ink', 'brand-soft'],
  ['ok', 'surface'],
  ['ok', 'ok-soft'],
  ['warn', 'surface'],
  ['warn', 'warn-soft'],
  ['danger', 'surface'],
  ['danger', 'danger-soft'],
  ['brand-ink', 'danger'],
  ['ink', 'danger-soft'],
  ['ink', 'warn-soft'],
  ['ink', 'ok-soft'],
  ['ink-soft', 'line'],
];

describe('colour contrast (WCAG 2.1 AA, 4.5:1 for normal text)', () => {
  it.each(PAIRS)('%s on %s', (fg, bg) => {
    expect(ratio(token(fg), token(bg))).toBeGreaterThanOrEqual(4.5);
  });

  it('focus outline is visible against the page (3:1 for UI components)', () => {
    expect(ratio(token('focus'), token('bg'))).toBeGreaterThanOrEqual(3);
    expect(ratio(token('focus'), token('surface'))).toBeGreaterThanOrEqual(3);
  });
});
