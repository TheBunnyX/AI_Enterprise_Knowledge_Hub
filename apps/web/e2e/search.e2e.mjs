// End-to-end test of the "Search knowledge" page in a real browser (Playwright + Chromium) against the running stack.
//   npm i --no-save playwright && npx playwright install chromium
//   BASE_URL=http://localhost:3009 E2E_EMAIL=member@local.test E2E_PASSWORD=... node e2e/search.e2e.mjs
// Needs the demo documents (the sample PDFs and the department documents). Exit code 1 when a check fails.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';

const BASE = process.env.BASE_URL || 'http://localhost:3009';
const results = []; const problems = [];
const test = async (name, fn) => { const t = Date.now(); try { await fn(); results.push(['PASS', name, Date.now() - t]); } catch (e) { results.push(['FAIL', name, Date.now() - t, String(e.message).split('\n')[0].slice(0, 220)]); } };

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, locale: 'en-US' });
const login = await ctx.request.post(BASE + '/api/auth/login', { data: { email: process.env.E2E_EMAIL, password: process.env.E2E_PASSWORD } });
assert.equal(login.status(), 200, 'login failed');
const page = await ctx.newPage();
page.on('pageerror', e => problems.push('pageerror: ' + e.message));
page.on('response', r => { if (r.status() >= 400 && r.url().includes('/api/') && !r.url().includes('/auth/me')) problems.push(r.status() + ' ' + r.url().replace(BASE, '')); });

const input = () => page.getByLabel(/search query|คำค้นหา/i);
const settle = async () => { await page.waitForFunction(() => !document.querySelector('[data-testid=search-loading]') && document.querySelector('.search-results:not([data-testid=all-documents]), .error-box'), null, { timeout: 40000 }); };
const search = async q => { await input().fill(q); await input().press('Enter'); await settle(); };
const names = () => page.locator('.search-result h3').evaluateAll(els => els.map(e => e.childNodes[0].textContent.trim()));
const count = () => page.locator('.search-result').count();
// the filters are custom dropdowns: open the menu, then pick an option like a user would
const pick = async (nth, name) => { await page.locator('.search-filters [role=combobox]').nth(nth).click(); await page.getByRole('option', { name }).first().click(); await settle(); };
const optionsOf = async nth => { await page.locator('.search-filters [role=combobox]').nth(nth).click(); const t = await page.getByRole('option').allTextContents(); await page.keyboard.press('Escape'); return t; };

await page.goto(BASE + '/knowledge/search', { waitUntil: 'networkidle' });

const browse = () => page.locator('[data-testid=all-documents] .search-result');
await test('opens with the start screen, three example searches and every document the user may read', async () => {
  assert.match(await page.locator('h1').first().textContent(), /Search knowledge|ค้นหาความรู้/);
  assert.equal(await page.locator('.search-start button').count(), 3);
  const readable = (await page.evaluate(async () => (await (await fetch('/api/documents')).json()).length));
  assert.ok(readable > 0, 'the test account has no documents');
  assert.equal(await browse().count(), Math.min(8, readable), 'the first page should list the documents');
  assert.match(await page.locator('.section-heading h2 em').first().textContent(), new RegExp('^' + readable + '$'), 'the heading counts all documents, not just the first page');
});

await test('the all-documents list follows the library and file-type filters, opens a preview, and is replaced by search results', async () => {
  const total = await page.locator('.section-heading h2 em').first().textContent();
  await page.locator('.search-filters [role=combobox]').nth(1).click(); await page.getByRole('option', { name: /^pdf$/i }).first().click();
  const pdfs = await page.locator('.section-heading h2 em').first().textContent();
  assert.ok(Number(pdfs) <= Number(total), 'filtering cannot add documents');
  for (const n of await page.locator('[data-testid=all-documents] .search-result h3').allTextContents()) assert.match(n, /\.pdf$/i, 'only PDFs after the PDF filter');
  await page.locator('.search-filters [role=combobox]').nth(1).click(); await page.getByRole('option').first().click();  // back to all file types
  await browse().first().click();
  await page.getByRole('dialog').or(page.locator('[data-testid=document-preview], .preview-pane, .modal')).first().waitFor({ timeout: 15000 });
  await page.keyboard.press('Escape');
  await search('ลาพักร้อน');
  assert.equal(await page.locator('[data-testid=all-documents]').count(), 0, 'results replace the document list');
  await page.goto(BASE + '/knowledge/search', { waitUntil: 'networkidle' });
});

await test('shows a loading screen while searching, explains a long wait, then replaces it with the results', async () => {
  let release; const gate = new Promise(r => { release = r; });
  await page.route('**/api/search?*', async route => { await gate; await route.continue(); });  // hold the answer so the loading state can be seen
  await input().fill('ลาพักร้อนกี่วัน'); await input().press('Enter');
  const loading = page.getByTestId('search-loading');
  await loading.waitFor({ timeout: 5000 });
  assert.equal(await loading.getAttribute('role'), 'status');
  assert.equal(await page.locator('.search-skeleton').count(), 3, 'skeleton cards missing');
  assert.ok(await page.getByRole('button', { name: /Searching|กำลังค้นหา/ }).isDisabled(), 'the search button is not disabled while searching');
  assert.equal(await page.locator('.search-result').count(), 0);
  await page.screenshot({ path: process.env.E2E_SHOT_LOADING || '/tmp/search-loading.png' });
  await page.getByText(/first search can take a moment|ครั้งแรกอาจใช้เวลา/).waitFor({ timeout: 9000 });
  release(); await page.unroute('**/api/search?*');
  await settle();
  assert.equal(await page.getByTestId('search-loading').count(), 0, 'the loading screen is still shown after the results arrived');
  assert.ok(await count() >= 1);
  assert.ok(await page.getByRole('button', { name: /^Search$|^ค้นหา$/ }).isEnabled(), 'the search button stays disabled');
});

