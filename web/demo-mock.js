/* ===========================================================================
   ARISE SERVER — the preview's own little server
   The published preview has no Arise API behind it. Before this file every
   button in it answered "nothing was changed": a new user never appeared, a
   Disable never stuck. This is a stateful stand-in for the API, in the
   browser: it starts from window.ARISE_DEMO_DATA (the server's own sample
   answers, scripts/gen-demo-data.py), keeps what you do in localStorage
   (arise.preview.v1), and answers every call the dashboard makes in the same
   shape the real server does, with the same validation messages.
   Things that leave the box on the real server (email, push, a reboot, the
   monitor opening a site) answer demo: true, so the dashboard says plainly
   that nothing went anywhere. Everything else really changes.
   web/app.js routes api() here only when the page is the preview
   (window.ARISE_FORCE_DEMO, or the API is unreachable).
   =========================================================================== */
(() => {
'use strict';
const SEED = window.ARISE_DEMO_DATA;
if (!SEED) return;
const KEY = 'arise.preview.v1';
const VERSION = 1;

/* ---------- small helpers ---------- */
const clone = x => (x === undefined ? undefined : JSON.parse(JSON.stringify(x)));
const pad = n => String(n).padStart(2, '0');
const isoMin = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const isoSec = (d = new Date()) => isoMin(d) + ':' + pad(d.getSeconds());
const hex = (n = 8) => Array.from(crypto.getRandomValues(new Uint8Array(Math.ceil(n / 2))), b => b.toString(16).padStart(2, '0')).join('').slice(0, n);
const token = (n = 12) => { const a = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'; return Array.from(crypto.getRandomValues(new Uint8Array(n)), b => a[b % a.length]).join(''); };
const ok = (extra = {}) => Object.assign({ ok: true, preview: true }, extra);
const fail = err => ({ ok: false, err });
const http = (status, message, extra = {}) => ({ __status: status, error: Object.assign({ message }, extra) });
const NAME_RE = /^[A-Za-z][A-Za-z0-9._-]{1,63}$/;          // server/arise_server/directory.py
const SHARE_RE = /^[A-Za-z0-9][A-Za-z0-9 _-]{0,31}$/;       // server/arise_server/shares.py
const EMAIL_RE = /^[^@\s,;]+@[^@\s,;]+\.[A-Za-z]{2,}$/;
const MEMBER_OK = ['/auth/', '/me', '/files/', '/search', '/links', '/sermons', '/bible', '/sites', '/health', '/church', '/sunday', '/kiosk/open', '/kiosk/claude-desktop', '/public/', '/push/', '/about/week', '/about/whatsnew', '/calendar', '/weather', '/help', '/apps/open/'];
const memberOk = p => MEMBER_OK.some(m => p === m.replace(/\/$/, '') || p.startsWith(m));
const SAMPLE_SECRET = SEED['POST /me/2fa/setup']?.secret || '';

/* ---------- state ---------- */
// G: every GET answer, starting from the seed; X: what the seed does not hold.
let G, X;
const mem = { uploads: {}, blobs: {}, strikes: {} };   // this page only, never stored
function fresh() {
  G = clone(SEED);
  X = { v: VERSION, dirty: [], session: { user: 'bradly', role: 'admin' }, pw: {}, twofa: (SEED['GET /directory/2fa']?.users || []).slice(), twofaSince: {}, fs: {}, content: {}, trash: clone(SEED['GET /files/trash']?.items || []), events: [], reauthAt: 0, deletedUsers: [] };
  // The file tree, from every sample folder listing.
  for (const k of Object.keys(SEED)) { const m = k.match(/^GET \/files\/list\?root=(\w+)&path=(.*)$/); if (m) X.fs[m[1] + ':' + norm(m[2])] = clone(SEED[k].entries || []); }
  X.events = clone((SEED['GET /calendar']?.items || []).filter(i => !i.service));
}
function load() {
  fresh();
  let s = null; try { s = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch {}
  if (!s || s.v !== VERSION) return;
  for (const [k, v] of Object.entries(s.gets || {})) G[k] = v;
  Object.assign(X, s.x || {});
}
// Written at once, not later: a sign-in or sign-out reloads the page straight after.
function save() {
  const gets = {}; for (const k of X.dirty) if (k in G) gets[k] = G[k];
  try { localStorage.setItem(KEY, JSON.stringify({ v: VERSION, gets, x: X })); } catch {}
}
const touch = (...keys) => { for (const k of keys) if (!X.dirty.includes(k)) X.dirty.push(k); save(); };
const get = k => G[k];
// A sample the seed does not carry starts empty rather than breaking the window that reads it.
const getOr = (k, d) => (G[k] === undefined ? (G[k] = d) : G[k]);
// Nothing is built until the preview asks: on the real server this file only sits there.
let ready = false; const init = () => { if (!ready) { load(); ready = true; } };

/* ---------- who is signed in ---------- */
const users = () => get('GET /directory/users').users;
const groups = () => get('GET /directory/groups').groups;
const userOf = n => users().find(u => u.name.toLowerCase() === String(n || '').toLowerCase());
const isAdminUser = u => !!u && (u.groups || []).includes('Domain Admins');
const me = () => X.session;
const claudeOk = () => ['bradly', 'bradly.dyer'].includes(String(me()?.user || '').toLowerCase());
const isAdmin = () => me()?.role === 'admin';
function groupsOf(name) { const u = userOf(name); return u ? (u.groups || []).slice() : (isAdmin() ? ['Domain Admins'] : []); }
function shares() { return get('GET /shares').shares; }
function canUse(share, user, gs) {
  const v = share.valid_users || []; if (!v.length) return true;
  return v.some(x => x === user || (x.startsWith('@') && gs.includes(x.slice(1))) || (x === '%S'));
}
function roots() {
  const s = me(); if (!s) return [];
  if (s.role === 'admin') return clone(SEED['GET /files/roots']?.roots || [{ id: 'data', name: 'Server', path: '/srv/arise' }]);
  const gs = groupsOf(s.user);
  const out = [{ id: 'home', name: 'My files', path: '/srv/arise/homes/' + s.user, home: true }];
  for (const sh of shares()) {
    if (['homes', 'sysvol', 'netlogon'].includes(sh.name) || sh.browseable === false) continue;
    if (canUse(sh, s.user, gs)) out.push({ id: 'share:' + sh.name, name: sh.name, path: sh.path, share: true, writable: !!sh.writable && (!(sh.write_list || []).length || canUse({ valid_users: sh.write_list }, s.user, gs)) });
  }
  return out;
}
function authMe() {
  const s = me(); if (!s) return { error: { message: 'Sign in' } };
  const u = userOf(s.user);
  return { user: s.user, role: s.role, demo: true, preview: true, display: u?.display || '', groups: groupsOf(s.user), roots: roots(), links_days: 0, claude: claudeOk() };
}

/* ---------- the file tree ---------- */
function norm(p) { p = '/' + String(p || '/').replace(/\\/g, '/').split('/').filter(x => x && x !== '.').join('/'); return p; }
const join = (a, b) => norm(a + '/' + b);
const parent = p => norm(p.split('/').slice(0, -1).join('/'));
const base = p => p.split('/').filter(Boolean).pop() || '';
// A dashboard root plus a path inside it, to a place in the sample tree.
function place(rootId, rel) {
  rel = norm(rel); const s = me(); if (!s) return null;
  if (rootId === 'data' || rootId === 'nas') return isAdmin() ? { root: rootId, path: rel } : null;
  if (rootId === 'home') return { root: 'data', path: norm('/homes/' + s.user + rel) };
  if (rootId.startsWith('share:')) { const r = roots().find(x => x.id === rootId); return r ? { root: 'data', path: norm('/shares/' + rootId.slice(6) + rel) } : null; }
  return null;
}
const fsk = (root, path) => root + ':' + norm(path);
function entryOf(root, path) { if (norm(path) === '/') return { name: '', dir: true }; return (X.fs[fsk(root, parent(path))] || []).find(e => e.name === base(path)) || null; }
function list(root, path) { const k = fsk(root, path); if (X.fs[k]) return X.fs[k]; const e = entryOf(root, path); return e && e.dir ? (X.fs[k] = []) : null; }
function sortEntries(es) { es.sort((a, b) => (b.dir - a.dir) || a.name.localeCompare(b.name, 'en', { sensitivity: 'base' })); return es; }
function mkdirp(root, path) {
  path = norm(path); if (path === '/') { X.fs[fsk(root, '/')] = X.fs[fsk(root, '/')] || []; return; }
  mkdirp(root, parent(path));
  const sib = list(root, parent(path)) || (X.fs[fsk(root, parent(path))] = []);
  if (!sib.find(e => e.name === base(path))) { sib.push({ name: base(path), dir: true, size: null, mtime: isoMin() }); sortEntries(sib); }
  X.fs[fsk(root, path)] = X.fs[fsk(root, path)] || [];
}
function putFile(root, path, size, text) {
  mkdirp(root, parent(path)); const sib = list(root, parent(path)); const n = base(path);
  const old = sib.find(e => e.name === n); if (old) { old.size = size; old.mtime = isoMin(); old.dir = false; } else { sib.push({ name: n, dir: false, size, mtime: isoMin() }); sortEntries(sib); }
  if (text != null) X.content[fsk(root, path)] = text; else delete X.content[fsk(root, path)];
}
// Lift a file or a whole folder out of the tree (for the Trash), and put it back.
function takeOut(root, path) {
  path = norm(path); const sib = list(root, parent(path)); if (!sib) return null; const i = sib.findIndex(e => e.name === base(path)); if (i < 0) return null;
  const entry = sib.splice(i, 1)[0]; const sub = {}; const content = {}; const pre = fsk(root, path);
  for (const k of Object.keys(X.fs)) if (k === pre || k.startsWith(pre + '/')) { sub[k.slice(pre.length) || '/'] = X.fs[k]; delete X.fs[k]; }
  for (const k of Object.keys(X.content)) if (k === pre || k.startsWith(pre + '/')) { content[k.slice(pre.length) || '/'] = X.content[k]; delete X.content[k]; }
  return { entry, sub, content };
}
function putBack(root, path, pack) {
  mkdirp(root, parent(path)); const sib = list(root, parent(path)); const e = Object.assign({}, pack.entry, { name: base(path) }); sib.push(e); sortEntries(sib);
  const pre = fsk(root, path);
  for (const [k, v] of Object.entries(pack.sub || {})) X.fs[k === '/' ? pre : pre + k] = v;
  for (const [k, v] of Object.entries(pack.content || {})) X.content[k === '/' ? pre : pre + k] = v;
}
function sizeOf(root, path) { const e = entryOf(root, path); if (!e) return 0; if (!e.dir) return e.size || 0; let t = 0; for (const c of list(root, path) || []) t += sizeOf(root, join(path, c.name)); return t; }
function countFiles(root, path) { let n = 0; for (const c of list(root, path) || []) n += c.dir ? countFiles(root, join(path, c.name)) : 1; return n; }
function walk(root, path, fn, depth = 0) { if (depth > 12) return; for (const e of list(root, path) || []) { const p = join(path, e.name); fn(e, p); if (e.dir) walk(root, p, fn, depth + 1); } }
// Which share a place lives on, for the Trash label and Get Info.
function shareOf(root, path) {
  const parts = norm(path).split('/').filter(Boolean);
  if (root === 'nas') return { label: 'synology', base: '/mnt/synology', rel: parts.join('/') };
  if (parts[0] === 'homes' && parts[1]) return { label: 'homes', base: '/srv/arise/homes', rel: parts.slice(1).join('/'), owner: parts[1] };
  if (parts[0] === 'shares' && parts[1]) return { label: parts[1], base: '/srv/arise/shares/' + parts[1], rel: parts.slice(2).join('/') };
  return { label: parts[0] || 'data', base: '/srv/arise/' + (parts[0] || ''), rel: parts.slice(1).join('/') };
}
const TEXT_RE = /\.(txt|md|csv|json|ya?ml|toml|log)$/i;

/* ---------- the calendar, computed like server/arise_server/calendar.py ---------- */
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const services = () => get('GET /church')?.services || [];
function addHours(s, h) { const d = new Date(s); d.setHours(d.getHours() + h); return isoMin(d); }
function serviceItems(from, to) {
  const out = []; const d = new Date(from); d.setHours(0, 0, 0, 0);
  for (; d <= to; d.setDate(d.getDate() + 1)) {
    const date = isoMin(d).slice(0, 10);
    for (const s of services()) if (DAYS.indexOf(s.day) === d.getDay()) { const start = `${date}T${s.time}`; if (new Date(start) >= from && new Date(start) <= to) out.push({ id: `svc-${s.day}-${s.time}-${date}`, title: s.name, start, end: addHours(start, 2), where: s.site, service: true }); }
  }
  return out;
}
const byStart = (a, b) => a.start.localeCompare(b.start);
function calendar(y, m) {
  const from = new Date(y, m - 1, 1), to = new Date(y, m, 0, 23, 59);
  const items = serviceItems(from, to).concat(X.events.filter(e => { const d = new Date(e.start); return d >= from && d <= to; })).sort(byStart);
  const now = new Date(), end = new Date(now.getTime() + 14 * 86400000);
  const upcoming = serviceItems(now, end).concat(X.events.filter(e => { const d = new Date(e.start); return d >= now && d <= end; })).sort(byStart);
  return { year: y, month: m, items, upcoming, services: clone(SEED['GET /calendar']?.services || services()), demo: true };
}
// The same guard as church.in_service_now: from a service's start to two hours after, Pineville time.
function inService() {
  const t = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }));
  for (const s of services()) {
    if (DAYS.indexOf(s.day) !== t.getDay()) continue;
    const [h, mi] = s.time.split(':').map(Number); const st = new Date(t); st.setHours(h, mi, 0, 0); const en = new Date(st.getTime() + 2 * 3600000);
    if (t >= st && t < en) return { name: s.name, day: s.day, time: s.time, ends_at: `${pad(en.getHours())}:${pad(en.getMinutes())}` };
  }
  return null;
}

/* ---------- a little Markdown, for the editor preview and the email ---------- */
function mdHtml(src, pStyle = '') {
  const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2">$1</a>');
  let out = '', list = false;
  for (const l of String(src || '').split('\n')) {
    if (/^\s*[-*] /.test(l)) { if (!list) { out += '<ul>'; list = true; } out += `<li>${inline(l.replace(/^\s*[-*] /, ''))}</li>`; continue; }
    if (list) { out += '</ul>'; list = false; }
    const h = l.match(/^(#{1,4}) (.*)/); if (h) { out += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`; continue; }
    if (l.trim()) out += `<p${pStyle ? ` style='${pStyle}'` : ''}>${inline(l)}</p>`;
  }
  if (list) out += '</ul>';
  return out;
}

/* ---------- TOTP, so a real Microsoft Authenticator code works in the preview ---------- */
function b32(s) { const A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = ''; for (const c of s.replace(/=+$/, '').toUpperCase()) { const v = A.indexOf(c); if (v < 0) continue; bits += v.toString(2).padStart(5, '0'); } const out = []; for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2)); return new Uint8Array(out); }
async function totp(secret, step) {
  const key = await crypto.subtle.importKey('raw', b32(secret), { name: 'HMAC', hash: 'SHA-1' }, false, ['sign']);
  const msg = new ArrayBuffer(8); new DataView(msg).setUint32(4, step);
  const h = new Uint8Array(await crypto.subtle.sign('HMAC', key, msg)); const o = h[19] & 15;
  return String((((h[o] & 127) << 24) | (h[o + 1] << 16) | (h[o + 2] << 8) | h[o + 3]) % 1e6).padStart(6, '0');
}
async function codeOk(code) {
  code = String(code || '').replace(/\s/g, ''); if (!/^\d{6}$/.test(code)) return false;
  if (!SAMPLE_SECRET || !(crypto && crypto.subtle)) return true;   // no WebCrypto here: any six digits
  const step = Math.floor(Date.now() / 30000);
  try { for (const d of [-1, 0, 1]) if (await totp(SAMPLE_SECRET, step + d) === code) return true; } catch { return true; }
  return code === '000000';   // the preview's spare key, for anyone without the app
}

/* ---------- the routes ---------- */
const R = [];
const route = (method, re, fn) => R.push([method, re, fn]);
const recentOk = () => Date.now() - (X.reauthAt || 0) < 300000;
const needRecent = () => recentOk() ? null : http(403, 'Type your password again', { reauth: true });

// ----- sign-in -----
route('POST', /^\/auth\/login$/, async b => {
  const name = String(b.user || '').trim(), pw = String(b.password || '');
  if (!name || !pw) return http(401, 'Wrong user or password');
  const u = userOf(name);
  if (u && !u.enabled) return http(401, 'That account is disabled. An administrator can enable it in Directory.');
  if (u && X.pw[u.name] && X.pw[u.name] !== pw) return http(401, 'Wrong user or password');
  const user = u ? u.name : name; const role = u ? (isAdminUser(u) ? 'admin' : 'member') : 'admin';
  if (X.twofa.includes(user)) { const p = 'pending-' + token(10); mem.strikes[p] = { user, role, left: 3, at: Date.now() }; return ok({ need_code: true, pending: p, user }); }
  X.session = { user, role }; if (u) { u.last_logon = isoSec(); touch('GET /directory/users'); }
  save(); return ok({ user, role });
});
route('POST', /^\/auth\/login\/code$/, async b => {
  const p = mem.strikes[b.pending]; if (!p || Date.now() - p.at > 300000) return http(401, 'Sign in again: that took more than five minutes');
  if (!(await codeOk(b.code))) { p.left--; if (p.left <= 0) { delete mem.strikes[b.pending]; return http(401, 'Three wrong codes. Sign in again.'); } return http(401, `That code is not right (${p.left} more ${p.left === 1 ? 'try' : 'tries'}). In the preview the code from the sample key works, or 000000.`); }
  delete mem.strikes[b.pending]; X.session = { user: p.user, role: p.role }; const u = userOf(p.user); if (u) { u.last_logon = isoSec(); touch('GET /directory/users'); } save(); return ok({ user: p.user });
});
route('POST', /^\/auth\/reauth$/, b => { const s = me(); const pw = String(b.password || ''); if (!pw || (X.pw[s?.user] && X.pw[s.user] !== pw)) return http(401, 'That is not your password'); X.reauthAt = Date.now(); save(); return ok({ until: 300 }); });
route('POST', /^\/auth\/logout$/, () => { X.session = null; save(); return ok(); });
route('POST', /^\/me\/password$/, b => {
  const rules = get('GET /me/password/rules') || {}; const min = rules.min_length || 8; const s = me();
  if (!b.old) return fail('Type your current password');
  if (X.pw[s.user] && X.pw[s.user] !== b.old) return fail('The current password is not right');
  if (String(b.new || '').length < min) return fail(`At least ${min} characters`);
  if (s.user && String(b.new).toLowerCase().includes(s.user.split('.')[0].toLowerCase())) return fail('A password cannot contain your name');
  X.pw[s.user] = b.new; save(); return ok();
});
// ----- two-step (optional; Microsoft Authenticator) -----
route('POST', /^\/me\/2fa\/setup$/, () => { const s = clone(SEED['POST /me/2fa/setup'] || {}); delete s.demo; X.twofaPending = me().user; save(); return ok(Object.assign(s, { note: 'Preview: this is the sample key. Scan it, or type 000000.' })); });
route('POST', /^\/me\/2fa\/enable$/, async b => { if (!(await codeOk(b.code))) return fail('That code is not right. Type the six digits the app shows now (or 000000 in the preview).'); const u = me().user; if (!X.twofa.includes(u)) X.twofa.push(u); X.twofaSince[u] = isoMin(); save(); return ok({ on: true }); });
route('POST', /^\/me\/2fa\/disable$/, async b => { if (!b.password) return fail('Type your password'); if (!(await codeOk(b.code))) return fail('That code is not right'); const u = me().user; X.twofa = X.twofa.filter(x => x !== u); save(); return ok({ on: false }); });

// ----- Directory -----
route('POST', /^\/directory\/users$/, b => {
  const name = String(b.name || '').trim();
  if (!NAME_RE.test(name)) return fail('name: letters, digits, dot, dash, underscore; 2-64 chars; starts with a letter');
  if (String(b.password || '').length < 8) return fail('password: at least 8 characters');
  if (userOf(name)) return fail(`${name} already exists`);
  const want = (b.groups || []).map(g => String(g).trim()).filter(Boolean); const missing = want.filter(g => !groups().find(x => x.name.toLowerCase() === g.toLowerCase()));
  if (missing.length) return fail(`no such group: ${missing.join(', ')} (make it under Groups first)`);
  const gnames = want.map(g => groups().find(x => x.name.toLowerCase() === g.toLowerCase()).name);
  users().push({ name, display: String(b.display || '').trim(), groups: gnames, enabled: true, last_logon: null, home: `\\\\arise-server\\homes\\${name}` });
  for (const g of gnames) { const gr = groups().find(x => x.name === g); if (!gr.members.includes(name)) gr.members.push(name); }
  X.pw[name] = b.password;
  for (const f of ['Documents', 'Photos', 'Videos', 'Music', 'Downloads']) mkdirp('data', `/homes/${name}/${f}`);
  touch('GET /directory/users', 'GET /directory/groups'); return ok({ out: `created ${name}` });
});
route('POST', /^\/directory\/users\/([^/]+)\/reset-password$/, (b, m) => { const u = userOf(m[1]); if (!u || String(b.password || '').length < 8) return fail('bad name or password shorter than 8'); X.pw[u.name] = b.password; save(); return ok(); });
route('POST', /^\/directory\/users\/([^/]+)\/(enable|disable)$/, (b, m) => {
  const u = userOf(m[1]); if (!u) return fail('no such user');
  if (m[2] === 'disable' && u.name === me()?.user) return fail('You cannot disable the account you are signed in with');
  u.enabled = m[2] === 'enable'; touch('GET /directory/users'); return ok();
});
route('DELETE', /^\/directory\/users\/([^/]+)$/, (b, m) => {
  const r = needRecent(); if (r) return r;
  const u = userOf(m[1]); if (b.confirm !== m[1]) return fail('type the user name to confirm; the home folder is kept either way'); if (!u) return fail('no such user');
  if (u.name === me()?.user) return fail('You cannot delete the account you are signed in with');
  G['GET /directory/users'].users = users().filter(x => x !== u);
  for (const g of groups()) g.members = g.members.filter(x => x !== u.name);
  X.twofa = X.twofa.filter(x => x !== u.name); delete X.pw[u.name];
  touch('GET /directory/users', 'GET /directory/groups'); return ok();
});
route('POST', /^\/directory\/groups$/, b => {
  const name = String(b.name || '').trim(); if (!NAME_RE.test(name.replace(/ /g, '_'))) return fail('bad group name');
  if (groups().find(g => g.name.toLowerCase() === name.toLowerCase())) return fail(`${name} already exists`);
  groups().push({ name, members: [], description: String(b.description || '').trim() }); touch('GET /directory/groups'); return ok();
});
route('POST', /^\/directory\/groups\/([^/]+)\/members$/, (b, m) => {
  const g = groups().find(x => x.name === m[1]); const u = userOf(String(b.user || '').trim());
  if (!g) return fail('no such group'); if (!u) return fail(`no such user: ${b.user || '(empty)'}`);
  if (g.members.includes(u.name)) return fail(`${u.name} is already in ${g.name}`);
  g.members.push(u.name); if (!u.groups.includes(g.name)) u.groups.push(g.name); touch('GET /directory/groups', 'GET /directory/users'); return ok();
});
route('DELETE', /^\/directory\/groups\/([^/]+)\/members\/([^/]+)$/, (b, m) => {
  const g = groups().find(x => x.name === m[1]); const u = userOf(m[2]); if (!g || !u) return fail('no such group or user');
  if (g.name === 'Domain Admins' && u.name === me()?.user) return fail('You cannot take yourself out of Domain Admins');
  g.members = g.members.filter(x => x !== u.name); u.groups = u.groups.filter(x => x !== g.name); touch('GET /directory/groups', 'GET /directory/users'); return ok();
});
// ----- Shares -----
route('POST', /^\/shares$/, b => {
  const name = String(b.name || '').trim(), path = String(b.path || '').trim();
  if (!SHARE_RE.test(name)) return fail('share name: letters, digits, space, dash, underscore, up to 32');
  if (!path.startsWith('/')) return fail('path must be absolute');
  if (shares().find(s => s.name.toLowerCase() === name.toLowerCase())) return fail(`there is already a share called ${name}`);
  const group = String(b.group || 'Domain Users').trim();
  if (group !== 'Domain Users' && !groups().find(g => g.name === group)) return fail(`no such group: ${group}`);
  shares().push({ name, path, comment: String(b.comment || ''), writable: true, browseable: true, used: 0, mac: !!b.mac, valid_users: group === 'Domain Users' ? [] : ['@' + group], write_list: [] });
  if (path.startsWith('/srv/arise/')) mkdirp('data', path.slice('/srv/arise'.length)); else if (path.startsWith('/mnt/synology/')) mkdirp('nas', path.slice('/mnt/synology'.length));
  mkdirp('data', '/shares/' + name);
  touch('GET /shares'); return ok({ out: `added [${name}] at ${path}` });
});
route('DELETE', /^\/shares\/([^/]+)$/, (b, m) => {
  const name = decodeURIComponent(m[1]); if (b.confirm !== name) return fail('type the share name to confirm; files on disk are never touched');
  if (['homes', 'sysvol', 'netlogon'].includes(name)) return fail(`${name} is part of the domain and stays`);
  const before = shares().length; G['GET /shares'].shares = shares().filter(s => s.name !== name); if (shares().length === before) return fail('no such share');
  touch('GET /shares'); return ok();
});

// ----- Backups, the automator, the Synology, services -----
route('POST', /^\/backups\/run\/([^/]+)$/, (b, m) => {
  const job = (get('GET /backups/jobs').jobs || []).find(j => j.id === m[1]); if (!job) return fail('no such job');
  const t = new Date(); const sid = hex(8); const added = Math.round(2e6 + Math.random() * 6e8);
  get('GET /backups/history').rows.unshift({ job: job.id, name: job.name, started: isoSec(t), finished: isoSec(new Date(t.getTime() + 90000)), ok: true, snapshot_id: sid, bytes_added: added, files_new: Math.round(Math.random() * 300), error: null });
  const sn = get('GET /backups/snapshots'); (sn.snapshots = sn.snapshots || []).unshift({ id: sid, time: isoSec(t), tags: job.tags || [job.id], paths: job.paths || [] });
  const repo = get('GET /backups/repo'); repo.snapshots = (repo.snapshots || 0) + 1; repo.total_size = (repo.total_size || 0) + added;
  touch('GET /backups/history', 'GET /backups/snapshots', 'GET /backups/repo'); return ok({ started: true, job: job.id });
});
route('POST', /^\/backups\/check$/, () => { get('GET /backups/repo').last_check = isoSec(); touch('GET /backups/repo'); return ok({ out: 'restic check: no errors were found' }); });
route('POST', /^\/backups\/mirror$/, () => ok({ demo: true, repos: [], out: 'Preview: the GitHub mirror refreshes on the server at 04:00' }));
route('POST', /^\/automator\/preview$/, () => { const a = get('GET /automator'); a.manual = { mode: 'preview', started: isoSec(), finished: isoSec(), ok: true, code: 0 }; touch('GET /automator'); return ok({ mode: 'preview' }); });
route('POST', /^\/automator\/run$/, () => {
  const t = (get('GET /automations').timers || []).find(x => x.timer === 'arise-automator.timer');
  if (!t || t.enabled) return fail('The 02:05 timer is on, so the real run is the timer\'s alone (never by hand, never twice a night). Use Preview, or pause the timer in Automations first.');
  const a = get('GET /automator'); a.manual = { mode: 'run', started: isoSec(), finished: isoSec(), ok: true, code: 0 }; touch('GET /automator');
  return ok({ demo: true, mode: 'run', out: 'Preview: nothing was written to YouTube' });
});
route('POST', /^\/nas\/(mount|unmount)$/, (b, m) => { const n = get('GET /nas'); n.mounted = m[1] === 'mount'; touch('GET /nas'); return ok(); });
route('POST', /^\/services\/([^/]+)\/(start|stop|restart)$/, (b, m) => {
  const unit = decodeURIComponent(m[1]);
  if (unit === 'samba-ad-dc.service' && m[2] !== 'start') { const s = inService(); if (s) return fail(`Not during ${s.name}: it ends about ${s.ends_at}. Try again then.`); }
  const sv = (get('GET /services').services || []).find(x => x.unit === unit); if (!sv) return fail('no such unit');
  sv.active = m[2] === 'stop' ? 'inactive' : 'active'; sv.sub = m[2] === 'stop' ? 'dead' : 'running'; sv.since = isoSec(); touch('GET /services');
  return ok({ demo: unit === 'arise-web.service', out: `systemctl ${m[2]} ${unit}` });
});

// ----- the Store -----
const appsList = () => get('GET /apps').apps;
const catalogEntry = id => (get('GET /apps/templates').templates || []).concat(get('GET /apps/catalog')?.apps || []).find(x => x.id === id);
route('POST', /^\/apps\/deploy$/, b => {
  const e = catalogEntry(b.template); if (!e) return fail(`no template or catalogue entry called ${b.template}`);
  const name = b.name || e.id; const port = (e.ports || [])[0]?.split(':')[0];
  const old = appsList().find(a => a.name === name);
  const row = { name, template: e.id, status: 'running', ports: e.ports || [], cpu: 0.4, mem: Math.round((e.ram_mb || 200) * 0.6e6), url: port ? `http://arise-server:${port}` : '', updated: isoSec(), ram_mb: e.ram_mb, limit_mb: e.limits?.mem_mb, autostart: e.autostart !== false, source: e.source || 'template', mem_h: '' };
  if (old) Object.assign(old, row); else appsList().push(row);
  G[`GET /apps/${name}/logs`] = { name, text: `${isoSec()} ${name}: pulled ${e.image || e.id}, created, started (preview)\n` };
  touch('GET /apps', `GET /apps/${name}/logs`); return ok({ out: `${old ? 'redeployed' : 'deployed'} ${e.id} as ${name}` });
});
route('POST', /^\/apps\/([^/]+)\/(start|stop|restart)$/, (b, m) => { const a = appsList().find(x => x.name === m[1]); if (!a) return fail('no such app'); a.status = m[2] === 'stop' ? 'stopped' : 'running'; a.cpu = a.status === 'running' ? 0.8 : null; a.mem = a.status === 'running' ? Math.round((a.ram_mb || 200) * 0.6e6) : 0; a.updated = isoSec(); touch('GET /apps'); return ok({ out: `docker compose ${m[2]} ${a.name}` }); });
route('POST', /^\/apps\/([^/]+)\/remove$/, (b, m) => { if (b.confirm !== m[1]) return fail('type the app name to confirm'); const n = appsList().length; G['GET /apps'].apps = appsList().filter(x => x.name !== m[1]); if (appsList().length === n) return fail('no such app'); touch('GET /apps'); return ok({ out: `removed ${m[1]}; /srv/arise/apps/${m[1]} kept` }); });
route('POST', /^\/apps\/([^/]+)\/autostart$/, (b, m) => { const a = appsList().find(x => x.name === m[1]); if (!a) return fail('no such app'); a.autostart = !!b.on; touch('GET /apps'); return ok({ out: `autostart ${b.on ? 'on' : 'off'} for ${a.name}` }); });
route('POST', /^\/updates\/refresh$/, () => { const u = get('GET /updates'); u.last_check = isoSec(); touch('GET /updates'); return ok({ status: u }); });
route('POST', /^\/updates\/check-apps$/, () => { const u = get('GET /updates'); u.apps = u.apps || { apps: [] }; u.apps.checked_at = isoSec(); touch('GET /updates'); return ok({ checked_at: u.apps.checked_at, apps: u.apps.apps }); });
route('POST', /^\/updates\/queue$/, b => { const u = get('GET /updates'); u.queue = { packages: b.packages || [], apps: b.apps || [], reboot: !!b.reboot, queued_at: isoSec(), by: me()?.user }; touch('GET /updates'); return ok({ queue: u.queue }); });
route('POST', /^\/updates\/apply$/, b => {
  if (b.confirm !== 'install') return fail('type install to confirm');
  const s = inService(); if (s) return fail(`Not during ${s.name}: it ends about ${s.ends_at}.`);
  const u = get('GET /updates'); const q = u.queue || { packages: [], apps: [] };
  u.other = (u.other || []).filter(p => !q.packages.includes(p.name)); for (const a of (u.apps?.apps || [])) if (q.apps.includes(a.name)) a.update = false;
  const reboot = q.reboot && u.reboot_required; if (reboot) { u.reboot_required = false; u.reboot_pkgs = []; }
  const summary = `Preview: a snapshot first, then ${q.packages.length} package${q.packages.length === 1 ? '' : 's'} and ${q.apps.length} app${q.apps.length === 1 ? '' : 's'}${reboot ? ', then a reboot' : ''}. Nothing was installed on a real box.`;
  u.last_apply = { when: isoSec(), ok: true, summary }; u.queue = { packages: [], apps: [], reboot: false };
  touch('GET /updates'); return ok({ when: isoSec(), steps: [], summary });
});
route('POST', /^\/system\/update$/, () => ok({ demo: true, out: 'Preview: ariseOS updates itself from GitHub on the server' }));
route('POST', /^\/system\/power$/, b => {
  const r = needRecent(); if (r) return r;
  if (!['reboot', 'poweroff'].includes(b.action) || b.confirm !== b.action) return fail('type the word to confirm');
  const s = inService(); if (s) return fail(`Not during ${s.name}: it ends about ${s.ends_at}. Try again then.`);
  return ok({ demo: true, out: `Preview: the server would ${b.action === 'reboot' ? 'restart' : 'shut down'} now` });
});
route('POST', /^\/activity\/kill$/, b => {
  if (String(b.confirm) !== String(b.pid)) return fail('type the PID to confirm');
  if (+b.pid === 1) return fail('PID 1 is the system itself');
  const a = get('GET /activity'); const p = (a.processes || []).find(x => x.pid === +b.pid); if (!p) return fail(`no process ${b.pid}`);
  if (p.protected) return fail(`${p.name} is kept: the domain, Docker, SSH, the dashboard and systemd cannot be ended from here`);
  a.processes = a.processes.filter(x => x !== p); touch('GET /activity'); return ok({ out: `Ended ${p.name} (PID ${p.pid})` });
});
route('POST', /^\/automations\/([^/]+)\/(pause|resume)$/, (b, m) => {
  const name = decodeURIComponent(m[1]); if (b.confirm !== name) return fail('type the timer name to confirm');
  const t = (get('GET /automations').timers || []).find(x => x.timer === name); if (!t) return fail('no such timer');
  t.enabled = m[2] === 'resume'; t.state = t.enabled ? 'enabled' : 'disabled'; if (!t.enabled) t.next = null; else if (!t.next) t.next = isoSec(new Date(Date.now() + 3600000));
  touch('GET /automations'); return ok({ out: `systemctl ${t.enabled ? 'enable' : 'disable'} --now ${name}` });
});
route('POST', /^\/storage\/scan$/, () => { const s = get('GET /storage'); if (s.scan) s.scan.as_of = isoSec(); touch('GET /storage'); return ok(); });
route('POST', /^\/monitor\/power$/, b => { const m = get('GET /monitor'); for (const o of m.outputs || []) o.enabled = !!b.on; touch('GET /monitor'); return ok({ out: `monitor ${b.on ? 'on' : 'off'}` }); });

// ----- Finder -----
route('POST', /^\/files\/mkdir$/, b => {
  const pl = place(b.root, b.path); if (!pl) return fail('not a place you can write to');
  if (roots().find(r => r.id === b.root)?.writable === false) return fail('that share is read-only for you');
  const name = String(b.name || '').trim(); if (!name || name.startsWith('.') || /[/\\]/.test(name)) return fail('bad folder name');
  if ((list(pl.root, pl.path) || []).find(e => e.name === name)) return fail(`there is already something called ${name} here`);
  mkdirp(pl.root, join(pl.path, name)); save(); return ok();
});
route('POST', /^\/files\/upload$/, async b => {
  const f = b instanceof FormData ? b.get('file') : null; if (!f) return fail('no file');
  const pl = place(b.get('root'), b.get('path')); if (!pl) return fail('not a place you can write to');
  if (roots().find(r => r.id === b.get('root'))?.writable === false) return fail('that share is read-only for you');
  const p = join(pl.path, f.name); const text = TEXT_RE.test(f.name) && f.size <= 256 * 1024 ? await f.text() : null;
  putFile(pl.root, p, f.size, text); try { mem.blobs[fsk(pl.root, p)] = { url: URL.createObjectURL(f), type: f.type }; } catch {}
  save(); return ok({ name: f.name, size: f.size });
});
route('POST', /^\/files\/upload\/start$/, b => {
  const pl = place(b.root, b.path); if (!pl) return fail('not a place you can write to');
  if (b.size > 10 * 1024 ** 3) return fail('over the 10 GB limit');
  const fp = b.fingerprint || ''; const old = Object.entries(mem.uploads).find(([, u]) => u.fp === fp && u.name === b.name);
  if (old) return ok({ token: old[0], offset: old[1].offset, chunk: 8 * 1024 * 1024, size: b.size, resumed: old[1].offset > 0 });
  const t = 'up-' + token(10); mem.uploads[t] = { fp, name: b.name, size: b.size, offset: 0, root: pl.root, path: pl.path, parts: [] };
  return ok({ token: t, offset: 0, chunk: 8 * 1024 * 1024, size: b.size });
});
route('PUT', /^\/files\/upload\/chunk$/, (b, m, q) => { const u = mem.uploads[q.get('token')]; if (!u) return fail('no such upload'); if (+q.get('offset') !== u.offset) return ok({ offset: u.offset }); const n = b && b.size != null ? b.size : 0; u.offset += n; if (b instanceof Blob) u.parts.push(b); return ok({ offset: u.offset }); });
route('POST', /^\/files\/upload\/finish$/, b => {
  const u = mem.uploads[b.token]; if (!u) return fail('no such upload'); if (u.offset < u.size) return fail(`only ${u.offset} of ${u.size} bytes arrived`);
  const p = join(u.path, u.name); putFile(u.root, p, u.size, null);
  try { mem.blobs[fsk(u.root, p)] = { url: URL.createObjectURL(new Blob(u.parts)), type: '' }; } catch {}
  delete mem.uploads[b.token]; save(); return ok({ name: u.name, size: u.size });
});
route('PUT', /^\/files\/text$/, b => {
  const pl = place(b.root, b.path); if (!pl) return fail('not a place you can write to');
  if (!TEXT_RE.test(pl.path)) return fail('only plain text and Markdown files are edited here');
  if (roots().find(r => r.id === b.root)?.writable === false) return fail('that share is read-only for you');
  const text = String(b.text ?? ''); if (text.length > 1024 * 1024) return fail('over 1 MB: edit it on a Mac');
  putFile(pl.root, pl.path, new Blob([text]).size, text); save(); const e = entryOf(pl.root, pl.path); return ok({ bytes: e.size, mtime: e.mtime });
});
route('POST', /^\/files\/text\/preview$/, b => ({ html: mdHtml(b.text) }));
route('POST', /^\/files\/trash$/, b => {
  const pl = place(b.root, b.path); if (!pl) return fail('not a place you can change');
  if (roots().find(r => r.id === b.root)?.writable === false) return fail('that share is read-only for you');
  if (b.confirm !== base(pl.path)) return fail('type the name to confirm');
  const sh = shareOf(pl.root, pl.path); const pack = takeOut(pl.root, pl.path); if (!pack) return fail('no such file');
  const when = isoMin(); const user = me().user;
  X.trash.unshift({ base: sh.base, label: sh.label, user, rel: `${when.replace(/[:T-]/g, '')}-${pack.entry.name}`, name: pack.entry.name, original: sh.rel, dir: !!pack.entry.dir, size: pack.entry.dir ? null : pack.entry.size, when, from: 'portal', _root: pl.root, _path: pl.path, _pack: pack });
  save(); return ok({ trash: `.Trash/${user}/${pack.entry.name}` });
});
route('POST', /^\/files\/trash\/restore$/, b => {
  const i = X.trash.findIndex(t => t.base === b.base && t.user === b.user && t.rel === b.rel); if (i < 0) return fail('not in the Trash any more');
  const t = X.trash[i]; if (!isAdmin() && t.user !== me().user) return fail('that is someone else\'s');
  let root = t._root || 'data', path = t._path || norm((t.base.replace(/^\/srv\/arise/, '').replace(/^\/mnt\/synology/, '')) + '/' + t.original); if (t.base.startsWith('/mnt/synology')) root = 'nas';
  let renamed = false; if (entryOf(root, path)) { const dot = t.name.lastIndexOf('.'); const nn = dot > 0 && !t.dir ? t.name.slice(0, dot) + ' (put back)' + t.name.slice(dot) : t.name + ' (put back)'; path = join(parent(path), nn); renamed = true; }
  putBack(root, path, t._pack || { entry: { name: t.name, dir: t.dir, size: t.size, mtime: t.when }, sub: t.dir ? { '/': [] } : {}, content: {} });
  X.trash.splice(i, 1); save(); return ok({ restored: (t.label + '/' + path.split('/').filter(Boolean).slice(t.label === 'homes' ? 1 : t.label === 'synology' ? 0 : 2).join('/')), renamed });
});
route('POST', /^\/files\/trash\/empty$/, b => {
  if (!isAdmin()) return http(403, 'Emptying the Trash is the administrator\'s click');
  if (b.confirm !== b.share) return fail('type the share name to confirm');
  const n = X.trash.filter(t => t.label === b.share).length; X.trash = X.trash.filter(t => t.label !== b.share); save(); return ok({ removed: n });
});
route('POST', /^\/files\/versions\/restore$/, b => {
  const pl = place(b.root, b.path); if (!pl) return fail('not a place you can change'); const e = entryOf(pl.root, pl.path); if (!e) return fail('no such file');
  const v = versionsOf(pl.root, pl.path).versions.find(x => x.snapshot === b.snapshot); if (!v) return fail('no such copy in the backup');
  const d = v.time.slice(0, 10); const n = base(pl.path); const dot = n.lastIndexOf('.');
  const restored = dot > 0 && !e.dir ? `${n.slice(0, dot)} (restored ${d})${n.slice(dot)}` : `${n} (restored ${d})`;
  if (e.dir) mkdirp(pl.root, join(parent(pl.path), restored)); else putFile(pl.root, join(parent(pl.path), restored), v.size, X.content[fsk(pl.root, pl.path)] ?? null);
  save(); return ok({ restored });
});
function versionsOf(root, path) {
  const sh = shareOf(root, path); const e = entryOf(root, path);
  if (root === 'nas') return { backed_up: false, path, versions: [] };
  const job = sh.label === 'homes' ? ['homes', 'Home folders'] : norm(path).startsWith('/shares') ? ['shares', 'Shared folders'] : norm(path).startsWith('/automator') ? ['automator', 'YouTube automator'] : null;
  if (!job || !e) return { backed_up: !!job, path, versions: [], job: job?.[0], job_name: job?.[1] };
  const out = []; const t = new Date(); t.setHours(3, 0, 0, 0); if (t > new Date()) t.setDate(t.getDate() - 1);
  for (const back of [0, 1, 2, 6, 13]) { const d = new Date(t); d.setDate(d.getDate() - back); const mt = new Date(d); mt.setDate(mt.getDate() - 1); out.push({ snapshot: hashOf(path + back), time: isoSec(d), size: e.dir ? null : Math.round((e.size || 1000) * (1 - back * 0.01)), mtime: isoSec(mt), dir: !!e.dir }); }
  return { path: '/srv/arise' + norm(path), job: job[0], job_name: job[1], versions: out, backed_up: true };
}
function hashOf(s) { let h = 2166136261; for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16).padStart(8, '0'); }

