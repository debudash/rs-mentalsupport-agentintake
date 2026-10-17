// Gentle mode on the running app: a stressed client sees a slower, softer Intake.
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import { mkdirSync } from 'node:fs';

const BASE = process.env.BASE_URL || 'http://localhost:8000';
const OUT = fileURLToPath(new URL('./shots/', import.meta.url));
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1100, height: 1000 } });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
const checks = [];
const check = (name, ok) => checks.push(`${ok ? 'PASS' : 'FAIL'}  ${name}`);

await page.goto(BASE);
await page.getByLabel('Email').fill(`gentle-${Date.now()}@riverside.test`);
await page.getByLabel('Password').fill('gentle-mode-pass-1');
await page.getByRole('button', { name: 'Create account' }).click();
await page.getByRole('heading', { name: 'Consent' }).waitFor();
await page.getByLabel(/onboarding data being stored/).check();
await page.getByLabel(/18 or older/).check();
await page.getByRole('button', { name: 'Agree and continue' }).click();
await page.getByText(/bringing you here/).waitFor();

const box = page.getByLabel('Type your answer');
check('before stress: no "Take a break"', !(await page.getByRole('button', { name: 'Take a break' }).isVisible()));
await box.fill("honestly I'm so overwhelmed by all of this, I almost didn't sign up");
await page.getByRole('button', { name: 'Send' }).click();
await page.getByRole('button', { name: 'Take a break' }).waitFor({ timeout: 15000 });
const chat = (await page.locator('.chat').textContent()) ?? '';
check('reassurance said once (card), not repeated in the chat', !/take this slowly/i.test(chat));
check('"Take a break" offered apart from the answers', (await page.locator('.quick-replies').getByRole('button', { name: 'Take a break' }).count()) === 0);
check('high-stress supportive card shown', await page.locator('[data-trigger="high_stress"]').isVisible());
await page.screenshot({ path: `${OUT}15-gentle-mode.png`, fullPage: true });

await page.getByRole('button', { name: 'Take a break' }).click();
check('break screen', await page.getByRole('heading', { name: /take all the time you need/i }).isVisible());
await page.screenshot({ path: `${OUT}16-take-a-break.png`, fullPage: true });
await page.getByRole('button', { name: /ready to continue/i }).click();
check('back to the conversation', await box.isVisible());

await page.reload();
await page.getByRole('heading', { name: 'About you' }).waitFor();
await page.getByText(/bringing you here|in your own words|How long|feeling overall/).first().waitFor();
const persisted = await page
  .getByRole('button', { name: 'Take a break' })
  .waitFor({ timeout: 10000 })
  .then(() => true, () => false);
check('gentle mode persists after reload', persisted);

console.log(checks.join('\n'));
console.log('page errors:', errors.length ? errors : 'none');
await browser.close();