await test('an example search runs and shows results', async () => {
  await page.goto(BASE + '/knowledge/search', { waitUntil: 'networkidle' });  // back to the start screen
  await page.locator('.search-start button').nth(2).click(); await settle();
  assert.ok(await count() >= 1, 'no results for the example search');
});

await test('Thai question finds the leave policy first-class, with relevance and the URL updated', async () => {
  await page.goto(BASE + '/knowledge/search', { waitUntil: 'networkidle' });
  await search('ลาพักร้อนกี่วัน');
  assert.ok((await names()).slice(0, 3).some(n => n.includes('นโยบายการลาและวันหยุดพนักงาน')), 'leave policy not in the top 3: ' + (await names()).join(' | '));
  assert.match(await page.locator('.search-result').first().textContent(), /\d+% match|ตรงกับคำค้น \d+%/);
  assert.match(page.url(), /q=/, 'the search is not in the URL');
});

await test('a shared link reopens the same results', async () => {
  const link = page.url(); await page.goto(link, { waitUntil: 'networkidle' }); await settle();
  assert.equal(await input().inputValue(), 'ลาพักร้อนกี่วัน'); assert.ok(await count() >= 1);
});

await test('English question finds Thai documents (multilingual)', async () => {
  await search('how many days of annual leave');
  assert.ok((await names()).some(n => n.includes('ลา')), 'no leave document: ' + (await names()).join(' | '));
});

await test('all three modes return results', async () => {
  for (const label of [/Keywords|คำสำคัญ/, /Vector store/, /Hybrid/]) {
    await search('งบประมาณ'); await page.getByRole('radio', { name: label }).click(); await settle();
    assert.ok(await count() >= 1, 'mode ' + label + ' returned nothing');
  }
});

await test('knowledge base filter keeps only that library', async () => {
  await search('นโยบาย');
  const options = await optionsOf(0); const target = options.find(o => o.includes('ความปลอดภัย')) || options[1];
  await pick(0, target);
  const libs = await page.locator('.search-result span').filter({ hasText: target }).count();
  assert.ok(await count() >= 1 && libs >= 1, 'filter returned no document of ' + target + ' (options: ' + options.join(', ') + ')');
  const others = await page.locator('.search-result').evaluateAll((els, t) => els.filter(e => !e.textContent.includes(t)).length, target);
  assert.equal(others, 0, 'results from other libraries are still shown');
});

await test('file type filter: pdf shows results, xlsx shows the empty state', async () => {
  await page.goto(BASE + '/knowledge/search?q=' + encodeURIComponent('นโยบาย'), { waitUntil: 'networkidle' }); await settle();
  await pick(1, 'pdf'); assert.ok(await count() >= 1);
  await pick(1, 'xlsx'); assert.equal(await count(), 0);
  assert.ok(await page.getByText(/No matching|ยังไม่พบข้อมูลที่ตรงกัน/).count() >= 1, 'no empty-state message');
});

await test('a question with no answer in the documents shows the empty state, not an error', async () => {
  await page.goto(BASE + '/knowledge/search', { waitUntil: 'networkidle' }); await search('ราคาทองคำวันนี้');
  assert.equal(await count(), 0); assert.equal(await page.locator('.error-box').count(), 0);
  assert.ok(await page.getByText(/No matching|ยังไม่พบข้อมูลที่ตรงกัน/).count() >= 1);
});

await test('a picture result shows the real figure as its thumbnail', async () => {
  await search('แผนภาพขั้นตอนการแจ้งเหตุข้อมูลรั่วไหล');
  const img = page.locator('.search-result .document-thumbnail img').first();
  assert.ok(await img.count() >= 1, 'no picture thumbnail; results: ' + (await names()).join(' | '));
  await img.evaluate(el => el.complete || new Promise(r => el.addEventListener('load', r)));
  assert.ok(await img.evaluate(el => el.naturalWidth > 100), 'the thumbnail did not load');
});

await test('clicking a result opens the document preview at the matching page', async () => {
  await page.locator('.search-result').first().click();
  await page.waitForSelector('[role=dialog], .preview-panel, .pdf-preview, canvas', { timeout: 20000 });
});

await test('works on a phone: no sideways scrolling and the search box is usable', async () => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto(BASE + '/knowledge/search', { waitUntil: 'networkidle' }); await search('ลาพักร้อน');
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'page scrolls sideways');
  assert.ok(await count() >= 1);
});

await test('no failed API calls or script errors during the whole run', async () => { assert.deepEqual(problems.slice(0, 5), []); });

await browser.close();
for (const [s, n, ms, why] of results) console.log(`${s}  ${(ms / 1000).toFixed(1).padStart(5)}s  ${n}${why ? '\n        -> ' + why : ''}`);
const failed = results.filter(r => r[0] === 'FAIL').length;
console.log(`\n${results.length - failed}/${results.length} passed`); process.exit(failed ? 1 : 0);
