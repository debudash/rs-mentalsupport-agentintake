// Walk the real UI end to end and screenshot each Step. Verification only (not in repo).
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import { mkdirSync } from 'node:fs';

const BASE = process.env.BASE_URL || 'http://localhost:8000';
const OUT = fileURLToPath(new URL('./shots/', import.meta.url));
const CARD = fileURLToPath(new URL('../evals/datasets/ocr/golden/photo_03.jpg', import.meta.url));

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
const errors = [];
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
page.on('pageerror', (e) => errors.push(String(e)));
const shot = (name) => page.screenshot({ path: `${OUT}${name}.png`, fullPage: true });

await page.goto(BASE);
await page.getByRole('heading', { name: 'Start your sign-up' }).waitFor();
await shot('01-signup');
await page.getByLabel('Email').fill(`ui-${Date.now()}@riverside.test`);
await page.getByLabel('Password').fill('ui-test-password-1');
await page.getByRole('button', { name: 'Create account' }).click();

await page.getByRole('heading', { name: 'Consent' }).waitFor();
await shot('02-consent');
await page.getByLabel(/onboarding data being stored/).check();
await page.getByLabel(/read a photo of my ID/).check();
await page.getByLabel(/18 or older/).check();
await page.getByRole('button', { name: 'Agree and continue' }).click();

await page.getByRole('heading', { name: 'About you' }).waitFor();
await page.getByText(/bringing you here/).waitFor();
await page.getByLabel('Type your answer').fill('mostly anxiety honestly, the last few months');
await page.getByRole('button', { name: 'Send' }).click();
await page.waitForTimeout(800);
await page.getByLabel('Type your answer').fill('How much does this cost?');
await page.getByRole('button', { name: 'Send' }).click();
await page.waitForTimeout(800);
await shot('03-intake-chat');
const answers = [
  ['reason_text', 'Prefer not to say'],
  ['duration', '1 to 6 months'],
  ['distress', '4'],
];
for (const [, label] of answers) {
  await page.getByRole('button', { name: label, exact: true }).click();
  await page.waitForTimeout(500);
}
await shot('04-intake-support-card');
await page.getByRole('button', { name: 'No', exact: true }).click();
await page.waitForTimeout(500);
await page.getByRole('button', { name: 'Either is fine' }).click();
await page.waitForTimeout(500);
await page.getByRole('button', { name: 'Mornings' }).click();
await page.getByRole('button', { name: 'Afternoons' }).click();
await page.getByRole('button', { name: 'Evenings' }).click();
await page.getByRole('button', { name: 'Done' }).click();
await page.waitForTimeout(500);
await page.getByRole('button', { name: 'No preference' }).click();
await page.waitForTimeout(500);
await page.getByRole('button', { name: 'Either', exact: true }).click();

await page.getByRole('heading', { name: 'Your details' }).waitFor({ timeout: 10000 });
await shot('05-identity-choose');
const chooser = page.waitForEvent('filechooser');
await page.getByRole('button', { name: 'Take or choose a photo' }).click();
await (await chooser).setFiles(CARD);
await page.getByRole('heading', { name: 'Check your details' }).waitFor({ timeout: 20000 });
await shot('06-identity-review');
await page.getByRole('button', { name: 'These details are correct' }).click();

await page.getByRole('heading', { name: 'Book' }).waitFor();
await page.locator('.slots button').first().waitFor();
await shot('07-scheduling');
await page.locator('.slots button').first().click();
await page.getByRole('button', { name: /^Book / }).click();

await page.getByRole('heading', { name: "You're all set" }).waitFor();
await page.getByText('Your initial consultation is booked').waitFor();
await shot('08-done');

// Keyboard check on the done screen: Tab reaches the skip link first, then controls.
await page.keyboard.press('Tab');
const first = await page.evaluate(() => document.activeElement?.textContent);

await page.getByRole('button', { name: 'Withdraw and delete everything' }).click();
await shot('09-withdraw');
await page.getByLabel(/I understand/).check();
await page.getByRole('button', { name: 'Delete everything' }).click();
await page.getByRole('heading', { name: 'Everything has been deleted' }).waitFor();
await shot('10-receipt');

console.log('first Tab stop:', first);
console.log('console errors:', errors.length ? errors : 'none');
await browser.close();
