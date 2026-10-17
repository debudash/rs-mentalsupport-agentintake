// Keyboard-only walk: only Tab / Shift+Tab / Space / Enter / typing. Reports each check.
const BASE = process.env.BASE_URL || 'http://localhost:8000';
import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
const results = [];
const record = (name, ok, detail = '') => results.push(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  — ' + detail}`);
const focused = () =>
  page.evaluate(() => {
    const el = document.activeElement;
    return { tag: el?.tagName, text: (el?.textContent || el?.getAttribute('aria-label') || el?.id || '').trim().slice(0, 60), type: el?.getAttribute('type') };
  });

async function tabTo(predicate, max = 40) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press('Tab');
    const f = await focused();
    if (predicate(f)) return f;
  }
  return null;
}

await page.goto(BASE);
await page.getByRole('heading', { name: 'Start your sign-up' }).waitFor();
const skip = await tabTo((f) => true, 1);
record('first Tab stop is the skip link', skip?.text === 'Skip to content', JSON.stringify(skip));
const crisis = await tabTo((f) => f.text.includes('988'));
record('crisis link reachable by keyboard', !!crisis);
await tabTo((f) => f.tag === 'INPUT' && f.type === 'email');
await page.keyboard.type(`kb-${Date.now()}@riverside.test`);
await page.keyboard.press('Tab');
await page.keyboard.type('keyboard-only-pass-1');
await page.keyboard.press('Enter');
await page.getByRole('heading', { name: 'Consent' }).waitFor();
record('sign-up submits with Enter', true);

let f = await focused();
record('focus on the Step heading after Step change', f.tag === 'H1' && f.text === 'Consent', JSON.stringify(f));
for (const n of [1, 2, 3]) {
  await tabTo((x) => x.tag === 'INPUT' && x.type === 'checkbox');
  await page.keyboard.press('Space');
}
const agree = await tabTo((x) => x.text === 'Agree and continue');
record('consent checkboxes toggle with Space; Agree enabled', !!agree && !(await page.getByRole('button', { name: 'Agree and continue' }).isDisabled()));
await page.keyboard.press('Enter');
await page.getByRole('heading', { name: 'About you' }).waitFor();
f = await focused();
record('focus on Intake heading', f.tag === 'H1' && f.text === 'About you', JSON.stringify(f));

await page.getByText(/bringing you here/).waitFor();
const reply = await tabTo((x) => x.text === 'Anxiety or worry');
record('quick replies reachable by Tab', !!reply);
await page.keyboard.press('Enter');
await page.getByText(/in your own words/).first().waitFor();
const box = await tabTo((x) => x.tag === 'INPUT' && x.type === 'text');
record('chat text box reachable', !!box);
await page.keyboard.type('Work has been a lot lately');
await page.keyboard.press('Enter');
await page.getByText(/How long has this been going on/).waitFor();
record('chat message sends with Enter', true);

const answers = ['1 to 6 months', '2', 'No', 'Either is fine'];
for (const a of answers) {
  const b = await tabTo((x) => x.text === a);
  if (!b) { record(`reach "${a}"`, false); break; }
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
}
for (const a of ['Mornings', 'Evenings']) {
  await tabTo((x) => x.text === a);
  await page.keyboard.press('Space');
}
await tabTo((x) => x.text === 'Done');
await page.keyboard.press('Enter');
await page.waitForTimeout(400);
for (const a of ['No preference', 'Either']) {
  await tabTo((x) => x.text === a);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
}
await page.getByRole('heading', { name: 'Your details' }).waitFor();
record('whole Intake completed by keyboard (incl. multi-choice with Space)', true);

const photo = await tabTo((x) => x.text === 'Take or choose a photo');
record('"Take or choose a photo" reachable', !!photo);
const typeInstead = await tabTo((x) => x.text === 'Type my details instead');
await page.keyboard.press('Enter');
await page.getByLabel('Full legal name').waitFor();
await tabTo((x) => x.tag === 'INPUT');
await page.keyboard.type('Kay Board');
await page.keyboard.press('Tab');
await page.keyboard.type('1991-02-03');
await page.keyboard.press('Tab');
await page.keyboard.type('5 Key St, Springfield, RS 12345');
const confirm = await tabTo((x) => x.text === 'These details are correct');
await page.keyboard.press('Enter');
await page.getByRole('heading', { name: 'Book' }).waitFor();
record('manual identity entry by keyboard', !!typeInstead && !!confirm);

const day = await tabTo((x) => x.tag === 'BUTTON' && /^[A-Z][a-z]{2} \d+ [A-Z][a-z]{2}$/.test(x.text));
record('day picker reachable', !!day);
const time = await tabTo((x) => /AM|PM/.test(x.text) && !x.text.startsWith('Book'));
await page.keyboard.press('Enter');
const book = await tabTo((x) => x.text.startsWith('Book '), 10);
record('Book reachable within 10 Tabs after choosing a time', !!book);
await page.keyboard.press('Enter');
await page.getByText('Your initial consultation is booked').waitFor();
const cal = await tabTo((x) => x.text === 'Add to my calendar', 5);
record('Done: calendar button reachable', !!cal);

const withdraw = await tabTo((x) => x.text === 'Withdraw and delete everything');
await page.keyboard.press('Enter');
await page.getByRole('heading', { name: 'Withdraw and delete everything' }).waitFor();
await tabTo((x) => x.type === 'checkbox');
await page.keyboard.press('Space');
await tabTo((x) => x.text === 'Delete everything');
await page.keyboard.press('Enter');
await page.getByRole('heading', { name: 'Everything has been deleted' }).waitFor();
f = await focused();
record('Withdrawal by keyboard; focus moves to the receipt heading', !!withdraw && f.tag === 'H1', JSON.stringify(f));

console.log(results.join('\n'));
console.log('page errors:', errors.length ? errors : 'none');
await browser.close();