// ----- share links -----
route('POST', /^\/links$/, b => {
  const pl = place(b.root, b.path); if (!pl) return fail('not a place you can share from'); const e = entryOf(pl.root, pl.path); if (!e) return fail('no such file');
  const days = b.days == null ? 0 : +b.days; const exp = days > 0 ? isoMin(new Date(Date.now() + Math.min(days, 365) * 86400000)) : null;
  const t = token(12); const link = { root: b.root, path: norm(b.path), name: e.name || base(pl.path), user: me().user, created: isoMin(), expires: exp, note: String(b.note || ''), downloads: 0, dir: !!e.dir, token: t, expired: false };
  get('GET /links').links.unshift(link); touch('GET /links'); return ok({ token: t, link, url: `${location.origin}/s/${t}` });
});
route('DELETE', /^\/links\/([^/]+)$/, (b, m) => { const L = get('GET /links'); const l = L.links.find(x => x.token === m[1]); if (!l) return fail('no such link'); if (!isAdmin() && l.user !== me().user) return fail('that link is someone else\'s'); L.links = L.links.filter(x => x !== l); touch('GET /links'); return ok(); });

// ----- Sunday, the calendar, the monitor -----
route('POST', /^\/sunday\/(\d+)$/, (b, m) => { const s = get('GET /sunday'); const it = (s.items || []).find(x => x.i === +m[1]); if (!it) return fail('no such item'); it.done = !it.done; it.by = it.done ? me().user : ''; it.at = it.done ? isoMin() : ''; touch('GET /sunday'); return ok({ sunday: s.sunday, items: s.items }); });
// Leaving (round 2, 24): marked now, disabled after the grace period, files moved to who takes them.
const auditAdd = (action, target, detail) => { const a = getOr('GET /audit?limit=60', { events: [] }); (a.events = a.events || []).unshift({ t: new Date().toISOString().slice(0, 19), who: me()?.user, action, target, ok: true, ...(detail ? { detail } : {}) }); touch('GET /audit?limit=60'); };
route('POST', /^\/directory\/users\/([^/]+)\/leaving$/, (b, m) => {
  if (!isAdmin()) return http(403, 'Administrator only'); const name = decodeURIComponent(m[1]); const to = String(b.move_to || '');
  if (!userOf(name)) return fail('no such user'); if (!to || !userOf(to)) return fail('pick who takes the files'); if (to.toLowerCase() === name.toLowerCase()) return fail('the files cannot move to the person who is leaving');
  const days = b.days === undefined ? 30 : +b.days; if (!(days >= 0 && days <= 365)) return fail('the grace period is 0 to 365 days');
  const L = getOr('GET /directory/leaving', { entries: [], grace_days: 30 }); const now = new Date(); const on = new Date(now.getTime() + days * 86400000);
  const entry = { name, move_to: to, by: me().user, since: now.toISOString().slice(0, 19), disable_on: on.toISOString().slice(0, 10), done: null };
  L.entries = L.entries.filter(e => e.name !== name || e.done).concat([entry]); touch('GET /directory/leaving'); auditAdd('directory.leaving', name, `files to ${to}; disabled on ${entry.disable_on}`);
  return ok({ entry, demo: true });
});
route('DELETE', /^\/directory\/users\/([^/]+)\/leaving$/, (b, m) => {
  if (!isAdmin()) return http(403, 'Administrator only'); const name = decodeURIComponent(m[1]); const L = getOr('GET /directory/leaving', { entries: [], grace_days: 30 });
  const keep = L.entries.filter(e => e.name !== name || e.done); if (keep.length === L.entries.length) return fail(`${name} is not marked as leaving`);
  L.entries = keep; touch('GET /directory/leaving'); auditAdd('directory.leaving.cancel', name); return ok();
});
route('POST', /^\/repos\/sync$/, () => { if (!isAdmin()) return http(403, 'Administrator only'); const r = getOr('GET /repos', { repos: [] }); const t = new Date().toISOString(); r.last = t; (r.repos || []).forEach(x => { x.when = t; }); touch('GET /repos'); return ok({ demo: true, started: true }); });
// Claude Desktop on the closet monitor: Bradly opens it (round 4, 44); anyone's lock closes it.
route('POST', /^\/kiosk\/claude-desktop$/, b => { const a = b.action || 'open'; if (!['open', 'close', 'status'].includes(a)) return fail('action is open, close or status'); if (a === 'open' && !claudeOk()) return fail("Claude on this box is Bradly's (round 4, 44)"); return ok({ demo: true, action: a, state: a === 'open' ? 'open' : 'closed' }); });
route('POST', /^\/kiosk\/open$/, b => ok({ demo: true, out: `Preview: the closet monitor would open ${b.url}` }));
const calClean = b => { const title = String(b.title || '').trim().slice(0, 120), start = String(b.start || '').trim().slice(0, 16); if (!title || isNaN(new Date(start))) return null; let end = String(b.end || '').trim().slice(0, 16); if (end && (isNaN(new Date(end)) || new Date(end) < new Date(start))) end = ''; return { title, start, end, where: String(b.where || '').trim().slice(0, 120), note: String(b.note || '').trim().slice(0, 1000) }; };
route('POST', /^\/calendar$/, b => { if (!isAdmin()) return http(403, 'Adding events is for the administrator'); const c = calClean(b); if (!c) return fail('a title and a start time are needed'); const ev = Object.assign({ id: hex(8) }, c, { who: me().user, added: isoMin() }); X.events.push(ev); save(); return ok({ event: ev }); });
route('PUT', /^\/calendar\/([^/]+)$/, (b, m) => { if (!isAdmin()) return http(403, 'Editing events is for the administrator'); const c = calClean(b); if (!c) return fail('a title and a start time are needed'); const ev = X.events.find(e => e.id === m[1]); if (!ev) return fail('no such event'); Object.assign(ev, c); save(); return ok({ event: ev }); });
route('DELETE', /^\/calendar\/([^/]+)$/, (b, m) => { if (!isAdmin()) return http(403, 'Removing events is for the administrator'); const n = X.events.length; X.events = X.events.filter(e => e.id !== m[1]); if (X.events.length === n) return fail('no such event (a service comes from the settings and cannot be removed here)'); save(); return ok(); });

