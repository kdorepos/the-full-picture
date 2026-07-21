// Strict visual/CSS audit — drives Playwright over the built site and reports
// layout defects the eye misses: overflow, collisions, children escaping their
// container, and sub-target tap sizes. Also writes full-page screenshots for a
// human/agent to eyeball. Deterministic: same build → same findings.
//
// Usage:  node scripts/visual-audit.mjs <baseUrl>
//   (start `astro preview` first; pass e.g. http://localhost:4433)
// Outputs: JSON findings on stdout + PNGs under shots/audit/.
import { chromium } from 'playwright';
import { readdirSync, mkdirSync } from 'node:fs';

const base = process.argv[2] || 'http://localhost:4433';
const slugs = readdirSync('src/data/episodes')
  .filter((f) => f.endsWith('.json'))
  .map((f) => f.replace('.json', ''));
const pages = ['/', ...slugs.map((s) => `/ep/${s}`)];
const viewports = [
  { name: 'desktop', width: 1180, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
];
mkdirSync('shots/audit', { recursive: true });

// Runs in the page. Returns an array of {check, selector, detail} defects.
function audit() {
  const out = [];
  const sel = (el) =>
    el.tagName.toLowerCase() +
    (el.id ? `#${el.id}` : '') +
    (typeof el.className === 'string' && el.className.trim()
      ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.')
      : '');
  const vw = document.documentElement.clientWidth;

  // 1) Whole-page horizontal scroll — almost always a defect on a fixed-width design.
  const sw = document.documentElement.scrollWidth;
  if (sw - vw > 1) out.push({ check: 'page-hscroll', selector: 'html', detail: `scrollWidth ${sw} > viewport ${vw}` });

  const skip = new Set(['IFRAME', 'PRE', 'CODE', 'TEXTAREA', 'SVG', 'IMG', 'BR', 'HR']);
  const els = [...document.querySelectorAll('main *, footer *, header *')];
  for (const el of els) {
    if (skip.has(el.tagName)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;

    // 2) Content wider than its box with overflow visible → text/pseudo spilling out
    //    (this is exactly the "TOP LOT runs under the poster" class of bug).
    if (cs.overflowX === 'visible' && el.scrollWidth - el.clientWidth > 3) {
      out.push({ check: 'content-overflow', selector: sel(el), detail: `content ${el.scrollWidth}px in ${el.clientWidth}px box` });
    }
    // 3) Content clipped by overflow:hidden → silent truncation.
    if ((cs.overflowX === 'hidden' || cs.overflowX === 'clip') && el.scrollWidth - el.clientWidth > 3 && el.textContent.trim()) {
      out.push({ check: 'clipped-text', selector: sel(el), detail: `${el.scrollWidth}px clipped to ${el.clientWidth}px` });
    }
    // 4) Element escaping its parent's right/left edge (layout leak).
    const p = el.parentElement;
    if (p) {
      const pr = p.getBoundingClientRect();
      const pcs = getComputedStyle(p);
      if (pcs.overflow === 'visible' && (r.right - pr.right > 2 || pr.left - r.left > 2)) {
        out.push({ check: 'escapes-parent', selector: sel(el), detail: `child [${Math.round(r.left)},${Math.round(r.right)}] vs parent [${Math.round(pr.left)},${Math.round(pr.right)}]` });
      }
    }
  }

  // 5) Sub-44px tap targets on narrow screens (WCAG/iOS) — only standalone controls,
  //    not inline text links inside a paragraph (those are read, not tapped as targets).
  if (vw < 500) {
    for (const el of document.querySelectorAll('a[href], button')) {
      const st = getComputedStyle(el);
      if (st.display === 'inline') continue;
      // Skip pure text links (no background/border/padding) — they're read in a list,
      // not tapped as a control; flex/grid children get blockified but are still text.
      const boxed = (st.backgroundColor !== 'rgba(0, 0, 0, 0)' && st.backgroundColor !== 'transparent')
        || st.borderTopWidth !== '0px' || st.borderBottomWidth !== '0px'
        || parseFloat(st.paddingTop) + parseFloat(st.paddingBottom) >= 8;
      if (!boxed) continue;
      const r = el.getBoundingClientRect();
      if (el.offsetParent && r.width > 0 && r.height > 0 && r.height < 40) {
        out.push({ check: 'small-tap-target', selector: sel(el), detail: `${Math.round(r.width)}x${Math.round(r.height)}px` });
      }
    }
  }
  return out;
}

const browser = await chromium.launch();
const findings = [];
const shots = [];
for (const vp of viewports) {
  const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1 });
  // fake an in-flight transcription so the homepage panel is in view too
  await page.route('**/api/progress*', (r) =>
    r.fulfill({ json: { active: true, phase: 'transcribing', slug: '__audit__', title: 'Sample Episode In Progress', done: 4, total: 15, pct: 27 } }));
  for (const path of pages) {
    await page.goto(base + path, { waitUntil: 'networkidle' });
    await page.waitForTimeout(400);
    const defects = await page.evaluate(audit);
    for (const d of defects) findings.push({ page: path, viewport: vp.name, ...d });
    const shot = `shots/audit/${(path === '/' ? 'home' : path.slice(4)).replace(/\W+/g, '-')}-${vp.name}.png`;
    await page.screenshot({ path: shot, fullPage: true });
    shots.push(shot);
  }
  await page.close();
}
await browser.close();
console.log(JSON.stringify({ pages, viewports: viewports.map((v) => v.name), shots, findings }, null, 2));
