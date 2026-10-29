// The preview sweep: every app, every control, as the administrator and as a member,
// on a desktop screen and a phone. It drives the published preview (no API behind it:
// web/demo-mock.js answers), does the real flows (make a user, disable them, add an
// event, upload a file, trash it, put it back…) and checks the result is there after a
// re-render and after a reload. Then it clicks everything else once and flags any
// control that did nothing, any page error, any "not in the preview yet".
//
//   node tests/ui/sweep.js [out-dir]            (Playwright and Chromium are on the box)
//   DEMO_DATA=… node tests/ui/sweep.js          to sweep a freshly generated sample set
// Exit code 1 when anything failed.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { serve } = require('./serve-preview');

const OUT = process.argv[2] || path.join(require('os').tmpdir(), 'arise-sweep');
fs.mkdirSync(OUT, { recursive: true });
const results = [];
const rec = (area, control, ok, note = '') => { results.push({ area, control, result: ok === true ? 'pass' : ok === 'skip' ? 'skip' : 'FAIL', note: String(note || '').slice(0, 300) }); if (ok !== true && ok !== 'skip') console.log(`  FAIL ${area} · ${control} · ${note}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

const INSTRUMENT = () => {
  window.__errs = []; window.__toasts = []; window.__warn = [];
  addEventListener('error', e => window.__errs.push('error: ' + (e.message || e.type)));
  addEventListener('unhandledrejection', e => window.__errs.push('rejection: ' + ((e.reason && e.reason.message) || e.reason)));
  const ow = console.warn; console.warn = (...a) => { window.__warn.push(a.join(' ')); ow.apply(console, a); };
  const oe = console.error; console.error = (...a) => { window.__errs.push('console.error: ' + a.join(' ')); oe.apply(console, a); };
  document.addEventListener('DOMContentLoaded', () => { const t = document.getElementById('toasts'); if (t) new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) if (n.nodeType === 1) window.__toasts.push({ cls: n.className, text: n.textContent }); }).observe(t, { childList: true }); });
};

async function newPage(browser, url, viewport = { width: 1440, height: 900 }, storage) {
  const ctx = await browser.newContext({ viewport, storageState: storage });
  await ctx.addInitScript(INSTRUMENT);
  const p = await ctx.newPage(); p.ctx = ctx;
  p.on('pageerror', e => p.evaluate(m => window.__errs && window.__errs.push('pageerror: ' + m), e.message).catch(() => {}));
  p.on('dialog', d => d.accept().catch(() => {}));            // the editor's "discard changes?" confirm
  p.on('popup', pop => pop.close().catch(() => {}));           // Watch / Studio / an assistant: a new tab, closed again
  await p.goto(url, { waitUntil: 'domcontentloaded' }); await settle(p, 1400);
  return p;
}
const settle = (p, ms = 450) => p.waitForTimeout(ms);
const toasts = p => p.evaluate(() => { const t = window.__toasts.slice(); window.__toasts.length = 0; return t; });
const errs = p => p.evaluate(() => { const e = window.__errs.slice(); window.__errs.length = 0; return e; });
const warns = p => p.evaluate(() => { const w = window.__warn.filter(x => x.includes('not in the preview')); window.__warn.length = 0; return w; });
async function app(p, id) { await p.evaluate(i => window.arise.openApp(i), id); for (let i = 0; i < 40; i++) { const busy = await p.evaluate(i => { const b = document.getElementById('wb-' + i); return !b || !!b.querySelector('.skeleton') && !b.querySelector('.finder, .help, .calapp, .settings'); }, id); if (!busy) break; await sleep(100); } await settle(p, 250); }
const modalOpen = p => p.evaluate(() => document.getElementById('modal').open);
const closeModal = p => p.evaluate(() => { const m = document.getElementById('modal'); if (m.open) m.close(); });
async function confirmWord(p, word) { await p.fill('#cfWord', word); await p.click('#cfGo'); await settle(p, 500); await reauth(p); }
async function reauth(p, pw = 'any-password') { if (await p.$('#raPw')) { await p.fill('#raPw', pw); await p.click('#raf button[type=submit]'); await settle(p, 700); } }
const text = (p, sel) => p.evaluate(s => document.querySelector(s)?.textContent || '', sel);
// The text of the first row under sel that mentions needle (querySelector has no :has-text).
const rowText = (p, sel, needle) => p.evaluate(([s, n]) => [...document.querySelectorAll(s + ' tr')].find(t => t.textContent.includes(n))?.textContent || '', [sel, needle]);
const exists = (p, sel) => p.evaluate(s => !!document.querySelector(s), sel);
async function ctxPick(p, sel, label) { await p.click(sel, { button: 'right' }); await settle(p, 200); const ok = await p.evaluate(l => { const b = [...document.querySelectorAll('#ctx button')].find(x => x.textContent.trim() === l); if (b) { b.click(); return true; } return false; }, label); await settle(p, 450); return ok; }
async function flame(p, label) { await p.click('#barLogo'); await settle(p, 200); const ok = await p.evaluate(l => { const b = [...document.querySelectorAll('#menuDrop button')].find(x => x.textContent.startsWith(l)); if (b) { b.click(); return true; } return false; }, label); await settle(p, 500); return ok; }
// Unlock the lock screen. A two-step user is asked for the six digits after the password; the password alone must not unlock.
async function unlock(p) { await p.fill('#lockPw', 'whatever'); await p.keyboard.press('Enter'); await settle(p, 600);
  const asked = await p.evaluate(() => !document.getElementById('lock').hidden && /digits/i.test(document.getElementById('lockPw').placeholder));
  if (asked) { await p.fill('#lockPw', '000000'); await p.keyboard.press('Enter'); await settle(p, 600); }
  return asked; }
async function step(area, control, fn) { const pg = step.page; if (pg) await pg.evaluate(() => { const m = document.getElementById('modal'); if (m && m.open) m.close(); const c = document.getElementById('ctx'); if (c) c.hidden = true; }).catch(() => {}); try { const had = pg ? await pg.evaluate(() => !!document.getElementById('barClock')).catch(() => true) : true; const r = await fn(); if (pg && had && !/Sign out|Sign-in|Member/.test(area + control) && !(await pg.evaluate(() => !!document.getElementById('barClock')).catch(() => true))) return rec(area, control, false, 'the desktop went away (the sign-in screen came up) during this step'); if (r === 'skip') return rec(area, control, 'skip'); rec(area, control, r === undefined ? true : r === true ? true : false, r === false ? 'the expected change did not show' : (typeof r === 'string' ? r : '')); } catch (e) { step.n = (step.n || 0) + 1; if (pg) await pg.screenshot({ path: path.join(OUT, `fail-${step.n}.png`) }).catch(() => {}); const why = e.message.split('\n').filter(l => /intercepts pointer|not visible|not enabled|not stable|outside of the viewport/.test(l)).slice(-1)[0] || ''; rec(area, control, false, e.message.split('\n')[0] + (why ? ' · ' + why.trim() : '')); } }
const bad = (ts, re) => ts.some(t => /\bbad\b/.test(t.cls) && (!re || re.test(t.text)));

/* ---------------- the flows ---------------- */
async function flows(browser, url) {
  const p = await newPage(browser, url); step.page = p; p.setDefaultTimeout(6000);
  const A = 'admin';
  await step(A, 'the desktop boots with no error', async () => { const e = await errs(p); return e.length ? 'errors: ' + e.join(' | ') : true; });
  // Most flows sign in as staff and members through the dashboard: the portal setting. The default ("none": staff use their Macs) has its own step below.
  await p.evaluate(() => window.AriseMock.setStaffAccess('portal'));

  // Directory: users
  await app(p, 'directory');
  await p.screenshot({ path: path.join(OUT, 'dir-1-before.png') });
  await step('Directory', 'New user: a bad name is refused with the rule', async () => { await p.click('#addUser'); await p.fill('#nuName', 'Bad Name'); await p.fill('#nuPw', 'longpassword1'); await p.click('#nuGo'); await settle(p); const t = await toasts(p); await closeModal(p); return bad(t, /name: letters/) || 'no error toast: ' + JSON.stringify(t); });
  await step('Directory', 'New user: a short password is refused', async () => { await p.click('#addUser'); await p.fill('#nuDisp', 'Short Pass'); await p.fill('#nuPw', 'short'); await p.click('#nuGo'); await settle(p); const t = await toasts(p); await closeModal(p); return bad(t, /8 characters/) || JSON.stringify(t); });
  await step('Directory', 'New user: John Smith becomes john.smith, in Staff', async () => { await p.click('#addUser'); await p.fill('#nuDisp', 'John Smith'); const nm = await p.inputValue('#nuName'); if (nm !== 'john.smith') return 'name filled as ' + nm; await p.fill('#nuPw', 'longpassword1'); await p.check('#nuGroups input[value="Staff"]'); await p.uncheck('#nuTemp'); await p.click('#nuGo'); await settle(p, 800); return await exists(p, '#uTable tr[data-q^="john.smith"]'); });
  await p.screenshot({ path: path.join(OUT, 'dir-2-created.png') });
  await step('Directory', 'the new user is still there after a reload', async () => { await p.reload({ waitUntil: 'domcontentloaded' }); await settle(p, 1300); await app(p, 'directory'); return await exists(p, '#uTable tr[data-q^="john.smith"]'); });
  await step('Directory', 'the same name twice is refused', async () => { await p.click('#addUser'); await p.fill('#nuDisp', 'John Smith'); await p.fill('#nuPw', 'longpassword1'); await p.click('#nuGo'); await settle(p); const t = await toasts(p); await closeModal(p); return bad(t, /already exists/) || JSON.stringify(t); });
  await step('Directory', 'Disable shows disabled', async () => { await p.click('[data-tog="john.smith"]'); await settle(p, 700); return (await text(p, '#uTable tr[data-q^="john.smith"]')).includes('disabled'); });
  await p.screenshot({ path: path.join(OUT, 'dir-3-disabled.png') });
  await step('Directory', 'Enable flips it back', async () => { await p.click('[data-tog="john.smith"]'); await settle(p, 700); return !(await text(p, '#uTable tr[data-q^="john.smith"]')).includes('disabled'); });
  await p.screenshot({ path: path.join(OUT, 'dir-4-enabled.png') });
  await step('Directory', 'you cannot disable yourself', async () => { await p.click('[data-tog="bradly"]'); await settle(p); return bad(await toasts(p), /signed in with/); });
  await step('Directory', 'Reset password', async () => { await p.click('[data-pw="john.smith"]'); await p.fill('#rpPw', 'newpassword22'); await p.uncheck('#rpTemp'); await p.click('#rpGo'); await settle(p); const t = await toasts(p); return t.some(x => /Password set/.test(x.text)) || JSON.stringify(t); });
  await step('Directory', 'Find a user filters the list', async () => { await p.fill('#uq', 'john'); await settle(p, 150); const n = await p.evaluate(() => [...document.querySelectorAll('#uTable tbody tr')].filter(t => !t.hidden).length); await p.fill('#uq', ''); return n === 1 || 'rows shown: ' + n; });
  // groups
  await step('Directory', 'New group Praise-Team', async () => { await p.click('#dirTabs [data-t="groups"]'); await p.click('#addGroup'); await p.fill('#ngName', 'Praise-Team'); await p.fill('#ngDesc', 'Sweep group'); await p.click('#ngGo'); await settle(p, 700); return (await text(p, '[data-tab="groups"]')).includes('Praise-Team'); });
  await step('Directory', 'the Groups tab stays open after a re-render', async () => (await p.evaluate(() => !document.querySelector('#wb-directory [data-tab="groups"]').hidden)));
  await step('Directory', 'Add member john.smith to Praise-Team', async () => { await p.click('[data-addm="Praise-Team"]'); await p.fill('#amUser', 'john.smith'); await p.click('#amGo'); await settle(p, 700); return await exists(p, '[data-rmm="Praise-Team"][data-u="john.smith"]'); });
  await step('Directory', 'Add a member who does not exist is refused', async () => { await p.click('[data-addm="Praise-Team"]'); await p.fill('#amUser', 'nobody.here'); await p.click('#amGo'); await settle(p); const t = await toasts(p); await closeModal(p); return bad(t, /no such user/) || JSON.stringify(t); });
  await step('Directory', 'Take john.smith out of Praise-Team', async () => { await p.click('[data-rmm="Praise-Team"][data-u="john.smith"]'); await confirmWord(p, 'john.smith'); return !(await exists(p, '[data-rmm="Praise-Team"][data-u="john.smith"]')); });
  // shares
  await step('Directory', 'Shares tab: New share youth', async () => { await p.click('#dirTabs [data-t="shares"]'); await p.click('#addShare'); await p.fill('#nsName', 'youth'); if ((await p.inputValue('#nsPath')) !== '/srv/arise/shares/youth') return 'path not filled'; await p.click('#nsGo'); await settle(p, 700); return (await text(p, '#wb-directory [data-tab="shares"]')).includes('youth'); });
  await step('Directory', 'Folders and permissions shows the Pastors share and the ACLs', async () => { await p.click('#wb-directory #shFolders'); await settle(p, 600); const t = await text(p, '#modalBody'); await closeModal(p); return (t.includes('[pastors]') && t.includes('[church]') && t.includes('setfacl')) || t.slice(0, 200); });
  await step('Directory', 'a bad share name is refused', async () => { await p.click('#addShare'); await p.fill('#nsName', '!!'); await p.fill('#nsPath', '/srv/arise/x'); await p.click('#nsGo'); await settle(p); const t = await toasts(p); await closeModal(p); return bad(t, /share name/) || JSON.stringify(t); });
  await step('Directory', 'Remove share youth (typed name)', async () => { await p.click('#wb-directory [data-rm="youth"]'); await confirmWord(p, 'youth'); return !(await text(p, '#wb-directory [data-tab="shares"]')).includes('[youth]') && !(await exists(p, '#wb-directory [data-rm="youth"]')); });
  await step('Directory', 'Delete john.smith asks twice (name, then password)', async () => { await p.click('#dirTabs [data-t="users"]'); await p.click('[data-del="john.smith"]'); await p.fill('#cfWord', 'john.smith'); await p.click('#cfGo'); await settle(p, 500); const asked = await exists(p, '#raPw'); await reauth(p); await settle(p, 600); const gone = !(await exists(p, '#uTable tr[data-q^="john.smith"]')); return asked && gone ? true : `asked again: ${asked}, gone: ${gone}`; });
  // put john back for the sign-in tests
  await p.click('#addUser'); await p.fill('#nuDisp', 'John Smith'); await p.fill('#nuPw', 'longpassword1'); await p.check('#nuGroups input[value="Staff"]'); await p.uncheck('#nuTemp'); await p.click('#nuGo'); await settle(p, 700);

  // Finder
  await app(p, 'files');
  await step('Finder', 'Home folders → bradly', async () => { await p.click('[data-go="data|/homes"]'); await settle(p, 500); await p.dblclick('.fi[data-n="bradly"]'); await settle(p, 500); return (await text(p, '.finder__tb .title')) === 'bradly'; });
  await step('Finder', 'New folder', async () => { await p.click('#fNew'); await p.fill('#nfName', 'Sweep folder'); await p.click('#nfGo'); await settle(p, 600); return await exists(p, '.fi[data-n="Sweep folder"]'); });
  await step('Finder', 'a folder with a slash is refused', async () => { await p.click('#fNew'); await p.fill('#nfName', 'a/b'); await p.click('#nfGo'); await settle(p); const t = await toasts(p); await closeModal(p); return bad(t, /bad folder name/) || JSON.stringify(t); });
  await step('Finder', 'Upload a text file', async () => { await p.setInputFiles('#fsUp', { name: 'notes.md', mimeType: 'text/markdown', buffer: Buffer.from('# Sweep notes\n\nHello from the sweep.\n') }); await settle(p, 800); return await exists(p, '.fi[data-n="notes.md"]'); });
  await step('Finder', 'Edit the text file and save', async () => { await p.dblclick('.fi[data-n="notes.md"]'); await settle(p, 500); await p.fill('#edText', '# Sweep notes\n\nEdited by the sweep.\n'); await p.click('#edSave'); await settle(p, 500); const st = await text(p, '#edSt'); await p.click('#edClose'); await settle(p, 300); return st.startsWith('saved') || 'status: ' + st; });
  await step('Finder', 'the Markdown preview renders', async () => { await p.dblclick('.fi[data-n="notes.md"]'); await settle(p, 500); await p.click('#edTabs [data-t="prev"]'); await settle(p, 400); const h = await p.evaluate(() => document.getElementById('edPrev').innerHTML); await p.click('#edClose'); return h.includes('<h1>') || h; });
  await step('Finder', 'Quick Look (Space) shows the saved text', async () => { await p.click('.fi[data-n="notes.md"]'); await p.keyboard.press(' '); await settle(p, 400); const t = await text(p, '#qlBody'); await p.click('#qlClose'); return t.includes('Edited by the sweep') || t; });
  await step('Finder', 'Get Info', async () => { const ok = await ctxPick(p, '.fi[data-n="notes.md"]', 'Get Info'); const o = await modalOpen(p); const t = await text(p, '#modalBody'); await closeModal(p); return ok && o && t.includes('notes.md') ? true : 'no info'; });
  await step('Finder', 'Previous Versions', async () => { await ctxPick(p, '.fi[data-n="notes.md"]', 'Previous Versions…'); const t = await text(p, '#modalBody'); const btn = await exists(p, '#modalBody [data-snap]'); if (btn) { await p.click('#modalBody [data-snap]'); await settle(p, 600); } else await closeModal(p); return btn ? await exists(p, '.fi[data-n^="notes (restored"]') : t; });
  await step('Finder', 'Share Link…', async () => { await ctxPick(p, '.fi[data-n="notes.md"]', 'Share Link…'); await p.click('#slGo'); await settle(p, 400); const t = await text(p, '#slOut'); await closeModal(p); return /\/s\//.test(t) || t; });
  await step('Finder', 'Shared links lists it, and Remove takes it away', async () => { await p.click('#fLinks'); await settle(p, 400); const n = (await p.$$('#modalBody [data-rm]')).length; const has = (await text(p, '#modalBody')).includes('notes.md'); if (!has) { await closeModal(p); return 'not listed'; } await p.click('#modalBody tr:has-text("notes.md") [data-rm]'); await settle(p, 500); const n2 = (await p.$$('#modalBody [data-rm]')).length; await closeModal(p); return n2 === n - 1 || `${n} → ${n2}`; });
  // round 5: the home quota, Share with…, Shared with me, the hidden Pastors folder (rows 13, 18, 19)
  await step('Finder', 'the quota line shows bradly against 50 GB', async () => { const t = await text(p, '#fQuota'); return /of 50\.0 GB/.test(t) || 'quota line: ' + t; });
  await step('Finder', 'Share with… a person tells them it is shared', async () => { const ok = await ctxPick(p, '.fi[data-n="notes.md"]', 'Share with…'); if (!ok) return 'no Share with… in the menu'; await p.fill('#swTo', 'office'); await p.click('#swF button[type=submit]'); await settle(p, 600); const t = await toasts(p); return t.some(x => /Shared with office/.test(x.text)) || JSON.stringify(t); });
  await step('Finder', 'the recipient has it under Shared with me', async () => { const r = await p.evaluate(async () => { window.AriseMock.viewAs('member'); const who = window.AriseMock.session().user; const roots = (await window.AriseMock.handle('GET', '/files/roots')).roots || []; const lst = roots.find(x => x.shared) ? await window.AriseMock.handle('GET', '/files/list?root=' + encodeURIComponent(roots.find(x => x.shared).id) + '&path=/') : null; window.AriseMock.viewAs('admin'); return { who, names: roots.filter(x => x.shared).map(x => x.name), entries: (lst?.entries || []).map(e => e.name) }; }); return (r.who === 'office' && r.names.includes('notes (from bradly).md') && r.entries.join() === 'notes.md') || JSON.stringify(r); });
  await step('Finder', 'Shared by me lists it, and Stop sharing takes it back', async () => { await p.click('#fSharedBy'); await settle(p, 400); const has = (await text(p, '#modalBody')).includes('notes.md'); const b = await p.$('#modalBody [data-unshare]'); if (!b) return 'no Stop sharing button'; await b.click(); await settle(p, 700); const t = await toasts(p); await closeModal(p); const left = await p.evaluate(async () => ((await window.AriseMock.handle('GET', '/files/shared')).by_me || []).length); return (has && t.some(x => /Stopped sharing/.test(x.text)) && left === 0) || `listed: ${has}, left: ${left}, ${JSON.stringify(t)}`; });
  await step('Finder', 'the Pastors folder is hidden from the administrator', async () => { await p.click('[data-go="data|/"]'); await settle(p, 500); const homes = await exists(p, '.fi[data-n="homes"]'); const pastors = await exists(p, '.fi[data-n="pastors"]'); await p.click('[data-go="data|/homes"]'); await settle(p, 400); await p.dblclick('.fi[data-n="bradly"]'); await settle(p, 500); return (homes && !pastors) || `homes: ${homes}, pastors shown: ${pastors}`; });
  await step('Finder', 'Move to Trash (typed name)', async () => { await ctxPick(p, '.fi[data-n="notes.md"]', 'Move to Trash'); await confirmWord(p, 'notes.md'); return !(await exists(p, '.fi[data-n="notes.md"]')); });
  await step('Finder', 'the Trash holds it; Put Back brings it home', async () => { await p.click('[data-go="@trash|/"]'); await settle(p, 500); const row = await p.$('tr:has-text("notes.md") [data-back]'); if (!row) return 'not in the Trash'; await row.click(); await settle(p, 600); await p.click('[data-go="data|/homes"]'); await settle(p, 400); await p.dblclick('.fi[data-n="bradly"]'); await settle(p, 500); return await exists(p, '.fi[data-n="notes.md"]'); });
  await step('Finder', 'Recents shows this week\'s files', async () => { await p.click('[data-go="@recent|/"]'); await settle(p, 500); return (await text(p, '#fMain')).includes('notes.md'); });
  await step('Finder', 'All Documents (everyone\'s, side by side)', async () => { await p.click('[data-go="@all:Documents|/"]'); await settle(p, 500); return (await p.$$('#fMain [data-p]')).length > 0; });
  await step('Finder', 'Empty Trash asks for the share, then the name', async () => { await p.click('[data-go="@trash|/"]'); await settle(p, 500); const n = (await p.$$('[data-back]')).length; if (!n) return 'skip'; await p.click('#fEmpty'); await settle(p, 300); const share = await p.inputValue('#etShare'); await p.click('#etGo'); await settle(p, 300); await confirmWord(p, share); const n2 = (await p.$$('[data-back]')).length; return n2 < n || `${n} → ${n2}`; });
  await step('Finder', 'Spotlight finds the uploaded file', async () => { await p.keyboard.press('Control+Space'); await p.keyboard.type('notes'); await settle(p, 700); const t = await text(p, '#spotRes'); await p.keyboard.press('Escape'); return t.includes('notes.md') || t.slice(0, 120); });

  // Calendar
  await app(p, 'calendar');
  const day = await p.evaluate(() => { const d = new Date(); d.setDate(Math.min(27, d.getDate() + 2)); return d.toISOString().slice(0, 10); });
  await step('Calendar', 'Add an event shows in the month', async () => { await p.click('#calAdd'); await p.fill('#evT', 'Sweep bake sale'); await p.fill('#evS', day + 'T10:00'); await p.click('#evf button[type=submit]'); await settle(p, 700); return (await text(p, '.calm')).includes('Sweep bake sale'); });
  await step('Calendar', 'an event without a title is refused', async () => { await p.click('#calAdd'); await p.fill('#evS', day + 'T10:00'); await p.evaluate(() => { const t = document.getElementById('evT'); t.removeAttribute('required'); t.value = '  '; }); await p.click('#evf button[type=submit]'); await settle(p); const t = await toasts(p); await closeModal(p); return bad(t, /title/) || JSON.stringify(t); });
  await step('Calendar', 'Edit the event', async () => { await p.click('.calm__ev:has-text("Sweep bake sale")'); await p.click('#evEd'); await p.fill('#evT', 'Sweep bake sale (moved)'); await p.click('#evf button[type=submit]'); await settle(p, 700); return (await text(p, '.calm')).includes('(moved)'); });
  await step('Calendar', 'Next month and back', async () => { const a = await text(p, '.calapp__hd h2'); await p.click('#calNext'); await settle(p, 400); const b = await text(p, '.calapp__hd h2'); await p.click('#calPrev'); await settle(p, 400); return a !== b && (await text(p, '.calapp__hd h2')) === a; });
  await step('Calendar', 'Subscribe shows the feed address', async () => { await p.click('#calSub'); await settle(p, 300); const v = await p.inputValue('#subUrl'); await closeModal(p); return /^webcal:/.test(v) || v; });
  await step('Calendar', 'Remove the event (typed word)', async () => { await p.click('.calm__ev:has-text("(moved)")'); await p.click('#evRm'); await confirmWord(p, 'remove'); return !(await text(p, '.calm')).includes('(moved)'); });

  // Sunday
  await app(p, 'sunday');
  await step('Sunday', 'a tick stays ticked after a re-render and a reload', async () => { const before = await p.isChecked('input[data-i="2"]'); await p.click('input[data-i="2"]'); await settle(p, 600); const mid = await p.isChecked('input[data-i="2"]'); await p.reload({ waitUntil: 'domcontentloaded' }); await settle(p, 1300); await app(p, 'sunday'); const after = await p.isChecked('input[data-i="2"]'); return mid !== before && after === mid; });

  // Backups, automator, Synology, services
  await app(p, 'backups');
  await step('Backups', 'Run now adds a history row', async () => { const n = (await p.$$('[data-tab="hist"] tbody tr')).length; await p.click('[data-run="homes"]'); await sleep(3200); return (await p.$$('[data-tab="hist"] tbody tr')).length === n + 1; });
  await step('Backups', 'the Repos tab lists the Arise repos and Sync now stamps them', async () => { await p.click('#bkTabs [data-t="repos"]'); await settle(p, 800); const rows = (await p.$$('#bkRepos tbody tr')).length; await toasts(p); await p.click('#repoSync'); await settle(p, 600); const t = await toasts(p); return rows >= 8 && t.some(x => /Sync started/.test(x.text)) ? true : `${rows} rows, toasts ${JSON.stringify(t.map(x => x.text))}`; });
  await step('Backups', 'Check now stamps the integrity check', async () => { await p.click('#bkCheck'); await settle(p, 500); await p.evaluate(() => window.arise.rerender('backups')); await settle(p, 500); return (await text(p, '#wb-backups')).includes('just now'); });
  await step('Backups', 'the tabs open (History, Snapshots, Restore)', async () => { for (const t of ['snaps', 'restore', 'hist']) { await p.click(`#bkTabs [data-t="${t}"]`); await settle(p, 120); if (await p.evaluate(x => document.querySelector(`#wb-backups [data-tab="${x}"]`).hidden, t)) return t + ' did not show'; } return true; });
  await step('Backups', 'Where tonight\'s backup goes names the live target', async () => { const t = await text(p, '#bkTarget'); return (t.includes('Arise-Home') && t.includes('live')) || 'panel: ' + t.slice(0, 160); });
  await app(p, 'automator');
  await step('Automator', 'Run now is refused while the 02:05 timer is on', async () => { await p.click('#auRun'); await p.click('#auGo'); await settle(p, 500); const t = await toasts(p); await closeModal(p); return bad(t, /timer is on/) || JSON.stringify(t); });
  await step('Automator', 'Preview tonight', async () => { await p.click('#auPreview'); await settle(p, 400); const t = await toasts(p); return t.some(x => /Preview started/.test(x.text)) || JSON.stringify(t); });
  await step('Automator', 'a past report opens', async () => { await p.click('#auTabs [data-t="reports"]'); await p.click('[data-rep]'); await settle(p, 400); return (await text(p, '#repBody')).length > 20; });
  await step('Automator', 'Videos lists the channel with thumbnails and filters by title', async () => { await p.click('#auTabs [data-t="videos"]'); await settle(p, 600); const n = (await p.$$('#chVideos .vcard')).length; await p.fill('#chQ', 'pitch'); await settle(p, 900); const m = (await p.$$('#chVideos .vcard')).length; await p.fill('#chQ', ''); await settle(p, 900); return n >= 5 && m >= 1 && m < n ? true : `cards ${n}, after filter ${m}`; });
  await step('Automator', 'Shorts / Services filter', async () => { await p.click('#chKind [data-k="short"]'); await settle(p, 700); const k = await p.$$eval('#chVideos .vcard small', els => els.map(e => e.textContent)); await p.click('#chKind [data-k=""]'); await settle(p, 700); return k.length > 0 && k.every(t => /Short/.test(t)) ? true : JSON.stringify(k); });
  await step('Automator', 'a video opens: thumbnails, YouTube and Studio links, chapters, transcript', async () => { await p.click('#chVideos .vcard[data-vid="AnVfOCesXM4"]'); await settle(p, 1400); const r = await p.evaluate(() => ({ yt: !!document.querySelector('#chVideos a[href^="https://youtu.be/AnVfOCesXM4"]'), studio: !!document.querySelector('#chVideos a[href="https://studio.youtube.com/video/AnVfOCesXM4/edit"]'), thumbs: document.querySelectorAll('#chVideos .chthumbs figure').length, chap: document.querySelectorAll('#chVideos .chchap__r').length, tx: document.querySelectorAll('#chTxL .chtx__r').length, shorts: document.querySelectorAll('#chVideos .chv ~ .grid .vcard').length })); return r.yt && r.studio && r.thumbs >= 2 && r.chap >= 3 && r.tx > 10 && r.shorts >= 1 ? true : JSON.stringify(r); });
  await step('Automator', 'a chapter jumps the transcript to its moment', async () => { await p.click('#chVideos .chchap__r:nth-child(4) button'); await settle(p, 700); const t = await p.evaluate(() => { const on = document.querySelector('#chTxL .chtx__r.on'); return on ? +on.dataset.t : null; }); return t === 2400 ? true : `highlighted ${t}`; });
  await step('Automator', 'find in this transcript marks the lines', async () => { await p.fill('#chTxQ', 'altar'); await settle(p, 600); const n = (await p.$$('#chTxL .chtx__r.hit')).length; return n > 0 ? true : 'no lines marked'; });
  await step('Automator', 'Copy clean strips ** and CCLI numbers', async () => { const r = await p.evaluate(() => window.arise.cleanDesc('**PRAISE** (CCLI Song # 7213077)\nLine two  ')); return r === 'PRAISE\nLine two' ? true : JSON.stringify(r); });
  await step('Automator', 'a Short opens its full service', async () => { await p.click('#chVideos .vcard[data-vid="yMewy7Nwi3c"]'); await settle(p, 1200); await p.click('#chVideos .chv__acts [data-vid="AnVfOCesXM4"]'); await settle(p, 1200); const t = await text(p, '#chVideos .chv__title'); await p.click('#chBack'); await settle(p, 700); return /PITCH THE SHIP/i.test(t) ? true : t; });
  await step('Automator', 'Search finds the transcript and opens the video at that moment', async () => { await p.click('#auTabs [data-t="search"]'); await p.fill('#chSQ', 'garrison'); await p.click('#chSF button'); await settle(p, 900); const groups = (await p.$$('#chSR .chg')).length; await p.click('#chSR .chhit__t'); await settle(p, 1400); const r = await p.evaluate(() => ({ title: document.querySelector('#chSearch .chv__title')?.textContent || '', on: document.querySelector('#chTxL .chtx__r.on')?.dataset.t })); await p.click('#chBack'); await settle(p, 900); const back = (await p.$$('#chSR .chg')).length; return groups >= 1 && /garrison/i.test(r.title) && r.on != null && back === groups ? true : JSON.stringify({ groups, ...r, back }); });
  await step('Automator', 'Search: nothing found says so, and the kind chips switch', async () => { await p.fill('#chSQ', 'zzqqxx'); await p.click('#chSF button'); await settle(p, 700); const e = await text(p, '#chSR'); await p.click('#chSK [data-k="all"]'); await settle(p, 700); const on = await p.evaluate(() => document.querySelector('#chSK .chip.active')?.dataset.k); return /Nothing found/.test(e) && on === 'all' ? true : `${e.slice(0, 80)} / ${on}`; });
  await step('Songs', 'the song list opens and finds a song by title, writer and CCLI number', async () => { await p.click('#auTabs [data-t="songs"]'); await settle(p, 700); const n = (await p.$$('#chSongs [data-song]')).length; const find = async q => { await p.fill('#sgQ', q); await settle(p, 800); return p.$$eval('#chSongs [data-song] b', els => els.map(e => e.textContent)); }; const a = await find('battles'), b = await find('figueroa'), c = await find('7247827'); await p.fill('#sgQ', ''); await settle(p, 800); return n >= 5 && /Surrounded/.test(a[0]) && /Surrounded/.test(b[0]) && /Revival/.test(c[0]) ? true : JSON.stringify({ n, a, b, c }); });
  await step('Songs', 'a line of the lyrics finds its song', async () => { await p.fill('#sgQ', 'sample chorus'); await settle(p, 800); const t = await p.$$eval('#chSongs [data-song]', els => els.map(e => e.textContent)); await p.fill('#sgQ', ''); await settle(p, 800); return t.length >= 1 && /Revival/.test(t[0]) && /chorus/i.test(t[0]) ? true : JSON.stringify(t); });
  await step('Songs', 'paste lyrics into a song, save, and they show', async () => { await p.click('#chSongs [data-song="7122057"]'); await settle(p, 900); await p.fill('#sgText', 'Verse 1\nSample pasted from Proclaim\n\nChorus\nSample chorus for the test'); await p.click('#sgSave'); await settle(p, 900); const t = await text(p, '#sgLyr'); return /pasted from Proclaim/.test(t) ? true : t.slice(0, 80); });
  await step('Songs', 'Find a line in the transcripts opens the Search tab with that line', async () => { await p.click('#sgFind'); await settle(p, 900); const q = await p.evaluate(() => document.querySelector('#chSQ')?.value); const on = await p.evaluate(() => !document.getElementById('chSearch').hidden); await p.click('#auTabs [data-t="songs"]'); await settle(p, 500); return on && q === '"Sample pasted from Proclaim"' ? true : `${on} ${q}`; });
  await step('Songs', 'removing lyrics asks for the title, then they are gone', async () => { await p.click('#sgRm'); await p.fill('#cfWord', 'Make Room'); await p.click('#cfGo'); await settle(p, 900); const t = await p.evaluate(() => !!document.querySelector('#sgText')); await p.click('#sgBack'); await settle(p, 700); return t ? true : 'no paste box after removing'; });
  await step('Songs', 'importing a ChordPro file links it by its CCLI number', async () => { await p.setInputFiles('#sgFile', { name: 'make-room.cho', mimeType: 'text/plain', buffer: Buffer.from('{title: Make Room}\n{ccli: 7122057}\n{soc}\n[G]Sample imported line\n{eoc}\n') }); await settle(p, 1000); const m = await text(p, '#modal'); await closeModal(p); await settle(p, 600); const row = await text(p, '#chSongs [data-song="7122057"]'); return /linked/.test(m) && /Make Room/.test(m) && /yes/i.test(row) ? true : `${m.slice(0, 120)} / ${row}`; });
  await step('Automator', 'Server switch shows the runner and the checklist', async () => { await p.click('#auTabs [data-t="switch"]'); await settle(p, 700); const t = await text(p, '#auSwitch'); const rows = (await p.$$('#auSwitch .chsw__r')).length; return /the PC/.test(t) && rows >= 5 ? true : `${rows} rows: ${t.slice(0, 80)}`; });
  // ---- round 5: the Desktop folder, notifications, department checklists, the monitor's size, the guided setup ----
  await p.evaluate(() => { Object.keys(window.arise.S.wins).forEach(k => window.arise.closeApp(k)); }); await settle(p, 300);
  await step('Desktop', 'the Desktop folder shows on the wallpaper, with the drives', async () => { await p.evaluate(() => window.arise.buildDeskIcons()); await settle(p, 800); const n = await p.$$eval('#deskIcons .deskico', els => els.map(e => e.dataset.dn)); const drives = (await p.$$('#icons .ico')).length; return n.includes('Glory Night run sheet.md') && n.includes('Outpour graphics') && drives >= 1 ? true : JSON.stringify({ n, drives }); });
  await step('Desktop', 'double-click a text file opens it in the editor', async () => { await p.dblclick('#deskIcons .deskico[data-dn="Glory Night run sheet.md"]'); const ok = await p.waitForSelector('#modal[open] #edText', { timeout: 4000 }).then(() => true, () => false); if (!ok) await p.screenshot({ path: path.join(OUT, 'desk-editor-fail.png') }); await p.keyboard.press('Escape'); await p.evaluate(() => { const m = document.getElementById('modal'); if (m && m.open) m.close(); }); return ok ? true : 'no editor'; });
  await step('Desktop', 'double-click a folder opens it in Finder', async () => { await p.dblclick('#deskIcons .deskico[data-dn="Outpour graphics"]'); await settle(p, 1200); const t = await text(p, '#wb-files'); await p.evaluate(() => window.arise.closeApp('files')); await settle(p, 300); return /outpour-lower-third/.test(t) ? true : t.slice(0, 80); });
  await step('Desktop', 'right-click gives Open, Get Info and Move to Trash', async () => { await p.click('#deskIcons .deskico[data-dn="stage-wide.jpg"]', { button: 'right' }); await settle(p, 200); const t = await text(p, '#ctx'); await p.keyboard.press('Escape'); await p.mouse.click(600, 500); return /Open/.test(t) && /Get Info/.test(t) && /Trash/.test(t) ? true : t; });
  await step('Desktop', 'an icon dragged on the wallpaper stays where it was put, after a reload', async () => { const b = await p.$('#deskIcons .deskico[data-dn="stage-wide.jpg"]'); const box = await b.boundingBox(); await p.dragAndDrop('#deskIcons .deskico[data-dn="stage-wide.jpg"]', '#stage', { targetPosition: { x: 420, y: 260 } }); await settle(p, 600); await p.reload({ waitUntil: 'domcontentloaded' }); await settle(p, 1800); await p.evaluate(() => window.arise.buildDeskIcons()); await settle(p, 700); const b2 = await p.$('#deskIcons .deskico[data-dn="stage-wide.jpg"]'); const box2 = b2 && await b2.boundingBox(); return box2 && Math.abs(box2.x - box.x) > 40 ? true : JSON.stringify({ box, box2 }); });
  await step('Desktop', 'a file dragged out of Finder lands on the Desktop', async () => { await p.evaluate(() => { window.arise.S.fs = Object.assign(window.arise.S.fs || { view: 'icon', hist: [], fwd: [], q: '' }, { root: 'data', path: '/homes/bradly/Documents', sel: null }); window.arise.openApp('files'); }); await settle(p, 1400); await p.dragAndDrop('#fMain [data-n="Sunday setlist 2026-10-26.pdf"]', '#stage', { targetPosition: { x: 300, y: 420 } }); await settle(p, 1200); const on = await exists(p, '#deskIcons .deskico[data-dn="Sunday setlist 2026-10-26.pdf"]'); await p.evaluate(() => window.arise.closeApp('files')); await settle(p, 300); return on ? true : 'not on the Desktop'; });
  await step('Notifications', 'the clock shows the unread count; the notification centre lists them and clears it', async () => { await p.evaluate(() => window.arise.notifyBadge(true)); await settle(p, 400); const n = await p.evaluate(() => document.getElementById('barClock').dataset.unread); await p.click('#barClock'); await settle(p, 900); const t = await text(p, '#ncNotes'); await p.click('#barClock'); await settle(p, 600); const after = await p.evaluate(() => document.getElementById('barClock').dataset.unread); return +n >= 1 && /Media checklist/.test(t) && !after ? true : JSON.stringify({ n, t: t.slice(0, 80), after }); });
  await step('Department checklists', 'the Sunday app shows each department\'s list', async () => { await app(p, 'sunday'); await settle(p, 900); const d = await p.$$eval('#deptLists .dept', els => els.map(e => e.dataset.dept)); return d.includes('Media') && d.includes('Childrens-Department') ? true : JSON.stringify(d); });
  await step('Department checklists', 'ticking an item counts it', async () => { await p.click('#deptLists .dept[data-dept="Media"] input[data-dept-i="0"]'); await settle(p, 800); const t = await text(p, '#deptLists .dept[data-dept="Media"]'); return /1 of 5/.test(t) ? true : t.slice(0, 120); });
  await step('Department checklists', 'a nudge at or after the service is refused', async () => { await p.click('[data-dedit="Media"]'); await settle(p, 300); await p.fill('[data-denudge="Sunday Service"]', '11:00'); await toasts(p); await p.click('#deF button[type=submit]'); await settle(p, 500); const t = await toasts(p); await closeModal(p); return t.some(x => /at or after/.test(x.text)) ? true : JSON.stringify(t); });
  await step('Department checklists', 'the leader and the items are edited', async () => { await p.click('[data-dedit="Inedge"]'); await settle(p, 300); await p.fill('#deItems', 'Room set up\nSound check'); await p.fill('#deLead', 'inedge'); await p.click('#deF button[type=submit]'); await settle(p, 900); const t = await text(p, '#deptLists .dept[data-dept="Inedge"]'); return /Room set up/.test(t) && /Leader: inedge/.test(t) ? true : t.slice(0, 160); });
  await p.evaluate(() => window.arise.closeApp('sunday')); await settle(p, 300);
  await step('Settings', 'The monitor & setup: the text size for the closet monitor', async () => { await app(p, 'settings'); await p.click('[data-sec="monitor"]'); await settle(p, 700); await toasts(p); await p.click('[data-scale="1.4"]'); await settle(p, 800); const t = await toasts(p); const on = await p.evaluate(() => document.querySelector('[data-scale="1.4"]')?.classList.contains('active')); return t.some(x => /140%/.test(x.text)) && on ? true : JSON.stringify({ t, on }); });
  await step('Setup', 'the guided setup opens from Settings and walks the steps', async () => { await p.click('#stSetup'); await settle(p, 900); const steps = await p.$$eval('[data-wstep]', els => els.map(e => e.dataset.wstep)); await p.click('[data-wstep="discord"]'); await settle(p, 600); await p.click('[data-wmark="done"]'); await settle(p, 900); const after = await p.evaluate(() => document.querySelector('[data-wstep="discord"] .pill')?.textContent); await closeModal(p); return steps.join(',') === 'people,shares,synology,discord,resend,tailscale' && after === 'done' ? true : JSON.stringify({ steps, after }); });
  await step('Setup', 'Later closes it until Settings opens it again', async () => { await p.click('#stSetup'); await settle(p, 800); await p.click('#wzLater'); await settle(p, 500); const st = await p.evaluate(async () => (await window.arise.api('/setup')).dismissed); return st === true ? true : `dismissed ${st}`; });
  await p.evaluate(() => window.arise.closeApp('settings')); await settle(p, 300);
  await app(p, 'nas');
  await step('Synology', 'Unmount then Mount', async () => { await p.click('#nasUn'); await settle(p, 700); const off = (await text(p, '#wb-nas')).includes('not mounted'); await p.click('#nasMount'); await settle(p, 700); const on = !(await text(p, '#wb-nas')).includes('not mounted'); return off && on; });
  await app(p, 'services');
  await step('Services', 'Stop and Start a unit', async () => { await p.click('[data-svc="docker.service"][data-do="stop"]'); await sleep(1500); const s1 = await rowText(p, '#wb-services', 'docker.service'); await p.click('[data-svc="docker.service"][data-do="start"]'); await sleep(1500); const s2 = await rowText(p, '#wb-services', 'docker.service'); return s1.includes('inactive') && s2.includes('active · running') ? true : s1 + ' / ' + s2; });

  // Store
  await app(p, 'apps');
  await step('Store', 'Stop an app, then Start it', async () => { await p.click('[data-app="netdata"][data-do="stop"]'); await sleep(1900); const a = await rowText(p, '#wb-apps', 'netdata'); await p.click('[data-app="netdata"][data-do="start"]'); await sleep(1900); const b = await rowText(p, '#wb-apps', 'netdata'); return a.includes('stopped') && b.includes('running') ? true : a.slice(0, 60) + ' / ' + b.slice(0, 60); });
  await step('Store', 'Autostart off sticks after a reload', async () => { await p.uncheck('[data-auto="netdata"]'); await settle(p, 400); await p.reload({ waitUntil: 'domcontentloaded' }); await settle(p, 1300); await app(p, 'apps'); return !(await p.isChecked('[data-auto="netdata"]')); });
  await step('Store', 'Install from the catalogue', async () => { await p.click('#storeTabs [data-t="catalog"]'); await settle(p, 400); await p.fill('#storeQ', 'gitea'); await sleep(700); await p.click('[data-deploy="gitea"]'); await sleep(2500); await p.click('#storeTabs [data-t="installed"]'); await settle(p, 400); return (await text(p, '#wb-apps [data-tab="installed"]')).includes('gitea'); });
  await step('Store', 'Remove keeps the data folder (typed name)', async () => { await p.click('[data-rmapp="gitea"]'); await confirmWord(p, 'gitea'); return !(await exists(p, '[data-rmapp="gitea"]')); });
  await step('Store', 'the house look of an app', async () => { await p.click('#storeTabs [data-t="catalog"]'); await p.fill('#storeQ', ''); await sleep(600); const b = await p.$('[data-theme]'); if (!b) return 'no themed app'; await b.click(); await settle(p, 400); const o = await modalOpen(p); await closeModal(p); return o; });

  // Automations, updates, activity, storage, monitor, logs
  await app(p, 'automations');
  await step('Automations', 'Pause a timer, then Resume it', async () => { await p.click('[data-pause="arise-backup.timer"]'); await confirmWord(p, 'arise-backup.timer'); const a = await rowText(p, '#wb-automations', 'arise-backup.timer'); await p.click('[data-pause="arise-backup.timer"]'); await confirmWord(p, 'arise-backup.timer'); const b = await rowText(p, '#wb-automations', 'arise-backup.timer'); return a.includes('paused') && !b.includes('paused') ? true : a.slice(0, 80); });
  await app(p, 'updates');
  await step('Software Update', 'Queue the ticked items', async () => { await p.check('[data-pkg="tzdata"]'); await p.click('#upQueue'); await settle(p, 700); return (await text(p, '#wb-updates')).includes('just now'); });
  await step('Software Update', 'Install now (typed word) applies the queue', async () => { await p.click('#upNow'); await confirmWord(p, 'install'); await settle(p, 400); return (await text(p, '#wb-updates')).includes('Last apply'); });
  await app(p, 'activity');
  await step('Activity Monitor', 'End a process (typed PID)', async () => { const b = await p.$('[data-kill]'); if (!b) return 'no process to end'; const pid = await b.getAttribute('data-kill'); await b.click(); await confirmWord(p, pid); return !(await exists(p, `[data-kill="${pid}"]`)); });
  await step('Activity Monitor', 'sort by memory', async () => { await p.click('[data-sort="mem"]'); await settle(p, 400); return (await text(p, '#wb-activity th.on')).includes('Memory'); });
  await p.evaluate(() => window.arise.closeApp('activity'));
  await app(p, 'storage');
  await step('Storage', 'Rescan', async () => { await p.click('#stScan'); await settle(p, 400); return (await toasts(p)).some(t => /Scan started/.test(t.text)); });
  await step('Storage', 'the home quotas panel lists every home against 50 GB', async () => { await settle(p, 400); const t = await text(p, '#stQuotas'); return (t.includes('bradly') && t.includes('50.0 GB')) || 'panel: ' + t.slice(0, 160); });
  await app(p, 'monitor');
  await step('Monitor', 'Off now, On now', async () => { await p.click('[data-pw="0"]'); await sleep(1200); const off = (await text(p, '#wb-monitor')).includes('off'); await p.click('[data-pw="1"]'); await sleep(1200); return off; });
  await app(p, 'logs');
  await step('Logs', 'switch the source, search, last error', async () => { const opts = await p.$$eval('#logUnit option', o => o.map(x => x.value)); await p.selectOption('#logUnit', opts[1]); await settle(p, 600); await p.fill('#logQ', 'error'); await sleep(700); return (await p.inputValue('#logUnit')) === opts[1]; });

  // Network, remote
  await app(p, 'devices');
  await step('Network', 'Name a device', async () => { await p.click('[data-edit]'); await p.fill('#devName', 'Sweep router'); await p.click('#devF button[type=submit]'); await settle(p, 700); return (await text(p, '#wb-devices table')).includes('Sweep router'); });
  await step('Network', 'Scan now', async () => { await p.click('#devScan'); await settle(p, 700); return (await text(p, '#wb-devices')).includes('just now'); });
  await step('Network', 'Find cameras', async () => { await p.click('#devCams'); await settle(p, 700); return (await text(p, '#devCamsOut')).length > 10; });
  await app(p, 'remote');
  await step('Remote', 'Add a computer to the VPN', async () => { await p.click('#rmTabs [data-t="wg"]'); await p.click('#wgAdd'); await p.fill('#wgName', 'sweep-laptop'); await p.click('#wgGo'); await settle(p, 500); const c = await text(p, '#wgConf'); await closeModal(p); await p.evaluate(() => window.arise.rerender('remote')); await settle(p, 500); return c.includes('[Interface]') && (await text(p, '#wb-remote')).includes('sweep-laptop'); });

  // Mail
  await app(p, 'mail');
  await step('Mail', 'Preview fills the email', async () => { await p.fill('#mlSubj', 'Sweep news'); await p.fill('#mlBody', 'Hello church\n\n## This Sunday\n- 10:30 Pineville'); await p.click('#mlPrev'); await settle(p, 500); const h = await p.evaluate(() => document.getElementById('mlFrame').srcdoc); return h.includes('This Sunday') || 'srcdoc: ' + h.slice(0, 80); });
  await step('Mail', 'a test to a bad address is refused', async () => { await p.fill('#mlTestTo', 'not-an-email'); await p.click('#mlTest'); await settle(p); return bad(await toasts(p), /email address/); });
  await step('Mail', 'a test to a good address says what happens', async () => { await p.fill('#mlTestTo', 'bradly@example.com'); await p.click('#mlTest'); await settle(p); const t = await toasts(p); return t.some(x => /test/i.test(x.text) && !/\bbad\b/.test(x.cls)) || JSON.stringify(t); });
  await step('Mail', 'Import a Wix CSV adds contacts', async () => { await p.click('[data-tab="contacts"]'); await settle(p, 500); const n = await text(p, '#wb-mail b'); await p.setInputFiles('#mlCsv', { name: 'wix.csv', mimeType: 'text/csv', buffer: Buffer.from('Email,First Name,Last Name\nsweep.one@example.com,Sweep,One\nsweep.two@example.com,Sweep,Two\nbad-address,Bad,Row\n') }); await settle(p, 500); await p.click('#mlGo'); await sleep(1800); const n2 = await text(p, '#wb-mail b'); return +n2 === +n + 2 || `${n} → ${n2}`; });
  await step('Mail', 'Send to everyone (typed send) lands in Sent', async () => { await p.click('[data-tab="compose"]'); await settle(p, 400); await p.fill('#mlSubj', 'Sweep news'); await p.fill('#mlBody', 'Body'); await p.click('#mlSend'); await confirmWord(p, 'send'); await settle(p, 400); return (await text(p, '#wb-mail')).includes('Sweep news'); });

  // Security and two-step
  await app(p, 'security');
  await step('Security', 'Scan now records a scan', async () => { await p.click('#secScan'); await settle(p, 500); await p.evaluate(() => window.arise.rerender('security')); await settle(p, 500); return (await text(p, '#wb-security')).includes('clean'); });
  await step('Security', 'Two-step: turn it off (password + code)', async () => { await p.click('#secTwofa'); await settle(p, 400); if (!(await exists(p, '#tfOff'))) { await closeModal(p); return 'not on to begin with'; } await p.fill('#tfPw', 'x'); await p.fill('#tfCode', '000000'); await p.click('#tfOff button[type=submit]'); await settle(p, 600); return (await text(p, '#wb-security')).includes('Nobody has it on'); });
  await step('Security', 'Two-step: set up shows the QR, a code turns it on', async () => { await p.click('#secTwofa'); await settle(p, 600); const qr = await exists(p, '#tfQr svg'); await p.fill('#tfCode', '123'); await p.click('#tfOn button[type=submit]'); await settle(p); const refused = (await toasts(p)).some(t => /not right/.test(t.text)); await p.fill('#tfCode', '000000'); await p.click('#tfOn button[type=submit]'); await settle(p, 600); const on = (await text(p, '#wb-security')).includes('On for: bradly'); return qr && refused && on ? true : `qr ${qr} refused ${refused} on ${on}`; });

  // round 6: the church Macs (the server is their Active Directory; local accounts wait for a choice)
  await app(p, 'macs');
  await step('Macs', 'the app lists the three church Macs', async () => { const t = await text(p, '#wb-macs'); return (t.includes('3 Macs') && t.includes('OFFICE-MAC-01') && t.includes('KIDS-MAC')) || t.slice(0, 200); });
  await step('Macs', 'Enrol a Mac shows the one Terminal line with Copy', async () => { await p.click('#macEnrol'); await settle(p, 300); await p.fill('#meName', 'OFFICE-MAC-02'); await p.click('#meGo'); await settle(p, 500); const t = await text(p, '#meLine'); const copy = await exists(p, '#meCopy'); await closeModal(p); return (copy && /sudo bash -s -- --token \S+ --dns \S+ --name OFFICE-MAC-02/.test(t)) || t; });
  await step('Macs', "a Mac's card lists its local accounts, waiting for a choice", async () => { await p.click('#wb-macs tr[data-mac="mac-0000000000b2"]'); await settle(p, 700); const k = await rowText(p, '#wb-macs', 'Kristina Robinson'); return k.includes('waiting for your choice') || k; });
  await step('Macs', 'Convert kristina to a new server user: made first, the temporary password shown once', async () => { await p.click('[data-mchoose="kristina"]'); await settle(p, 800); if ((await p.inputValue('#mcUser')) !== 'kristina.robinson') return 'no suggestion'; const isNew = await text(p, '#mcNew'); await p.click('#mcGo'); await settle(p, 900); const pw = await text(p, '#modalBody .macs-secret'); await closeModal(p); await settle(p, 300); const row = await rowText(p, '#wb-macs', 'Kristina Robinson'); return (/not on the server yet/.test(isNew) && pw.trim().length >= 8 && row.includes('converting to kristina.robinson')) || JSON.stringify({ isNew, pw, row }); });
  await step('Macs', 'the new server user is in Directory', async () => p.evaluate(async () => ((await window.arise.api('/directory/users')).users || []).some(u => u.name === 'kristina.robinson')));
  await step('Macs', 'Link guest to office: the account stays, no new user', async () => { await p.click('[data-mchoose="guest"]'); await settle(p, 800); await p.check('input[name=mcA][value=link]'); await p.fill('#mcUser', 'office'); await settle(p, 100); await p.click('#mcGo'); await settle(p, 900); const secret = await exists(p, '#modalBody .macs-secret'); await closeModal(p); const row = await rowText(p, '#wb-macs', 'Guest'); return (!secret && row.includes('linked to office')) || JSON.stringify({ secret, row }); });
  await step('Macs', 'the tasks list has the conversion, the link and the files', async () => { const t = await text(p, '#wb-macs'); return (t.includes('Convert local account') && t.includes('Link local account') && t.includes('Nextcloud')) || 'missing tasks'; });
  await step('Macs', 'Show FileVault key asks for the password, then shows it', async () => { await p.click('[data-mshow="filevault"]'); await settle(p, 400); await reauth(p); await settle(p, 400); const t = await text(p, '#modalBody .macs-secret'); await closeModal(p); return t.trim().length > 8 || 'no key shown'; });
  await step('Macs', 'Back to all Macs', async () => { await p.click('#macBack'); await settle(p, 600); return (await text(p, '#wb-macs')).includes('Enrol a Mac'); });

  // Settings, power, the flame menu
  await app(p, 'settings');
  await step('System Settings', 'every section opens', async () => { const secs = await p.$$eval('[data-sec]', b => b.map(x => x.dataset.sec)); for (const s of secs) { await p.click(`[data-sec="${s}"]`); await settle(p, 250); if (!(await text(p, '.settings__body h2'))) return s + ' empty'; } return true; });
  await step('System Settings', 'Manage shares opens the Shares tab', async () => { await p.click('[data-sec="sharing"]'); await settle(p, 250); await p.click('[data-shares]'); await settle(p, 600); return await p.evaluate(() => !document.querySelector('#wb-directory [data-tab="shares"]').hidden); });
  await step('Power', 'Restart… asks for the word and the password', async () => { await flame(p, 'Restart…'); await p.fill('#cfWord', 'reboot'); await p.click('#cfGo'); await settle(p, 500); const asked = await exists(p, '#raPw') || 'no password asked (a yes within five minutes?)'; await reauth(p); await settle(p, 400); const t = await toasts(p); const said = t.some(x => /would restart|Not during/.test(x.text)); return said ? true : 'toasts: ' + JSON.stringify(t) + ' ' + asked; });

  // Spotlight, keys, overlays
  await step('Spotlight', 'a sum', async () => { await p.keyboard.press('Control+Space'); await p.keyboard.type('12*(3+4)'); await settle(p, 300); const t = await text(p, '#spotRes'); await p.keyboard.press('Enter'); await settle(p, 600); const r = await text(p, '#calcRes'); return t.includes('= 84') && r === '84' ? true : t.slice(0, 60) + ' / ' + r; });
  await step('Spotlight', 'a verse opens the Bible', async () => { await p.keyboard.press('Control+Space'); await p.keyboard.type('Psalm 23'); await settle(p, 300); await p.click('#spotRes button:has-text("Read Psalm 23")'); await settle(p, 800); return (await text(p, '#wb-bible h2')).includes('Psalm 23'); });
  await step('Spotlight', 'an app by name', async () => { await p.keyboard.press('Control+Space'); await p.keyboard.type('weather'); await settle(p, 300); await p.keyboard.press('Escape'); return true; });
  await step('Keys', 'F1 opens Help', async () => { await p.click('#stage', { position: { x: 20, y: 300 } }); await p.keyboard.press('F1'); await settle(p, 800); return !!(await p.evaluate(() => window.arise.S.wins.help)); });
  await step('Keys', 'Ctrl+/ shows the shortcuts', async () => { await p.click('#stage', { position: { x: 20, y: 300 } }); await p.keyboard.press('Control+/'); await settle(p, 300); const o = await modalOpen(p); await p.keyboard.press('Escape'); return o; });
  await step('Keys', 'Ctrl+← snaps a window to the left half', async () => { await app(p, 'about'); await p.evaluate(() => window.arise.focusWin('about')); await p.click('#stage', { position: { x: 5, y: 300 } }).catch(() => {}); await p.evaluate(() => window.arise.focusWin('about')); await p.keyboard.press('Control+ArrowLeft'); await settle(p, 200); return (await p.evaluate(() => window.arise.S.wins.about.el.style.left)) === '0px'; });
  await step('Keys', 'Ctrl+W closes the window', async () => { await p.evaluate(() => window.arise.focusWin('about')); await p.keyboard.press('Control+w'); await settle(p, 200); return !(await p.evaluate(() => window.arise.S.wins.about)); });
  await step('Keys', 'Ctrl+Alt+Q locks the screen, even with a window open', async () => { await app(p, 'calc'); await p.evaluate(() => window.arise.focusWin('calc')); await p.keyboard.press('Control+Alt+q'); await settle(p, 300); const locked = await p.evaluate(() => !document.getElementById('lock').hidden); const stillOpen = !!(await p.evaluate(() => window.arise.S.wins.calc)); if (locked) await unlock(p); return locked && stillOpen ? true : `locked ${locked}, window kept ${stillOpen}`; });
  await step('Keys', 'F3 Mission Control, Escape back', async () => { await p.keyboard.press('F3'); await settle(p, 300); const on = await p.evaluate(() => document.getElementById('stage').classList.contains('mc')); await p.keyboard.press('Escape'); return on; });
  await step('Lock', 'the lock screen unlocks with the password', async () => { await flame(p, 'Lock Screen'); const l = await p.evaluate(() => !document.getElementById('lock').hidden); const twofa = await p.evaluate(async () => ((await window.arise.api('/me/2fa')) || {}).on).catch(() => false); const asked = await unlock(p); const open = await p.evaluate(() => document.getElementById('lock').hidden); return l && open && (!twofa || asked) ? true : `locked ${l}, unlocked ${open}, two-step on ${twofa}, asked for digits ${asked}`; });
  await step('Dock', 'Remove from Dock, Keep in Dock', async () => { const has = () => exists(p, '#dock [data-app="terminal"]'); await p.evaluate(() => window.arise.closeApp('terminal')); await ctxPick(p, '#dock [data-app="terminal"]', 'Remove from Dock'); const gone = !(await has()); await p.evaluate(() => window.arise.toggleLaunchpad(true)); await settle(p, 200); await ctxPick(p, '[data-lp="terminal"]', 'Keep in Dock'); await p.evaluate(() => window.arise.toggleLaunchpad(false)); return gone && await has(); });
  await step('Widgets', 'Notification Center opens with the widgets', async () => { await p.click('#barClock'); await settle(p, 600); const t = await text(p, '#ncBody'); await p.click('#barClock'); return t.includes('Weather') && t.length > 100; });
  await step('Control Center', 'Bone theme and back', async () => { await p.click('#ccBtn'); await settle(p, 200); await p.click('#cc [data-act="theme"]'); await settle(p, 200); const bone = await p.evaluate(() => document.body.classList.contains('bone')); await p.click('#cc [data-act="theme"]'); await p.click('#ccBtn'); return bone; });
  await step('Control Center', 'Larger text', async () => { await p.click('#ccBtn'); await settle(p, 200); await p.click('#cc [data-act="a11y-text"]'); const on = await p.evaluate(() => document.body.classList.contains('a11y-text')); await p.click('#cc [data-act="a11y-text"]'); await p.click('#ccBtn'); return on; });
  await step('Walkthrough', 'Show me around, five steps', async () => { await p.evaluate(() => window.arise.walkthrough(true)); for (let i = 0; i < 5; i++) { await p.click('#wkNext'); await settle(p, 120); } return !(await exists(p, '.walk')); });
  await step('Preview menu', 'the badge menu lists the switches', async () => { await p.click('#demoBadge'); await settle(p, 200); const t = await text(p, '#ctx'); await p.keyboard.press('Escape'); await p.mouse.click(700, 500); return t.includes('View as a member') && t.includes('Reset the preview'); });
  const e1 = await errs(p); await step(A, 'no page errors in the flows', async () => e1.length ? e1.join(' | ') : true);
  const w1 = await warns(p); await step(A, 'nothing "not in the preview yet"', async () => w1.length ? w1.join(' | ') : true);

  // round 5: profiles, the people list, a temporary password, "Forgot your password?", settings that follow the account
  await step('Profile', 'My Profile saves a phone and a birthday, and lists my sign-ins', async () => { await flame(p, 'My Profile'); await settle(p, 500); await p.fill('#pf_mobile', '318-555-0199'); await p.fill('#pf_birthday', 'March 14'); await p.click('#pfSave'); await settle(p, 500); const t = await toasts(p); await flame(p, 'My Profile'); await settle(p, 500); const v = [await p.inputValue('#pf_mobile'), await p.inputValue('#pf_birthday')]; const rows = (await p.$$('#pfSignins tr')).length; await closeModal(p); return t.some(x => /Profile saved/.test(x.text)) && v[0] === '318-555-0199' && v[1] === '03-14' && rows >= 1 ? true : JSON.stringify({ t, v, rows }); });
  await step('Profile', 'a bad birthday is refused with the rule', async () => { await flame(p, 'My Profile'); await settle(p, 500); await p.fill('#pf_birthday', 'someday'); await p.click('#pfSave'); await settle(p, 500); const t = await toasts(p); await closeModal(p); return bad(t, /birthday/) || JSON.stringify(t); });
  let maryPw = '';
  await step('Directory', 'Import a people list: check first, then create with temporary passwords', async () => { await app(p, 'directory'); await p.click('#dirTabs [data-t="users"]'); await settle(p, 200); await p.click('#importPeople'); await settle(p, 300);
    await p.fill('#ipCsv', 'first,last,title,departments,personal_email,mobile,birthday,role\nMary,Jones,Minister,Worship,mary@example.com,,04-02,staff\nNo,,,,,,,\n'); await p.click('#ipCheck'); await settle(p, 600);
    const checked = await p.$$eval('#ipRows tbody tr', trs => trs.map(t => t.textContent)); await p.click('#ipGo'); await settle(p, 800);
    maryPw = await p.evaluate(() => { const tr = [...document.querySelectorAll('#ipRows tbody tr')].find(t => t.textContent.includes('mary.jones')); return tr ? tr.lastElementChild.textContent.trim() : ''; });
    await closeModal(p); await settle(p, 800);
    return checked.length === 2 && /ready/.test(checked[0]) && /refused/.test(checked[1]) && maryPw.length >= 12 ? true : JSON.stringify({ checked, maryPw }); });
  await step('Directory', 'the imported person shows with her title and "new password due"', async () => { await app(p, 'directory'); await p.click('#dirTabs [data-t="users"]'); await settle(p, 200); const t = await text(p, '#uTable tr[data-q^="mary.jones"]'); return /Minister Mary Jones/.test(t) && /new password due/.test(t) ? true : t; });
  await step('Directory', 'Profile on a user: an admin sets the title', async () => { await p.click('[data-prof="mary.jones"]'); await settle(p, 500); const disabled = await p.evaluate(() => document.querySelector('#pf_title').disabled); await p.fill('#pf_title', 'Pastor'); await p.click('#pfSave'); await settle(p, 900); const t = await text(p, '#uTable tr[data-q^="mary.jones"]'); return !disabled && /Pastor Mary Jones/.test(t) ? true : `${disabled} ${t}`; });
  await step('Sign-in', 'a temporary password asks for her own before anything else', async () => { await flame(p, 'Sign Out'); await settle(p, 1500); await p.fill('#lu', 'mary.jones'); await p.fill('#lp', maryPw); await p.click('#lf button'); await settle(p, 700); return await exists(p, '#ln1') ? true : await text(p, '.login'); });
  await step('Sign-in', 'two different new passwords are refused', async () => { await p.fill('#ln1', 'Own-Pass-7777!'); await p.fill('#ln2', 'Own-Pass-7778!'); await p.click('#lf button'); await settle(p, 400); return /not the same/.test(await text(p, '.login .toast')); });
  await step('Sign-in', 'her own password is set and she is signed in', async () => { await p.fill('#ln2', 'Own-Pass-7777!'); await p.click('#lf button'); await settle(p, 1800); return await p.evaluate(() => window.arise.S.user === 'mary.jones'); });
  await step('Sign-in', 'settings follow the account: the theme is saved on the server', async () => { await p.evaluate(() => window.arise.toggleTheme()); await settle(p, 1300); const pr = await p.evaluate(() => window.arise.api('/me/prefs')); await p.evaluate(() => window.arise.toggleTheme()); await settle(p, 1100); return pr.prefs && pr.prefs.theme === 'bone' ? true : JSON.stringify(pr); });
  await step('Sign-in', '"Forgot your password?" sends a link (shown as a sample here) and the link sets a new one', async () => { await flame(p, 'Sign Out'); await settle(p, 1500); await p.click('#lforgot'); await settle(p, 400); await p.fill('#lfu', 'mary.jones'); await p.click('#lf button'); await settle(p, 600);
    const msg = await text(p, '#lfOut'); if (!(await exists(p, '#lfOpen'))) return 'no sample link: ' + msg; await p.click('#lfOpen'); await settle(p, 800);
    await p.fill('#ln1', 'Reset-Pass-3333!'); await p.fill('#ln2', 'Reset-Pass-3333!'); await p.click('#lf button'); await settle(p, 600); const done = await text(p, '.login__ok');
    await p.click('#lback'); await settle(p, 600); await p.fill('#lu', 'mary.jones'); await p.fill('#lp', 'Reset-Pass-3333!'); await p.click('#lf button'); await settle(p, 1800);
    return /personal email on file/.test(msg) && /works now/.test(done) && await p.evaluate(() => window.arise.S.user === 'mary.jones') ? true : JSON.stringify({ msg, done }); });
  await step('Sign-in', 'the greeting and the name carry her title', async () => { const n = await p.evaluate(() => [window.arise.S.me.name, window.arise.S.me.greeting]); return n[0] === 'Pastor Mary Jones' && n[1] === 'Pastor Mary' ? true : JSON.stringify(n); });

  // sign-in: john.smith (a member, with the password set when he was made)
  await step('Sign-in', 'Sign out shows the sign-in screen', async () => { await flame(p, 'Sign Out'); await settle(p, 1500); return await exists(p, '.login #lf'); });
  await step('Sign-in', 'a wrong password is refused', async () => { await p.fill('#lu', 'john.smith'); await p.fill('#lp', 'wrong-one'); await p.click('#lf button'); await settle(p, 400); return (await text(p, '.login .toast')).includes('Wrong'); });
  await step('Sign-in', 'with staff access "none" (the default) john.smith gets "your files are on your Mac"', async () => { await p.evaluate(() => window.AriseMock.setStaffAccess('none')); await p.fill('#lu', 'john.smith'); await p.fill('#lp', 'longpassword1'); await p.click('#lf button'); await settle(p, 1800); const t = await text(p, '.onmac'); const desk = await exists(p, '#stage'); await p.click('#omOut'); await settle(p, 1500); return /on your Mac/.test(t) && !desk && await exists(p, '.login #lf') ? true : `${t.slice(0, 60)} desktop=${desk}`; });
  await p.evaluate(() => window.AriseMock.setStaffAccess('portal'));   // the portal stays a setting ([web] staff_access = "portal"): sweep it too
  await step('Sign-in', 'john.smith signs in with his password and gets the portal', async () => { await p.fill('#lu', 'john.smith'); await p.fill('#lp', 'longpassword1'); await p.click('#lf button'); await settle(p, 1800); return await p.evaluate(() => document.body.classList.contains('member') && window.arise.S.user === 'john.smith'); });
  await step('Member', 'Finder opens on My files: six folders and the Start here note', async () => { await app(p, 'files'); const n = (await p.$$('#fMain .fi')).length; const t = await text(p, '#fMain'); return n === 7 && /Start here/.test(t) && /Desktop/.test(t) ? true : `${n}: ${t.slice(0, 120)}`; });
  await step('Member', 'a member cannot open Directory', async () => { await p.evaluate(() => window.arise.openApp('directory')); await settle(p, 300); return !(await p.evaluate(() => window.arise.S.wins.directory)); });
  await step('Member', 'the calendar has no Add button for members', async () => { await app(p, 'calendar'); return !(await exists(p, '#calAdd')); });
  await step('Member', 'two-step for a member: turn it on', async () => { await flame(p, 'Two-step sign-in…'); await settle(p, 500); await p.fill('#tfCode', '000000'); await p.click('#tfOn button[type=submit]'); await settle(p, 500); return (await toasts(p)).some(t => /Two-step is on/.test(t.text)); });
  await step('Sign-in', 'with two-step on, sign-in asks for the six digits', async () => { await flame(p, 'Sign Out'); await settle(p, 1500); await p.fill('#lu', 'john.smith'); await p.fill('#lp', 'longpassword1'); await p.click('#lf button'); await settle(p, 600); const asked = await exists(p, '#lc'); await p.fill('#lc', '000000'); await p.click('#lf button'); await settle(p, 1800); return asked && await p.evaluate(() => window.arise.S.user === 'john.smith'); });
  const e2 = await errs(p); await step('Member', 'no page errors as a member', async () => e2.length ? e2.join(' | ') : true);
  await p.ctx.close();
}

/* ---------------- click everything once ---------------- */
// Every visible control in every window, once: on the window as it opens and then
// on each of its tabs. A control "answered" if anything happened: a modal, a menu,
// a toast, a window, Quick Look, a new tab, or any window's content changed.
// Clicking the tab that is already open, Refresh, Read and Today on what is already
// shown are allowed to change nothing.
const SKIP_IN_GENERIC = new Set(['terminal']);
const CTRL = i => `#wb-${i} button, #wb-${i} a.btn, #wb-${i} label.btn, #wb-${i} input[type=checkbox]`;
const IDEMPOTENT = /^(Refresh|Read|Today|Copy|Copy link|Copy the CSS|Copy result|Rescan|Scan now|Check now|Preview tonight|Last error ↓|Copy for Claude|Clear|=)$/;
async function sweepWindow(p, id) {
  const seen = new Set(); let answered = 0, quiet = 0; const none = [];
  const tabsOf = () => p.evaluate(i => [...document.querySelectorAll(`#wb-${i} .tabs button, #wb-${i} .settings__nav button`)].map(b => b.textContent.trim()), id);
  const states = [null, ...(await tabsOf())];
  const goTab = async label => { if (label == null) return; await p.evaluate(([i, l]) => { const b = [...document.querySelectorAll(`#wb-${i} .tabs button, #wb-${i} .settings__nav button`)].find(x => x.textContent.trim() === l); if (b && !b.classList.contains('active') && !b.classList.contains('on')) b.click(); }, [id, label]); await sleep(350); };
  for (const st of states) {
    await goTab(st);
    for (let guard = 0; guard < +(process.env.MAX_CONTROLS || 60); guard++) {
      const pick = await p.evaluate(([i, sel, seenList]) => {
        const keyOf = el => (el.closest('.tabs, .settings__nav') ? 'tab:' : '') + (el.getAttribute('aria-label') || el.textContent || el.value || el.tagName).trim().slice(0, 40) + '|' + [...el.attributes].filter(a => a.name.startsWith('data-')).map(a => a.name + '=' + a.value).join(',');
        const els = [...document.querySelectorAll(sel)].filter(el => el.offsetParent !== null && !el.disabled);
        const el = els.find(e => !seenList.includes(keyOf(e)) && !(e.tagName === 'A' && (e.target === '_blank' || /^(https?|webcal|smb|mailto):/.test(e.getAttribute('href') || ''))) && !(e.tagName === 'LABEL' && e.getAttribute('for')) && !/^(Sign Out|Shut Down)/.test(e.textContent.trim()));
        if (!el) return null;
        const label = (el.getAttribute('aria-label') || el.textContent || el.value || el.tagName).trim().slice(0, 40);
        const h = s => { let x = 0; for (let k = 0; k < s.length; k++) x = (x * 31 + s.charCodeAt(k)) | 0; return x; };
        const all = [...document.querySelectorAll('.win__body')].map(b => h(b.innerHTML) + ':' + [...b.querySelectorAll('input')].map(x => x.checked ? 1 : 0).join('')).join('|');
        window.__sig = { all, toasts: window.__toasts.length, wins: Object.keys(window.arise.S.wins).length };
        const active = el.classList.contains('active') || el.classList.contains('on') || el.getAttribute('aria-pressed') === 'true' || (el.type === 'submit' && el.form && !el.form.checkValidity());
        const key = keyOf(el); el.setAttribute('data-sweep-target', '1'); const dattr = [...el.attributes].filter(a => a.name.startsWith('data-')).map(a => a.name.slice(5) + '=' + a.value).join(' '); return { key, label: label + (dattr ? ` [${dattr}]` : ''), active, tab: !!el.closest('.tabs, .settings__nav') };
      }, [id, CTRL(id), [...seen]]);
      if (!pick) break;
      seen.add(pick.key);
      const pops = p.popups || 0;
      await p.evaluate(() => { const el = document.querySelector('[data-sweep-target]'); el.removeAttribute('data-sweep-target'); el.click(); }).catch(() => {});
      await sleep(380);
      const what = await p.evaluate(() => { const s = window.__sig; if (!s) return 'reloaded'; const h = x => { let v = 0; for (let k = 0; k < x.length; k++) v = (v * 31 + x.charCodeAt(k)) | 0; return v; }; const all = [...document.querySelectorAll('.win__body')].map(b => h(b.innerHTML) + ':' + [...b.querySelectorAll('input')].map(x => x.checked ? 1 : 0).join('')).join('|');
        return document.getElementById('modal').open ? 'modal' : !document.getElementById('ctx').hidden ? 'menu' : window.__toasts.length > s.toasts ? 'toast' : Object.keys(window.arise.S.wins).length !== s.wins ? 'window' : !document.getElementById('ql').hidden ? 'quicklook' : document.querySelector('.walk') ? 'walk' : all !== s.all ? 'changed' : ''; });
      let popped = (p.popups || 0) > pops; if (!what && !popped) { await sleep(600); popped = (p.popups || 0) > pops; }
      if (what || popped) answered++; else if (pick.active || IDEMPOTENT.test(pick.label.replace(/ \[.*$/, ''))) quiet++; else none.push(pick.label);
      await p.evaluate(() => { const m = document.getElementById('modal'); if (m.open) m.close(); document.getElementById('ctx').hidden = true; document.getElementById('ql').hidden = true; document.querySelector('.walk')?.remove(); });
      await p.evaluate(i => { Object.keys(window.arise.S.wins).filter(k => k !== i).forEach(k => window.arise.closeApp(k)); if (!window.arise.S.wins[i]) window.arise.openApp(i); }, id); await sleep(['apps', 'services', 'backups', 'automator', 'notes', 'photos'].includes(id) && !pick.tab ? 1700 : 120);   // these windows refresh themselves a moment after an action
      if (!pick.tab) await goTab(st);
    }
  }
  return { answered, quiet, none };
}
async function everyControl(browser, url, role) {
  const p = await newPage(browser, url); p.popups = 0; p.on('popup', () => { p.popups++; });
  if (role === 'member') { await p.evaluate(() => { window.AriseMock.setStaffAccess('portal'); window.AriseMock.viewAs('member'); window.AriseMock.flush(); }); await p.reload({ waitUntil: 'domcontentloaded' }); await settle(p, 1500); }
  const only = (process.env.APPS || '').split(',').filter(Boolean);
  const ids = (await p.evaluate(() => (window.arise.S.role === 'member' ? window.arise.APPS.filter(a => ['files', 'sermons', 'bible', 'sites', 'about', 'assist', 'sunday', 'calendar', 'calc', 'clock', 'help', 'notes', 'photos'].includes(a.id)) : window.arise.APPS).map(a => a.id))).filter(i => !only.length || only.includes(i));
  for (const id of ids) {
    if (SKIP_IN_GENERIC.has(id)) { rec(`${role} · ${id}`, 'opens', 'skip'); continue; }
    await p.evaluate(() => Object.keys(window.arise.S.wins).forEach(k => window.arise.closeApp(k)));
    await app(p, id);
    const opened = await p.evaluate(i => !!window.arise.S.wins[i], id);
    if (!opened) { const g = await p.evaluate(i => window.arise.APPS.find(a => a.id === i)?.groups, id); rec(`${role} · ${id}`, 'opens', role === 'member' && g ? 'skip' : false, 'did not open'); await toasts(p); continue; }
    const loadErr = await p.evaluate(i => document.querySelector(`#wb-${i} .panel--bad h3`)?.textContent === 'Could not load' ? document.querySelector(`#wb-${i} .panel--bad p`)?.textContent : '', id);
    rec(`${role} · ${id}`, 'opens', !loadErr, loadErr);
    const r = await sweepWindow(p, id);
    rec(`${role} · ${id}`, `${r.answered} controls answered, ${r.quiet} already showed it`, r.none.length === 0, r.none.length ? 'did nothing: ' + r.none.join(', ') : '');
    const e = await errs(p); if (e.length) rec(`${role} · ${id}`, 'no page errors', false, e.join(' | '));
    const w = await warns(p); if (w.length) rec(`${role} · ${id}`, 'all in the preview', false, w.join(' | '));
    const t = (await toasts(p)).filter(x => /\bbad\b/.test(x.cls) && !/not right|refused|Not during|already|no such|type the|is kept|cannot|timer is on|first|bad|empty|only|Type|that does not look/i.test(x.text));
    if (t.length) rec(`${role} · ${id}`, 'no unexpected red toasts', false, t.map(x => x.text).join(' | '));
  }
  await p.ctx.close();
}

/* ---------------- the phone ---------------- */
async function phone(browser, url) {
  const p = await newPage(browser, url, { width: 390, height: 844 });
  const ids = await p.evaluate(() => window.arise.APPS.filter(a => !a.hidden).map(a => a.id));
  for (const id of ids) {
    await p.evaluate(() => Object.keys(window.arise.S.wins).forEach(k => window.arise.closeApp(k)));
    await app(p, id); await settle(p, 200);
    const o = await p.evaluate(() => ({ page: document.documentElement.scrollWidth - innerWidth, body: document.body.scrollWidth - innerWidth }));
    rec(`phone · ${id}`, 'no sideways scroll', o.page <= 1 && o.body <= 1, `page +${o.page}px, body +${o.body}px`);
    if (['files', 'directory', 'calendar', 'sunday', 'apps', 'settings'].includes(id)) await p.screenshot({ path: path.join(OUT, `phone-${id}.png`) });
  }
  const e = await errs(p); rec('phone', 'no page errors', !e.length, e.join(' | '));
  await p.ctx.close();
}

(async () => {
  const srv = await serve(0); const url = `http://127.0.0.1:${srv.address().port}/`;
  const browser = await chromium.launch();
  const t0 = Date.now();
  try {
    const only = (process.env.ONLY || 'flows,admin,member,phone').split(',');
    if (only.includes('flows')) { console.log('flows…'); await flows(browser, url); }
    if (only.includes('admin')) { console.log('every control, admin…'); await everyControl(browser, url, 'admin'); }
    if (only.includes('member')) { console.log('every control, member…'); await everyControl(browser, url, 'member'); }
    if (only.includes('phone')) { console.log('the phone…'); await phone(browser, url); }
  } finally { await browser.close(); srv.close(); }
  const by = {}; for (const r of results) { const a = r.area.split(' · ')[0] === 'admin' || r.area.split(' · ')[0] === 'member' || r.area.split(' · ')[0] === 'phone' ? r.area : r.area; (by[a] = by[a] || { pass: 0, fail: 0, skip: 0 })[r.result === 'pass' ? 'pass' : r.result === 'skip' ? 'skip' : 'fail']++; }
  const lines = ['| Area | Control | Result | Note |', '|---|---|---|---|', ...results.map(r => `| ${r.area} | ${r.control} | ${r.result} | ${r.note.replace(/\|/g, '/')} |`)];
  fs.writeFileSync(path.join(OUT, 'sweep.md'), lines.join('\n') + '\n'); fs.writeFileSync(path.join(OUT, 'sweep.json'), JSON.stringify(results, null, 1));
  const fails = results.filter(r => r.result === 'FAIL');
  console.log(`\n${results.length} checks · ${results.length - fails.length} passed or skipped · ${fails.length} failed · ${Math.round((Date.now() - t0) / 1000)} s · ${path.join(OUT, 'sweep.md')}`);
  for (const f of fails) console.log(`FAIL | ${f.area} | ${f.control} | ${f.note}`);
  process.exit(fails.length ? 1 : 0);
})();