// ----- Network, remote -----
route('POST', /^\/devices\/scan$/, () => { const d = get('GET /devices'); d.meta = Object.assign(d.meta || {}, { last_scan: isoMin() }); for (const x of d.devices || []) if (x.online) x.last_seen = isoMin(); touch('GET /devices'); return ok({ found: (d.devices || []).filter(x => x.online).length, new: 0 }); });
route('POST', /^\/devices\/([0-9a-fA-F:]{17})$/, (b, m) => { const d = (get('GET /devices').devices || []).find(x => x.mac.toLowerCase() === m[1].toLowerCase()); if (!d) return fail('no such device'); if (b.name != null) d.name = String(b.name).trim(); if (b.note != null) d.note = String(b.note).trim(); if (b.kind != null) { d.kind = b.kind; d.kind_final = b.kind || d.guess || 'unknown'; } touch('GET /devices'); return ok(); });
route('DELETE', /^\/devices\/([0-9a-fA-F:]{17})$/, (b, m) => { const D = get('GET /devices'); const d = (D.devices || []).find(x => x.mac.toLowerCase() === m[1].toLowerCase()); if (!d) return fail('no such device'); if (d.online) return fail('it is on the network now; forget it once it has gone'); D.devices = D.devices.filter(x => x !== d); touch('GET /devices'); return ok(); });
route('POST', /^\/remote\/wireguard\/peers$/, b => {
  const name = String(b.name || '').trim(); if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$/.test(name)) return fail('name: letters, digits, dot, dash, up to 32');
  const wg = get('GET /remote').wireguard; wg.peers = wg.peers || []; if (wg.peers.find(p => p.name === name)) return fail(`${name} already has a key`);
  const used = new Set(wg.peers.map(p => +String(p.ip).split('.')[3])); let n = 10; while (used.has(n)) n++; const ip = `10.47.0.${n}`;
  wg.peers.push({ name, ip, handshake: 'never', rx: 0, tx: 0, online: false }); touch('GET /remote');
  return ok({ name, ip, config: `[Interface]\nPrivateKey = (preview: the real key is made on the server)\nAddress = ${ip}/32\nDNS = 10.47.0.1\n\n[Peer]\nPublicKey = (server key)\nEndpoint = ${wg.endpoint || 'arise.example:51820'}\nAllowedIPs = 10.47.0.0/24, 192.168.1.0/24\nPersistentKeepalive = 25\n` });
});

