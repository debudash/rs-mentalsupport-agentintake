// Book as the demo client, then view as the clinician and the operator. Verification only.
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import { mkdirSync } from 'node:fs';

const BASE = process.env.BASE_URL || 'http://localhost:8000';
const OUT = fileURLToPath(new URL('./shots/', import.meta.url));
mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const errors = [];

async function signIn(email, password) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
  await page.goto(BASE);
  await page.getByRole('button', { name: 'I already have an account' }).click();
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  return page;
}

const clinician = await signIn('clinician.ana@riverside.test', 'DemoClinician!2026');
await clinician.getByRole('heading', { name: /Upcoming initial consultations/ }).waitFor();
await clinician.waitForTimeout(800);
const items = clinician.locator('main ul li button');
if (await items.count()) {
  await items.first().click();
  await clinician.locator('dl').waitFor();
}
await clinician.screenshot({ path: `${OUT}11-clinician.png`, fullPage: true });

const operator = await signIn('operator.demo@riverside.test', 'DemoOperator!2026');
await operator.getByRole('heading', { name: 'Onboarding operations' }).waitFor();
await operator.getByText('ID reading accuracy').waitFor();
await operator.waitForTimeout(800);
await operator.screenshot({ path: `${OUT}12-dashboard.png`, fullPage: true });

console.log('clinician bookings listed:', await items.count());
console.log('errors:', errors.length ? errors : 'none');
await browser.close();
