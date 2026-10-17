// Parse and render every ```mermaid block in the given Markdown files with Mermaid itself.
//   node mermaid-check.mjs ../docs/ARCHITECTURE.md [more.md ...]
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';

const files = process.argv.slice(2);
const blocks = [];
for (const file of files) {
  const text = readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
  for (const m of text.matchAll(/```mermaid\n([\s\S]*?)```/g)) {
    const line = text.slice(0, m.index).split('\n').length;
    blocks.push({ file, line, code: m[1] });
  }
}

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setContent('<div id="out"></div>');
// GitLab bundles its own Mermaid; check with an older release too (MERMAID_VERSION=10.9.1).
const version = process.env.MERMAID_VERSION || '11.4.1';
await page.addScriptTag({ url: `https://cdn.jsdelivr.net/npm/mermaid@${version}/dist/mermaid.min.js` });
let failures = 0;
for (const b of blocks) {
  const result = await page.evaluate(async (code) => {
    window.mermaid.initialize({ startOnLoad: false });
    try {
      const { svg } = await window.mermaid.render('m' + Math.random().toString(36).slice(2), code);
      return { ok: !svg.includes('Syntax error'), error: null };
    } catch (e) {
      return { ok: false, error: String(e.message || e).split('\n').slice(0, 4).join(' | ') };
    }
  }, b.code);
  const kind = b.code.trim().split('\n')[0];
  console.log(`${result.ok ? 'OK  ' : 'FAIL'} ${b.file}:${b.line} ${kind}${result.error ? '\n     ' + result.error : ''}`);
  if (!result.ok) failures++;
}
console.log(`${blocks.length - failures}/${blocks.length} diagrams render`);
await browser.close();
process.exit(failures ? 1 : 0);