// ----- Mail (Resend) -----
function parseCsv(text) {
  const rows = []; let row = [], cur = '', q = false;
  for (let i = 0; i < text.length; i++) { const c = text[i]; if (q) { if (c === '"' && text[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') q = false; else cur += c; } else if (c === '"') q = true; else if (c === ',') { row.push(cur); cur = ''; } else if (c === '\n' || c === '\r') { if (c === '\r' && text[i + 1] === '\n') i++; row.push(cur); rows.push(row); row = []; cur = ''; } else cur += c; }
  if (cur || row.length) { row.push(cur); rows.push(row); }
  const head = (rows.shift() || []).map(h => h.trim().toLowerCase()); const col = names => head.findIndex(h => names.includes(h));
  const ei = col(['email', 'e-mail', 'email address', 'email 1', 'emails']); if (ei < 0) return { err: 'no email column (Wix exports one called "Email")' };
  const fi = col(['first name', 'first', 'firstname', 'given name']), li = col(['last name', 'last', 'lastname', 'surname', 'family name']);
  const seen = new Set((get('GET /mail/contacts').contacts || []).map(c => c.email.toLowerCase())); const good = []; let skipped = 0;
  for (const r of rows) { const e = String(r[ei] || '').trim(); if (!EMAIL_RE.test(e) || seen.has(e.toLowerCase())) { if (r.some(x => x.trim())) skipped++; continue; } seen.add(e.toLowerCase()); good.push({ email: e, first_name: fi >= 0 ? String(r[fi] || '').trim() : '', last_name: li >= 0 ? String(r[li] || '').trim() : '' }); }
  return { good, skipped, columns: { email: head[ei], first: fi >= 0 ? head[fi] : '', last: li >= 0 ? head[li] : '' } };
}
route('POST', /^\/mail\/import\/preview$/, b => { const p = parseCsv(String(b.csv || '')); if (p.err) return { err: p.err }; return { count: p.good.length, skipped: p.skipped, columns: p.columns, err: null, sample: p.good.slice(0, 5) }; });
route('POST', /^\/mail\/import$/, b => {
  const p = parseCsv(String(b.csv || '')); if (p.err) return fail(p.err); const C = get('GET /mail/contacts');
  for (const g of p.good) C.contacts.push(Object.assign({ id: 'c' + hex(6), created_at: new Date().toISOString(), unsubscribed: false }, g));
  C.count = C.contacts.length; const st = get('GET /mail'); st.import = { total: p.good.length, done: p.good.length, failed: 0, running: false, finished: isoMin(), errors: [] };
  touch('GET /mail/contacts', 'GET /mail'); return ok({ queued: p.good.length });
});
route('POST', /^\/mail\/preview$/, b => {
  const tpl = SEED['POST /mail/preview']?.html || '<p>@@BODY@@</p>'; const P = 'margin:0 0 16px;line-height:1.55';
  const body = mdHtml(b.body, P).replace(/<h(\d)>/g, `<h$1 style='margin:22px 0 10px;font-size:20px'>`).replace(/<ul>/g, `<ul style='margin:0 0 16px;padding-left:20px;line-height:1.55'>`);
  return { html: tpl.replace(`<p style='${P}'>@@BODY@@</p>`, body).replace('@@BODY@@', body).replace(/@@SUBJECT@@/g, String(b.subject || '').replace(/</g, '&lt;')) };
});
route('POST', /^\/mail\/test$/, b => { if (!EMAIL_RE.test(String(b.to || ''))) return fail('that does not look like an email address'); if (!b.subject || !b.body) return fail('subject and body first'); return ok({ demo: true, out: `Preview: a test would go to ${b.to}` }); });
route('POST', /^\/mail\/broadcasts$/, b => { if (!b.subject || !b.body) return fail('subject and body first'); const id = 'bc-' + hex(6); get('GET /mail/broadcasts').broadcasts.unshift({ id, name: b.subject, subject: b.subject, status: 'draft', created_at: new Date().toISOString(), sent_at: null }); touch('GET /mail/broadcasts'); return ok({ id }); });
route('POST', /^\/mail\/broadcasts\/([^/]+)\/send$/, (b, m) => { if (b.confirm !== 'send') return fail('type send to confirm'); const x = get('GET /mail/broadcasts').broadcasts.find(y => y.id === m[1]); if (!x) return fail('no such newsletter'); x.status = 'sent (preview: nothing was emailed)'; x.sent_at = new Date().toISOString(); touch('GET /mail/broadcasts'); return ok({ demo: true, out: 'Preview: nothing was emailed' }); });

// ----- push, notes, security -----
route('POST', /^\/push\/subscribe$/, () => fail('push goes to the administrator\'s phone from the real server only'));
route('POST', /^\/push\/test$/, () => ok({ demo: true, sent: 0 }));
route('POST', /^\/notify\/test$/, () => ok({ demo: true, out: 'Preview: no Discord webhook here' }));
route('POST', /^\/security\/scan\/run$/, () => { const s = inService(); if (s) return fail(`Not during ${s.name}.`); const sc = getOr('GET /security/scan', { quarantine: '/srv/arise/.quarantine', installed: true, quarantined: [], next: 'Sunday 23:30' }); sc.last = Object.assign({}, sc.last || {}, { when: isoMin(), scanned: (sc.last?.scanned || 18000) + Math.round(Math.random() * 40), infected: 0, found: [], ok: true, seconds: 1900 }); touch('GET /security/scan'); return ok({ started: true }); });
route('POST', /^\/security\/scan\/restore$/, b => { if (b.confirm !== b.name) return fail('type the file name to confirm'); const sc = getOr('GET /security/scan', { quarantined: [] }); const n = (sc.quarantined || []).length; sc.quarantined = (sc.quarantined || []).filter(q => q.file.split('/').pop() !== b.name); if (sc.quarantined.length === n) return fail('no such file in quarantine'); touch('GET /security/scan'); return ok({ out: `${b.name} is back where it was` }); });

/* ---------- the GETs that are computed, not stored ---------- */
function computedGet(p, q) {
  const s = me();
  if (p === '/automator/videos') {
    const all = (get('GET /automator/videos') || { videos: [] }).videos; const ql = (q.get('q') || '').trim().toLowerCase(); const kind = q.get('kind') || '', has = q.get('has') || '';
    let rows = all.filter(r => !ql || r.id.toLowerCase() === ql || ql.split(/\s+/).every(w => (r.title || '').toLowerCase().includes(w)));
    if (kind) rows = rows.filter(r => r.kind === kind);
    if (has) rows = rows.filter(r => has === 'transcript' ? r.transcript : has === 'chapters' ? r.chapters : has === 'held' ? r.held : true);
    return { demo: true, total: rows.length, page: 1, pages: 1, per: 48, videos: rows, note: (get('GET /automator/videos') || {}).note };
  }
  if (p === '/automator/search') {
    const raw = (q.get('q') || '').trim(), kind = q.get('kind') || 'transcript'; const words = raw.toLowerCase().replace(/"/g, '').split(/\s+/).filter(Boolean);
    const vids = (get('GET /automator/videos') || { videos: [] }).videos; const out = { query: raw, kind, demo: true, videos: [], files: [], titles: [], songs: [], count: 0, lyrics: 'Transcripts include what was sung. Never copy sung words into a title, description or Short.' };
    if (!words.length) return out;
    out.titles = vids.filter(v => words.every(w => (v.title || '').toLowerCase().includes(w)));
    if (kind === 'transcript' || kind === 'all') for (const v of vids) {
      const t = get(`GET /automator/videos/${v.id}/transcript`); if (!t || !(t.segments || []).length) continue;
      const hits = t.segments.filter(s => words.every(w => s.text.toLowerCase().includes(w))).map(s => {
        let sn = s.text.replace(/[\[\]]/g, ''); for (const w of words) sn = sn.replace(new RegExp('(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig'), '[$1]');
        const m = Math.floor(s.t / 60), h = Math.floor(m / 60); const at = h ? `${h}:${String(m % 60).padStart(2, '0')}:${String(Math.floor(s.t % 60)).padStart(2, '0')}` : `${m}:${String(Math.floor(s.t % 60)).padStart(2, '0')}`;
        return { kind: 'transcript', snippet: sn, link: `https://youtu.be/${v.id}?t=${Math.floor(s.t)}`, sec: s.t, at, repo: t.repo, path: t.source, history: false, private: false };
      });
      if (hits.length) { out.videos.push(Object.assign({}, v, { hits: hits.slice(0, 12), total: hits.length })); out.count += hits.length; }
    }
    return out;
  }
  if (p.startsWith('/automator/videos/') && p.endsWith('/transcript')) return getOr('GET ' + p, { ok: true, segments: [], sources: [], note: 'No timed transcript for this video in the sample set.' });
  if (p === '/automator/archive/doc') return { ok: true, demo: true, repo: q.get('repo'), path: q.get('path'), text: 'Sample: on the server this is the file’s text from the archive (read-only).' };
  if (p === '/auth/me') return authMe();
  if (p === '/files/roots') return { roots: roots() };
  if (p === '/files/list') {
    const pl = place(q.get('root') || 'data', q.get('path') || '/'); if (!pl) return { root: q.get('root'), path: q.get('path'), entries: [], error: 'not a place you can open' };
    const es = list(pl.root, pl.path); if (!es) return { root: q.get('root'), path: q.get('path'), entries: [], error: 'folder not found' };
    return { root: q.get('root'), path: norm(q.get('path') || '/'), entries: clone(sortEntries(es.slice())) };
  }
  if (p === '/files/info') {
    const pl = place(q.get('root'), q.get('path')); if (!pl) return { error: 'not a place you can open' }; const e = entryOf(pl.root, pl.path); if (!e) return { error: 'no such file' };
    const sh = shareOf(pl.root, pl.path); const sd = shares().find(x => x.name === sh.label);
    const who = sh.label === 'homes' ? [sh.owner] : sd ? ((sd.valid_users || []).length ? sd.valid_users.map(x => x.replace(/^@/, '')) : ['everyone in the domain']) : ['the administrators'];
    const smb = pl.root === 'nas' ? `smb://synology.ad.arisecenla.church/${sh.rel}` : sh.label === 'homes' ? `smb://arise-server.ad.arisecenla.church/${sh.owner}${sh.rel.split('/').slice(1).length ? '/' + sh.rel.split('/').slice(1).join('/') : ''}` : sd ? `smb://arise-server.ad.arisecenla.church/${sh.label}${sh.rel ? '/' + sh.rel : ''}` : '';
    return { name: e.name || base(pl.path), root: q.get('root'), path: q.get('path'), smb, access: { share: sh.label, who, write: sd?.write_list?.length ? sd.write_list.map(x => x.replace(/^@/, '')) : who, note: sh.label === 'homes' ? 'a home folder: only this person, and the administrators' : '' }, dir: !!e.dir, kind: e.dir ? 'Folder' : '', size: e.dir ? sizeOf(pl.root, pl.path) : e.size, files: e.dir ? countFiles(pl.root, pl.path) : null, size_complete: true, owner: sh.owner || s?.user, group: 'Domain Users', created: e.mtime, modified: e.mtime, abs: (pl.root === 'nas' ? '/mnt/synology' : '/srv/arise') + pl.path };
  }
  if (p === '/files/versions') { const pl = place(q.get('root'), q.get('path')); if (!pl) return { error: 'not a place you can open', versions: [] }; return versionsOf(pl.root, pl.path); }
  if (p === '/files/text') {
    const pl = place(q.get('root'), q.get('path')); if (!pl) return fail('not a place you can open'); const e = entryOf(pl.root, pl.path); if (!e || e.dir) return fail('no such file');
    if (!TEXT_RE.test(pl.path)) return fail('only plain text and Markdown files open here');
    const k = fsk(pl.root, pl.path); const text = X.content[k] ?? `# ${e.name}\n\nSample text. On the server this is the real file; in the preview what you type here is kept in this browser.\n`;
    return { ok: true, name: e.name, text, bytes: new Blob([text]).size, mtime: e.mtime };
  }
  if (p === '/files/all') {
    if (!isAdmin()) return { error: 'that is the administrator\'s view' };
    const folder = q.get('folder') || 'Documents'; const owners = []; const entries = [];
    for (const h of list('data', '/homes') || []) { if (!h.dir) continue; const fp = `/homes/${h.name}/${folder}`; const es = list('data', fp); if (!es) continue; owners.push(h.name); for (const e of es) entries.push(Object.assign({ owner: h.name, root: 'data', path: join(fp, e.name) }, e)); }
    return { folder, owners, entries };
  }
  if (p === '/files/recent') {
    const hits = []; const cut = Date.now() - 7 * 86400000;
    for (const r of roots()) { const pl = place(r.id, '/'); if (!pl) continue; walk(pl.root, pl.path, (e, fp) => { if (!e.dir && new Date(e.mtime) >= cut) hits.push({ root: r.id, path: r.id === 'data' || r.id === 'nas' ? fp : fp.slice(pl.path.length) || '/', name: e.name, size: e.size, mtime: e.mtime, where: parent(fp) }); }); }
    hits.sort((a, b) => b.mtime.localeCompare(a.mtime)); return { days: 7, hits: hits.slice(0, 200), truncated: hits.length > 200 };
  }
  if (p === '/files/trash') return { days: 30, admin: isAdmin(), items: X.trash.filter(t => isAdmin() || t.user === s?.user).map(t => { const c = Object.assign({}, t); delete c._pack; delete c._root; delete c._path; return c; }) };
  if (p === '/files/upload/status') { const u = mem.uploads[q.get('token')]; return u ? ok({ offset: u.offset }) : fail('no such upload'); }
  if (p === '/links') return { links: get('GET /links').links.filter(l => isAdmin() || l.user === s?.user).map(l => Object.assign({}, l, { expired: !!l.expires && new Date(l.expires) < new Date() })) };
  if (p === '/search') {
    const ql = (q.get('q') || '').trim().toLowerCase(); const out = { hits: [], transcripts: [], users: [], computers: [] }; if (!ql) return out;
    for (const r of roots()) { const pl = place(r.id, '/'); if (!pl) continue; walk(pl.root, pl.path, (e, fp) => { if (e.name.toLowerCase().includes(ql) && out.hits.length < 40) out.hits.push({ root: r.id, path: r.id === 'data' || r.id === 'nas' ? fp : fp.slice(pl.path.length), name: e.name, dir: e.dir, size: e.size }); }); }
    if (isAdmin()) { out.users = users().filter(u => u.name.toLowerCase().includes(ql) || (u.display || '').toLowerCase().includes(ql)).slice(0, 8); out.computers = (get('GET /directory/computers')?.computers || []).filter(c => c.name.toLowerCase().includes(ql)).slice(0, 8); }
    return out;
  }
  if (p === '/calendar') { const n = new Date(); return calendar(+(q.get('year') || n.getFullYear()), +(q.get('month') || n.getMonth() + 1)); }
  if (p === '/me/2fa') return { user: s?.user, on: X.twofa.includes(s?.user), since: X.twofaSince[s?.user] || null, available: true };
  if (p === '/directory/2fa') return { users: X.twofa.slice() };
  if (p === '/security') {
    const o = clone(getOr('GET /security', { demo: true, rows: [{ id: 'twofa', label: 'Two-step sign-in', level: 'ok', text: '', fix: '' }], worst: 'ok', ca: {}, rescue: {} })); o.twofa = X.twofa.slice(); const row = (o.rows || []).find(r => r.id === 'twofa');
    if (row) row.text = X.twofa.length ? `${X.twofa.length} ${X.twofa.length === 1 ? 'person has' : 'people have'} it on: ${X.twofa.join(', ')}.` : 'Nobody has it on. It is optional; anyone turns it on from the flame menu.';
    o.scan = Object.assign({}, o.scan || {}, getOr('GET /security/scan', { quarantined: [] })); return o;
  }
  if (p === '/overview') {
    const o = clone(get('GET /overview')); const ap = appsList();
    o.counts = Object.assign({}, o.counts, { users: users().length, groups: groups().length, shares: shares().length, apps: ap.length, apps_running: ap.filter(a => a.status === 'running').length, computers: (get('GET /directory/computers')?.computers || []).length });
    const h = get('GET /backups/history').rows || []; if (h[0]) o.backup = Object.assign({}, o.backup, { last: { name: h[0].name, started: h[0].started, ok: h[0].ok } });
    o.nas = Object.assign({}, o.nas, { mounted: !!get('GET /nas').mounted }); return o;
  }
  if (p === '/directory/status') { const st = clone(get('GET /directory/status')); return Object.assign(st, { users: users().length, groups: groups().length }); }
  if (p === '/help') {
    const all = clone(get('GET /help')); if (!isAdmin()) all.docs = (all.docs || []).filter(d => d.name === 'PORTAL-GUIDE');
    const ql = (q.get('q') || '').trim().toLowerCase();
    if (ql.length >= 2) { const hits = []; for (const d of all.docs || []) { const h = get('GET /help/' + d.name); const text = String(h?.html || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' '); const i = text.toLowerCase().indexOf(ql); if (i >= 0 || d.title.toLowerCase().includes(ql)) hits.push({ name: d.name, title: d.title, snippet: i >= 0 ? '…' + text.slice(Math.max(0, i - 60), i + 90) + '…' : d.blurb }); } all.search = { q: ql, hits }; }
    return all;
  }
  let m;
  if ((m = p.match(/^\/help\/([A-Za-z0-9_-]+)$/))) { if (!isAdmin() && m[1] !== 'PORTAL-GUIDE') return { ok: false, title: m[1], html: '<p>That guide is for the administrator. The portal guide is yours.</p>' }; return get('GET /help/' + m[1]) || { ok: false, name: m[1], title: m[1], html: `<p>${m[1]} is not in the preview. On the server every document in docs/ opens here.</p>` }; }
  if ((m = p.match(/^\/apps\/open\/([^/]+)$/))) { const a = appsList().find(x => x.template === m[1] || x.name === m[1]); return { ok: true, installed: !!a, running: a?.status === 'running', url: a?.url || '', name: m[1] }; }
  if ((m = p.match(/^\/apps\/theme\/([^/]+)$/))) { const seeded = get('GET /apps/theme/' + m[1]); if (seeded) return seeded; const e = catalogEntry(m[1]); if (!e) return fail('no such app'); const t = e.theme || { via: 'none' }; return { ok: true, name: m[1], via: t.via, accepts: t.accepts || [], note: t.note || '', env: t.env || {}, files: t.files || [], commands: t.commands || [], house: { red: '#D6222D', ink: '#0A0A0C', fonts: 'Anton and Oswald' } }; }
  if ((m = p.match(/^\/apps\/([^/]+)\/logs$/))) return get(`GET /apps/${m[1]}/logs`) || { name: m[1], text: `(no sample log for ${m[1]} in the preview)` };
  if ((m = p.match(/^\/logs\/file\/([^/]+)$/))) return get('GET /logs/file/' + m[1]) || { name: m[1], text: `(no sample of ${m[1]} in the preview)`, lines: 0 };
  if ((m = p.match(/^\/logs\/([^/]+)$/)) && m[1] !== 'sources') return get('GET /logs/' + m[1]) || { unit: m[1], text: `(no sample journal for ${m[1]} in the preview)`, lines: 0 };
  if (p === '/bible') { const ref = q.get('ref') || ''; const hit = Object.keys(SEED).find(k => k.toLowerCase() === ('GET /bible?ref=' + ref).toLowerCase()); if (hit) return clone(SEED[hit]); const refs = Object.keys(SEED).filter(k => k.startsWith('GET /bible?ref=')).map(k => k.slice(15)); return { ok: false, error: `The preview carries ${refs.length} passages (${refs.join(', ')}). On the server any reference is read from bible-api.com.` }; }
  if (p === '/mail') { const st = clone(get('GET /mail')); return st; }
  if (p === '/about/week' && !G['GET /about/week']) { const c = get('GET /church') || {}; return { verse: c.verse || null, services: services().length, published_this_week: 0, minutes_this_week: 0, latest: '' }; }
  if (p === '/push/key' && !G['GET /push/key']) return { key: '', available: false, note: 'the preview sends no push', enabled_for_me: false };
  if (p === '/mail/contacts') { const c = clone(get('GET /mail/contacts')); c.count = (c.contacts || []).length; return c; }
  return undefined;
}

/* ---------- the entry point app.js calls ---------- */
async function handle(method, fullPath, body) {
  init();
  method = (method || 'GET').toUpperCase();
  const [p0, qs] = String(fullPath).split('?'); const p = p0.split('/').map(seg => { try { return decodeURIComponent(seg); } catch { return seg; } }).join('/'); const q = new URLSearchParams(qs || '');
  const s = me();
  if (!s && !/^\/(auth\/(login|me|logout)|auth\/login\/code|public\/|health)/.test(p)) return http(401, 'Sign in');
  if (s && s.role !== 'admin' && !memberOk(p)) return http(403, 'That part of the dashboard is for the administrator');
  if (method === 'GET') {
    const c = computedGet(p, q); if (c !== undefined) return clone(c);
    const key = 'GET ' + decodeURIComponent(fullPath); if (key in G) return clone(G[key]);
    const noTr = key.replace(/&translation=[^&]*/, ''); if (noTr in G) return clone(G[noTr]);
    if (('GET ' + p) in G) return clone(G['GET ' + p]);
    return { error: { message: 'not in the preview' } };
  }
  let b = body; if (typeof b === 'string') { try { b = JSON.parse(b); } catch { b = {}; } }
  if (b == null) b = {};
  for (const [m, re, fn] of R) { if (m !== method) continue; const mm = p.match(re); if (mm) { try { return await fn(b, mm, q); } catch (e) { console.error('preview mock', method, p, e); return fail('The preview tripped over this one: ' + e.message); } } }
  console.warn('[preview] not in the preview yet:', method, p);
  return fail(`not in the preview yet: ${method} ${p}`);
}
// Quick Look and the editor in the preview: what was uploaded or typed here.
function fileFor(rootId, rel) { init(); const pl = place(rootId, rel); if (!pl) return null; const k = fsk(pl.root, pl.path); const blob = mem.blobs[k]; const text = X.content[k]; if (!blob && text == null) return null; return { url: blob?.url || null, type: blob?.type || '', text: text ?? null }; }
function reset() { try { localStorage.removeItem(KEY); } catch {} load(); ready = true; }
function viewAs(kind) {
  init();
  if (kind === 'member') { const u = users().find(x => x.enabled && !isAdminUser(x) && (x.groups || []).includes('Staff')) || users().find(x => !isAdminUser(x)); X.session = { user: u.name, role: 'member' }; }
  else { const u = users().find(isAdminUser); X.session = { user: u ? u.name : 'bradly', role: 'admin' }; }
  save();
}
window.AriseMock = { handle, fileFor, reset, viewAs, session: () => { init(); return clone(X.session); }, sampleNames: () => { init(); return users().filter(u => u.enabled).map(u => ({ name: u.name, role: isAdminUser(u) ? 'admin' : 'member' })); }, inService, flush: () => { init(); save(); } };
})();
