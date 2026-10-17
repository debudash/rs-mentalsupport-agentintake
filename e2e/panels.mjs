// Screenshot the operator dashboard's funnel and OCR-correction panels.
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import { mkdirSync } from 'node:fs';

const BASE = process.env.BASE_URL || 'http://localhost:8000';
const OUT = fileURLToPath(new URL('./shots/', import.meta.url));
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
await page.goto(BASE);
await page.getByRole('button', { name: 'I already have an account' }).click();
await page.getByLabel('Email').fill('operator.demo@riverside.test');
await page.getByLabel('Password').fill('DemoOperator!2026');
await page.getByRole('button', { name: 'Sign in' }).click();
await page.getByRole('heading', { name: 'Onboarding funnel' }).waitFor();
await page.locator('section[aria-labelledby="funnel-title"]').screenshot({ path: `${OUT}13-funnel.png` });
await page.locator('section[aria-labelledby="ocr-title"]').screenshot({ path: `${OUT}14-ocr-corrections.png` });
console.log('captured');
await browser.close();
