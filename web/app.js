/* ===========================================================================
   ARISE SERVER — the desktop
   Plain JS, no build step. A menu bar, windows, a floating dock, a launchpad.
   Every app is a view function that returns HTML and an optional after(root)
   hook; the window manager puts it in a window. When the API is unreachable
   (the published preview, a laptop) every call falls back to
   window.ARISE_DEMO_DATA, generated from the server's own sample responses.
   =========================================================================== */
(() => {
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const fmtB = n => { if (n == null) return '—'; n = +n; const u = ['B','KB','MB','GB','TB']; let i = 0; while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; } return (i === 0 ? n.toFixed(0) : n.toFixed(1)) + ' ' + u[i]; };
const fmtRate = n => n == null ? '—' : fmtB(n) + '/s';
const fmtN = n => n == null ? '—' : Number(n).toLocaleString('en-US');
const fmtUp = s => { if (s == null) return '—'; const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60); return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`; };
const fmtT = iso => { if (!iso) return '—'; const d = new Date(iso); if (isNaN(d)) return esc(iso); return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); };
const ago = iso => { if (!iso) return 'never'; if (iso === 'now') return 'now'; const d = new Date(iso); if (isNaN(d)) return esc(iso); const s = (Date.now() - d) / 1000; if (s < 60) return 'just now'; if (s < 3600) return `${Math.floor(s/60)} min ago`; if (s < 86400) return `${Math.floor(s/3600)} h ago`; return `${Math.floor(s/86400)} d ago`; };
const pct = (a, b) => b ? Math.round(a / b * 100) : 0;
// A department's name as people say it (round 7, 51): Children's Department, not "Childrens-Department".
const deptName = d => String(d || '').replace(/-/g, ' ').replace(/\bchildrens\b/i, "Children's");
const isPhone = () => matchMedia('(max-width: 900px)').matches;

/* ---------------- state ---------------- */
const S = { demo: false, demoOnly: false, authed: false, user: null, stats: null, hist: [], sse: null, demoTimer: null, machine: null, overview: null, wins: {}, z: 10 };

/* ---------------- API ---------------- */
const DEMO = window.ARISE_DEMO_DATA || null;
function demoLookup(method, path) {
  if (!DEMO) return null;
  const key = method + ' ' + decodeURIComponent(path);
  if (key in DEMO) return DEMO[key];
  const noTr = key.replace(/&translation=[^&]*/, '');
  if (noTr in DEMO) return DEMO[noTr];
  const base = method + ' ' + path.split('?')[0];
  if (base in DEMO) return DEMO[base];
  if (method !== 'GET') return { ok: true, demo: true, out: '(preview) nothing was changed' };
  if (path.startsWith('/search?q=')) {
    // Spotlight in the preview: walk the sample folder listings and the sample directory.
    const q = decodeURIComponent(path.slice(10)).trim().toLowerCase(); const hits = [];
    for (const k of Object.keys(DEMO)) { const m = k.match(/^GET \/files\/list\?root=(\w+)&path=(.*)$/); if (!m) continue; for (const e of DEMO[k].entries || []) if (e.name.toLowerCase().includes(q)) hits.push({ root: m[1], path: (m[2] === '/' ? '' : m[2]) + '/' + e.name, name: e.name, dir: e.dir, size: e.size }); }
    const users = (DEMO['GET /directory/users']?.users || []).filter(u => u.name.toLowerCase().includes(q) || (u.display || '').toLowerCase().includes(q)).slice(0, 8);
    const computers = (DEMO['GET /directory/computers']?.computers || []).filter(c => c.name.toLowerCase().includes(q)).slice(0, 8);
    return { demo: true, hits: hits.slice(0, 40), users, computers };
  }
  return null;
}
async function api(path, opts = {}) {
  const method = opts.method || 'GET';
  if (S.demoOnly) {
    // The preview has its own little server (web/demo-mock.js): what you do here sticks.
    if (window.AriseMock) {
      const r = await window.AriseMock.handle(method, path, opts.body);
      if (r && r.__status) throw Object.assign(new Error(r.error?.message || 'failed'), { status: r.__status, reauth: !!r.error?.reauth, setup: r.error?.setup });
      return r;
    }
    const d = demoLookup(method, path); if (d) return structuredClone(d); return { demo: true, error: { message: 'not in the preview' } };
  }
  let r;
  try {
    r = await fetch('/api' + path, { method, headers: opts.body && !(opts.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}, body: opts.body ? (opts.body instanceof FormData ? opts.body : JSON.stringify(opts.body)) : undefined, credentials: 'same-origin' });
  } catch (e) {
    const d = demoLookup(method, path);
    if (d) { setDemoOnly(); return structuredClone(d); }
    throw new Error('Could not reach the server');
  }
  const ct = r.headers.get('content-type') || '';
  if (!ct.includes('json')) {
    const d = demoLookup(method, path);
    if (d) { setDemoOnly(); return structuredClone(d); }
    throw new Error('The server answered with something that is not the Arise API');
  }
  if (r.status === 401) { const j = await r.json().catch(() => ({})); throw Object.assign(new Error(j.error?.message || 'Sign in'), { status: 401, setup: j.error?.setup }); }
  const j = await r.json();
  if (!r.ok) throw Object.assign(new Error(j.error?.message || j.err || `HTTP ${r.status}`), { status: r.status, reauth: !!j.error?.reauth });
  return j;
}
function setDemoOnly() {
  if (S.demoOnly) return;
  S.demoOnly = true; S.demo = true;
  const b = $('#demoBadge'); b.hidden = false; b.textContent = 'Preview · sample data';
  b.setAttribute('role', 'button'); b.tabIndex = 0; b.title = 'The preview: switch who is signed in, or start it over';
  const open = e => { e.preventDefault(); e.stopPropagation(); const r = b.getBoundingClientRect(); ctxMenu(Math.max(8, r.right - 230), r.bottom + 6, previewMenu()); };
  b.onclick = open; b.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') open(e); };
}
// The preview's own menu: who is signed in, and a way back to the sample data as it was.
function previewMenu() {
  const M = window.AriseMock; if (!M) return [['This preview keeps nothing', () => {}]];
  const s = M.session();
  return [[s ? `Signed in as ${s.user} (${s.role})` : 'Signed out', () => {}], null,
    ['View as a member', () => { M.viewAs('member'); location.reload(); }],
    ['View as the administrator', () => { M.viewAs('admin'); location.reload(); }],
    ['Sign out (the sign-in screen)', () => signOut()], null,
    ['Reset the preview…', () => confirmType('Start the preview over', 'reset', 'Everything you changed in this preview (users, files, events, ticks) goes, and the sample data comes back as it was. It only lives in this browser.', async () => { M.reset(); location.reload(); })]];
}

/* ---------------- toasts / modal ---------------- */
function toast(msg, kind = 'ok', ms = 4200) {
  if (kind === 'bad' && msg === 'cancelled') return;   // closing the password prompt is a choice, not an error
  const t = document.createElement('div'); t.className = 'toast ' + kind; t.innerHTML = esc(msg);
  $('#toasts').appendChild(t); setTimeout(() => t.remove(), ms);
}
function modal(html, onOpen) {
  const m = $('#modal'); $('#modalBody').innerHTML = html; m.showModal(); onOpen && onOpen(m);
  $$('[data-close]', m).forEach(b => b.onclick = () => m.close());
  return m;
}
function confirmType(title, word, text, onYes) {
  modal(`<h2>${esc(title)}</h2><p class="note" style="margin-bottom:14px">${text}</p>
    <div class="field"><label>Type <b>${esc(word)}</b> to confirm</label><input id="cfWord" autocomplete="off"></div>
    <div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn btn--danger" id="cfGo" disabled>Do it</button></div>`, m => {
    const i = $('#cfWord', m), go = $('#cfGo', m);
    i.oninput = () => go.disabled = i.value !== word;
    go.onclick = async () => { go.classList.add('busy'); try { await onYes(); m.close(); } catch (e) { toast(e.message, 'bad'); } finally { go.classList.remove('busy'); } };
    i.focus();
  });
}
/* The dangerous clicks (delete a user, empty a Trash, shut down) ask for the
   password again; the server remembers a yes for five minutes. withReauth(fn)
   runs fn, and when the server answers 403 reauth, asks, posts, and runs fn again. */
function reauth() {
  return new Promise((resolve, reject) => {
    const m = modal(`<h2>Your password, again</h2><p class="muted">This is one of the clicks that asks twice. A yes is remembered for five minutes.</p>
      <form id="raf" style="display:grid;gap:8px;margin-top:12px"><input type="password" id="raPw" placeholder="Password" autocomplete="current-password">
      <div class="acts"><button type="button" class="btn btn--ghost" data-close>Cancel</button><button class="btn" type="submit">Continue</button></div></form>`, mm => {
      $('#raPw', mm).focus();
      $('#raf', mm).onsubmit = async e => { e.preventDefault(); try { await api('/auth/reauth', { method: 'POST', body: { password: $('#raPw', mm).value } }); mm.close(); resolve(true); } catch (er) { toast(er.message, 'bad'); $('#raPw', mm).value = ''; $('#raPw', mm).focus(); } };
    });
    m.addEventListener('close', () => reject(new Error('cancelled')), { once: true });
  });
}
async function withReauth(fn) {
  try { return await fn(); }
  catch (e) { if (!e.reauth) throw e; await reauth(); return await fn(); }
}
async function act(btn, fn, okMsg) {
  btn.classList.add('busy'); btn.disabled = true;
  try { const r = await fn(); if (r && r.ok === false) throw new Error(r.err || r.error?.message || 'failed'); if (okMsg) toast(r?.demo ? okMsg + ' (sample mode: nothing changed)' : okMsg); return r; }
  catch (e) { toast(e.message, 'bad', 7000); }
  finally { btn.classList.remove('busy'); btn.disabled = false; }
}
function copyText(text, btn) {
  const done = () => { toast('Copied'); if (btn) { btn.textContent = 'Copied'; setTimeout(() => btn.textContent = 'Copy', 1500); } };
  try { navigator.clipboard.writeText(text).then(done, () => fallback()); } catch { fallback(); }
  function fallback() { const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); done(); } catch { toast('Select the text and copy it', 'warn'); } ta.remove(); }
}

/* ---------------- markdown (tiny, for reports) ---------------- */
function md(src) {
  const lines = String(src || '').split('\n'); let out = '', inList = false;
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>');
  for (const l of lines) {
    if (/^\s*[-*] /.test(l)) { if (!inList) { out += '<ul>'; inList = true; } out += `<li>${inline(l.replace(/^\s*[-*] /, ''))}</li>`; continue; }
    if (inList) { out += '</ul>'; inList = false; }
    const h = l.match(/^(#{1,3}) (.*)/); if (h) { out += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`; continue; }
    if (l.trim()) out += `<p>${inline(l)}</p>`;
  }
  if (inList) out += '</ul>';
  return out;
}

/* ---------------- live stats ---------------- */
function startStats() {
  if (S.demoOnly) return startDemoStats();
  if (S.sse) return;
  const live = $('#sideLive');
  api('/stats/history').then(h => { S.hist = h.history || []; S.machine = h.machine; if (h.latest?.t) onStat(h.latest); }).catch(() => {});
  const es = new EventSource('/api/stats/stream'); S.sse = es;
  es.onopen = () => { live.className = 'bar__live on'; $('#sideLiveText').textContent = 'live'; };
  es.onerror = () => { live.className = 'bar__live off'; $('#sideLiveText').textContent = 'reconnecting'; };
  es.onmessage = e => { try { onStat(JSON.parse(e.data)); } catch {} };
}
function startDemoStats() {
  if (S.demoTimer) return;
  const live = $('#sideLive'); live.className = 'bar__live on'; $('#sideLiveText').textContent = 'preview';
  S.machine = { hostname: 'arise-server', os: 'Linux 6.8 (Ubuntu 24.04)', cpu_model: 'Intel Core i5-6500 @ 3.20GHz', cpu_count: 4, ram_total: 16e9, ram_total_h: '14.9 GB' };
  let t = Math.floor(Date.now() / 1000), base = 22, rx = 1.2e6, up = 14 * 86400 + 3 * 3600;
  const tick = () => {
    base = Math.max(4, Math.min(92, base + (Math.random() - 0.5) * 14)); rx = Math.max(2e5, rx + (Math.random() - 0.5) * 6e5); t++; up++;
    onStat({ t, cpu: +base.toFixed(1), cores: [0,1,2,3].map(() => Math.max(0, Math.min(100, base + (Math.random() - 0.5) * 40))), cpu_count: 4, temp: 46 + base / 8,
      ram: { total: 16e9, used: 5.8e9 + base * 2e7, pct: +(36 + base / 8).toFixed(1) }, swap: { total: 4e9, used: 1.2e8, pct: 3 },
      net: { rx: Math.round(rx), tx: Math.round(rx / 4) }, disk_io: { read: Math.round(rx / 3), write: Math.round(rx / 6) }, load: [0.42, 0.58, 0.61], uptime: up,
      disks: [{ mount: '/', fs: 'ext4', total: 2.4e11, used: 7.1e10, free: 1.69e11, pct: 30 }, { mount: '/srv/arise', fs: 'ext4', total: 9.6e11, used: 2.6e11, free: 7e11, pct: 27 }, { mount: '/mnt/synology', fs: 'cifs', total: 1.6e13, used: 4.9e12, free: 1.11e13, pct: 31 }] });
  };
  for (let i = 0; i < 60; i++) tick();
  S.demoTimer = setInterval(tick, 1000);
}
function onStat(s) {
  S.stats = s; S.hist.push({ t: s.t, cpu: s.cpu, ram: s.ram?.pct, net: s.net, disk_io: s.disk_io }); if (S.hist.length > 60) S.hist.shift();
  const set = (id, v) => { const e = $(id); if (e) e.textContent = v; };  // the bar is gone on the login screen
  set('#miniCpu', s.cpu != null ? s.cpu.toFixed(0) + '%' : '–'); set('#miniRam', s.ram ? s.ram.pct.toFixed(0) + '%' : '–'); set('#miniUp', fmtUp(s.uptime));
  if (S.wins.overview && !S.wins.overview.min) paintLive(s);
  paintWidgetLive(s);
}
function spark(id, series, color) {
  const el = document.getElementById(id); if (!el) return;
  const w = 300, h = 46, n = Math.max(series.length, 2), max = Math.max(1, ...series.map(v => v || 0));
  const pts = series.map((v, i) => `${(i / (n - 1) * w).toFixed(1)},${(h - (v || 0) / max * (h - 4) - 2).toFixed(1)}`);
  el.setAttribute('viewBox', `0 0 ${w} ${h}`); el.setAttribute('preserveAspectRatio', 'none');
  el.innerHTML = `<defs><linearGradient id="g${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".35"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
    <polygon points="0,${h} ${pts.join(' ')} ${w},${h}" fill="url(#g${id})"/><polyline points="${pts.join(' ')}" fill="none" stroke="${color}" stroke-width="1.8" vector-effect="non-scaling-stroke"/>`;
}
function paintLive(s) {
  const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
  if (!document.getElementById('lvCpu')) return;
  set('lvCpu', s.cpu.toFixed(0)); set('lvRam', fmtB(s.ram.used)); set('lvRamPct', s.ram.pct.toFixed(0) + '%'); set('lvRx', fmtRate(s.net?.rx)); set('lvTx', fmtRate(s.net?.tx));
  set('lvLoad', (s.load || []).map(x => x.toFixed(2)).join(' · ')); set('lvTemp', s.temp ? s.temp.toFixed(0) + '°C' : '—'); set('lvUp', fmtUp(s.uptime));
  set('lvRd', fmtRate(s.disk_io?.read)); set('lvWr', fmtRate(s.disk_io?.write));
  const m = $('#lvCpuMeter i'); if (m) m.style.width = s.cpu + '%';
  const r = $('#lvRamMeter i'); if (r) r.style.width = s.ram.pct + '%';
  const cores = $('#lvCores'); if (cores && s.cores) { if (cores.children.length !== s.cores.length) cores.innerHTML = s.cores.map(() => '<i></i>').join(''); s.cores.forEach((c, i) => cores.children[i].style.height = Math.max(2, c) + '%'); }
  spark('spCpu', S.hist.map(x => x.cpu), '#D6222D'); spark('spRam', S.hist.map(x => x.ram), '#E0A32E'); spark('spNet', S.hist.map(x => (x.net?.rx || 0) + (x.net?.tx || 0)), '#5CA8E0');
  const dk = $('#lvDisks'); if (dk && s.disks && (!dk.dataset.t || Date.now() - +dk.dataset.t > 10000)) { dk.dataset.t = Date.now(); dk.innerHTML = s.disks.map(d => `<div class="stat" style="margin-bottom:12px"><div class="row row--between"><span class="mono" style="font-size:13px">${esc(d.mount)} <span style="color:var(--muted)">${esc(d.fs)}</span></span><span style="font-size:12.5px;color:var(--text2)">${fmtB(d.used)} of ${fmtB(d.total)}</span></div><div class="meter ${d.pct > 90 ? '' : d.pct > 75 ? 'meter--warn' : 'meter--ok'}"><i style="width:${d.pct}%"></i></div></div>`).join(''); }
}
function paintWidgetLive(s) {
  const c = $('#wgCpu'); if (!c) return;
  c.textContent = s.cpu.toFixed(0) + '%'; $('#wgCpuM').style.width = s.cpu + '%';
  $('#wgRam').textContent = fmtB(s.ram.used); $('#wgRamM').style.width = s.ram.pct + '%';
  $('#wgNet').textContent = '↓ ' + fmtRate(s.net?.rx) + '  ↑ ' + fmtRate(s.net?.tx);
  spark('wgSpark', S.hist.map(x => x.cpu), '#D6222D');
}
/* ---------------- views carried over from v0.1 (sidebar edition) ---------------- */
const V = {};

V.overview = async () => {
  const o = await api('/overview');
  if (o.demo) { S.demo = true; $('#demoBadge').hidden = false; if (!S.demoOnly) $('#demoBadge').textContent = 'Sample data'; }
  const a = o.automator || {}, b = o.backup || {}, n = o.nas || {}, c = o.counts || {};
  const att = (o.attention || []);
  return `
  <div class="grid fade">
    <div class="c12 panel ${att.some(x => x.level === 'bad') ? 'panel--bad' : att.length ? 'panel--warn' : 'panel--ok'}">
      <div class="panel__hd"><h3>${att.length ? 'Needs you' : 'All clear'}</h3><span class="sub">${esc(o.hostname)} · ${esc(o.realm || 'no domain')} · profile ${esc(o.profile)}</span></div>
      ${att.length ? `<div class="att">${att.map(x => `<div class="att__i ${x.level}">${esc(x.text)}</div>`).join('')}</div>` : `<div class="att"><div class="att__i ok">Every service is up, the last automator run was clean, the last backups succeeded and the Synology is mounted.</div></div>`}
    </div>

    <div class="c3 panel"><div class="stat"><span class="stat__l">CPU</span><span class="stat__v"><span id="lvCpu">–</span><small>%</small></span></div><div class="cores" id="lvCores"></div><div class="meter" id="lvCpuMeter"><i></i></div><svg class="spark" id="spCpu"></svg><div class="stat__n">load <span id="lvLoad">—</span> · <span id="lvTemp">—</span></div></div>
    <div class="c3 panel"><div class="stat"><span class="stat__l">Memory</span><span class="stat__v" id="lvRam">–</span><span class="stat__n"><span id="lvRamPct">—</span> of ${esc(S.machine?.ram_total_h || o.machine?.ram_total_h || '')}</span></div><div class="meter meter--warn" id="lvRamMeter"><i></i></div><svg class="spark" id="spRam"></svg></div>
    <div class="c3 panel"><div class="stat"><span class="stat__l">Network</span><span class="stat__v" style="font-size:22px">↓ <span id="lvRx">–</span></span><span class="stat__n">↑ <span id="lvTx">–</span></span></div><svg class="spark" id="spNet"></svg><div class="stat__n">disk ↓ <span id="lvRd">—</span> · ↑ <span id="lvWr">—</span></div></div>
    <div class="c3 panel"><div class="stat"><span class="stat__l">Uptime</span><span class="stat__v" id="lvUp">${fmtUp(S.stats?.uptime)}</span><span class="stat__n">${esc(o.machine?.cpu_model || '')}<br>${esc(o.machine?.os || '')} · ${o.machine?.cpu_count || '?'} cores</span></div></div>

    <div class="c4 panel"><div class="panel__hd"><h3>Directory</h3><span class="pill ${o.directory_ok ? 'ok' : 'bad'}">${o.directory_ok ? 'online' : 'down'}</span></div>
      <div class="kv"><dt>Realm</dt><dd>${esc(o.realm)}</dd><dt>Users</dt><dd>${c.users}</dd><dt>Groups</dt><dd>${c.groups}</dd><dt>Computers</dt><dd>${c.computers}</dd><dt>Shares</dt><dd>${c.shares}</dd></div>
      <div class="row" style="margin-top:14px"><a class="btn btn--sm" data-open="directory">Manage</a></div></div>
    <div class="c4 panel"><div class="panel__hd"><h3>Automator</h3><span class="pill ${a.last_ok === false ? 'bad' : a.last_ok ? 'ok' : ''}">${a.last_ok === false ? 'failures' : a.last_ok ? 'clean' : 'no run yet'}</span></div>
      <div class="kv"><dt>Last run</dt><dd>${fmtT(a.last_run)} <span style="color:var(--muted)">(${ago(a.last_run)})</span></dd><dt>Next</dt><dd>${fmtT(a.next_run)}</dd><dt>Quota</dt><dd>${fmtN(a.quota_today)} of ${fmtN(a.quota_daily)} units</dd><dt>Token</dt><dd>${a.token_ok ? `ok${a.token_days_left != null ? ` · ~${a.token_days_left} d left` : ''}` : '<span style="color:var(--redL)">missing</span>'}</dd><dt>Holds</dt><dd>${a.holds ?? '—'} videos</dd></div>
      <div class="meter ${pct(a.quota_today, a.quota_daily) > 75 ? 'meter--warn' : 'meter--ok'}"><i style="width:${pct(a.quota_today, a.quota_daily)}%"></i></div>
      <div class="row" style="margin-top:14px"><a class="btn btn--sm" data-open="automator">Open</a></div></div>
    <div class="c4 panel"><div class="panel__hd"><h3>Backups</h3><span class="pill ${b.failed_recent ? 'bad' : b.last ? 'ok' : ''}">${b.failed_recent ? `${b.failed_recent} failed` : b.last ? 'healthy' : 'none yet'}</span></div>
      <div class="kv"><dt>Last</dt><dd>${b.last ? `${esc(b.last.name)} · ${fmtT(b.last.started)} · ${b.last.ok ? 'ok' : 'failed'}` : '—'}</dd><dt>Jobs</dt><dd>${c.backups}</dd><dt>Running</dt><dd>${(b.running || []).length ? b.running.map(r => esc(r.job)).join(', ') : 'none'}</dd><dt>Synology</dt><dd>${n.mounted ? `mounted · ${fmtB(n.free)} free` : '<span style="color:var(--warn)">not mounted</span>'}</dd><dt>Apps</dt><dd>${c.apps_running} of ${c.apps} running</dd></div>
      <div class="row" style="margin-top:14px"><a class="btn btn--sm" data-open="backups">History</a></div></div>

    <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Disks</h3><span class="sub">refreshes every 10 s</span></div><div id="lvDisks"></div></div>
    <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Tonight</h3><span class="sub">America/Chicago</span></div>
      <div class="kv"><dt>02:00</dt><dd>YouTube quota resets (midnight Pacific)</dd><dt>02:05</dt><dd>arise-automator.timer runs arise_daily.py from the worklist</dd><dt>03:00</dt><dd>arise-backup.timer: restic snapshots to the Synology, then forget/prune</dd><dt>04:00</dt><dd>arise-mirror.timer refreshes the GitHub mirror</dd></div>
      <p class="note" style="margin-top:14px">A missed night is skipped, not lost: every job is resumable. If the box was off, the backup and mirror timers catch up when it next boots; the 02:05 automator does not, on purpose.</p></div>
  </div>`;
};

V.directory = async () => {
  const [st, us, gs, cs, tf, sh] = await Promise.all([api('/directory/status'), api('/directory/users'), api('/directory/groups'), api('/directory/computers'), api('/directory/2fa').catch(() => ({ users: [] })), api('/shares').catch(() => ({ shares: [] }))]);
  const users = us.users || [], groups = gs.groups || [], comps = cs.computers || []; const twofaOn = new Set(tf.users || []);
  S.dirGroups = groups.map(g => g.name); S.dirUsers = users.map(u => u.name);
  const kind = k => ({ mac: '', windows: '⊞', nas: '▤', pc: '▣' })[k] || '▣';
  return `
  <div class="fade">
    <div class="grid" style="margin-bottom:14px">
      <div class="c3 panel ${st.ldap_ok ? 'panel--ok' : 'panel--bad'}"><div class="stat"><span class="stat__l">Domain</span><span class="stat__v" style="font-size:22px">${esc(st.netbios)}</span><span class="stat__n">${esc(st.realm)}<br>${esc(st.dc || '')}</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Health</span><div class="row" style="margin-top:6px"><span class="pill ${st.ldap_ok ? 'ok' : 'bad'}">LDAP</span><span class="pill ${st.kerberos_ok ? 'ok' : 'bad'}">Kerberos</span><span class="pill ${st.dns_ok ? 'ok' : 'bad'}">DNS</span></div><span class="stat__n">forest level ${esc(st.forest_level || '—')}</span>${st.error ? `<span class="stat__n" style="color:var(--redL)">${esc(st.error)}</span>` : ''}</div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Accounts</span><span class="stat__v">${users.length}<small>users</small></span><span class="stat__n">${groups.length} groups · ${comps.length} computers</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Join a Mac</span><span class="stat__n" style="margin-top:4px">Open <a href="#" data-open="macs" style="color:var(--redL)">Macs</a> → Enrol a Mac, and paste the one line into Terminal on that Mac. Church Macs only; steps in docs/MACS.md.</span></div></div>
    </div>
    <div class="tabs" id="dirTabs"><button class="active" data-t="users">Users</button><button data-t="groups">Groups</button><button data-t="shares">Shares</button><button data-t="computers">Computers</button></div>
    <div data-tab="shares" hidden>${sharesHtml(sh.shares || [])}</div>
    <div data-tab="users">
      <div class="toolbar"><input class="search" placeholder="Find a user" id="uq"><span class="spacer"></span><button class="btn btn--ghost btn--sm" id="importPeople">Import a people list</button><button class="btn btn--sm" id="addUser">+ New user</button></div>
      <div class="panel panel--flat tbl-wrap"><table class="tbl" id="uTable"><thead><tr><th>User</th><th>Name</th><th>Groups</th><th>Last login</th><th>Home</th><th></th></tr></thead><tbody>
      ${users.map(u => `<tr data-q="${esc((u.name + ' ' + u.display).toLowerCase())}"><td><b>${esc(u.name)}</b> ${u.enabled ? '' : '<span class="pill warn">disabled</span>'}${twofaOn.has(u.name) ? ' <span class="pill info" title="Two-step sign-in is on">two-step</span>' : ''}${u.must_change ? ' <span class="pill warn" title="A temporary password: they choose their own at the next login">new password due</span>' : ''}</td><td>${esc(u.full_name || u.display)}</td><td>${(u.groups || []).map(g => `<span class="tag">${esc(g)}</span>`).join('')}</td><td class="dim">${u.last_logon ? fmtT(u.last_logon) : 'never'}</td><td class="mono dim" style="font-size:12px">${esc(u.home || '')}</td>
        <td class="acts"><button class="btn btn--ghost btn--xs" data-prof="${esc(u.name)}">Profile</button><button class="btn btn--ghost btn--xs" data-pw="${esc(u.name)}">Password</button><button class="btn btn--ghost btn--xs" data-2fa="${esc(u.name)}" data-on="${twofaOn.has(u.name) ? 1 : 0}">${twofaOn.has(u.name) ? 'Two-step off' : 'Two-step on'}</button><button class="btn btn--ghost btn--xs" data-tog="${esc(u.name)}" data-en="${u.enabled ? 0 : 1}">${u.enabled ? 'Disable' : 'Enable'}</button><button class="btn btn--danger btn--xs" data-del="${esc(u.name)}">Delete</button></td></tr>`).join('') || '<tr><td colspan="6" class="empty">No users yet</td></tr>'}
      </tbody></table></div>
    </div>
    <div data-tab="groups" hidden>
      <div class="toolbar"><span class="spacer"></span><button class="btn btn--sm" id="addGroup">+ New group</button></div>
      <div class="cards">${groups.map(g => `<div class="card"><h3>${esc(g.name)}</h3><p>${esc(g.description || '')}<br><span style="color:var(--muted)">${g.members.length} member${g.members.length === 1 ? '' : 's'}</span></p><div>${g.members.map(m => `<span class="tag tag--rm">${esc(m)}<button class="tag__x" data-rmm="${esc(g.name)}" data-u="${esc(m)}" aria-label="Take ${esc(m)} out of ${esc(g.name)}" title="Take ${esc(m)} out of ${esc(g.name)}">×</button></span>`).join('') || '<span class="tag" style="opacity:.5">empty</span>'}</div><div class="row"><button class="btn btn--ghost btn--xs" data-addm="${esc(g.name)}">+ Add member</button></div></div>`).join('')}</div>
    </div>
    <div data-tab="computers" hidden>
      <div class="panel panel--flat tbl-wrap"><table class="tbl"><thead><tr><th>Computer</th><th>Type</th><th>OS</th><th>IP</th><th>Last seen</th></tr></thead><tbody>
      ${comps.map(c => `<tr><td><b>${esc(c.name)}</b></td><td>${kind(c.kind)} ${esc(c.kind)}</td><td>${esc(c.os || '—')}</td><td class="mono dim">${esc(c.ip || '—')}</td><td class="dim">${c.last_seen ? fmtT(c.last_seen) : '—'}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">Nothing has joined the domain yet</td></tr>'}
      </tbody></table></div>
      <p class="note" style="margin-top:14px">Windows: Settings → System → About → <b>Domain or workgroup</b> → join <b>${esc(st.realm)}</b>. Synology: Control Panel → Domain/LDAP → Join Domain (see docs/SYNOLOGY.md). Macs: the bind script above.</p>
    </div>
  </div>`;
};
V.directory.after = root => {
  $$('a[data-open]', root).forEach(a => a.onclick = e => { e.preventDefault(); openApp(a.dataset.open); });
  tabs('#dirTabs', 'directory');
  sharesAfter(root, 'directory');
  $('#uq').oninput = e => { const q = e.target.value.toLowerCase(); $$('#uTable tbody tr').forEach(tr => tr.hidden = q && !(tr.dataset.q || '').includes(q)); };
  $('#addUser').onclick = () => modal(`<h2>New user</h2>
    <div class="row" style="gap:10px;align-items:flex-start"><div class="field" style="flex:0 0 130px"><label>Title</label><input id="nuTitle" placeholder="Pastor" autocomplete="off"><span class="hint">Apostle, Pastor, Minister… or blank.</span></div>
    <div class="field" style="flex:1"><label>Full name</label><input id="nuDisp" placeholder="Shown on the Mac login" autocomplete="off"></div></div>
    <div class="field"><label>User name</label><input id="nuName" placeholder="first.last" autocomplete="off" autocapitalize="none" spellcheck="false"><span class="hint">first.last, lowercase. This is what they type on the Mac and here.</span></div>
    <div class="field"><label>Password</label><input id="nuPw" type="password" autocomplete="new-password"><label class="chk" style="margin-top:8px"><input type="checkbox" id="nuTemp" checked> Temporary: they choose their own at their first login, on their Mac or here</label></div>
    <div class="field"><label>Groups</label><div class="checks" id="nuGroups">${(S.dirGroups || []).map(g => `<label><input type="checkbox" value="${esc(g)}"> ${esc(g)}</label>`).join('')}</div><span class="hint">The groups decide which shares they see. Domain Admins makes them an administrator.</span></div>
    <div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="nuGo">Create</button></div>`, m => {
    const disp = $('#nuDisp', m), nm = $('#nuName', m);
    disp.oninput = () => { if (nm.dataset.typed) return; nm.value = disp.value.trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9 .-]/g, '').trim().split(/\s+/).filter(Boolean).join('.'); };
    nm.oninput = () => { nm.dataset.typed = '1'; };
    $('#nuGo', m).onclick = async e => { const r = await act(e.target, () => api('/directory/users', { method: 'POST', body: { name: nm.value.trim(), display: disp.value.trim(), title: $('#nuTitle', m).value.trim(), temporary: $('#nuTemp', m).checked, password: $('#nuPw', m).value, groups: $$('#nuGroups input:checked', m).map(c => c.value) } }), 'User created'); if (r && r.ok !== false) { m.close(); rerender('directory'); } };
    disp.focus();
  });
  $$('[data-rmm]', root).forEach(b => b.onclick = () => confirmType(`Take ${b.dataset.u} out of ${b.dataset.rmm}`, b.dataset.u, `They lose what the <b>${esc(b.dataset.rmm)}</b> group gives: its shares, and the administrator's rights if it is Domain Admins. Their account and files stay.`, async () => { const r = await api(`/directory/groups/${encodeURIComponent(b.dataset.rmm)}/members/${encodeURIComponent(b.dataset.u)}`, { method: 'DELETE' }); if (r.ok === false) throw new Error(r.err); toast(`${b.dataset.u} is out of ${b.dataset.rmm}`); rerender('directory'); }));
  $$('[data-pw]').forEach(b => b.onclick = () => modal(`<h2>Reset password</h2><p class="note" style="margin-bottom:14px">For <b>${esc(b.dataset.pw)}</b>. Their Mac asks for the new one at next login; the cached mobile account updates then. They can also reset it themselves: "Forgot your password?" sends a link to the personal email on their profile.</p><div class="field"><label>New password</label><input id="rpPw" type="password"><label class="chk" style="margin-top:8px"><input type="checkbox" id="rpTemp" checked> Temporary: they choose their own at the next login</label></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="rpGo">Set</button></div>`, m => { $('#rpGo', m).onclick = async e => { const r = await act(e.target, () => api(`/directory/users/${encodeURIComponent(b.dataset.pw)}/reset-password`, { method: 'POST', body: { password: $('#rpPw', m).value, temporary: $('#rpTemp', m).checked } }), 'Password set'); if (r && r.ok !== false) m.close(); }; }));
  $$('[data-tog]').forEach(b => b.onclick = async () => { const r = await act(b, () => api(`/directory/users/${encodeURIComponent(b.dataset.tog)}/${b.dataset.en === '1' ? 'enable' : 'disable'}`, { method: 'POST' }), b.dataset.en === '1' ? 'Enabled' : 'Disabled'); if (r && r.ok !== false) rerender('directory'); });
  $$('[data-del]').forEach(b => b.onclick = () => confirmType('Delete user', b.dataset.del, `This removes the account from the domain. <b>The home folder stays on disk</b> - nothing in it is deleted. Deleting is your click, not the server's.`, async () => { const r = await withReauth(() => api(`/directory/users/${encodeURIComponent(b.dataset.del)}`, { method: 'DELETE', body: { confirm: b.dataset.del } })); if (r.ok === false) throw new Error(r.err); toast('User deleted'); rerender('directory'); }));
  $('#addGroup').onclick = () => modal(`<h2>New group</h2><div class="field"><label>Name</label><input id="ngName" placeholder="Praise-Team"></div><div class="field"><label>Description</label><input id="ngDesc"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="ngGo">Create</button></div>`, m => { $('#ngGo', m).onclick = async e => { const r = await act(e.target, () => api('/directory/groups', { method: 'POST', body: { name: $('#ngName', m).value.trim(), description: $('#ngDesc', m).value.trim() } }), 'Group created'); if (r && r.ok !== false) { m.close(); rerender('directory'); } }; });
  $$('[data-addm]').forEach(b => b.onclick = () => modal(`<h2>Add to ${esc(b.dataset.addm)}</h2><div class="field"><label>User name</label><input id="amUser" list="amList" autocomplete="off" placeholder="first.last"><datalist id="amList">${(S.dirUsers || []).map(u => `<option value="${esc(u)}">`).join('')}</datalist></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="amGo">Add</button></div>`, m => { $('#amUser', m).focus(); $('#amGo', m).onclick = async e => { const r = await act(e.target, () => api(`/directory/groups/${encodeURIComponent(b.dataset.addm)}/members`, { method: 'POST', body: { user: $('#amUser', m).value.trim() } }), 'Added'); if (r && r.ok !== false) { m.close(); rerender('directory'); } }; }));
};

// The shares: a tab in Directory (and the hidden "shares" window Settings can open).
V.shares = async () => `<div class="fade">${sharesHtml((await api('/shares')).shares || [])}</div>`;
V.shares.after = root => sharesAfter(root, 'shares');
function sharesHtml(shares) {
  return `
    <div class="toolbar"><span class="note" style="flex:1 1 auto">On a Mac: Finder → Go → Connect to Server → <b>smb://arise-server</b>. On Windows: <b>\\\\arise-server</b>. Sign in with the domain account.</span><button class="btn btn--sm" id="addShare">+ New share</button></div>
    <div class="cards">${shares.map(s => `<div class="card"><div class="row row--between"><h3>${esc(s.name)}</h3>${s.mac ? '<span class="pill info">Mac-ready</span>' : ''}</div><p>${esc(s.comment || '')}<br><span class="mono" style="font-size:12px;color:var(--muted)">${esc(s.path)}</span></p>
      <div class="kv"><dt>Used</dt><dd>${s.used != null ? fmtB(s.used) : '—'}</dd><dt>Access</dt><dd>${s.writable ? 'read & write' : 'read only'}${s.browseable ? '' : ' · hidden'}</dd></div>
      ${['homes', 'sysvol', 'netlogon'].includes(s.name) ? '' : `<div class="row"><button class="btn btn--danger btn--xs" data-rm="${esc(s.name)}">Remove share</button></div>`}</div>`).join('') || '<div class="empty">No shares defined</div>'}</div>
    <div class="grid" style="margin-top:14px"><div class="c6 panel panel--flat"><div class="panel__hd"><h3>How homes work</h3></div><p style="font-size:13.5px;color:var(--text2)">Every domain user gets <code>homes/&lt;user&gt;</code>, visible to them alone. A Mac with a mobile account keeps a cached copy and syncs Desktop and Documents to it. Move an old Mac's data in with <code>mac/migrate-mac-user.sh</code>.</p></div>
    <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Where the big files go</h3></div><p style="font-size:13.5px;color:var(--text2)">Service recordings, graphics and the podcast masters belong on the Synology's <code>media</code> share: four drives with redundancy. The old PC's single disk holds the directory, the automator and the apps, and is backed up to the NAS nightly.</p></div></div>`;
}
function sharesAfter(root, view) {
  const add = $('#addShare', root); if (add) add.onclick = () => modal(`<h2>New share</h2><div class="field"><label>Name</label><input id="nsName" placeholder="graphics" autocomplete="off"></div><div class="field"><label>Folder on the server</label><input id="nsPath" placeholder="/srv/arise/shares/graphics"><span class="hint">Filled in from the name; change it to put the share somewhere else (the Synology is /mnt/synology/…).</span></div><div class="field"><label>Who can use it</label><select id="nsGroup"><option>Domain Users</option>${(S.dirGroups || []).filter(g => g !== 'Domain Users').map(g => `<option>${esc(g)}</option>`).join('')}</select><span class="hint">"Domain Users" is everyone who signs in.</span></div><div class="field"><label>Description</label><input id="nsComment"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="nsGo">Create</button></div>`, m => {
    const nm = $('#nsName', m), pth = $('#nsPath', m); nm.oninput = () => { if (!pth.dataset.typed) pth.value = nm.value.trim() ? '/srv/arise/shares/' + nm.value.trim().toLowerCase().replace(/\s+/g, '-') : ''; }; pth.oninput = () => { pth.dataset.typed = '1'; }; nm.focus();
    $('#nsGo', m).onclick = async e => { const r = await act(e.target, () => api('/shares', { method: 'POST', body: { name: nm.value.trim(), path: pth.value.trim(), group: $('#nsGroup', m).value.trim(), comment: $('#nsComment', m).value.trim(), mac: true } }), 'Share created'); if (r && r.ok !== false) { m.close(); rerender(view); } }; });
  $$('[data-rm]', root).forEach(b => b.onclick = () => confirmType('Remove share', b.dataset.rm, 'The share stops being visible on the network. <b>The folder and its files stay on disk.</b>', async () => { const r = await api(`/shares/${encodeURIComponent(b.dataset.rm)}`, { method: 'DELETE', body: { confirm: b.dataset.rm } }); if (r.ok === false) throw new Error(r.err); toast('Share removed'); rerender(view); }));
}

V.backups = async () => {
  const [jobs, hist, repo, snaps] = await Promise.all([api('/backups/jobs'), api('/backups/history?limit=120'), api('/backups/repo'), api('/backups/snapshots?limit=40')]);
  let off = null; try { off = await api('/backups/offsite'); } catch {}
  const offTone = off ? ({ copy: 'ok', same: 'warn', off: 'warn' }[off.plan?.action] || 'bad') : 'warn';
  const offLast = off?.last;
  const offsite = off ? `<div class="panel panel--flat" style="margin-bottom:14px"><div class="panel__hd"><h3>Off-site copy · Arise-Home</h3><span class="sub">every snapshot but the raw recordings, after the nightly run</span></div>
      <p style="margin:0 0 6px"><span class="pill ${offTone}">${esc({ copy: 'copies tonight', same: 'same place', off: 'off', unreachable: 'not reachable', none: 'nothing ran' }[off.plan?.action] || off.plan?.action || '?')}</span> ${esc(off.plan?.why || '')}</p>
      <p class="note" style="margin:0">${offLast ? `Last: ${esc(fmtT(offLast.started))}, ${offLast.ok ? (offLast.copied != null ? offLast.copied + ' snapshots checked' : 'ok') : '<span style="color:var(--bad)">' + esc(offLast.error || 'failed') + '</span>'}${offLast.warning ? ' · ' + esc(offLast.warning) : ''}` : 'No off-site run yet.'}</p></div>` : '';
  const rows = hist.rows || [], running = hist.running || [];
  const lastOf = id => rows.find(r => r.job === id);
  const okRate = rows.slice(0, 50).filter(r => r.ok).length;
  return `<div class="fade">
    <div class="grid" style="margin-bottom:14px">
      <div class="c3 panel ${repo.ok ? 'panel--ok' : 'panel--bad'}"><div class="stat"><span class="stat__l">Repository</span><span class="stat__v">${fmtN(repo.snapshots)}<small>snapshots</small></span><span class="stat__n mono" style="font-size:12px">${esc(repo.repo)}</span>${repo.error ? `<span class="stat__n" style="color:var(--redL)">${esc(repo.error)}</span>` : ''}</div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Stored</span><span class="stat__v" style="font-size:26px">${fmtB(repo.total_size)}</span><span class="stat__n">${repo.raw_size ? `${fmtB(repo.raw_size)} before deduplication` : 'deduplicated and encrypted'}</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Last 50 runs</span><span class="stat__v">${okRate}<small>/ ${Math.min(rows.length, 50)} ok</small></span><span class="stat__n">keep ${repo.keep?.daily} daily · ${repo.keep?.weekly} weekly · ${repo.keep?.monthly} monthly</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Integrity</span><span class="stat__v" style="font-size:22px">${repo.last_check ? ago(repo.last_check) : 'never'}</span><span class="stat__n">last <code>restic check</code></span></div><div class="row" style="margin-top:10px"><button class="btn btn--ghost btn--xs" id="bkCheck">Check now</button><button class="btn btn--ghost btn--xs" id="bkMirror">Refresh GitHub mirror</button></div></div>
    </div>
    ${offsite}<div class="panel panel--flat" style="margin-bottom:14px"><div class="panel__hd"><h3>Jobs</h3><span class="sub">${esc(jobs.file || '')}</span></div><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Job</th><th>What</th><th>Last run</th><th>Result</th><th class="num">Added</th><th></th></tr></thead><tbody>
    ${(jobs.jobs || []).map(j => { const l = lastOf(j.id), run = running.find(r => r.job === j.id); return `<tr><td><b>${esc(j.name || j.id)}</b><br><span class="dim" style="font-size:11px">${(j.tags || []).map(t => `<span class="tag">${esc(t)}</span>`).join('')}</span></td><td class="mono dim" style="font-size:12px">${(j.paths || []).map(esc).join('<br>')}</td><td class="dim">${l ? fmtT(l.started) : 'never'}</td><td>${run ? '<span class="pill info">running</span>' : l ? `<span class="pill ${l.ok ? 'ok' : 'bad'}">${l.ok ? 'ok' : 'failed'}</span>` : '<span class="pill">—</span>'}</td><td class="num">${l?.ok ? fmtB(l.bytes_added) : '—'}</td><td class="acts"><button class="btn btn--ghost btn--xs" data-run="${esc(j.id)}" ${run ? 'disabled' : ''}>Run now</button></td></tr>`; }).join('')}
    </tbody></table></div></div>
    <div class="tabs" id="bkTabs"><button class="active" data-t="hist">History</button><button data-t="snaps">Snapshots</button><button data-t="restore">Restore</button>${S.role === 'admin' ? '<button data-t="repos">Repos</button>' : ''}</div>
    ${S.role === 'admin' ? `<div data-tab="repos" hidden class="panel panel--flat" id="bkRepos"><div class="empty">Loading the repos…</div></div>` : ''}
    <div data-tab="hist" class="panel panel--flat tbl-wrap"><table class="tbl"><thead><tr><th>When</th><th>Job</th><th>Result</th><th class="num">Added</th><th class="num">New files</th><th>Snapshot</th><th>Note</th></tr></thead><tbody>
    ${rows.map(r => `<tr><td class="dim">${fmtT(r.started)}</td><td>${esc(r.name || r.job)}</td><td><span class="pill ${r.ok ? 'ok' : 'bad'}">${r.ok ? 'ok' : 'failed'}</span></td><td class="num">${r.ok ? fmtB(r.bytes_added) : '—'}</td><td class="num">${r.ok ? fmtN(r.files_new) : '—'}</td><td class="mono dim">${esc(r.snapshot_id || '')}</td><td style="font-size:12.5px;color:${r.error ? 'var(--redL)' : 'var(--muted)'}">${esc(r.error || r.warning || '')}</td></tr>`).join('') || '<tr><td colspan="7" class="empty">No runs recorded yet. The first one happens at 03:00, or press Run now.</td></tr>'}
    </tbody></table></div>
    <div data-tab="snaps" hidden class="panel panel--flat tbl-wrap"><table class="tbl"><thead><tr><th>Snapshot</th><th>Time</th><th>Tags</th><th>Paths</th></tr></thead><tbody>
    ${(snaps.snapshots || []).map(s => `<tr><td class="mono">${esc(s.id)}</td><td class="dim">${fmtT(s.time)}</td><td>${(s.tags || []).map(t => `<span class="tag">${esc(t)}</span>`).join('')}</td><td class="mono dim" style="font-size:12px">${(s.paths || []).map(esc).join('<br>')}</td></tr>`).join('') || `<tr><td colspan="4" class="empty">${esc(snaps.error || 'No snapshots yet')}</td></tr>`}
    </tbody></table></div>
    <div data-tab="restore" hidden class="panel panel--flat"><div class="panel__hd"><h3>Restoring</h3></div><div class="md">
      ${md(`Restores are done on the server's command line on purpose - a restore overwrites, and that is your click.\n\n**One file or folder from the latest snapshot of a job:**\n\n- \`sudo arisectl backup restore latest --tag homes --path /srv/arise/homes/office/Documents --target /srv/arise/restore\`\n\n**Everything from a given snapshot:**\n\n- \`sudo arisectl backup snapshots\` to find the id, then \`sudo arisectl backup restore <id> --target /srv/arise/restore\`\n\nRestored files land under the target folder, never on top of the live ones. Copy back what you need. Full walkthroughs: docs/BACKUPS.md.`)}</div></div>
  </div>`;
};
V.backups.after = () => {
  tabs('#bkTabs', 'backups');
  $$('[data-run]').forEach(b => b.onclick = async () => { const r = await act(b, () => api(`/backups/run/${encodeURIComponent(b.dataset.run)}`, { method: 'POST' }), `Started ${b.dataset.run}; the row appears when it finishes`); if (r) setTimeout(() => rerender('backups'), 2500); });
  $('#bkCheck').onclick = e => act(e.target, () => api('/backups/check', { method: 'POST' }), 'Check started; it can take a while on a big repo');
  $('#bkMirror').onclick = e => act(e.target, () => api('/backups/mirror', { method: 'POST' }), 'Mirror refreshed');
  if ($('#bkRepos')) paintRepos();
};
// The Arise repos in /srv/arise/repos, two-way with GitHub every 15 minutes (docs/REPOS.md).
const REPO_POLICY = { all: 'two-way', branches: 'two-way, main is pull-only', none: 'pull-only' };
async function paintRepos() {
  const el = $('#bkRepos'); if (!el) return;
  const r = await api('/repos').catch(e => ({ err: e.message, repos: [] }));
  el.innerHTML = `<div class="panel__hd"><h3>Repos</h3><span class="sub mono">${esc(r.root || '/srv/arise/repos')}</span><button class="btn btn--ghost btn--xs" id="repoSync" style="margin-left:auto">Sync now</button></div>
    <p class="note" style="margin:0 0 10px">Every 15 minutes each repo pulls from GitHub and pushes what was committed here. A commit is checked for passwords and tokens before it leaves. Last sync: <b>${r.last ? ago(r.last) : 'not yet'}</b>.${r.token === false ? ' <span style="color:var(--redL)">No GitHub token is set: <code>sudo arisectl repos setup</code>.</span>' : ''}${r.err ? ` <span style="color:var(--redL)">${esc(r.err)}</span>` : ''}</p>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Repo</th><th>Direction</th><th>Branch</th><th class="num">Ahead</th><th class="num">Behind</th><th>Result</th></tr></thead><tbody>
    ${(r.repos || []).map(x => `<tr><td><b>${esc(x.name)}</b><br><small class="muted mono">${esc(x.repo)}</small></td><td>${esc(REPO_POLICY[x.policy] || x.policy || '')}</td><td class="mono">${esc(x.branch || '—')}${x.dirty ? ' <span class="tag">uncommitted</span>' : ''}</td><td class="num">${x.ahead ?? '—'}</td><td class="num">${x.behind ?? '—'}</td><td><span class="pill ${x.ok ? 'ok' : 'bad'}">${x.ok ? 'ok' : 'needs you'}</span> <small class="muted">${esc(x.why || '')}</small></td></tr>`).join('') || '<tr><td colspan="6" class="empty">No repos listed in arise.toml</td></tr>'}
    </tbody></table></div>`;
  $('#repoSync').onclick = async e => { const x = await act(e.target, () => api('/repos/sync', { method: 'POST' }), 'Sync started; the table updates when it finishes'); if (x && x.ok !== false) setTimeout(paintRepos, 4000); };
}

V.automator = async () => {
  const [a, wl, h] = await Promise.all([api('/automator'), api('/automator/worklist'), api('/automator/holds')]);
  const q = pct(a.quota_today, a.quota_daily); S.auA = a;
  return `<div class="fade">
    <div class="grid" style="margin-bottom:14px">
      <div class="c3 panel ${a.last_ok === false ? 'panel--bad' : a.last_ok ? 'panel--ok' : 'panel--warn'}"><div class="stat"><span class="stat__l">Last run</span><span class="stat__v" style="font-size:22px">${a.last_run ? ago(a.last_run) : 'never'}</span><span class="stat__n">${esc(a.last_summary || 'no report on this server yet')}</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Quota today</span><span class="stat__v">${fmtN(a.quota_today ?? 0)}<small>/ ${fmtN(a.quota_daily)}</small></span><span class="stat__n">resets ${esc(a.quota_reset || '2 AM Central')} · next run ${fmtT(a.next_run)}</span></div><div class="meter ${q > 75 ? 'meter--warn' : 'meter--ok'}"><i style="width:${q}%"></i></div></div>
      <div class="c3 panel ${!a.token_ok || a.signin?.expired ? 'panel--bad' : a.signin?.soon ? 'panel--warn' : 'panel--ok'}"><div class="stat"><span class="stat__l">Sign-in</span><span class="stat__v" style="font-size:22px">${!a.token_ok ? 'no token' : a.signin?.expired ? 'ended' : 'signed in'}</span><span class="stat__n">${esc(a.signed_in_as || '')}${a.signin?.known ? `${a.signed_in_as ? ' · ' : ''}${a.signin.expired ? 'ended' : 'ends'} ${esc(a.signin.expires_text)}` : a.signin?.testing ? `${a.signed_in_as ? ' · ' : ''}renewal date not known yet` : ''}</span>${a.token_note ? `<span class="stat__n" style="color:var(--warn)">${esc(a.token_note)}</span>` : ''}${a.signin?.testing ? '<button class="btn btn--xs" id="auRenew" type="button" style="margin-top:8px;align-self:flex-start">Renew for the week</button>' : ''}</div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Guard rails</span><span class="stat__v">${a.holds}<small>on hold</small></span><span class="stat__n">${a.rules} standing rules · ${a.worklist_enabled} of ${a.worklist_total} jobs enabled</span></div><div class="row" style="margin-top:10px"><button class="btn btn--ghost btn--xs" id="auPreview">Preview tonight</button><button class="btn btn--xs" id="auRun">Run now</button></div></div>
    </div>
    ${a.manual?.started ? `<p class="note" style="margin-bottom:14px"><b>${esc(a.manual.mode)}</b> started ${fmtT(a.manual.started)} · ${a.manual.finished ? (a.manual.ok ? 'finished ok' : `failed: ${esc(a.manual.error || 'exit ' + a.manual.code)}`) : 'still running'} · output in last-run.log</p>` : ''}
    <div class="tabs" id="auTabs"><button class="active" data-t="videos">Videos</button><button data-t="search">Search</button><button data-t="songs">Songs</button><button data-t="report">Latest report</button><button data-t="work">Worklist</button><button data-t="holds">Hold list</button><button data-t="reports">Past reports</button><button data-t="switch">Server switch</button></div>
    <div data-tab="videos" id="chVideos"><div class="empty">Loading the videos…</div></div>
    <div data-tab="search" hidden id="chSearch"></div>
    <div data-tab="songs" hidden id="chSongs"><div class="empty">Loading the songs…</div></div>
    <div data-tab="switch" hidden id="auSwitch"><div class="empty">Loading…</div></div>
    <div data-tab="report" hidden class="panel panel--flat"><div class="md">${md(a.latest_report)}</div></div>
    <div data-tab="work" hidden class="panel panel--flat tbl-wrap"><table class="tbl"><thead><tr><th>#</th><th>Job</th><th>Note</th><th class="num">Est. units</th><th>State</th></tr></thead><tbody>
      ${(wl.jobs || []).map(j => `<tr><td class="num dim">${esc(j.priority ?? '')}</td><td><b>${esc(j.id)}</b></td><td style="font-size:13px;color:var(--text2)">${esc(j.note || j.why || '')}</td><td class="num">${j.cost_estimate != null ? fmtN(j.cost_estimate) : '—'}</td><td>${j.enabled === false ? '<span class="pill warn">off</span>' : '<span class="pill ok">on</span>'}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">No worklist.json found</td></tr>'}
    </tbody></table><p class="note" style="margin-top:12px">The automator runs only what is in <code>worklist.json</code>, in priority order. To stop a job for a night set its <code>enabled</code> to false in that file - don't delete it; the note saying why it exists is worth keeping.</p></div>
    <div data-tab="holds" hidden><div class="grid"><div class="c6 panel panel--flat"><div class="panel__hd"><h3>Videos no script may write to</h3></div><table class="tbl"><tbody>${(h.videos || []).map(v => `<tr><td class="mono">${esc(v.id)}</td><td style="font-size:13px;color:var(--text2)">${esc(v.reason || '')}</td></tr>`).join('') || '<tr><td class="empty">none</td></tr>'}</tbody></table></div>
      <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Standing rules</h3></div><ul style="padding-left:18px;font-size:13.5px;color:var(--text2)">${(h.rules || []).map(r => `<li style="margin:6px 0">${esc(typeof r === 'string' ? r : JSON.stringify(r))}</li>`).join('')}</ul><p class="note" style="margin-top:12px">Edited only in <code>holds.json</code>, read on every write by <code>hold_gate.py</code>. A missing hold file refuses every write - it fails closed.</p></div></div></div>
    <div data-tab="reports" hidden class="panel panel--flat"><div class="row" style="flex-wrap:wrap;gap:8px">${(a.reports || []).map(r => `<button class="btn btn--ghost btn--xs" data-rep="${esc(r)}">${esc(r.replace('.md', ''))}</button>`).join('') || '<span class="empty" style="width:100%">no reports yet</span>'}</div><div id="repBody" class="md" style="margin-top:16px"></div></div>
  </div>`;
};
/* The weekly YouTube sign-in (Oct 29). The OAuth app stays in Testing, so Google ends the
   server's sign-in seven days after it is given. Bradly renews from the Media Mac (signed in to
   the channel's Google account), in Safari: the Google page opens in this same browser, he
   approves, copies the localhost:8765 address that fails to load and pastes it back here.
   The Media Mac is shared and a dashboard sign-in lasts a year, so this browser is signed out
   afterwards unless he unticks the box (never on the closet monitor). The token is never shown. */
function ytRenew() {
  const stepOne = r => `<h2>Renew the YouTube sign-in</h2>
    <p class="note">Do this on the <b>Media Mac</b>: it is signed in to the channel's Google account. It takes a minute.</p>
    <ol class="yt__steps">
      <li><a class="btn" id="ytGo" href="${esc(r.url)}" target="_blank" rel="noopener">Open Google's sign-in</a><span class="muted"> It opens in a new tab of this browser. Choose <b>Arise Church</b>, then Advanced → Go to … (the church's own app), then Allow.</span></li>
      <li>The new tab then tries <code>${esc(r.redirect)}</code> and <b>fails to load</b>. That is expected. Copy the whole address from that tab's address bar (click it, ⌘A, ⌘C), close the tab, and come back here.</li>
      <li><label for="ytAddr">Paste it here (⌘V)</label><input id="ytAddr" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" inputmode="url" placeholder="http://localhost:8765/?state=…&amp;code=…"></li>
    </ol>
    <label class="check" style="margin-top:6px"><input type="checkbox" id="ytOut" ${S.kiosk ? '' : 'checked'}> Sign me out of this browser when done (the Media Mac is shared)</label>
    <p class="note" id="ytMsg" style="min-height:1.2em"></p>
    <div class="acts"><button type="button" class="btn btn--ghost" data-close>Cancel</button><button class="btn" type="button" id="ytDone" disabled>Renew</button></div>
    <p class="note">The link works ten minutes and once. ${r.demo ? 'Sample: nothing goes to Google.' : 'Nothing about the sign-in itself is shown or kept anywhere but the server\'s secrets folder.'}</p>`;
  withReauth(() => api('/automator/signin/start', { method: 'POST' })).then(r => {
    if (r.ok === false) { toast(r.err, 'bad', 8000); return; }
    modal(stepOne(r), m => {
      const inp = $('#ytAddr', m), go = $('#ytDone', m), msg = $('#ytMsg', m);
      const check = () => { const v = inp.value.trim(); go.disabled = !/code=|^[\w./-]{20,}$/.test(v); msg.textContent = v && /localhost:8765/.test(v) && !/code=/.test(v) ? 'That address has no code= in it: copy it after you pressed Allow.' : ''; };
      inp.addEventListener('input', check); inp.addEventListener('paste', () => setTimeout(check, 0));
      $('#ytGo', m).addEventListener('click', () => setTimeout(() => inp.focus(), 400));
      go.onclick = async () => {
        go.disabled = true; msg.textContent = 'Checking with Google…';
        try {
          const f = await api('/automator/signin/finish', { method: 'POST', body: { address: inp.value.trim(), sign_out: $('#ytOut', m).checked } });
          if (f.ok === false) { msg.textContent = f.err; go.disabled = false; return; }
          $('#modalBody').innerHTML = `<h2>Signed in as ${esc(f.channel || 'Arise Church')}</h2>
            <p>The server's sign-in now ends <b>${esc(f.expires_text || 'in seven days')}</b>. A reminder comes Saturday evening and Sunday after the service if it is due.</p>
            ${f.signed_out ? '<p class="note">This browser is signed out of the dashboard. Your other devices stay signed in.</p>' : '<div class="acts"><button class="btn btn--ghost" type="button" id="ytLogout">Sign me out of this browser</button></div>'}
            ${f.note ? `<p class="note">${esc(f.note)}</p>` : ''}
            <div class="acts"><button class="btn" type="button" id="ytClose">Done</button></div>`;
          const close = () => { m.close(); if (f.signed_out) location.reload(); else rerender('automator'); };
          $('#ytClose').onclick = close;
          if ($('#ytLogout')) $('#ytLogout').onclick = async () => { await api('/auth/logout', { method: 'POST' }).catch(() => {}); location.reload(); };
        } catch (er) { msg.textContent = er.message; go.disabled = false; }
      };
    });
  }).catch(er => { if (er.message !== 'cancelled') toast(er.message, 'bad'); });
}
V.automator.after = () => {
  tabs('#auTabs', 'automator');
  if ($('#auRenew')) $('#auRenew').onclick = () => ytRenew();
  chVideos(); chSearch(); chSongs(); chSwitch();
  $('#auPreview').onclick = e => act(e.target, () => api('/automator/preview', { method: 'POST' }), 'Preview started: a dry run, nothing is written to YouTube');
  $('#auRun').onclick = e => modal(`<h2>Run the automator now?</h2><p class="note" style="margin-bottom:14px">This spends real quota and writes to the channel exactly as the 02:05 run would. The hold list still applies. If a chat session is also working today, remember the 10,000 units are shared.</p><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="auGo">Run</button></div>`, m => { $('#auGo', m).onclick = async ev => { const r = await act(ev.target, () => api('/automator/run', { method: 'POST' }), 'Run started; the report appears when it finishes'); if (r) { m.close(); setTimeout(() => rerender('automator'), 3000); } }; });
  $$('[data-rep]').forEach(b => b.onclick = async () => { $$('[data-rep]').forEach(x => x.classList.toggle('active', x === b)); const r = await api(`/automator/reports/${encodeURIComponent(b.dataset.rep)}`); $('#repBody').innerHTML = `<h3 style="margin:0 0 10px">${esc(b.dataset.rep.replace('.md', '').replace('_', ' · '))}</h3>` + md(r.text || '(an empty report)'); });
};

/* ---------------- the channel: every video, a search that opens on the video ----------------
   Read-only, from the archive (docs/ARCHIVE.md) and the channel snapshots in the automator repo.
   Nothing here spends quota or writes to YouTube. */
const CH = { q: '', kind: '', has: '', page: 1, sq: '', skind: 'transcript', hist: false, priv: false, open: null, at: null, from: null };
const KIND_LABEL = { service: 'Service', short: 'Short', video: 'Video' };
const dur = s => { if (s == null || s === '') return ''; s = Math.max(0, Math.round(+s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return h ? `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}` : `${m}:${String(x).padStart(2, '0')}`; };
const fmtD = d => { if (!d) return 'no date'; const t = new Date(String(d).slice(0, 10) + 'T12:00:00'); return isNaN(t) ? esc(d) : t.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }); };
const snip = s => esc(s || '').replace(/\[([^\]]{1,80})\]/g, '<mark>$1</mark>');
// "Copy clean" for StreamYard (CLAUDE.md, Oct 5): no ** and no "CCLI #123".
const cleanDesc = t => String(t || '').replace(/\*\*|__/g, '').replace(/[ \t]*\(?\bCCLI\s*(?:Song\s*)?(?:No\.?|#)\s*\d+\)?/gi, '').replace(/[ \t]+$/gm, '');
// A thumbnail that falls back (the toolkit's own file, then a plain title card) when YouTube's image cannot load.
const thumbImg = (src, title, seconds, fallback) => `<div class="vthumb"><span class="vthumb__ph">${esc(String(title || '').split(' | ')[0])}</span><img loading="lazy" alt="" src="${esc(src || '')}" data-fallback="${esc(fallback || '')}">${seconds ? `<span class="vthumb__d">${dur(seconds)}</span>` : ''}</div>`;
function wireThumbs(root) {
  $$('.vthumb img', root).forEach(img => { const fail = () => { const f = img.dataset.fallback; if (f) { img.dataset.fallback = ''; img.src = f; } else img.remove(); }; img.onerror = fail; if (img.complete && img.naturalWidth === 0 && img.getAttribute('src')) fail(); });
}
const vcard = v => `<button class="vcard" data-vid="${esc(v.id)}">${thumbImg(v.thumb, v.title || v.id, v.seconds)}<span class="vcard__b"><b>${esc(v.title || v.id)}</b><small>${fmtD(v.date)} · ${KIND_LABEL[v.kind] || 'Video'}</small><span class="vcard__p">${v.held ? '<span class="tag tag--warn">on hold</span>' : ''}${v.transcript ? '<span class="tag">transcript</span>' : ''}${v.chapters ? '<span class="tag">chapters</span>' : ''}${v.shorts ? `<span class="tag">${v.shorts} Shorts</span>` : ''}</span></span></button>`;

function chWire(root, from) {
  wireThumbs(root);
  $$('[data-vid]', root).forEach(b => b.onclick = e => { e.preventDefault(); CH.open = b.dataset.vid; CH.at = b.dataset.at != null && b.dataset.at !== '' ? +b.dataset.at : null; CH.from = from; (from === 'search' ? chSearch : chVideos)(); });
  $$('[data-doc-path]', root).forEach(b => b.onclick = () => chDoc(b.dataset.docRepo, b.dataset.docPath, b.dataset.docLine));
}

async function chVideos() {
  const el = $('#chVideos'); if (!el) return;
  if (CH.open && CH.from === 'videos') return chVideo(el, CH.open, CH.at);
  const p = new URLSearchParams({ q: CH.q, kind: CH.kind, has: CH.has, page: CH.page });
  const r = await api('/automator/videos?' + p).catch(e => ({ error: e.message, videos: [] }));
  if (!el.isConnected) return;
  const typing = document.activeElement && document.activeElement.id === 'chQ';
  el.innerHTML = `<div class="chbar"><input id="chQ" type="search" placeholder="Find a video by title or id" value="${esc(CH.q)}" autocomplete="off">
    <div class="seg" id="chKind">${[['', 'All'], ['service', 'Services'], ['short', 'Shorts'], ['video', 'Other']].map(([k, l]) => `<button data-k="${k}" class="${CH.kind === k ? 'active' : ''}">${l}</button>`).join('')}</div>
    <select id="chHas">${[['', 'Everything'], ['transcript', 'Has a transcript'], ['chapters', 'Has chapters'], ['held', 'On the hold list']].map(([k, l]) => `<option value="${k}" ${CH.has === k ? 'selected' : ''}>${l}</option>`).join('')}</select>
    <span class="muted chbar__n">${fmtN(r.total || 0)} ${r.total === 1 ? 'video' : 'videos'}</span></div>
    ${r.error ? `<p class="note" style="color:var(--warn);margin-bottom:12px">${esc(r.error)}</p>` : ''}
    <div class="vgrid">${(r.videos || []).map(vcard).join('') || '<div class="empty">No videos match.</div>'}</div>
    ${r.pages > 1 ? `<div class="row chpager"><button class="btn btn--ghost btn--xs" id="chPrev" ${r.page <= 1 ? 'disabled' : ''}>← Newer</button><span class="muted">Page ${r.page} of ${r.pages}</span><button class="btn btn--ghost btn--xs" id="chNext" ${r.page >= r.pages ? 'disabled' : ''}>Older →</button></div>` : ''}
    <p class="note" style="margin-top:12px">${esc(r.note || '')} Open a video for its thumbnails, links, chapters, songs and transcript.</p>`;
  chWire(el, 'videos');
  const q = $('#chQ', el); let t;
  q.oninput = () => { clearTimeout(t); t = setTimeout(() => { CH.q = q.value.trim(); CH.page = 1; chVideos(); }, 300); };
  if (typing) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  $$('#chKind button', el).forEach(b => b.onclick = () => { CH.kind = b.dataset.k; CH.page = 1; chVideos(); });
  $('#chHas', el).onchange = e => { CH.has = e.target.value; CH.page = 1; chVideos(); };
  const pv = $('#chPrev', el), nx = $('#chNext', el);
  if (pv) pv.onclick = () => { CH.page--; chVideos(); };
  if (nx) nx.onclick = () => { CH.page++; chVideos(); };
}

const CH_KINDS = [['transcript', 'Transcripts'], ['description', 'Descriptions'], ['chapters', 'Chapters'], ['song', 'Songs'], ['setlist', 'Set lists'], ['note', 'Notes'], ['all', 'Everything']];
function chSearch() {
  const el = $('#chSearch'); if (!el) return;
  if (CH.open && CH.from === 'search') return chVideo(el, CH.open, CH.at);
  el.innerHTML = `<form class="chsearch" id="chSF"><input id="chSQ" type="search" placeholder="Search what was preached, the descriptions, the songs…" value="${esc(CH.sq)}" autocomplete="off"><button class="btn" type="submit">Search</button></form>
    <div class="row chchips" id="chSK">${CH_KINDS.map(([k, l]) => `<button type="button" class="chip ${CH.skind === k ? 'active' : ''}" data-k="${k}">${l}</button>`).join('')}
      <label class="chk"><input type="checkbox" id="chHist" ${CH.hist ? 'checked' : ''}> past versions</label>${S.me?.claude ? `<label class="chk" title="emails/, memory/: names of private people. Bradly only."><input type="checkbox" id="chPriv" ${CH.priv ? 'checked' : ''}> private folders</label>` : ''}</div>
    <div id="chSR">${CH.sq ? '<div class="empty">Searching…</div>' : `<div class="chhint"><p>Search every sermon transcript, description, chapter list and set list in the archive. Each result opens its video, with the thumbnails, the YouTube and Studio links, the chapters, the songs and the transcript at that moment.</p>
      <p class="muted">Try <a href="#" data-try="framing">framing</a>, <a href="#" data-try="&quot;peace is a garrison&quot;">"peace is a garrison"</a> (quotes match the exact phrase), or a CCLI number like <a href="#" data-try="7247827" data-kind="all">7247827</a>.</p></div>`}</div>`;
  const run = () => { const v = $('#chSQ', el).value.trim(); if (!v) { toast('Type a word, a phrase in quotes, or a CCLI number to search for', 'warn'); $('#chSQ', el).focus(); return; } CH.sq = v; chSearch(); };
  $('#chSF', el).onsubmit = e => { e.preventDefault(); run(); };
  $$('#chSK .chip', el).forEach(b => b.onclick = () => { CH.skind = b.dataset.k; CH.sq = $('#chSQ', el).value.trim(); chSearch(); });
  $('#chHist', el).onchange = e => { CH.hist = e.target.checked; if (CH.sq) chSearch(); };
  const pr = $('#chPriv', el); if (pr) pr.onchange = e => { CH.priv = e.target.checked; if (CH.sq) chSearch(); };
  $$('[data-try]', el).forEach(a => a.onclick = e => { e.preventDefault(); CH.sq = a.dataset.try; if (a.dataset.kind) CH.skind = a.dataset.kind; chSearch(); });
  if (CH.sq) chSearchRun(); else $('#chSQ', el).focus();
}
async function chSearchRun() {
  const out = $('#chSR'); if (!out) return;
  const want = JSON.stringify([CH.sq, CH.skind, CH.hist, CH.priv]); CH.want = want;
  const p = new URLSearchParams({ q: CH.sq, kind: CH.skind, history: CH.hist, private: CH.priv });
  const r = await api('/automator/search?' + p).catch(e => ({ error: e.message, videos: [] }));
  if (!out.isConnected || CH.want !== want) return;
  const songs = (r.songs || []).map(s => `<div class="panel panel--flat chsong"><div class="kicker">From song_bank.json</div><b>${esc(s.title)}</b> ${s.ccli ? `<span class="mono">CCLI ${esc(s.ccli)}</span>` : '<span class="tag">no CCLI number</span>'}<div class="muted">${esc(s.writers || '')}</div>${s.credit_line ? `<div class="mono" style="font-size:12px;margin-top:6px">${esc(s.credit_line)}</div>` : ''}</div>`).join('');
  const titles = (r.titles || []).length ? `<div class="kicker" style="margin:14px 0 8px">Titles that match</div><div class="vgrid vgrid--sm">${r.titles.map(vcard).join('')}</div>` : '';
  const vids = r.videos || [];
  const groups = vids.map(g => `<div class="panel panel--flat chg"><div class="chg__hd"><button class="chg__t" data-vid="${esc(g.id)}" aria-label="Open">${thumbImg(g.thumb, g.title || g.id, g.seconds)}</button><div class="chg__m"><button class="linkish" data-vid="${esc(g.id)}"><b>${esc(g.title || g.id)}</b></button><div class="muted">${fmtD(g.date)} · ${KIND_LABEL[g.kind] || 'Video'} · ${g.total > g.hits.length ? `the first ${g.hits.length} of ${g.total} matches` : `${g.hits.length} ${g.hits.length === 1 ? 'match' : 'matches'}`}${g.held ? ' · <span class="tag tag--warn">on hold</span>' : ''}</div>
      <div class="row" style="margin-top:8px;gap:6px"><button class="btn btn--xs" data-vid="${esc(g.id)}">Open</button><a class="btn btn--ghost btn--xs" href="${esc(g.watch)}" target="_blank" rel="noopener">YouTube</a><a class="btn btn--ghost btn--xs" href="${esc(g.studio)}" target="_blank" rel="noopener">Studio</a></div></div></div>
    <div class="chhits">${g.hits.map(h => `<div class="chhit">${h.at != null ? `<button class="chhit__t mono" data-vid="${esc(g.id)}" data-at="${h.sec}" title="Open the transcript here">${esc(h.at)}</button>` : `<span class="tag">${esc(h.kind)}</span>`}<span class="chhit__s">${snip(h.snippet)}</span>${h.history ? '<span class="tag">past version</span>' : ''}${h.private ? '<span class="tag">private</span>' : ''}${h.link ? `<a class="chhit__y" href="${esc(h.link)}" target="_blank" rel="noopener" title="Watch from here on YouTube">▶</a>` : ''}</div>`).join('')}</div></div>`).join('');
  const files = (r.files || []).length ? `<div class="kicker" style="margin:14px 0 8px">In files that name no video</div><div class="panel panel--flat">${r.files.map(f => `<button class="chfile" data-doc-repo="${esc(f.repo)}" data-doc-path="${esc(f.path)}" data-doc-line="${f.lines ? f.lines[0] : ''}"><span class="tag">${esc(f.kind)}</span><span class="mono chfile__p">${esc(f.path)}</span><span class="chhit__s">${snip(f.snippet)}</span></button>`).join('')}</div>` : '';
  const none = !songs && !titles && !groups && !files && !r.error;
  out.innerHTML = (r.error ? `<p class="note" style="color:var(--warn)">${esc(r.error)}</p>` : '') + songs + titles
    + (groups ? `<div class="kicker" style="margin:14px 0 8px">${fmtN(r.count)} ${r.count === 1 ? 'match' : 'matches'} in ${vids.length} ${vids.length === 1 ? 'video' : 'videos'}</div>${groups}` : '') + files
    + (none ? `<div class="empty">Nothing found for “${esc(CH.sq)}”${CH.skind !== 'all' ? ` in ${esc((CH_KINDS.find(k => k[0] === CH.skind) || [, ''])[1].toLowerCase())}. Try Everything.` : '.'}</div>` : '')
    + `<p class="note" style="margin-top:12px">${esc(r.lyrics || '')} A hit is a lead to check, never a fact: speakers come from Bradly and song credits from song_bank.json.</p>`;
  chWire(out, 'search');
}

async function chVideo(el, vid, at) {
  el.innerHTML = '<div class="empty">Opening…</div>';
  const v = await api('/automator/videos/' + encodeURIComponent(vid)).catch(e => ({ ok: false, err: e.message }));
  if (!el.isConnected) return;
  const backTo = () => { CH.open = null; CH.at = null; (CH.from === 'search' ? chSearch : chVideos)(); };
  const back = `<button class="btn btn--ghost btn--xs" id="chBack">← ${CH.from === 'search' ? 'Back to the results' : 'All videos'}</button>`;
  if (v.ok === false) { el.innerHTML = back + `<p class="note" style="margin-top:12px;color:var(--warn)">${esc(v.err || 'Could not open that video')}</p>`; $('#chBack', el).onclick = backTo; return; }
  const vers = v.versions || [];
  let cur = vers.findIndex(x => !x.history && (x.text || '').trim()); if (cur < 0) cur = 0;
  const own = (v.thumbs || [])[0]?.url || '';
  el.innerHTML = `<div class="row" style="justify-content:space-between;margin-bottom:12px">${back}<span class="muted mono" style="font-size:12px">${esc(v.id)}</span></div>
  <div class="chv"><div class="chv__hero">${thumbImg(v.thumb_large, v.title || v.id, v.seconds, own)}</div>
    <div class="chv__meta"><div class="kicker">${KIND_LABEL[v.kind] || 'Video'} · ${fmtD(v.date)}${v.seconds ? ' · ' + dur(v.seconds) : ''}</div><h2 class="chv__title">${esc(v.title || v.id)}</h2>
      ${v.now && v.now.title && v.now.title !== v.title ? `<p class="note">On YouTube now: <b>${esc(v.now.title)}</b> <span class="muted">(checked ${esc(v.now.checked || '')})</span></p>` : ''}
      ${v.held ? `<p class="note chv__held"><b>On the hold list.</b> No script writes to this video${v.held_reason ? ': ' + esc(v.held_reason) : ''}.</p>` : ''}
      ${v.date_note ? `<p class="note">Date: ${esc(v.date_note)}.</p>` : ''}
      <div class="row chv__acts"><a class="btn" href="${esc(v.watch)}" target="_blank" rel="noopener">Watch on YouTube</a><a class="btn btn--ghost" href="${esc(v.studio)}" target="_blank" rel="noopener">Open in Studio</a><button class="btn btn--ghost" id="chCopyLink">Copy link</button>${v.parent_video ? `<button class="btn btn--ghost" data-vid="${esc(v.parent_video.id)}">The full service</button>` : ''}</div>
      <div class="row" style="gap:6px;margin-top:10px;flex-wrap:wrap">${v.transcript ? '<span class="tag">transcript</span>' : ''}${(v.chapters || []).length ? `<span class="tag">${v.chapters.length} chapters</span>` : ''}${(v.shorts || []).length ? `<span class="tag">${v.shorts.length} Shorts</span>` : ''}${v.privacy ? `<span class="tag">${esc(v.privacy)}</span>` : ''}${v.sample ? '<span class="tag">sample</span>' : ''}</div></div></div>
  <div class="grid" style="margin-top:14px">
    <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Thumbnails</h3><span class="sub">${(v.thumbs || []).length + 1}</span></div><div class="chthumbs">
      <figure><a href="${esc(v.thumb_max)}" target="_blank" rel="noopener">${thumbImg(v.thumb, v.title, null)}</a><figcaption>On YouTube now<br><span class="muted"><a href="${esc(v.thumb_max)}" target="_blank" rel="noopener">full size</a></span></figcaption></figure>
      ${(v.thumbs || []).map(t => `<figure><a href="${esc(t.url)}" target="_blank" rel="noopener">${thumbImg(t.url, t.name, null)}</a><figcaption title="${esc(t.repo + '/' + t.path)}">${esc(t.name)}<br><span class="muted">${esc(t.why)}${t.width ? ` · ${t.width}×${t.height}` : ''} · <a href="${esc(t.url)}" download="${esc(t.name)}">download</a></span></figcaption></figure>`).join('')}</div>
      ${(v.thumbs || []).length ? '' : '<p class="note">No thumbnail file in the archive names this video or its date.</p>'}</div>
    ${v.kind === 'short' && !(v.chapters || []).length ? '' : `<div class="c6 panel panel--flat"><div class="panel__hd"><h3>Chapters</h3><span class="sub">${(v.chapters || []).length || 'none'}</span></div>${(v.chapters || []).length ? `<div class="chchap">${v.chapters.map(c => `<div class="chchap__r"><button class="mono" data-seek="${c.sec}" title="Show this moment in the transcript">${esc(c.at)}</button><span>${esc(c.title)}</span><a href="${esc(c.link)}" target="_blank" rel="noopener" title="Watch from here">▶</a></div>`).join('')}</div>` : '<p class="note">No chapters in the description.</p>'}</div>`}
    ${(v.credits || []).length || (v.setlists || []).length ? `<div class="c6 panel panel--flat"><div class="panel__hd"><h3>Songs</h3></div>${(v.credits || []).length ? `<ul class="chcred">${v.credits.map(c => `<li>${esc(c)}</li>`).join('')}</ul><p class="note">As the description writes them. Credits come only from song_bank.json.</p>` : ''}${(v.setlists || []).map(s => `<details style="margin-top:8px"><summary>Set list · <span class="mono">${esc(s.path)}</span></summary><pre class="log pre">${esc(s.text)}</pre></details>`).join('')}</div>` : ''}
    ${(v.shorts || []).length ? `<div class="c6 panel panel--flat"><div class="panel__hd"><h3>Shorts from this service</h3><span class="sub">${v.shorts.length}</span></div><div class="vgrid vgrid--sm">${v.shorts.map(vcard).join('')}</div></div>` : ''}
    <div class="c12 panel panel--flat"><div class="panel__hd"><h3>Description</h3>${vers.length > 1 ? `<select id="chVer">${vers.map((x, i) => `<option value="${i}" ${i === cur ? 'selected' : ''}>${esc(x.source)}${x.history ? ' (past version)' : ''}${x.private ? ' (private)' : ''}</option>`).join('')}</select>` : ''}<span class="row" style="margin-left:auto;gap:6px">${vers.length ? '<button class="btn btn--ghost btn--xs" id="chCopyDesc">Copy</button><button class="btn btn--ghost btn--xs" id="chCopyClean" title="No ** and no CCLI numbers: the text for StreamYard">Copy clean</button>' : ''}</span></div>
      ${vers.length ? `<pre class="chdesc" id="chDesc">${esc(vers[cur].text)}</pre>` : '<p class="note">No description in the snapshots or the archive.</p>'}<p class="note" style="margin-top:8px">${esc(v.note || '')}</p></div>
    <div class="c12 panel panel--flat" id="chTx"><div class="panel__hd"><h3>Transcript</h3></div><div class="empty">${v.transcript ? 'Loading the transcript…' : 'No transcript for this video in the archive.'}</div></div>
    <div class="c12 panel panel--flat"><div class="panel__hd"><h3>In the archive</h3><span class="sub">${(v.files || []).length} ${(v.files || []).length === 1 ? 'file' : 'files'}</span></div>${(v.files || []).map(f => `<button class="chfile" data-doc-repo="${esc(f.repo)}" data-doc-path="${esc(f.path)}"><span class="tag">${esc(f.kind)}</span><span class="mono chfile__p">${esc(f.path)}</span>${f.history ? '<span class="tag">past version</span>' : ''}${f.private ? '<span class="tag">private</span>' : ''}</button>`).join('') || '<p class="note">No file names this video by its id.</p>'}</div>
  </div>`;
  chWire(el, CH.from || 'videos');
  $('#chBack', el).onclick = backTo;
  $('#chCopyLink', el).onclick = e => copyText(v.watch, e.target);
  const ver = $('#chVer', el); if (ver) ver.onchange = () => { cur = +ver.value; $('#chDesc', el).textContent = vers[cur].text; };
  const cd = $('#chCopyDesc', el); if (cd) cd.onclick = e => copyText(vers[cur].text, e.target);
  const cc = $('#chCopyClean', el); if (cc) cc.onclick = () => copyText(cleanDesc(vers[cur].text));
  $$('[data-seek]', el).forEach(b => b.onclick = () => chSeek(+b.dataset.seek));
  if (v.transcript) chTranscript(vid, at);
}
async function chTranscript(vid, at, source) {
  const box = $('#chTx'); if (!box) return;
  const t = await api(`/automator/videos/${encodeURIComponent(vid)}/transcript` + (source ? '?source=' + encodeURIComponent(source) : '')).catch(e => ({ ok: false, err: e.message }));
  if (!box.isConnected) return;
  if (t.ok === false || !(t.segments || []).length) { const e = $('.empty', box); if (e) e.textContent = t.err || t.note || 'No timed transcript for this video.'; return; }
  box.innerHTML = `<div class="panel__hd"><h3>Transcript</h3><span class="sub">${fmtN(t.segments.length)} lines</span>${(t.sources || []).length > 1 ? `<select id="chTxSrc">${t.sources.map(s => `<option value="${esc(s.path)}" ${s.path === t.source ? 'selected' : ''}>${esc(s.path)} (${s.segments})</option>`).join('')}</select>` : `<span class="muted mono" style="font-size:11px">${esc(t.source || '')}</span>`}<input id="chTxQ" type="search" placeholder="Find in this transcript" autocomplete="off" style="margin-left:auto;width:220px"><span class="muted" id="chTxN"></span></div>
    <p class="note" style="margin-bottom:8px">${esc(t.lyrics || '')}</p>
    <div class="chtx" id="chTxL">${t.segments.map(s => `<div class="chtx__r" data-t="${s.t}"><a class="mono" href="${esc(t.link)}?t=${Math.floor(s.t)}" target="_blank" rel="noopener" title="Watch from here">${dur(s.t)}</a><span>${esc(s.text)}</span></div>`).join('')}</div>`;
  const src = $('#chTxSrc', box); if (src) src.onchange = () => chTranscript(vid, null, src.value);
  const q = $('#chTxQ', box); let tm;
  q.oninput = () => { clearTimeout(tm); tm = setTimeout(() => {
    const w = q.value.trim().toLowerCase(); const rows = $$('#chTxL .chtx__r', box); let n = 0, first = null;
    rows.forEach(r => { const hit = !!w && r.lastElementChild.textContent.toLowerCase().includes(w); r.classList.toggle('hit', hit); if (hit) { n++; first = first || r; } });
    $('#chTxN', box).textContent = w ? `${n} ${n === 1 ? 'line' : 'lines'}` : '';
    if (first) { const L = $('#chTxL', box); L.scrollTop = first.offsetTop - L.offsetTop - 40; }
  }, 200); };
  if (at != null) chSeek(at);
}
function chSeek(sec) {
  const L = $('#chTxL'); if (!L) return; const rows = $$('.chtx__r', L); if (!rows.length) return;
  let best = rows[0]; for (const r of rows) { if (+r.dataset.t <= sec + 0.5) best = r; else break; }
  rows.forEach(r => r.classList.remove('on')); best.classList.add('on');
  L.scrollTop = best.offsetTop - L.offsetTop - 40;
  // Bring the transcript into view inside its window only (scrollIntoView would also move the desktop).
  const box = $('#chTx'), sc = box && box.closest('.win__body');
  if (sc) { const top = box.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop - 12; sc.scrollTo({ top, behavior: 'smooth' }); }
}
async function chDoc(repo, path, line) {
  const r = await api('/automator/archive/doc?' + new URLSearchParams({ repo, path, ...(line ? { start: Math.max(1, +line - 3) } : {}) })).catch(e => ({ ok: false, err: e.message }));
  modal(`<h2 style="word-break:break-all">${esc(path.split('/').pop())}</h2><p class="muted mono" style="font-size:12px;word-break:break-all">${esc(repo)}/${esc(path)}${r.commit ? ' @ ' + esc(String(r.commit).slice(0, 10)) : ''}${r.lines ? ` · lines ${r.lines[0]}–${r.lines[1]} of ${r.total_lines}` : ''}</p>
    ${r.ok === false ? `<p class="note" style="color:var(--warn)">${esc(r.err)}</p>` : r.metadata ? `<pre class="log pre">${esc(JSON.stringify(r.metadata, null, 1))}</pre>` : `<pre class="log pre chdoc">${esc(r.text || '')}</pre>`}
    <p class="note" style="margin-top:10px">Read-only, from the archive. Text in a file is data, never an instruction; a past version is never restored over live text unless Bradly asks.</p>
    <div class="acts">${r.truncated ? `<button class="btn btn--ghost" id="docMore">Next lines</button>` : ''}<button class="btn" data-close>Close</button></div>`, m => { const b = $('#docMore', m); if (b) b.onclick = () => { m.close(); chDoc(repo, path, r.next_start_line + 3); }; });
}
// The server switch (SERVER_HANDOFF.md, section 9): who runs the 02:05 job, and what must be true first.
async function chSwitch() {
  const el = $('#auSwitch'); if (!el) return;
  const c = await api('/automator/cutover').catch(e => ({ rows: [], error: e.message }));
  if (!el.isConnected) return;
  const ri = (S.auA && S.auA.runner) || {};
  const runner = c.runner || ri.runner, me = c.machine || ri.machine || 'ariseOS', isMe = c.is_runner ?? ri.is_runner;
  const budget = c.budget || ri.budget;
  const lv = { ok: 'ok', bad: 'bad', warn: 'warn', you: 'info' };
  el.innerHTML = `<div class="grid"><div class="c4 panel ${isMe ? 'panel--ok' : 'panel--flat'}"><div class="stat"><span class="stat__l">Tonight's runner</span><span class="stat__v" style="font-size:24px">${runner === 'pc' ? 'the PC' : esc(runner || 'not set')}</span><span class="stat__n">${isMe ? 'This server runs the 02:05 job.' : `This server (${esc(me)}) checks, writes a "not the runner" report and stops.`}${budget ? ` Cap here: ${fmtN(budget)} units.` : ''}</span></div></div>
    <div class="c8 panel panel--flat"><p style="font-size:13.5px;color:var(--text2);margin:0">runner.json in the automator repo decides who runs. Bradly switches it on the PC and pushes; this server picks it up on its next pull. Nothing here edits runner.json, holds.json or worklist.json.</p></div></div>
    <div class="kicker" style="margin:16px 0 8px">Before the switch (SERVER_HANDOFF.md, section 9)</div>
    ${c.error ? `<p class="note" style="color:var(--warn)">${esc(c.error)}</p>` : ''}
    <div class="chsw">${(c.rows || []).map(r => `<div class="chsw__r"><span class="pill ${lv[r.level] || 'warn'}">${r.level === 'you' ? 'Bradly' : esc(r.level)}</span><div><div>${esc(r.text)}</div>${r.fix ? `<code class="chsw__fix">${esc(r.fix)}</code>` : ''}</div></div>`).join('') || '<div class="empty">No checklist</div>'}</div>`;
}

/* ---------------- songs: the song list, and the lyrics Bradly adds ----------------
   The list is song_bank.json (read-only); lyrics live on the server only (docs/AUTOMATOR.md, Songs). */
const SG = { q: '', has: '', open: null };
const SECTION_RE = /^(verse|chorus|pre-?chorus|bridge|tag|intro|outro|vamp|ending|interlude|refrain|hook|turnaround|channel)\b[\s\d:.()x]*$/i;
const firstLine = t => (String(t || '').split('\n').map(l => l.trim()).find(l => l && !SECTION_RE.test(l)) || '');
function chOpenVideo(vid) { CH.open = vid; CH.at = null; CH.from = 'videos'; const b = $('#auTabs [data-t="videos"]'); if (b) b.click(); chVideos(); }
function chFindLine(line) { CH.sq = `"${line.replace(/"/g, '').slice(0, 80)}"`; CH.skind = 'transcript'; CH.open = null; const b = $('#auTabs [data-t="search"]'); if (b) b.click(); chSearch(); }
async function chSongs() {
  const el = $('#chSongs'); if (!el) return;
  if (SG.open) return sgSong(el, SG.open);
  const r = await api('/songs?' + new URLSearchParams({ q: SG.q, has: SG.has })).catch(e => ({ error: e.message, songs: [] }));
  if (!el.isConnected) return;
  const typing = document.activeElement && document.activeElement.id === 'sgQ';
  const c = r.counts || {};
  el.innerHTML = `<div class="chbar"><input id="sgQ" type="search" placeholder="Find a song: title, CCLI number, writer, or a line of the lyrics" value="${esc(SG.q)}" autocomplete="off">
    <div class="seg" id="sgHas">${[['', `All${c.all != null ? ' ' + c.all : ''}`], ['lyrics', `With lyrics${c.lyrics != null ? ' ' + c.lyrics : ''}`], ['missing', 'No lyrics yet'], ['original', 'Originals']].map(([k, l]) => `<button data-k="${k}" class="${SG.has === k ? 'active' : ''}">${esc(l)}</button>`).join('')}</div>
    <label class="btn btn--ghost btn--xs sgimp" for="sgFile" title="SongSelect .txt or .usr, ChordPro, or plain text">Import lyrics files</label><input type="file" id="sgFile" multiple accept=".txt,.usr,.cho,.chopro,.chordpro,.pro,.crd" hidden></div>
    ${r.error ? `<p class="note" style="color:var(--warn);margin-bottom:12px">${esc(r.error)}</p>` : ''}
    <div class="panel panel--flat tbl-wrap"><table class="tbl sgtbl"><thead><tr><th>Song</th><th>CCLI</th><th>Writers</th><th>Lyrics</th><th class="num">Sung</th><th>Last sung</th></tr></thead><tbody>
    ${(r.songs || []).map(s => `<tr data-song="${esc(s.key)}" tabindex="0"><td><b>${esc(s.title)}</b>${s.original ? ' <span class="tag">original</span>' : ''}${s.in_bank === false ? ' <span class="tag tag--warn">not in song_bank.json</span>' : ''}${s.snippet ? `<br><small class="muted">${snip(s.snippet)}</small>` : ''}</td><td class="mono">${esc(s.ccli || '—')}</td><td class="dim" style="font-size:12.5px">${esc(s.writers || '')}</td><td>${s.lyrics ? '<span class="pill ok">yes</span>' : '<span class="pill">not yet</span>'}</td><td class="num">${s.sung || 0}</td><td class="dim">${s.last_sung ? fmtD(s.last_sung) : '—'}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">No song matches.</td></tr>'}
    </tbody></table></div>
    <p class="note" style="margin-top:12px">The list is song_bank.json, read-only here (songs are added on the PC). Paste a song's lyrics into it from Proclaim, or import SongSelect .txt / .usr or ChordPro files: a file links to its song by the CCLI number in it, or by a title only one song has. ${esc(r.note || '')}</p>`;
  const q = $('#sgQ', el); let t;
  q.oninput = () => { clearTimeout(t); t = setTimeout(() => { SG.q = q.value.trim(); chSongs(); }, 300); };
  if (typing) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  $$('#sgHas button', el).forEach(b => b.onclick = () => { SG.has = b.dataset.k; chSongs(); });
  $$('[data-song]', el).forEach(tr => { const go = () => { SG.open = tr.dataset.song; chSongs(); }; tr.onclick = go; tr.onkeydown = e => { if (e.key === 'Enter') go(); }; });
  $('#sgFile', el).onchange = async e => {
    const files = await Promise.all([...e.target.files].map(f => f.text().then(text => ({ name: f.name, text }))));
    if (!files.length) return;
    const res = await api('/songs/import', { method: 'POST', body: { files } }).catch(er => ({ ok: false, err: er.message }));
    if (res.ok === false) return toast(res.err, 'bad');
    modal(`<h2>Lyrics imported</h2><p class="note" style="margin-bottom:10px">${res.linked} linked to their song, ${res.unlinked} kept but not linked, ${res.failed} not read.${res.demo ? ' (sample mode: kept in this preview only)' : ''}</p>
      <div class="sgres">${res.results.map(x => `<div class="sgres__r"><span class="pill ${x.ok ? (x.matched_by ? 'ok' : 'warn') : 'bad'}">${x.ok ? (x.matched_by ? 'linked' : 'kept') : 'failed'}</span><div><b>${esc(x.name)}</b>${x.title ? ` → ${esc(x.title)}` : ''}<br><small class="muted">${esc(x.matched_by ? 'by ' + x.matched_by : x.note || x.err || '')}</small></div></div>`).join('')}</div>
      <div class="acts"><button class="btn" data-close>Done</button></div>`);
    chSongs();
  };
}
async function sgSong(el, key) {
  el.innerHTML = '<div class="empty">Opening…</div>';
  const s = await api('/songs/' + encodeURIComponent(key)).catch(e => ({ ok: false, err: e.message }));
  if (!el.isConnected) return;
  const back = `<button class="btn btn--ghost btn--xs" id="sgBack">← All songs</button>`;
  const goBack = () => { SG.open = null; chSongs(); };
  if (s.ok === false) { el.innerHTML = back + `<p class="note" style="margin-top:12px;color:var(--warn)">${esc(s.err)}</p>`; $('#sgBack', el).onclick = goBack; return; }
  const L = s.lyrics;
  const kv = [['CCLI', s.ccli ? `<span class="mono">${esc(s.ccli)}</span>` : (s.original ? 'none: an Arise original' : 'none in song_bank.json')], ['Writers', esc(s.writers || '—')], ['Copyright', esc(s.copyright || '—')], ['Admin', esc(s.admin || '—')],
    ['Credit line', s.credit_line ? `${esc(s.credit_line)} <button class="btn btn--ghost btn--xs" id="sgCopyCredit">Copy</button>` : '—'], ['Performed by', esc(s.performed_by || '—')], ['Verified', esc(s.verified || '—')], ['Note', esc(s.note || '—')]];
  el.innerHTML = `<div class="row" style="justify-content:space-between;margin-bottom:12px">${back}<span class="muted mono" style="font-size:12px">${esc(s.key)}</span></div>
    <div class="grid">
      <div class="c4 panel panel--flat"><div class="kicker">${s.in_bank ? 'song_bank.json' : 'Lyrics only: not in song_bank.json'}</div><h2 class="chv__title">${esc(s.title)}</h2>
        <dl class="kv sgkv">${kv.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>
        <p class="note" style="margin-top:10px">Credits come only from song_bank.json, as written there. A new song or a correction is made on the PC.</p></div>
      <div class="c8 panel panel--flat" id="sgLyrBox"></div>
      <div class="c12 panel panel--flat"><div class="panel__hd"><h3>Where it was sung</h3><span class="sub">${(s.sung || []).length}</span></div>
        ${(s.sung || []).length ? `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Date</th><th>Service</th><th>From</th><th></th></tr></thead><tbody>${s.sung.map(x => `<tr><td>${fmtD(x.date)}</td><td>${esc(x.title || x.service || '')}</td><td class="dim">${esc(x.from)}</td><td>${x.video_id ? `<button class="btn btn--ghost btn--xs" data-open-vid="${esc(x.video_id)}">Open the video</button>` : ''}</td></tr>`).join('')}</tbody></table></div>`
          : '<p class="note">No set list or description in the archive names this song yet.</p>'}</div>
    </div>`;
  $('#sgBack', el).onclick = goBack;
  const cc = $('#sgCopyCredit', el); if (cc) cc.onclick = e => copyText(s.credit_line, e.target);
  $$('[data-open-vid]', el).forEach(b => b.onclick = () => chOpenVideo(b.dataset.openVid));
  const box = $('#sgLyrBox', el);
  const view = () => {
    box.innerHTML = `<div class="panel__hd"><h3>Lyrics</h3>${L ? `<span class="sub">${esc(L.source || '')}${L.updated ? ' · ' + fmtT(L.updated) : ''}${s.versions ? ` · ${s.versions} earlier ${s.versions === 1 ? 'version' : 'versions'} kept` : ''}</span>` : ''}</div>
      ${L ? `<pre class="chdesc sglyr" id="sgLyr">${esc(L.text)}</pre>
        <div class="row" style="gap:8px;margin-top:10px;flex-wrap:wrap"><button class="btn btn--ghost btn--xs" id="sgEdit">Edit</button><button class="btn btn--ghost btn--xs" id="sgFind" title="Select a line first, or it uses the first one">Find a line in the transcripts</button><button class="btn btn--ghost btn--xs" id="sgRm" style="margin-left:auto">Remove the lyrics</button></div>`
      : `<p class="note" style="margin-bottom:8px">No lyrics yet. Paste them here (from Proclaim's song editor, or SongSelect), with the section names (Verse 1, Chorus) on their own lines.</p>`}
      <p class="note" style="margin-top:10px">${esc(s.licence || '')}</p>`;
    if (!L) return edit('');
    $('#sgEdit', box).onclick = () => edit(L.text);
    $('#sgFind', box).onclick = () => { const sel = String(window.getSelection() || '').trim().split('\n')[0]; const line = sel || firstLine(L.text); if (line) chFindLine(line); };
    $('#sgRm', box).onclick = () => confirmType('Remove these lyrics', s.title, 'The file moves to the lyrics folder’s .removed folder on the server; nothing is deleted.', async () => {
      const r = await api(`/songs/${encodeURIComponent(s.key)}/lyrics`, { method: 'DELETE', body: { confirm: s.title } }); if (r.ok === false) throw new Error(r.err); toast('Lyrics removed (kept in .removed)'); sgSong(el, key); });
  };
  const edit = text => {
    const area = document.createElement('div');
    area.innerHTML = `<textarea id="sgText" class="sgtext" spellcheck="false" placeholder="Verse 1\n…\n\nChorus\n…">${esc(text)}</textarea>
      <div class="row" style="gap:8px;margin-top:10px"><button class="btn" id="sgSave">Save</button>${L ? '<button class="btn btn--ghost" id="sgCancel">Cancel</button>' : ''}<span class="muted" style="font-size:12px">${L ? 'The current version is kept when you save.' : ''}</span></div>`;
    const hd = $('.panel__hd', box) || box; box.querySelectorAll('pre, .row').forEach(x => x.remove()); hd.after(area);
    const ta = $('#sgText', box); ta.focus();
    $('#sgSave', box).onclick = async e => { const r = await act(e.target, () => api(`/songs/${encodeURIComponent(s.key)}/lyrics`, { method: 'PUT', body: { text: ta.value, source: L ? 'edited' : 'pasted' } }), 'Lyrics saved'); if (r && r.ok !== false) sgSong(el, key); };
    const cn = $('#sgCancel', box); if (cn) cn.onclick = view;
  };
  view();
}

/* ---- sharing (round 5) ----
   Share with a person or a group (row 19): the server writes an ACL on the item and a link in
   their "shared" share, so it appears on their Mac and here, and tells them by push and email.
   The quota line (row 13) and Shared by me live here too. server/arise_server/sharing.py. */
function canShareWith(root, p) {
  if (!p || p === '/' || String(root).startsWith('shared:') || String(root).startsWith('@')) return false;
  return !isMember() || root === 'home';   // members share only their own files
}
async function shareWith(root, p, n) {
  const ppl = await api('/files/share/people').catch(() => ({ people: [], groups: [], typed: true }));
  const opts = [...(ppl.people || []).map(u => `<option value="${esc(u.name)}">${esc(u.display)}</option>`), ...(ppl.groups || []).map(g => `<option value="@${esc(g)}">Everyone in ${esc(g)}</option>`)].join('');
  modal(`<h2>Share “${esc(n)}”</h2><p class="muted">With a person or a group in the church. It appears in their <b>shared</b> share on their Mac and in their Finder here, and they get a notice.</p>
    <form id="swF" style="display:grid;gap:10px;margin-top:12px">
      <div class="field"><label>With</label><input id="swTo" list="swList" placeholder="${ppl.typed ? 'first.last' : 'a name, or @Group'}" autocomplete="off"><datalist id="swList">${opts}</datalist><span class="hint">Several? Separate them with commas.</span></div>
      <div class="field"><label>They can</label><select id="swPerm"><option value="read">Open and copy it</option><option value="write">Open and edit it</option></select></div>
      <div class="acts"><button type="button" class="btn btn--ghost" data-close>Cancel</button><button class="btn" type="submit">Share</button></div></form>`, m => {
    $('#swTo', m).focus();
    $('#swF', m).onsubmit = async e => { e.preventDefault(); const to = $('#swTo', m).value.split(',').map(x => x.trim()).filter(Boolean);
      const r = await act($('button[type=submit]', m), () => api('/files/share', { method: 'POST', body: { root, path: p, to, perm: $('#swPerm', m).value } }), `Shared with ${to.join(', ')}`);
      if (r && r.ok !== false) m.close(); };
  });
}
async function sharedByModal() {
  const r = await api('/files/shared').catch(e => ({ by_me: [], with_me: [], err: e.message }));
  const rows = (r.all || r.by_me || []);
  const row = x => `<tr><td><b>${esc(x.name)}</b>${x.dir ? ' <span class="tag">folder</span>' : ''}<br><small class="muted">${esc(x.rel)}</small></td><td>${esc((x.to || []).join(', '))}</td><td>${x.perm === 'write' ? 'can edit' : 'can open'}</td>${r.all ? `<td>${esc(x.owner)}</td>` : ''}<td><button class="btn btn--ghost btn--xs" data-unshare="${esc(x.id)}">Stop sharing</button></td></tr>`;
  modal(`<h2>${r.all ? 'Everything shared' : 'Shared by me'}</h2>
    ${rows.length ? `<table class="tbl" style="margin-top:10px"><thead><tr><th>Item</th><th>With</th><th>Can</th>${r.all ? '<th>By</th>' : ''}<th></th></tr></thead><tbody>${rows.map(row).join('')}</tbody></table>` : '<p class="empty">Nothing shared yet. Right-click a file or folder, then Share with…</p>'}
    ${(r.with_me || []).length ? `<h3 style="margin-top:16px">Shared with me</h3><ul class="plain">${r.with_me.map(x => `<li>${esc(x.link)} <small class="muted">from ${esc(x.owner)}, ${x.perm === 'write' ? 'can edit' : 'can open'}</small></li>`).join('')}</ul>` : ''}
    <div class="acts"><button class="btn" data-close>Done</button></div>`, m => {
    $$('[data-unshare]', m).forEach(b => b.onclick = async () => { const x = await act(b, () => api('/files/share/' + encodeURIComponent(b.dataset.unshare), { method: 'DELETE' }), 'Stopped sharing'); if (x && x.ok !== false) { m.close(); sharedByModal(); rerender('files'); } });
  });
}
async function quotaLine(root, fs) {
  const el = $('#fQuota', root); if (!el) return;
  const home = fs.root === 'home' || (fs.root === 'data' && /^\/homes\/[^/]+/.test(fs.path));
  if (!home) { el.hidden = true; return; }
  const user = fs.root === 'home' ? '' : fs.path.split('/')[2];
  const q = await api('/files/quota' + (user ? '?user=' + encodeURIComponent(user) : '')).catch(() => null);
  if (!q || !q.quota || !el.isConnected) { el.hidden = true; return; }
  el.hidden = false; el.className = 'fquota' + (q.full ? ' full' : q.warn ? ' warn' : '');
  el.innerHTML = `<span>${user ? esc(user) + ': ' : ''}${fmtB(q.used)} of ${fmtB(q.quota)}</span><div class="meter ${q.full ? '' : q.warn ? 'meter--warn' : 'meter--ok'}"><i style="width:${Math.min(100, q.pct || 0)}%"></i></div>${q.warn ? `<small>${q.full ? 'Full: uploads stop until space is freed.' : 'Nearly full.'}</small>` : ''}`;
}

V.nas = async () => {
  const n = await api('/nas');
  const d = n.dsm || {};
  const used = pct(n.used, n.total);
  return `<div class="fade"><div class="grid">
    <div class="c4 panel ${n.mounted ? 'panel--ok' : 'panel--bad'}"><div class="stat"><span class="stat__l">Mount</span><span class="stat__v" style="font-size:22px">${n.mounted ? 'mounted' : 'not mounted'}</span><span class="stat__n mono" style="font-size:12px">${esc(n.protocol)}://${esc(n.host)}/${esc(n.share)} → ${esc(n.mount)}</span><span class="stat__n">${n.reachable === false ? '<span style="color:var(--redL)">does not answer ping</span>' : n.reachable ? 'answers on the network' : ''}</span></div><div class="row" style="margin-top:12px">${n.mounted ? '<button class="btn btn--ghost btn--xs" id="nasUn">Unmount</button>' : '<button class="btn btn--xs" id="nasMount">Mount</button>'}</div></div>
    <div class="c4 panel panel--flat"><div class="stat"><span class="stat__l">Space</span><span class="stat__v" style="font-size:26px">${fmtB(n.free)}<small>free</small></span><span class="stat__n">${fmtB(n.used)} used of ${fmtB(n.total)}</span></div><div class="meter ${used > 85 ? '' : used > 70 ? 'meter--warn' : 'meter--ok'}"><i style="width:${used}%"></i></div></div>
    <div class="c4 panel panel--flat"><div class="stat"><span class="stat__l">DSM</span>${n.dsm ? (d.ok ? `<span class="stat__v" style="font-size:22px">${esc(d.volume_status || '?')}</span><span class="stat__n">${esc(d.model || '')} · ${esc(d.version || '')} · ${d.drives ?? '?'} drives · ${esc(d.raid || '')}${d.temperature ? ` · ${d.temperature}°C` : ''}</span>` : `<span class="stat__v" style="font-size:18px;color:var(--warn)">not readable</span><span class="stat__n">${esc(d.error || '')}</span>`) : '<span class="stat__v" style="font-size:18px">not configured</span><span class="stat__n">Set <code>dsm_url</code> and the credentials file in arise.toml to read health here.</span>'}</div></div>
    <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Role of the Synology</h3></div><div class="md">${md(`- **Bulk storage**: the \`media\` and \`homes\` shares live here on four drives with redundancy.\n- **Backup target**: the restic repository for the old PC's directory, automator, apps and config.\n- **Domain member**: once joined (docs/SYNOLOGY.md), the same accounts work on the NAS shares.\n- **Off-site copy**: Hyper Backup from the NAS to a USB drive or a cloud bucket completes the 3-2-1 rule.`)}</div></div>
    <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Off-site copy</h3></div>${n.hyper_backup ? `<div class="kv"><dt>Task</dt><dd>${esc(n.hyper_backup.task)}</dd><dt>Last</dt><dd>${fmtT(n.hyper_backup.last)} · ${n.hyper_backup.ok ? 'ok' : 'failed'}</dd></div>` : '<p class="note">Hyper Backup status is read from DSM when configured. Until then, check it in DSM → Hyper Backup.</p>'}</div>
  </div></div>`;
};
V.nas.after = () => { const m = $('#nasMount'); if (m) m.onclick = e => act(e.target, () => api('/nas/mount', { method: 'POST' }), 'Mounted').then(() => rerender('nas')); const u = $('#nasUn'); if (u) u.onclick = e => act(e.target, () => api('/nas/unmount', { method: 'POST' }), 'Unmounted').then(() => rerender('nas')); };

V.services = async () => {
  const r = await api('/services');
  return `<div class="fade panel panel--flat tbl-wrap"><table class="tbl"><thead><tr><th>Service</th><th>Unit</th><th>State</th><th>Since</th><th></th></tr></thead><tbody>
    ${(r.services || []).map(s => `<tr><td><b>${esc(s.name)}</b></td><td class="mono dim" style="font-size:12px">${esc(s.unit)}</td><td><span class="pill ${s.active === 'active' ? 'ok' : s.active === 'failed' ? 'bad' : 'warn'}">${esc(s.active)}${s.sub ? ' · ' + esc(s.sub) : ''}</span></td><td class="dim">${s.since ? fmtT(s.since) : '—'}</td>
      <td class="acts"><button class="btn btn--ghost btn--xs" data-svc="${esc(s.unit)}" data-do="restart">Restart</button>${s.active === 'active' ? `<button class="btn btn--ghost btn--xs" data-svc="${esc(s.unit)}" data-do="stop">Stop</button>` : `<button class="btn btn--xs" data-svc="${esc(s.unit)}" data-do="start">Start</button>`}<a class="btn btn--ghost btn--xs" data-log="${esc(s.unit)}">Logs</a></td></tr>`).join('')}
  </tbody></table></div>`;
};
V.services.after = () => { $$('[data-log]').forEach(a => a.onclick = e => { e.preventDefault(); S.logUnit = a.dataset.log; openApp('logs'); }); $$('[data-svc]').forEach(b => b.onclick = async () => { if (b.dataset.svc === 'arise-web.service' && b.dataset.do !== 'restart') { toast('Stopping the dashboard from the dashboard is a bad idea', 'warn'); return; } const r = await act(b, () => api(`/services/${encodeURIComponent(b.dataset.svc)}/${b.dataset.do}`, { method: 'POST' }), `${b.dataset.do} ${b.dataset.svc}`); if (r) setTimeout(() => rerender('services'), 1200); }); };

V.overview.after = () => { $$('[data-open]').forEach(a => a.onclick = e => { e.preventDefault(); openApp(a.dataset.open); }); };

/* ---------------- v0.2 apps ---------------- */
const ICO = {
  folder: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 5h8l2 2h10v13H2z"/></svg>',
  file: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M5 2h9l5 5v15H5z"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 3l15 9-15 9z"/></svg>',
};
const FICO = { d: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M2 5h8l2 2h10v13H2z'/%3E%3C/svg%3E\")", f: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M5 2h9l5 5v15H5z'/%3E%3C/svg%3E\")" };

V.files = async () => {
  S.fs = S.fs || { root: (S.me?.roots?.[0]?.id) || 'data', path: '/', view: 'icon', hist: [], fwd: [], sel: null, q: '' };
  const fs = S.fs;
  const allOf = fs.root.startsWith('@all:') ? fs.root.slice(5) : null;   // the admin's "All Documents" and friends
  const special = fs.root === '@recent' || fs.root === '@trash' || !!allOf;   // places, not folders
  if (!special && S.me?.roots?.length && !S.me.roots.some(r => r.id === fs.root)) Object.assign(fs, { root: S.me.roots[0].id, path: '/', hist: [], fwd: [] });
  const [roots, list] = await Promise.all([api('/files/roots'), allOf ? api(`/files/all?folder=${encodeURIComponent(allOf)}`) : special ? api(fs.root === '@recent' ? '/files/recent' : '/files/trash') : api(`/files/list?root=${encodeURIComponent(fs.root)}&path=${encodeURIComponent(fs.path)}`)]);
  S.roots = roots.roots || []; S.fsDemo = !!list.demo; S.trashItems = fs.root === '@trash' ? (list.items || []) : null;
  const ql = fs.q.toLowerCase();
  const entries = (list.entries || []).filter(e => !ql || e.name.toLowerCase().includes(ql));
  const parts = special ? [] : fs.path.split('/').filter(Boolean);
  const rootName = allOf ? 'All ' + allOf : special ? (fs.root === '@recent' ? 'Recents' : 'Trash') : (S.roots.find(r => r.id === fs.root)?.name || fs.root);
  const title = parts.length ? parts[parts.length - 1] : rootName;
  const FAV = isMember() ? [] : [['Home folders', 'data', '/homes', 'users'], ['Shares', 'data', '/shares', 'folder'], ['Media', 'nas', '/arise/media', 'sermons'], ['Automator', 'data', '/automator/ARISE_YouTube_Updater', 'automator'], ['Apps', 'data', '/apps', 'apps'], ['Backups', 'data', '/backups', 'backups']];
  const side = `<div class="finder__side"><h4>Favorites</h4>${FAV.map(f => `<button data-go="${f[1]}|${f[2]}" class="${fs.root === f[1] && fs.path === f[2] ? 'on' : ''}"><i style="--i:${ICONURL[f[3]]}"></i>${esc(f[0])}</button>`).join('')}
    <h4>${isMember() ? 'Your places' : 'Locations'}</h4>${S.roots.filter(r => !r.shared).map(r => `<button data-go="${r.id}|/" class="${fs.root === r.id && fs.path === '/' ? 'on' : ''}"><i style="--i:${ICONURL[r.id === 'nas' ? 'nas' : r.home ? 'users' : r.share ? 'folder' : 'server']}"></i>${esc(r.name)}</button>`).join('')}
    <h4>Places</h4><button data-go="@recent|/" class="${fs.root === '@recent' ? 'on' : ''}"><i style="--i:${ICONURL.recent}"></i>Recents</button><button data-go="@trash|/" class="${fs.root === '@trash' ? 'on' : ''}"><i style="--i:${ICONURL.trash}"></i>Trash</button>
    ${isMember() ? '' : `<h4>Everyone</h4>` + ['Documents', 'Photos', 'Videos', 'Music', 'Downloads'].map(f => `<button data-go="@all:${f}|/" class="${fs.root === '@all:' + f ? 'on' : ''}" title="Every person's ${f} folder, side by side"><i style="--i:${ICONURL.folder}"></i>All ${f}</button>`).join('')}
    ${S.roots.some(r => r.shared) ? `<h4>Shared with me</h4>` + S.roots.filter(r => r.shared).map(r => `<button data-go="${r.id}|/" class="${fs.root === r.id ? 'on' : ''}" title="From ${esc(r.from)}${r.writable ? ', you can edit' : ', read only'}"><i style="--i:${ICONURL.folder}"></i>${esc(r.name)}</button>`).join('') : ''}
    <h4>Sharing</h4><button id="fLinks"><i style="--i:${ICONURL.backups}"></i>Shared links</button><button id="fSharedBy"><i style="--i:${ICONURL.users}"></i>Shared by me</button>
    <div class="fquota" id="fQuota" hidden></div></div>`;
  const tools = special
    ? (fs.root === '@trash' && !isMember() ? `<button class="btn btn--ghost btn--xs" id="fEmpty">Empty Trash…</button>` : '')
    : `<label class="btn btn--ghost btn--xs" for="fsUp">Upload</label><input id="fsUp" type="file" hidden><button class="btn btn--ghost btn--xs" id="fNew">New folder</button>${IS_MAC ? `<button class="btn btn--ghost btn--xs" id="fMac" title="Open this folder in the Mac's Finder, over the share">Open on my Mac</button>` : ''}`;
  const tb = `<div class="finder__tb"><span class="nav"><button id="fBack" ${fs.hist.length ? '' : 'disabled'} title="Back">‹</button><button id="fFwd" ${fs.fwd.length ? '' : 'disabled'} title="Forward">›</button></span><span class="title">${esc(title)}</span>
    <span class="views"><button id="fIcon" class="${fs.view === 'icon' ? 'on' : ''}" title="Icons" ${special ? 'disabled' : ''}>▦</button><button id="fList" class="${fs.view === 'list' || special ? 'on' : ''}" title="List">☰</button></span>
    <input class="search" id="fQ" placeholder="${special ? 'Filter by name' : 'Filter this folder'}" value="${esc(fs.q)}">${tools}</div>`;
  const icon = e => e.dir ? ICONURL.folder : fileIcon(e.name);
  let main, status;
  if (allOf) {
    const es = (list.entries || []).filter(e => !ql || e.name.toLowerCase().includes(ql) || e.owner.toLowerCase().includes(ql));
    status = `${es.length} item${es.length === 1 ? '' : 's'} in ${(list.owners || []).length} ${allOf} folder${(list.owners || []).length === 1 ? '' : 's'}`;
    main = list.error ? `<div class="finder__main empty">${esc(list.error)}</div>` : !es.length ? `<div class="finder__main empty">Nobody has anything in ${esc(allOf)} yet</div>`
      : `<div class="finder__main" id="fMain" style="padding:0"><table class="tbl"><thead><tr><th>Name</th><th>Whose</th><th>Date modified</th><th class="num">Size</th><th>Kind</th></tr></thead><tbody>${es.map(e => `<tr data-n="${esc(e.name)}" data-dir="${e.dir ? 1 : 0}" data-r="${esc(e.root)}" data-p="${esc(e.path)}" tabindex="0"><td class="fname"><i style="--i:${icon(e)}"></i>${esc(e.name)}</td><td><span class="owner">${esc(e.owner)}</span></td><td class="dim">${fmtT(e.mtime)}</td><td class="num dim">${e.dir ? '—' : fmtB(e.size)}</td><td class="dim">${e.dir ? 'Folder' : kindOf(e.name)}</td></tr>`).join('')}</tbody></table></div>`;
  } else if (fs.root === '@recent') {
    const hits = (list.hits || []).filter(h => !ql || h.name.toLowerCase().includes(ql));
    status = `${hits.length} file${hits.length === 1 ? '' : 's'} changed in the last ${list.days || 7} days${list.truncated ? ' (the newest 200)' : ''}`;
    main = !hits.length ? `<div class="finder__main empty">${list.error ? esc(list.error) : 'Nothing has changed this week'}</div>`
      : `<div class="finder__main" id="fMain" style="padding:0"><table class="tbl"><thead><tr><th>Name</th><th>Where</th><th>Modified</th><th class="num">Size</th></tr></thead><tbody>${hits.map(h => `<tr data-n="${esc(h.name)}" data-dir="0" data-r="${esc(h.root)}" data-p="${esc(h.path)}" tabindex="0"><td class="fname"><i style="--i:${fileIcon(h.name)}"></i>${esc(h.name)}</td><td class="dim">${esc(h.where || '')}</td><td class="dim">${fmtT(h.mtime)}</td><td class="num dim">${fmtB(h.size)}</td></tr>`).join('')}</tbody></table></div>`;
  } else if (fs.root === '@trash') {
    const items = (list.items || []).filter(t => !ql || t.name.toLowerCase().includes(ql));
    status = `${items.length} item${items.length === 1 ? '' : 's'} · gone for good after ${list.days || 30} days`;
    main = !items.length ? `<div class="finder__main empty">The Trash is empty</div>`
      : `<div class="finder__main" id="fMain" style="padding:0"><table class="tbl"><thead><tr><th>Name</th><th>Was in</th>${list.admin ? '<th>By</th>' : ''}<th>Deleted</th><th class="num">Size</th><th></th></tr></thead><tbody>${items.map(t => { const i = (list.items || []).indexOf(t); return `<tr data-t="${i}" tabindex="0"><td class="fname"><i style="--i:${t.dir ? ICONURL.folder : fileIcon(t.name)}"></i>${esc(t.name)}</td><td class="dim">${esc(t.label)}/${esc(t.original.split('/').slice(0, -1).join('/'))}</td>${list.admin ? `<td class="dim">${esc(t.user)}${t.from === 'mac' ? ' <small>(Mac)</small>' : ''}</td>` : ''}<td class="dim">${fmtT(t.when)}</td><td class="num dim">${t.dir ? '—' : fmtB(t.size)}</td><td class="acts"><button class="btn btn--ghost btn--xs" data-back="${i}">Put Back</button></td></tr>`; }).join('')}</tbody></table></div>`;
  } else if (list.error) main = `<div class="finder__main empty">${esc(list.error)}</div>`;
  else if (!entries.length) main = `<div class="finder__main empty">${fs.q ? 'Nothing matches' : 'Empty folder'}</div>`;
  else if (fs.view === 'icon') main = `<div class="finder__main" id="fMain">${entries.map((e, i) => `<div class="fi ${fs.sel === e.name ? 'sel' : ''}" data-n="${esc(e.name)}" data-dir="${e.dir ? 1 : 0}" tabindex="0"><i class="fico" style="--i:${icon(e)}"></i><span>${esc(e.name)}</span></div>`).join('')}</div>`;
  else main = `<div class="finder__main" id="fMain" style="padding:0"><table class="tbl"><thead><tr><th>Name</th><th>Date modified</th><th class="num">Size</th><th>Kind</th></tr></thead><tbody>${entries.map(e => `<tr class="${fs.sel === e.name ? 'sel' : ''}" data-n="${esc(e.name)}" data-dir="${e.dir ? 1 : 0}" tabindex="0"><td class="fname"><i style="--i:${icon(e)}"></i>${esc(e.name)}</td><td class="dim">${fmtT(e.mtime)}</td><td class="num dim">${e.dir ? '—' : fmtB(e.size)}</td><td class="dim">${e.dir ? 'Folder' : kindOf(e.name)}</td></tr>`).join('')}</tbody></table></div>`;
  const crumbs = special ? `<button data-go="${fs.root}|/">${esc(rootName)}</button>` : [`<button data-go="${fs.root}|/">${esc(rootName)}</button>`].concat(parts.map((p, i) => `<span>›</span><button data-go="${fs.root}|/${parts.slice(0, i + 1).join('/')}">${esc(p)}</button>`)).join('');
  const path = `<div class="finder__path">${crumbs}<span class="st">${status || `${entries.length} item${entries.length === 1 ? '' : 's'}`}${list.demo ? ' · sample' : ''}</span></div>`;
  return `<div class="finder">${side}${tb}${main}${path}</div>`;
};
const ICONURL = {
  folder: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cpath d='M4 14h20l6 6h30v32H4z' fill='%23D6222D'/%3E%3Cpath d='M4 26h56v26H4z' fill='%23DB3F48'/%3E%3C/svg%3E\")",
  file: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cpath d='M14 4h24l14 14v42H14z' fill='%23F4F2F0'/%3E%3Cpath d='M38 4v14h14z' fill='%23c9c5c0'/%3E%3C/svg%3E\")",
  image: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cpath d='M14 4h24l14 14v42H14z' fill='%23F4F2F0'/%3E%3Cpath d='M38 4v14h14z' fill='%23c9c5c0'/%3E%3Cpath d='M20 50l10-14 8 9 5-6 7 11z' fill='%23D6222D'/%3E%3Ccircle cx='24' cy='30' r='4' fill='%23D6222D'/%3E%3C/svg%3E\")",
  text: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cpath d='M14 4h24l14 14v42H14z' fill='%23F4F2F0'/%3E%3Cpath d='M38 4v14h14z' fill='%23c9c5c0'/%3E%3Cpath d='M20 30h24v3H20zm0 8h24v3H20zm0 8h16v3H20z' fill='%236A6A6E'/%3E%3C/svg%3E\")",
  code: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cpath d='M14 4h24l14 14v42H14z' fill='%230A0A0C' stroke='%236A6A6E' stroke-width='2'/%3E%3Cpath d='M26 32l-6 6 6 6M38 32l6 6-6 6' fill='none' stroke='%23DB3F48' stroke-width='3'/%3E%3C/svg%3E\")",
  video: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cpath d='M14 4h24l14 14v42H14z' fill='%230A0A0C' stroke='%236A6A6E' stroke-width='2'/%3E%3Cpath d='M26 30l16 9-16 9z' fill='%23D6222D'/%3E%3C/svg%3E\")",
  zip: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cpath d='M14 4h24l14 14v42H14z' fill='%23F4F2F0'/%3E%3Cpath d='M28 4h4v6h-4zm0 10h4v6h-4zm0 10h4v6h-4zm0 10h4v6h-4z' fill='%236A6A6E'/%3E%3C/svg%3E\")",
  server: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect x='8' y='10' width='48' height='18' fill='%231C1C22' stroke='%236A6A6E' stroke-width='2'/%3E%3Crect x='8' y='36' width='48' height='18' fill='%231C1C22' stroke='%236A6A6E' stroke-width='2'/%3E%3Ccircle cx='16' cy='19' r='3' fill='%233DBE7A'/%3E%3Ccircle cx='16' cy='45' r='3' fill='%233DBE7A'/%3E%3C/svg%3E\")",
  nas: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect x='10' y='6' width='44' height='52' fill='%231C1C22' stroke='%236A6A6E' stroke-width='2'/%3E%3Crect x='16' y='12' width='32' height='8' fill='%23D6222D'/%3E%3Crect x='16' y='24' width='32' height='8' fill='%23DB3F48'/%3E%3Crect x='16' y='36' width='32' height='8' fill='%23DB3F48'/%3E%3Crect x='16' y='48' width='32' height='6' fill='%233a3a40'/%3E%3C/svg%3E\")",
  users: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm0 2c-4 0-7 2-7 5v2h14v-2c0-3-3-5-7-5zm8-2a3 3 0 1 0 0-6 3 3 0 0 0 0 6z'/%3E%3C/svg%3E\")",
  sermons: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M2 5h20v14H2zm8 3v8l6-4z'/%3E%3C/svg%3E\")",
  automator: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M6 3l15 9-15 9z'/%3E%3C/svg%3E\")",
  apps: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M3 3h5v5H3zm7 0h5v5h-5zm7 0h5v5h-5zM3 10h5v5H3zm7 0h5v5h-5zm7 0h5v5h-5zM3 17h5v5H3zm7 0h5v5h-5zm7 0h5v5h-5z'/%3E%3C/svg%3E\")",
  backups: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 2l9 4v6c0 5-4 9-9 10-5-1-9-5-9-10V6z'/%3E%3C/svg%3E\")",
  recent: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 2a8 8 0 1 1 0 16 8 8 0 0 1 0-16zm-1 3h2v5.6l3.5 2-1 1.7L11 13.2z'/%3E%3C/svg%3E\")",
  trash: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M9 2h6l1 2h5v2H3V4h5zM5 7h14l-1.2 14H6.2zm4 2v10h2V9zm4 0v10h2V9z'/%3E%3C/svg%3E\")",
};
// Data URIs land inside double-quoted style="" attributes, so they must carry single quotes only.
const _sq = u => u.replace(/'/g, '%27').replace(/"/g, "'");
for (const k in ICONURL) ICONURL[k] = _sq(ICONURL[k]);
for (const k in FICO) FICO[k] = _sq(FICO[k]);
function kindOf(n) { const e = (n.split('.').pop() || '').toLowerCase(); return ({ jpg: 'JPEG image', jpeg: 'JPEG image', png: 'PNG image', gif: 'GIF image', webp: 'WebP image', svg: 'SVG image', md: 'Markdown', txt: 'Plain text', csv: 'CSV', json: 'JSON', yaml: 'YAML', yml: 'YAML', toml: 'TOML', py: 'Python', js: 'JavaScript', sh: 'Shell script', bat: 'Batch file', pdf: 'PDF', mp4: 'MPEG-4 movie', mov: 'QuickTime movie', mp3: 'MP3 audio', wav: 'WAV audio', zip: 'ZIP archive', gz: 'Gzip archive', xlsx: 'Excel workbook', docx: 'Word document', pptx: 'PowerPoint', git: 'Git repository' })[e] || (e ? e.toUpperCase() + ' file' : 'Document'); }
function fileIcon(n) { const e = (n.split('.').pop() || '').toLowerCase(); if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'heic'].includes(e)) return ICONURL.image; if (['md', 'txt', 'csv', 'log', 'pdf', 'docx', 'xlsx', 'pptx'].includes(e)) return ICONURL.text; if (['py', 'js', 'sh', 'bat', 'json', 'yaml', 'yml', 'toml', 'html', 'css', 'ps1'].includes(e)) return ICONURL.code; if (['mp4', 'mov', 'mkv', 'webm', 'mp3', 'wav', 'm4a'].includes(e)) return ICONURL.video; if (['zip', 'gz', 'tgz', 'tar', '7z', 'dmg'].includes(e)) return ICONURL.zip; return ICONURL.file; }
function fsNav(root, path, pushHist = true) { const fs = S.fs; if (pushHist) { fs.hist.push({ root: fs.root, path: fs.path }); fs.fwd = []; } fs.root = root; fs.path = (path || '/').replace(/\/+/g, '/') || '/'; fs.sel = null; fs.q = ''; rerender('files'); }
V.files.after = root => {
  const fs = S.fs;
  const special = fs.root === '@recent' || fs.root === '@trash';
  $$('[data-go]', root).forEach(b => b.onclick = () => { const [r, p] = b.dataset.go.split('|'); fsNav(r, p); });
  const fl = $('#fLinks', root); if (fl) fl.onclick = () => linksModal();
  const fsb = $('#fSharedBy', root); if (fsb) fsb.onclick = () => sharedByModal();
  quotaLine(root, fs);
  $('#fBack', root).onclick = () => { const h = fs.hist.pop(); if (!h) return; fs.fwd.push({ root: fs.root, path: fs.path }); fs.root = h.root; fs.path = h.path; fs.sel = null; rerender('files'); };
  $('#fFwd', root).onclick = () => { const h = fs.fwd.pop(); if (!h) return; fs.hist.push({ root: fs.root, path: fs.path }); fs.root = h.root; fs.path = h.path; fs.sel = null; rerender('files'); };
  $('#fIcon', root).onclick = () => { fs.view = 'icon'; rerender('files'); }; $('#fList', root).onclick = () => { fs.view = 'list'; rerender('files'); };
  const q = $('#fQ', root); q.oninput = () => { fs.q = q.value; clearTimeout(S.fqT); S.fqT = setTimeout(() => rerender('files'), 250); };
  const up = $('#fsUp', root); if (up) up.onchange = async e => { const f = e.target.files[0]; if (!f) return;
    if (f.size > 8 * 1024 * 1024) { const ok = await uploadBig(f, fs.root, fs.path); if (ok) rerender('files'); return; }
    const fd = new FormData(); fd.append('root', fs.root); fd.append('path', fs.path); fd.append('file', f); const r = await act($('label[for=fsUp]', root), () => api('/files/upload', { method: 'POST', body: fd }), `Uploaded ${f.name}`); if (r) rerender('files'); };
  const nf = $('#fNew', root); if (nf) nf.onclick = () => modal(`<h2>New folder</h2><div class="field"><label>Name</label><input id="nfName" placeholder="untitled folder"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="nfGo">Create</button></div>`, m => { $('#nfGo', m).onclick = async e => { const r = await act(e.target, () => api('/files/mkdir', { method: 'POST', body: { root: fs.root, path: fs.path, name: $('#nfName', m).value.trim() } }), 'Folder created'); if (r && r.ok !== false) { m.close(); rerender('files'); } }; $('#nfName', m).focus(); });
  const mac = $('#fMac', root); if (mac) mac.onclick = () => openOnMac(fs.root, fs.path);
  const emp = $('#fEmpty', root); if (emp) emp.onclick = () => emptyTrash();
  if (fs.root === '@trash') {
    $$('[data-back]', root).forEach(b => b.onclick = async () => { const t = S.trashItems[+b.dataset.back]; if (!t) return; const r = await act(b, () => api('/files/trash/restore', { method: 'POST', body: { base: t.base, user: t.user, rel: t.rel } }), `${t.name} is back in ${t.label}/${t.original.split('/').slice(0, -1).join('/') || ''}`); if (r && r.ok !== false) { if (r.renamed) toast(`Put back as “${r.restored.split('/').pop()}”: the old name was taken`, 'warn', 6000); rerender('files'); } });
    $$('[data-t]', root).forEach(el => el.oncontextmenu = e => { e.preventDefault(); const t = S.trashItems[+el.dataset.t]; ctxMenu(e.clientX, e.clientY, [['Put Back', () => $(`[data-back="${el.dataset.t}"]`, root).click()], null, ['Copy original path', () => copyText(t.label + '/' + t.original)]]); });
    return;
  }
  if (fs.root.startsWith('@all:')) {
    $$('[data-p]', root).forEach(el => {
      const r = el.dataset.r, p = el.dataset.p, n = el.dataset.n, dir = el.dataset.dir === '1';
      const go = () => dir ? fsNav(r, p) : isText(n) ? editText(r, p, n) : quickLook(r, p, n);
      el.ondblclick = go; el.onkeydown = e => { if (e.key === 'Enter') go(); };
      el.oncontextmenu = e => { e.preventDefault(); ctxMenu(e.clientX, e.clientY, [['Open', go], ['Show in their folder', () => fsNav(r, p.split('/').slice(0, -1).join('/') || '/')], dir ? null : ['Download', () => finderDownload(r, p)], null, ['Get Info', () => getInfo(n, dir, p, r)], ['Previous Versions…', () => versionsModal(r, p, n)], null, ['Move to Trash', () => trashIt(r, p, n)]]); };
    });
    return;
  }
  if (fs.root === '@recent') {
    $$('[data-p]', root).forEach(el => {
      const r = el.dataset.r, p = el.dataset.p, n = el.dataset.n;
      el.ondblclick = () => quickLook(r, p, n);
      el.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); quickLook(r, p, n); } };
      el.oncontextmenu = e => { e.preventDefault(); ctxMenu(e.clientX, e.clientY, [['Quick Look', () => quickLook(r, p, n)], ['Show in folder', () => fsNav(r, p.split('/').slice(0, -1).join('/') || '/')], isText(n) ? ['Edit', () => editText(r, p, n)] : null, ['Download', () => finderDownload(r, p)], null, ['Get Info', () => getInfo(n, false, p, r)], ['Previous Versions…', () => versionsModal(r, p, n)], null, ['Share Link…', () => shareLink(r, p, n)]]); };
    });
    return;
  }
  const items = $$('[data-n]', root);
  const pathOf = el => (fs.path === '/' ? '' : fs.path) + '/' + el.dataset.n;
  const open = el => { const n = el.dataset.n; if (el.dataset.dir === '1') fsNav(fs.root, pathOf(el)); else if (isText(n)) editText(fs.root, pathOf(el), n); else quickLook(fs.root, pathOf(el), n); };
  items.forEach(el => {
    el.onclick = e => { items.forEach(x => x.classList.remove('sel')); el.classList.add('sel'); fs.sel = el.dataset.n; };
    el.ondblclick = () => open(el);
    el.onkeydown = e => {
      if (e.key === 'Enter') open(el);
      if (e.key === ' ' && !e.metaKey && !e.ctrlKey) { e.preventDefault(); if (el.dataset.dir !== '1') quickLook(fs.root, pathOf(el), el.dataset.n); }
      if ((e.key === 'Backspace' && (e.metaKey || e.ctrlKey)) || e.key === 'Delete') { e.preventDefault(); trashIt(fs.root, pathOf(el), el.dataset.n); }
    };
    el.oncontextmenu = e => { e.preventDefault(); el.click(); const p = pathOf(el), n = el.dataset.n, dir = el.dataset.dir === '1';
      ctxMenu(e.clientX, e.clientY, [
        ['Open', () => open(el)],
        dir ? null : ['Quick Look', () => quickLook(fs.root, p, n)],
        !dir && isText(n) ? ['Edit', () => editText(fs.root, p, n)] : null,
        dir ? null : ['Download', () => finderDownload(fs.root, p)],
        ['Compress', () => finderZip(fs.root, p, n)],
        null,
        ['Get Info', () => getInfo(n, dir, p, fs.root)],
        ['Previous Versions…', () => versionsModal(fs.root, p, n)],
        IS_MAC && dir ? ['Open on my Mac', () => openOnMac(fs.root, p)] : null,
        null,
        ['Share Link…', () => shareLink(fs.root, p, n)],
        canShareWith(fs.root, p) ? ['Share with…', () => shareWith(fs.root, p, n)] : null,
        null,
        ['Copy path', () => copyText((S.roots.find(r => r.id === fs.root)?.path || '') + p)],
        null,
        ['Move to Trash', () => trashIt(fs.root, p, n)],
      ]); };
  });
  const main = $('#fMain', root); if (main) main.oncontextmenu = e => { if (e.target !== main) return; e.preventDefault(); ctxMenu(e.clientX, e.clientY, [['New folder', () => $('#fNew', root).click()], ['Upload here', () => $('#fsUp', root).click()], IS_MAC ? ['Open on my Mac', () => openOnMac(fs.root, fs.path)] : null, null, ['Get Info', () => getInfo(fs.path.split('/').pop() || (S.roots.find(r => r.id === fs.root)?.name || ''), true, fs.path, fs.root)], null, ['Show as icons', () => { fs.view = 'icon'; rerender('files'); }], ['Show as list', () => { fs.view = 'list'; rerender('files'); }], null, ['Refresh', () => rerender('files')]]); };
};
const isText = n => /\.(txt|md|csv|json|ya?ml|toml|log)$/i.test(n || '');
// A big upload goes up in 8 MB pieces and survives a dropped connection or a closed
// laptop: start again with the same file and the server says where it left off.
async function uploadBig(f, root, path) {
  if (f.size > 10 * 1024 ** 3) { toast(`${f.name} is over the 10 GB limit; copy it onto the share from a Mac`, 'bad', 8000); return false; }
  const fp = `${f.name}|${f.size}|${f.lastModified}`;
  const t = document.createElement('div'); t.className = 'toast'; t.innerHTML = `<b>${esc(f.name)}</b><br><span class="up__pct">starting…</span><div class="up__bar"><i style="width:0"></i></div>`; $('#toasts').appendChild(t);
  const say = (pct, msg) => { $('.up__pct', t).textContent = msg; $('.up__bar i', t).style.width = pct + '%'; };
  const done = (ok, msg) => { t.className = 'toast ' + (ok ? 'ok' : 'bad'); say(ok ? 100 : 0, msg); setTimeout(() => t.remove(), ok ? 5000 : 12000); };
  let st;
  try { st = await api('/files/upload/start', { method: 'POST', body: { root, path, name: f.name, size: f.size, fingerprint: fp } }); } catch (e) { done(false, e.message); return false; }
  if (st.ok === false) { done(false, st.err); return false; }
  if (st.demo) { for (let i = 1; i <= 5; i++) { await new Promise(r => setTimeout(r, 120)); say(i * 20, `sample mode: pretending to send ${fmtB(f.size * i / 5)} of ${fmtB(f.size)}`); } done(true, 'sample mode: nothing was stored'); return true; }
  let offset = st.offset || 0; const chunk = st.chunk || 8 * 1024 * 1024; let fails = 0;
  if (st.resumed) say(Math.round(offset / f.size * 100), `resuming from ${fmtB(offset)}`);
  while (offset < f.size) {
    const piece = f.slice(offset, Math.min(f.size, offset + chunk));
    try {
      const j = S.demoOnly ? await api(`/files/upload/chunk?token=${encodeURIComponent(st.token)}&offset=${offset}`, { method: 'PUT', body: piece })
        : await (await fetch(`/api/files/upload/chunk?token=${encodeURIComponent(st.token)}&offset=${offset}`, { method: 'PUT', body: piece, credentials: 'same-origin' })).json();
      if (j.ok === false) { done(false, j.err); return false; }
      offset = j.offset; fails = 0;
      say(Math.round(offset / f.size * 100), `${fmtB(offset)} of ${fmtB(f.size)}`);
    } catch (e) {
      if (++fails > 30) { done(false, `Lost the connection; pick the same file again to resume from ${fmtB(offset)}`); return false; }
      say(Math.round(offset / f.size * 100), `connection dropped, retrying (${fails})…`); await new Promise(r => setTimeout(r, Math.min(15000, 1500 * fails)));
      try { const q = await api(`/files/upload/status?token=${encodeURIComponent(st.token)}`); if (q.ok !== false) offset = q.offset; } catch {}
    }
  }
  let fin; try { fin = await api('/files/upload/finish', { method: 'POST', body: { token: st.token } }); } catch (e) { done(false, e.message); return false; }
  if (fin.ok === false) { done(false, fin.err); return false; }
  done(true, `Uploaded ${fmtB(f.size)}`); return true;
}
function finderDownload(root, p) { if (S.demoOnly || S.fsDemo) return toast('Preview: nothing to download'); location.href = `/api/files/download?root=${encodeURIComponent(root)}&path=${encodeURIComponent(p)}`; }
function finderZip(root, p, name) { if (S.demoOnly || S.fsDemo) return toast(`Preview: on the server this downloads ${name}.zip`); toast(`Zipping ${name}… the download starts when it is ready`); location.href = `/api/files/zip?root=${encodeURIComponent(root)}&path=${encodeURIComponent(p)}`; }
async function openOnMac(root, p) {
  let r; try { r = await api(`/files/info?root=${encodeURIComponent(root)}&path=${encodeURIComponent(p)}`); } catch (e) { return toast(e.message, 'bad'); }
  if (!r.smb) return toast('No share reaches that folder from a Mac', 'warn');
  if (S.demoOnly) return toast(`Preview: on a Mac this opens ${r.smb}`);
  location.href = r.smb;
}
function trashIt(root, p, name) {
  const r = S.roots.find(x => x.id === root); if (r && r.writable === false) return toast('That share is read-only for you', 'warn');
  confirmType(`Move “${name}” to the Trash`, name, `It sits in the Trash for 30 days, where Put Back brings it home; after that it is gone. A Mac's delete on the share lands in the same Trash.`, async () => {
    const x = await api('/files/trash', { method: 'POST', body: { root, path: p, confirm: name } });
    if (x.ok === false) throw new Error(x.err);
    toast(x.demo ? 'Sample mode: nothing moved' : `${name} is in the Trash`); S.fs.sel = null; rerender('files');
  });
}
async function emptyTrash() {
  const items = S.trashItems || []; const labels = [...new Set(items.map(t => t.label))];
  if (!labels.length) return toast('The Trash is already empty');
  modal(`<h2>Empty Trash</h2><p class="muted">Everyone's deleted items in one share go for good. The nightly backup does not keep the Trash.</p>
    <div class="field" style="margin-top:12px"><label>Which share</label><select id="etShare">${labels.map(l => `<option>${esc(l)}</option>`).join('')}</select></div>
    <div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn btn--danger" id="etGo">Continue…</button></div>`, m => {
    $('#etGo', m).onclick = () => { const share = $('#etShare', m).value; m.close();
      confirmType(`Empty the Trash of “${share}”`, share, `${items.filter(t => t.label === share).length} item(s) from every user. There is no undo.`, async () => {
        const x = await api('/files/trash/empty', { method: 'POST', body: { share, confirm: share } });
        if (x.ok === false) throw new Error(x.err);
        toast(x.demo ? 'Sample mode: nothing removed' : `Emptied: ${x.removed} item(s) gone`); rerender('files');
      }); };
  });
}
async function getInfo(name, dir, p, root) {
  root = root || S.fs.root;
  let r; try { r = await api(`/files/info?root=${encodeURIComponent(root)}&path=${encodeURIComponent(p)}`); } catch (e) { return toast(e.message, 'bad'); }
  if (r.error) return toast(r.error, 'bad');
  const isDir = r.dir ?? dir; const n = r.name || name;
  const size = isDir ? `${r.size_complete ? '' : 'at least '}${fmtB(r.size)}${r.files != null ? ` · ${r.files.toLocaleString()} files${r.size_complete ? '' : ' counted so far'}` : ''}` : fmtB(r.size);
  const acc = r.access || {};
  const who = (acc.who || []).join(', ') || '—'; const write = (acc.write || []).join(', ');
  modal(`<div class="about"><div class="flame" style="background:${isDir ? ICONURL.folder : fileIcon(n)} center/70% no-repeat #000"></div><div><h2 style="font-size:20px;word-break:break-word">${esc(n)}</h2>
    <dl class="kv"><dt>Kind</dt><dd>${isDir ? 'Folder' : kindOf(n)}</dd><dt>Size</dt><dd>${size}</dd><dt>Owner</dt><dd>${esc(r.owner || '—')}${r.group ? ` <span class="muted">(${esc(r.group)})</span>` : ''}</dd><dt>Created</dt><dd>${fmtT(r.created)}</dd><dt>Modified</dt><dd>${fmtT(r.modified)}</dd>
    <dt>Where</dt><dd class="mono" style="font-size:12px;word-break:break-all">${esc(r.abs || ((S.roots.find(x => x.id === root)?.name || root) + p))}</dd>
    <dt>On a Mac</dt><dd class="mono" style="font-size:12px;word-break:break-all">${r.smb ? esc(r.smb) + ` <button class="btn btn--ghost btn--xs" id="giCopy">Copy</button>` : 'not on a share'}</dd>
    <dt>Who can open it</dt><dd>${esc(who)}${write && write !== who ? `<br><span class="muted">can change it: ${esc(write)}</span>` : acc.read_only ? '<br><span class="muted">read only for everyone but the write list</span>' : ''}${acc.note ? `<br><small class="muted">${esc(acc.note)}</small>` : ''}</dd></dl></div></div>
    <div class="acts"><button class="btn btn--ghost btn--xs" id="giVers">Previous Versions…</button>${IS_MAC && r.smb && isDir ? `<button class="btn btn--ghost btn--xs" id="giMac">Open on my Mac</button>` : ''}<span class="spacer"></span><button class="btn btn--ghost" data-close>Close</button></div>`, m => {
    const c = $('#giCopy', m); if (c) c.onclick = e => copyText(r.smb, e.target);
    $('#giVers', m).onclick = () => { m.close(); versionsModal(root, p, n); };
    const mb = $('#giMac', m); if (mb) mb.onclick = () => openOnMac(root, p);
  });
}
async function versionsModal(root, p, name) {
  let r; try { r = await api(`/files/versions?root=${encodeURIComponent(root)}&path=${encodeURIComponent(p)}`); } catch (e) { return toast(e.message, 'bad'); }
  const vs = r.versions || [];
  const body = !r.backed_up ? `<p class="note">Not backed up: nothing covers this place. ${/synology|recordings/i.test(p + (r.path || '')) ? 'The recordings live on the Synology and its RAID is their protection (docs/BACKUPS.md).' : 'Only the shares, the homes, the automator and the server config are in the nightly backup.'}</p>`
    : r.error ? `<p class="note">Could not read the backup: ${esc(r.error)}</p>`
    : !vs.length ? `<p class="muted">The backup has no copy of this yet. New files appear after tonight's 03:00 run.</p>`
    : `<p class="muted">From the nightly “${esc(r.job_name || r.job)}” backup. A restore lands <b>beside</b> the file as “${esc(name.replace(/(\.[^.]+)?$/, ' (restored DATE)$1'))}”; nothing is overwritten.</p>
       <table class="tbl" style="margin-top:10px"><thead><tr><th>Backed up</th><th>File dated</th><th class="num">Size</th><th></th></tr></thead><tbody>${vs.map(v => `<tr><td>${fmtT(v.time)}</td><td class="dim">${fmtT(v.mtime)}</td><td class="num dim">${v.dir ? 'folder' : fmtB(v.size)}</td><td class="acts"><button class="btn btn--ghost btn--xs" data-snap="${esc(v.snapshot)}">Restore</button></td></tr>`).join('')}</tbody></table>`;
  modal(`<h2>Previous versions of “${esc(name)}”</h2>${body}${r.demo ? '<p class="muted" style="margin-top:8px">Sample data.</p>' : ''}<div class="acts"><button class="btn btn--ghost" data-close>Close</button></div>`, m => {
    $$('[data-snap]', m).forEach(b => b.onclick = async () => { const x = await act(b, () => api('/files/versions/restore', { method: 'POST', body: { root, path: p, snapshot: b.dataset.snap } })); if (x && x.ok !== false) { toast(x.demo ? `Sample mode: would restore as “${x.restored}”` : `Restored as “${x.restored}” beside the original`, 'ok', 7000); m.close(); rerender('files'); } });
  });
}
async function editText(root, p, name) {
  let r; try { r = await api(`/files/text?root=${encodeURIComponent(root)}&path=${encodeURIComponent(p)}`); } catch (e) { return toast(e.message, 'bad'); }
  if (r.ok === false) return toast(r.err, 'bad', 7000);
  const md = /\.md$/i.test(name); const ro = (S.roots || []).find(x => x.id === root)?.writable === false;
  let dirty = false, mtime = r.mtime;
  const m = modal(`<div class="edit"><div class="edit__hd"><h2 style="margin:0;font-size:18px">${esc(name)}</h2>${md ? `<span class="tabs edit__tabs" id="edTabs"><button class="active" data-t="edit">Edit</button><button data-t="prev">Preview</button></span>` : ''}<span class="spacer"></span><small class="muted" id="edSt">${fmtB(r.bytes)}${ro ? ' · read only' : ''}${r.demo ? ' · sample' : ''}</small></div>
    <div data-tab="edit"><textarea id="edText" spellcheck="false" ${ro ? 'readonly' : ''}>${esc(r.text)}</textarea></div><div data-tab="prev" hidden><div class="md" id="edPrev"></div></div>
    <div class="acts"><span class="muted" style="margin-right:auto">${kbd('⌘S')} saves</span><button class="btn btn--ghost" id="edClose">Close</button>${ro ? '' : '<button class="btn" id="edSave">Save</button>'}</div></div>`, async m => {
    const ta = $('#edText', m);
    ta.oninput = () => { dirty = true; $('#edSt', m).textContent = 'unsaved changes'; };
    const save = async () => { if (ro) return; const b = $('#edSave', m); const x = await act(b, () => api('/files/text', { method: 'PUT', body: { root, path: p, text: ta.value, mtime } })); if (x && x.ok !== false) { dirty = false; mtime = x.mtime || mtime; $('#edSt', m).textContent = x.demo ? 'sample mode: not saved on a server' : `saved · ${fmtB(x.bytes)}`; } };
    const sb = $('#edSave', m); if (sb) sb.onclick = save;
    ta.onkeydown = e => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') { e.preventDefault(); save(); } if (e.key === 'Tab') { e.preventDefault(); const s = ta.selectionStart; ta.setRangeText('  ', s, ta.selectionEnd, 'end'); dirty = true; } };
    const tabs = $('#edTabs', m); if (tabs) $$('button', tabs).forEach(b => b.onclick = async () => { $$('button', tabs).forEach(x => x.classList.toggle('active', x === b)); $$('[data-tab]', m).forEach(pn => pn.hidden = pn.dataset.tab !== b.dataset.t); if (b.dataset.t === 'prev') { $('#edPrev', m).innerHTML = '<p class="muted">rendering…</p>'; try { const x = await api('/files/text/preview', { method: 'POST', body: { text: ta.value } }); $('#edPrev', m).innerHTML = x.html || '<p class="muted">(the preview renders on the server)</p>'; } catch (e) { $('#edPrev', m).innerHTML = `<p class="note">${esc(e.message)}</p>`; } } });
    const guard = ev => { if (dirty && !confirm(`Discard the unsaved changes to ${name}?`)) { ev.preventDefault(); return false; } return true; };
    m.addEventListener('cancel', ev => { if (!guard(ev)) ev.preventDefault(); }, { once: false });
    $('#edClose', m).onclick = () => { if (guard({ preventDefault() {} })) m.close(); };
    m.classList.add('modal--wide'); m.addEventListener('close', () => m.classList.remove('modal--wide'), { once: true });
    ta.focus();
  });
}
function shareLink(root, p, name) {
  // Round 7, 47: only admins make an outside link, and each ends after 7 days.
  if (S.role !== 'admin') return modal(`<h2>Share “${esc(name)}”</h2><p class="muted" style="margin:10px 0 14px">A link that works without signing in is made by an administrator, and it ends after 7 days. For people at church, use <b>Share with…</b>: it shows up in their Shared with me.</p><div class="acts"><button class="btn" data-close>OK</button></div>`);
  const days = S.me?.links_days || 7;
  modal(`<h2>Share “${esc(name)}”</h2><p class="muted">Anyone with the link can download it, no sign-in, until it ends (7 days at most) or you remove it. Folders arrive as a zip.</p>
    <div class="row" style="gap:10px;margin:12px 0"><label>Ends <select id="slDays"><option value="1">in 1 day</option><option value="3">in 3 days</option><option value="7" ${days >= 7 ? 'selected' : ''}>in 7 days</option></select></label><input id="slNote" placeholder="Note to yourself (optional)" style="flex:1"></div>
    <div id="slOut"></div><div class="acts"><button class="btn btn--ghost" data-close>Close</button><button class="btn" id="slGo">Make link</button></div>`, () => {
    $('#slGo').onclick = async () => { const b = $('#slGo'); b.disabled = true; try { const r = await api('/links', { method: 'POST', body: { root, path: p, days: +$('#slDays').value, note: $('#slNote').value } });
      if (r.ok === false) throw new Error(r.err); const url = r.url || (location.origin + '/s/' + r.token);
      $('#slOut').innerHTML = `<div class="log pre" style="user-select:all;word-break:break-all">${esc(url)}</div><div class="row" style="gap:8px;margin-top:8px"><button class="btn btn--xs" id="slCopy">Copy link</button><span class="muted">${r.demo ? 'sample: this link is not real' : r.preview ? 'preview: this link only opens on the real server' : r.link.expires ? 'until ' + esc(r.link.expires) : 'until you remove it'}</span></div>`;
      $('#slCopy').onclick = e => copyText(url, e.target); b.textContent = 'Made'; } catch (e) { toast(e.message, 'bad'); b.disabled = false; } };
  });
}
async function linksModal() {
  let r; try { r = await api('/links'); } catch (e) { return toast(e.message, 'bad'); }
  const rows = r.links || [];
  modal(`<h2>Shared links</h2><p class="muted">${rows.length ? 'Remove a link and it stops working at once.' : 'Nothing shared yet. Right-click a file in Finder and pick Share Link.'}</p>
    <table class="tbl" style="margin-top:10px"><thead><tr><th>File</th><th>Until</th><th class="num">Downloads</th>${S.role === 'admin' ? '<th>By</th>' : ''}<th></th></tr></thead><tbody>${rows.map(l => `<tr class="${l.expired ? 'dim' : ''}"><td>${esc(l.name)}<br><small class="muted">${esc(l.note || l.root + l.path)}</small></td><td>${l.expired ? 'expired' : l.expires ? esc(l.expires.replace('T', ' ')) : 'never'}</td><td class="num">${l.downloads || 0}</td>${S.role === 'admin' ? `<td>${esc(l.user)}</td>` : ''}<td><button class="btn btn--ghost btn--xs" data-copy="${esc(l.token)}">Copy</button> <button class="btn btn--ghost btn--xs" data-rm="${esc(l.token)}">Remove</button></td></tr>`).join('')}</tbody></table>
    <div class="acts"><button class="btn btn--ghost" data-close>Close</button></div>`, () => {
    $$('[data-copy]').forEach(b => b.onclick = e => copyText(location.origin + '/s/' + b.dataset.copy, e.target));
    $$('[data-rm]').forEach(b => b.onclick = async () => { const x = await api('/links/' + b.dataset.rm, { method: 'DELETE' }); if (x.ok === false) return toast(x.err, 'bad'); toast('Link removed'); linksModal(); });
  });
}
async function changePassword() {
  let rules = null; try { rules = await api('/me/password/rules'); } catch {}
  const minLen = rules?.min_length || 8;
  modal(`<h2>Change your password</h2><p class="muted">This is your directory password: the same one for the Macs, the shares and this dashboard.</p>
    ${rules?.words?.length ? `<ul class="pwrules" style="margin-top:10px">${rules.words.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : ''}
    <form id="pwf" style="display:grid;gap:8px;margin-top:12px"><input type="password" id="pwOld" placeholder="Current password" autocomplete="current-password"><input type="password" id="pwNew" placeholder="New password (${minLen} or more)" autocomplete="new-password" aria-describedby="pwWord"><div class="pwmeter" id="pwMeter"><i></i></div><div class="pwword" id="pwWord"></div><input type="password" id="pwNew2" placeholder="New password again" autocomplete="new-password">
    <div class="acts"><button type="button" class="btn btn--ghost" data-close>Cancel</button><button class="btn" type="submit">Change</button></div></form>`, () => {
    $('#pwNew').oninput = e => { const pw = e.target.value; const sc = pwScore(pw, S.user); const m = $('#pwMeter'); m.className = 'pwmeter s' + sc; $('i', m).style.width = (sc * 25) + '%'; $('#pwWord').textContent = !pw ? '' : pw.length < minLen ? `${minLen - pw.length} more character${minLen - pw.length === 1 ? '' : 's'}` : PW_WORDS[sc] || 'Weak'; };
    $('#pwf').onsubmit = async e => { e.preventDefault(); if ($('#pwNew').value !== $('#pwNew2').value) return toast('The two new passwords differ', 'warn'); if ($('#pwNew').value.length < minLen) return toast(`At least ${minLen} characters`, 'warn');
      const r = await api('/me/password', { method: 'POST', body: { old: $('#pwOld').value, new: $('#pwNew').value } }).catch(er => ({ ok: false, err: er.message }));
      if (r.ok === false) return toast(r.err, 'bad'); toast(r.demo ? 'Sample mode: nothing changed' : 'Password changed'); $('[data-close]').click(); };
  });
}
async function quickLook(root, p, name) {
  const ql = $('#ql'); $('#qlTitle').textContent = name; const url = `/api/files/view?root=${encodeURIComponent(root)}&path=${encodeURIComponent(p)}`;
  $('#qlDl').href = `/api/files/download?root=${encodeURIComponent(root)}&path=${encodeURIComponent(p)}`; $('#qlDl').onclick = e => { if (S.demoOnly || S.fsDemo) { e.preventDefault(); toast('Preview: nothing to download'); } };
  const body = $('#qlBody'); ql.hidden = false;
  const e = (name.split('.').pop() || '').toLowerCase();
  if (S.demoOnly || S.fsDemo) {
    // The preview shows what was uploaded or typed in it; the sample files are names without content.
    const f = S.demoOnly && window.AriseMock ? window.AriseMock.fileFor(root, p) : null;
    if (f && f.url && ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp'].includes(e)) { body.innerHTML = `<img src="${f.url}" alt="">`; return; }
    if (f && f.url && ['mp4', 'webm', 'mov'].includes(e)) { body.innerHTML = `<video src="${f.url}" controls style="max-width:100%;max-height:100%"></video>`; return; }
    if (f && f.url && ['mp3', 'wav', 'm4a'].includes(e)) { body.innerHTML = `<audio src="${f.url}" controls></audio>`; return; }
    if (f && f.url && e === 'pdf') { body.innerHTML = `<object data="${f.url}" type="application/pdf" style="width:100%;height:100%"></object>`; return; }
    if (f && f.text != null) { body.innerHTML = `<pre>${esc(f.text.slice(0, 200000))}</pre>`; return; }
    body.innerHTML = `<div class="none"><div class="fico" style="--i:${fileIcon(name)}"></div>${esc(kindOf(name))}<br><span style="font-size:12px">${S.demoOnly ? 'A sample file: a name with no content behind it. Upload a file here and Quick Look shows it.' : 'Quick Look shows the real file on the server: images, text, markdown, JSON, PDFs.'}</span></div>`; return;
  }
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp'].includes(e)) body.innerHTML = `<img src="${url}" alt="">`;
  else if (['md', 'txt', 'csv', 'log', 'json', 'yaml', 'yml', 'toml', 'py', 'js', 'sh', 'bat', 'ps1', 'html', 'css', 'conf', 'cfg', 'ini'].includes(e)) { body.innerHTML = '<pre>loading…</pre>'; try { const r = await fetch(url, { credentials: 'same-origin' }); const t = await r.text(); body.innerHTML = `<pre>${esc(t.slice(0, 200000))}</pre>`; } catch { body.innerHTML = '<pre>could not read</pre>'; } }
  else if (e === 'pdf') body.innerHTML = `<object data="${url}" type="application/pdf" style="width:100%;height:100%"></object>`;
  else if (['mp4', 'webm', 'mov'].includes(e)) body.innerHTML = `<video src="${url}" controls style="max-width:100%;max-height:100%"></video>`;
  else if (['mp3', 'wav', 'm4a'].includes(e)) body.innerHTML = `<audio src="${url}" controls></audio>`;
  else body.innerHTML = `<div class="none"><div class="fico" style="--i:${fileIcon(name)}"></div>${esc(kindOf(name))}<br><span style="font-size:12px">No preview for this kind; download it.</span></div>`;
}
function ctxMenu(x, y, items) {
  const c = $('#ctx'); c.innerHTML = items.map(it => it ? `<button>${esc(it[0])}</button>` : '<hr>').join(''); c.hidden = false;
  const fns = items.filter(Boolean); $$('button', c).forEach((b, i) => b.onclick = () => { c.hidden = true; fns[i][1](); });
  c.style.left = Math.min(x, innerWidth - 220) + 'px'; c.style.top = Math.min(y, innerHeight - c.offsetHeight - 10) + 'px';
  const close = ev => { if (!c.contains(ev.target)) { c.hidden = true; document.removeEventListener('pointerdown', close, true); } }; setTimeout(() => document.addEventListener('pointerdown', close, true), 0);
}

V.sermons = async () => {
  const r = await api('/sermons');
  S.sermonKind = S.sermonKind || 'all';
  const kinds = ['all', 'Sunday Service', 'Glory Night', 'Short', 'Conference'];
  const vids = (r.videos || []).filter(v => S.sermonKind === 'all' || v.kind === S.sermonKind);
  return `<div class="fade">
    <div class="toolbar"><span class="mark" style="margin:0"><span class="kicker">${esc(r.handle)} · ${fmtN(r.count)} videos</span></span><span class="spacer"></span><div class="tabs" style="margin:0;border:0" id="smKinds">${kinds.map(k => `<button class="${k === S.sermonKind ? 'active' : ''}" data-k="${esc(k)}">${k === 'all' ? 'All' : esc(k + 's')}</button>`).join('')}</div></div>
    ${r.source === 'sample' || r.demo ? '<p class="note" style="margin-bottom:10px">Sample list. On the server this reads the automator\'s channel inventory (no quota spent) and shows real thumbnails.</p>' : `<p class="note" style="margin-bottom:10px">From <code>${esc(r.source)}</code>, updated ${fmtT(r.updated)}.</p>`}
    <div class="grid"><div class="c8">${vids.map(v => `<div class="sermon"><a class="sermon__th" href="https://www.youtube.com/watch?v=${esc(v.id)}" target="_blank" rel="noopener"><img src="https://i.ytimg.com/vi/${esc(v.id)}/mqdefault.jpg" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'ph',innerHTML:'<i>${ICO.play.replace(/"/g, '&quot;')}</i>'}))"><span class="dur">${esc(v.duration || '')}</span></a>
      <div><h3>${esc(v.title)}</h3><p>${esc(v.kind)}${v.speaker ? ' · ' + esc(v.speaker) : ''} · ${esc(v.published)}${v.views ? ' · ' + fmtN(v.views) + ' views' : ''}${v.privacy && v.privacy !== 'public' ? ` · <span style="color:var(--warn)">${esc(v.privacy)}</span>` : ''}</p><p><a href="https://www.youtube.com/watch?v=${esc(v.id)}" target="_blank" rel="noopener">Watch</a> · <a href="https://studio.youtube.com/video/${esc(v.id)}/edit" target="_blank" rel="noopener">Studio</a> · <span class="mono dim" style="font-size:11.5px">${esc(v.id)}</span></p></div></div>`).join('') || '<div class="empty">Nothing in this group</div>'}</div>
    <div class="c4"><div class="panel panel--flat"><div class="panel__hd"><h3>Playlists</h3></div>${(r.playlists || []).map(p => `<div class="widget__row"><span>${esc(p.title)}</span><a href="https://www.youtube.com/playlist?list=${esc(p.id)}" target="_blank" rel="noopener" style="color:var(--redL);text-decoration:none;font-size:12px">Open</a></div>`).join('')}</div>
      <div class="panel panel--flat" style="margin-top:12px"><div class="panel__hd"><h3>Live</h3></div><p style="font-size:13px;color:var(--text2)">Sundays 10:30 AM and Glory Night Mondays 7 PM stream from StreamYard. <a href="https://www.youtube.com/@arisechurch4147/live" target="_blank" rel="noopener" style="color:var(--redL)">Open the live page</a>.</p><p class="note" style="margin-top:10px;font-size:12px">StreamYard holds its own copy of the title and description and pushes it to YouTube and Facebook when saved there.</p></div></div></div>
  </div>`;
};
V.sermons.after = () => { $$('#smKinds button').forEach(b => b.onclick = () => { S.sermonKind = b.dataset.k; rerender('sermons'); }); };

V.bible = async () => {
  S.bible = S.bible || { ref: 'John 3:16', tr: 'web' };
  const [tr, r] = await Promise.all([api('/bible/translations'), api(`/bible?ref=${encodeURIComponent(S.bible.ref)}&translation=${encodeURIComponent(S.bible.tr)}`)]);
  const chips = ['John 3:16', 'Psalm 23', 'Romans 8:28', 'Isaiah 40:31', 'Philippians 4:6-7', 'Exodus 19:5-6'];
  return `<div class="fade">
    <div class="panel" style="margin-bottom:14px"><div class="grid" style="align-items:end"><div class="c4 field" style="margin:0"><label>Bible</label><select id="bbTr">${(tr.translations || []).map(t => `<option value="${esc(t.id)}" ${t.id === (r.translation || S.bible.tr) ? 'selected' : ''}>${esc(t.name)}</option>`).join('')}</select></div>
      <div class="c6 field" style="margin:0"><label>Reference</label><input id="bbRef" value="${esc(S.bible.ref)}" placeholder="John 3:16"></div><div class="c2"><button class="btn" id="bbGo" style="width:100%;justify-content:center">Read</button></div></div>
      <div class="chips">${chips.map(c => `<button class="chip ${c.toLowerCase() === String(r.reference || S.bible.ref).toLowerCase() ? 'on' : ''}" data-ref="${esc(c)}">${esc(c)}</button>`).join('')}</div></div>
    ${r.ok ? `<div class="mark"><span class="kicker">${esc(r.translation_name || r.translation)}</span></div><h2 style="color:#fff">${esc(r.reference)}</h2>
      <p class="passage">${(r.verses || []).map(v => `<b>${v.verse}</b>${esc(v.text)}`).join(' ')}</p>
      <div class="row" style="margin-top:18px"><button class="btn btn--ghost btn--sm" id="bbCopy">Copy</button><a class="btn btn--ghost btn--sm" href="https://arisecenla.church/arise-bible?ref=${encodeURIComponent(r.reference)}" target="_blank" rel="noopener">Open on arisecenla.church</a></div>
      <p class="note" style="margin-top:14px;font-size:12px">${esc(r.copyright || '')}${r.demo ? ' · Preview text is the King James Version whatever Bible is picked; the server reads bible-api.com.' : ' · Read on the server from bible-api.com, no key needed. Study notes, the dictionary and audio are on the website\'s Bible Search.'}</p>` : `<div class="empty">${esc(r.error?.message || r.error || 'Nothing found')}</div>`}
  </div>`;
};
V.bible.after = () => {
  const go = () => { S.bible = { ref: $('#bbRef').value.trim(), tr: $('#bbTr').value }; rerender('bible'); };
  $('#bbGo').onclick = go; $('#bbRef').onkeydown = e => { if (e.key === 'Enter') go(); }; $('#bbTr').onchange = go;
  $$('[data-ref]').forEach(b => b.onclick = () => { S.bible = { ref: b.dataset.ref, tr: $('#bbTr').value }; rerender('bible'); });
  const c = $('#bbCopy'); if (c) c.onclick = () => copyText($('.passage').innerText, c);
};

V.remote = async () => {
  const r = await api('/remote');
  const ts = r.tailscale || {}, wg = r.wireguard || {}, g = r.guacamole || {}, ssh = r.ssh || {};
  const peerRow = p => `<div class="peer ${p.online ? 'on' : ''}"><i></i><span>${esc(p.name)} <span class="m">${esc(p.ip)}${p.os ? ' · ' + esc(p.os) : ''}${p.site ? ' · ' + esc(p.site) : ''}</span></span><span class="m">${p.online ? 'online' : esc(p.last_seen || p.handshake || 'offline')}</span></div>`;
  return `<div class="fade">
    <div class="grid" style="margin-bottom:14px">
      <div class="c3 panel ${ssh.active ? (ssh.password_auth ? 'panel--warn' : 'panel--ok') : 'panel--bad'}"><div class="stat"><span class="stat__l">SSH</span><span class="stat__v" style="font-size:22px">${ssh.active ? `port ${ssh.port}` : 'down'}</span><span class="stat__n">${ssh.keys} key${ssh.keys === 1 ? '' : 's'} · password login ${ssh.password_auth ? '<span style="color:var(--warn)">on</span>' : 'off'}</span></div></div>
      <div class="c3 panel ${ts.up ? 'panel--ok' : ts.installed ? 'panel--bad' : 'panel--flat'}"><div class="stat"><span class="stat__l">Tailscale</span><span class="stat__v" style="font-size:22px">${ts.up ? 'connected' : ts.installed ? 'not up' : 'not installed'}</span><span class="stat__n">${ts.up ? `${esc(ts.self?.ip)} · ${(ts.peers || []).filter(p => p.online).length} of ${(ts.peers || []).length} devices online` : 'docs/REMOTE-ACCESS.md'}</span></div></div>
      <div class="c3 panel ${wg.up ? 'panel--ok' : wg.installed ? 'panel--bad' : 'panel--flat'}"><div class="stat"><span class="stat__l">WireGuard</span><span class="stat__v" style="font-size:22px">${wg.up ? 'up' : wg.installed ? 'down' : 'not installed'}</span><span class="stat__n">${wg.up ? `${esc(wg.interface)} · ${(wg.peers || []).filter(p => p.online).length} of ${(wg.peers || []).length} peers online` : 'self-hosted alternative'}</span></div></div>
      <div class="c3 panel ${g.running ? 'panel--ok' : 'panel--flat'}"><div class="stat"><span class="stat__l">Remote desktop</span><span class="stat__v" style="font-size:22px">${g.running ? 'Guacamole up' : g.installed ? 'stopped' : 'not installed'}</span><span class="stat__n">${g.running ? `<a href="${esc(g.url)}" target="_blank" rel="noopener" style="color:var(--redL)">${esc(g.url)}</a>` : 'install the guacamole app'}</span></div></div>
    </div>
    <div class="tabs" id="rmTabs"><button class="active" data-t="how">How to reach it</button><button data-t="ts">Tailscale</button><button data-t="wg">WireGuard</button><button data-t="rd">Remote desktop</button><button data-t="ssh">SSH</button></div>
    <div data-tab="how"><div class="grid">
      <div class="c6 panel panel--flat"><div class="panel__hd"><h3>From the church (Pineville)</h3></div><div class="md">${md(`- **This dashboard**: ${r.dashboard_url}\n- **Terminal**: the Terminal app here, or \`ssh bradly@${r.hostname}\`\n- **Files**: Finder → Go → Connect to Server → \`smb://${r.hostname}\``)}</div></div>
      <div class="c6 panel panel--flat"><div class="panel__hd"><h3>From Alexandria, the Hub, or home</h3></div><div class="md">${md(`1. Turn on the VPN on that computer (${r.vpn_mode === 'wireguard' ? 'the WireGuard app with its peer config' : 'the Tailscale app, signed in'}).\n2. Everything above works the same: ${ts.self?.dns ? `**http://${ts.self.dns}:4147**` : r.dashboard_url}, \`ssh\`, \`smb://\`.\n3. Another computer's screen: **Remote desktop** (Guacamole) in the browser. No app needed on the far end but Screen Sharing (Mac) or Remote Desktop (Windows) turned on.`)}</div></div>
      <div class="c12 panel panel--flat"><div class="panel__hd"><h3>What is exposed to the internet</h3></div><p style="font-size:13.5px;color:var(--text2)">${r.vpn_mode === 'wireguard' ? 'One UDP port (51820) on the Pineville router, answering only to known keys. Nothing else.' : 'Nothing. Tailscale connects out; no port is opened on the church router. The dashboard, SSH and the shares are only reachable on the church network or through the VPN.'}</p></div>
    </div></div>
    <div data-tab="ts" hidden>${ts.up ? `<div class="kv" style="margin-bottom:14px"><dt>This server</dt><dd>${esc(ts.self?.name)} · ${esc(ts.self?.ip)} · ${esc(ts.self?.dns || '')}</dd><dt>LAN route</dt><dd>${(ts.subnet_routes || []).map(esc).join(', ') || '<span style="color:var(--warn)">none advertised: off-site computers reach the server but not the church LAN</span>'}</dd></div><div class="panel panel--flat">${(ts.peers || []).map(peerRow).join('') || '<div class="empty">No other devices yet. Install Tailscale on a Mac and sign in.</div>'}</div>` : `<div class="md">${md(ts.installed ? `Tailscale is installed but not connected. On the server:\n\n- \`sudo tailscale up --ssh --advertise-routes=192.168.1.0/24\`\n\nthen approve the route in the Tailscale admin console.` : `Not installed. On the server:\n\n- \`curl -fsSL https://tailscale.com/install.sh | sh\`\n- \`sudo tailscale up --ssh --advertise-routes=192.168.1.0/24\`\n\nThen install the Tailscale app on every off-site Mac, PC and phone and sign in with the same account. docs/REMOTE-ACCESS.md has the whole walk-through.`)}</div>`}</div>
    <div data-tab="wg" hidden><div class="toolbar"><span class="note" style="flex:1 1 auto">${wg.up ? `Interface <b>${esc(wg.interface)}</b> on <b>${esc(wg.endpoint || 'no public endpoint set')}</b>, subnet ${esc(wg.subnet)}.` : 'WireGuard is the self-hosted option: one UDP port forwarded on the Pineville router. Install with <code>install.sh --with-wireguard</code>.'}</span><button class="btn btn--sm" id="wgAdd" ${wg.up || r.demo ? '' : 'disabled'}>+ Add a computer</button></div><div class="panel panel--flat">${(wg.peers || []).map(peerRow).join('') || '<div class="empty">No peers yet</div>'}</div></div>
    <div data-tab="rd" hidden><div class="md">${md(g.running ? `Guacamole is running at **${g.url}**. It shows another computer's screen inside this browser: Windows PCs over RDP, Macs over Screen Sharing (VNC), the server over SSH.\n\nAdd a connection in Guacamole → Settings → Connections. Each church computer needs sharing turned on once:\n\n- **Mac**: System Settings → General → Sharing → Screen Sharing on (and "Allow VNC viewers" with a password).\n- **Windows Pro**: Settings → System → Remote Desktop on.` : `Install the **guacamole** app from Apps. It shows another computer's screen inside this browser: Windows PCs over RDP, Macs over Screen Sharing, the server over SSH. First login is guacadmin / guacadmin; change it at once.`)}</div>${g.connections?.length ? `<div class="panel panel--flat" style="margin-top:12px">${g.connections.map(c => `<div class="widget__row"><span>${esc(c.name)}</span><b>${esc(c.protocol)}</b></div>`).join('')}</div>` : ''}</div>
    <div data-tab="ssh" hidden><div class="grid"><div class="c6"><div class="md">${md(`**From a Mac or PC**\n\n- \`ssh bradly@${r.hostname}\` on the church network\n- \`ssh bradly@${ts.self?.ip || '<tailscale-ip>'}\` over the VPN\n\n**Keys, not passwords.** On your Mac: \`ssh-keygen -t ed25519\` then \`ssh-copy-id bradly@${r.hostname}\`. Once a key is on the box, the installer turns password login off.`)}</div></div><div class="c6 panel panel--flat"><div class="panel__hd"><h3>Recent logins</h3></div>${(ssh.last_logins || []).map(l => `<div class="widget__row"><span>${esc(l.user)} from ${esc(l.from)}</span><b>${esc(l.when)}</b></div>`).join('') || '<div class="empty">none</div>'}</div></div></div>
  </div>`;
};
V.remote.after = () => {
  tabs('#rmTabs', 'remote');
  $('#wgAdd').onclick = () => modal(`<h2>Add a computer to the VPN</h2><p class="note" style="margin-bottom:14px">Makes a key pair for it and hands you a config to paste into the WireGuard app on that computer. Name it after the computer.</p><div class="field"><label>Name</label><input id="wgName" placeholder="hub-laptop"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="wgGo">Create</button></div>`, m => {
    $('#wgGo', m).onclick = async e => { const r = await act(e.target, () => api('/remote/wireguard/peers', { method: 'POST', body: { name: $('#wgName', m).value.trim() } })); if (!r || r.ok === false) return;
      $('#modalBody', m).innerHTML = `<h2>${esc(r.name)} · ${esc(r.ip || '')}</h2><p class="note" style="margin-bottom:12px">Paste this into WireGuard → Add tunnel → Create from scratch (or save as ${esc(r.name)}.conf and import). It is shown once.</p><pre class="config" id="wgConf">${esc(r.config)}</pre><div class="acts"><button class="btn btn--ghost" id="wgCopy">Copy</button><button class="btn" data-close>Done</button></div>`;
      $('#wgCopy', m).onclick = () => copyText(r.config, $('#wgCopy', m)); $$('[data-close]', m).forEach(b => b.onclick = () => { m.close(); rerender('remote'); }); };
  });
};

V.sites = async () => {
  const r = await api('/sites');
  return `<div class="fade"><div class="site">${(r.sites || []).map(s => `<div class="site__c ${s.kind === 'main' ? 'main' : ''}"><div class="site__hd"><span class="strip ${s.kind === 'main' ? '' : 'strip--mute'}"><span>${esc(s.kind)}</span></span><h3>${esc(s.name)}</h3><span class="pill ${s.probe_status?.ok === true ? 'ok' : s.probe_status?.ok === false ? 'bad' : ''}">${s.probe_status?.ok === true ? `reachable · ${s.probe_status.ms} ms` : s.probe_status?.ok === false ? 'unreachable' : 'no probe set'}</span></div>
    <div class="site__meta">${s.address ? esc(s.address) + '<br>' : ''}${s.services ? esc(s.services) + '<br>' : ''}Network ${esc(s.subnet)} · link: ${esc(s.vpn)}${s.probe ? ' · probe ' + esc(s.probe) : ''}<br><span style="color:var(--muted)">${esc(s.note)}</span></div>
    <div style="margin-top:10px">${(s.computers || []).map(c => `<span class="tag">${esc(c)}</span>`).join('') || '<span class="tag" style="opacity:.5">no joined computers seen on this network</span>'}</div></div>`).join('')}</div>
    <p class="note" style="margin-top:14px">Set each site's <code>probe</code> in arise.toml to something at that site that is always on (its router, a Mac) and this page shows whether the link is up. Alexandria's Macs bind to the domain over the VPN and keep working on cached accounts when it is down. docs/MULTI-SITE.md.</p></div>`;
};

const KIND_ICON = { server: 'server', nas: 'nas', mac: 'users', pc: 'apps', router: 'remote', switch: 'remote', network: 'remote', printer: 'text', camera: 'sermons', iot: 'folder', phone: 'users', unknown: 'file' };
V.devices = async () => {
  const r = await api('/devices'); S.devCache = r;
  const m = r.meta || {}, devs = r.devices || [], online = devs.filter(d => d.online).length, fresh = devs.filter(d => d.first_seen === m.last_scan).length;
  const row = d => `<tr class="${d.online ? '' : 'dim'}" data-mac="${esc(d.mac)}"><td><i class="fico" style="--i:${ICONURL[KIND_ICON[d.kind_final] || 'file']};width:18px;height:18px;display:inline-block;vertical-align:-4px;margin-right:8px"></i><b>${esc(d.name || d.hostname?.split('.')[0] || d.vendor || 'unknown device')}</b>${d.first_seen === m.last_scan ? ' <span class="tag" style="background:var(--red);color:#fff">new</span>' : ''}${d.joined ? ' <span class="tag">joined</span>' : ''}<br><small class="muted">${esc(d.hostname || '')}${d.note ? (d.hostname ? ' · ' : '') + esc(d.note) : ''}</small></td>
    <td class="mono">${esc(d.ip || '')}${d.stray ? `<br><span class="tag" style="background:var(--amber,#E0A32E);color:#000">stray: ${esc(d.stray)}</span>` : ''}${(d.ips || []).length > 1 ? `<br><small class="muted">before: ${esc((d.ips || []).filter(x => x !== d.ip).join(', '))}</small>` : ''}</td><td class="mono" style="font-size:11.5px">${esc(d.mac)}</td><td>${esc(d.vendor || '')}</td><td>${esc(d.kind_final)}</td><td>${d.online ? '<span class="pill pill--ok">on</span>' : esc(ago(d.last_seen))}</td><td><button class="btn btn--ghost btn--xs" data-edit="${esc(d.mac)}">Name</button></td></tr>`;
  return `<div class="fade"><div class="row row--between" style="margin-bottom:12px"><div><div class="kicker">Everything on the switch</div><h2 style="margin:0">${devs.length} devices · ${online} on now${fresh ? ` · <span style="color:var(--redL)">${fresh} new</span>` : ''}</h2>
      <p class="note" style="margin:6px 0 0">${esc(r.network?.subnet || '')} on ${esc(r.network?.iface || '')} · last scan ${m.last_scan ? ago(m.last_scan) : 'never'}${m.tool ? ' · ' + esc(m.tool) : ''}${r.demo ? ' · sample' : ''}. This is Netgear A's wire. The office Netgear and the Google Mesh show as one device each; what is behind them is their own network and cannot be seen from here.</p></div>
      <div class="row" style="gap:8px"><button class="btn btn--ghost" id="devCams">Find cameras</button><button class="btn btn--ghost" id="devWide">Wide scan</button><button class="btn" id="devScan">Scan now</button></div></div>
    <table class="tbl"><thead><tr><th>Device</th><th>Address</th><th>MAC</th><th>Maker</th><th>Kind</th><th>Seen</th><th></th></tr></thead><tbody>${devs.map(row).join('') || '<tr><td colspan="7" class="muted">Nothing yet. Scan now.</td></tr>'}</tbody></table>
    <p class="note" style="margin-top:12px">A scan runs every hour by itself (arise-devices.timer). Give a device a name once and it keeps it, whatever address the router hands it next.</p>
    ${devs.some(d => d.stray) ? `<div class="card" style="margin-top:12px;border-left:3px solid var(--amber,#E0A32E)"><b>Stray devices.</b> The ones marked <i>stray</i> are on this wire but carry an address from another network, usually left by whoever installed them. Nothing on your network can talk to them until each one is given an address in ${esc(r.network?.subnet || 'this network')}. That is a setting on the device (its own web page, reached from a laptop temporarily set to its range), not on any router.</div>` : ''}
    <div id="devCamsOut" style="margin-top:22px"></div>
    <div id="devBehind" style="margin-top:22px"><div class="kicker">Behind the other routers</div><div class="skeleton"></div></div></div>`;
};
async function paintBehind(root) {
  const box = $('#devBehind', root); if (!box) return;
  let r; try { r = await api('/devices/behind'); } catch (e) { box.innerHTML = `<div class="kicker">Behind the other routers</div><p class="note">${esc(e.message)}</p>`; return; }
  const rs = r.routers || [];
  box.innerHTML = `<div class="kicker">Behind the other routers</div><p class="note" style="margin:6px 0 10px">Read from each router's own attached-devices list, with its admin password, never written to. Set them up as <code>[[routers]]</code> in arise.toml.${rs.length ? '' : ' None configured yet.'}</p>` +
    rs.map(x => `<div class="card" style="margin-bottom:10px"><div class="row row--between"><b>${esc(x.name)}</b><span class="muted">${esc(x.host || '')}${x.ok ? ` · ${x.devices.length} attached` : ''}</span></div>` +
      (x.ok ? `<table class="tbl" style="margin-top:8px"><thead><tr><th>Device</th><th>Address</th><th>MAC</th><th>Link</th></tr></thead><tbody>${x.devices.map(d => `<tr><td>${esc(d.hostname || d.name || 'unnamed')}</td><td class="mono">${esc(d.ip)}</td><td class="mono" style="font-size:11.5px">${esc(d.mac)}</td><td>${esc(d.kind_final)}${d.link_rate ? ' · ' + esc(String(d.link_rate)) + ' Mb/s' : ''}${d.signal != null ? ' · ' + esc(String(d.signal)) + '%' : ''}</td></tr>`).join('') || '<tr><td colspan="4" class="muted">nothing attached</td></tr>'}</tbody></table>`
        : `<p class="note" style="margin:8px 0 0">${esc(x.err || 'did not answer')}</p>`) + '</div>').join('');
}
V.devices.after = root => {
  paintBehind(root);
  $('#devWide', root).onclick = async () => { const b = $('#devWide', root); b.disabled = true; b.textContent = 'Scanning 9 ranges…'; try { const r = await api('/devices/scan?wide=1', { method: 'POST' }); if (r.ok === false) throw new Error(r.err); toast(r.demo ? 'Sample wide scan' : `Found ${r.found}, ${r.new} new`); rerender('devices'); } catch (e) { toast(e.message, 'bad'); b.disabled = false; b.textContent = 'Wide scan'; } };
  $('#devCams', root).onclick = async () => { const b = $('#devCams', root); b.disabled = true; b.textContent = 'Asking…'; const out = $('#devCamsOut', root);
    try { const r = await api('/devices/cameras'); if (r.ok === false) throw new Error(r.err); const cams = r.cameras || [];
      out.innerHTML = `<div class="kicker">Cameras (ONVIF discovery)</div>` + (cams.length ? `<table class="tbl" style="margin-top:8px"><thead><tr><th>Camera</th><th>Model</th><th>Address</th><th>Reachable</th></tr></thead><tbody>${cams.map(c => `<tr><td><b>${esc(c.name || 'unnamed')}</b></td><td>${esc(c.hardware || '')}</td><td class="mono">${esc(c.ip)}</td><td>${c.reachable ? '<span class="pill pill--ok">yes</span>' : `<span class="tag" style="background:var(--amber,#E0A32E);color:#000">no: other network</span>`}</td></tr>`).join('')}</tbody></table>${cams.some(c => !c.reachable) ? `<p class="note" style="margin-top:8px">A camera that answers but is not reachable is powered and on this wire, parked on another address range. Give it an address in ${esc(r.subnet || 'this network')} from its own web page and it will show up for everything, including the router.</p>` : ''}`
        : `<p class="note" style="margin-top:8px">No camera answered in ${r.seconds || 3} seconds. Either they have no power (a switch that is not a PoE switch gives a PoE camera nothing; look for a PoE mark on the switch and a lit LED on the camera), they are not ONVIF, or they are behind another router. A powered camera answers this even when it is parked on the wrong address range.</p>`); }
    catch (e) { out.innerHTML = `<p class="note">${esc(e.message)}</p>`; } b.disabled = false; b.textContent = 'Find cameras'; };
  $('#devScan', root).onclick = async () => { const b = $('#devScan', root); b.disabled = true; b.textContent = 'Scanning…'; try { const r = await api('/devices/scan', { method: 'POST' }); if (r.ok === false) throw new Error(r.err); toast(r.demo ? 'Sample scan' : `Found ${r.found}, ${r.new} new`); rerender('devices'); } catch (e) { toast(e.message, 'bad'); b.disabled = false; b.textContent = 'Scan now'; } };
  $$('[data-edit]', root).forEach(btn => btn.onclick = () => { const d = (S.devCache?.devices || []).find(x => x.mac === btn.dataset.edit); if (!d) return;
    modal(`<h2>${esc(d.name || d.hostname || d.mac)}</h2><form id="devF" style="display:grid;gap:8px;margin-top:10px"><input id="devName" placeholder="Name (e.g. Office printer)" value="${esc(d.name || '')}"><input id="devNote" placeholder="Note" value="${esc(d.note || '')}"><select id="devKind">${['', 'server', 'nas', 'mac', 'pc', 'router', 'switch', 'network', 'printer', 'camera', 'iot', 'phone', 'unknown'].map(k => `<option value="${k}" ${(d.kind || '') === k ? 'selected' : ''}>${k || 'kind: as guessed (' + esc(d.guess || 'unknown') + ')'}</option>`).join('')}</select>
      <dl class="kv" style="margin-top:6px"><dt>MAC</dt><dd class="mono">${esc(d.mac)}</dd><dt>First seen</dt><dd>${esc(d.first_seen || '')}</dd><dt>Addresses</dt><dd class="mono">${esc((d.ips || []).join(', '))}</dd></dl>
      <div class="acts"><button type="button" class="btn btn--ghost" data-close>Cancel</button>${d.online ? '' : '<button type="button" class="btn btn--ghost" id="devForget">Forget</button>'}<button class="btn" type="submit">Save</button></div></form>`, () => {
      $('#devF').onsubmit = async e => { e.preventDefault(); const r = await api('/devices/' + encodeURIComponent(d.mac), { method: 'POST', body: { name: $('#devName').value, note: $('#devNote').value, kind: $('#devKind').value } }); if (r.ok === false) return toast(r.err, 'bad'); $('[data-close]').click(); rerender('devices'); };
      const f = $('#devForget'); if (f) f.onclick = async () => { await api('/devices/' + encodeURIComponent(d.mac), { method: 'DELETE' }); $('[data-close]').click(); rerender('devices'); };
    }); });
};

V.assist = async () => {
  const c = await api('/church'); S.church = c;
  const tiles = (c.assistants || []).map(a => `<button class="assist__t" data-url="${esc(a.url)}"><i>${a.id === 'claude' ? 'Anthropic' : a.id === 'chatgpt' ? 'OpenAI' : a.id === 'grok' ? 'xAI' : a.id === 'studio' ? 'Google' : 'Streaming'}</i><b>${esc(a.name)}</b><span>${esc(a.what)}</span></button>`).join('');
  return `<div class="fade"><div class="kicker">Your assistants, your accounts</div><p class="note" style="margin:6px 0 14px">${S.kiosk ? 'On the monitor each one opens in its own window on top of the desktop; close that window to come back.' : 'Each opens in a new tab, signed in as you. Nothing is stored on the server.'} No API keys anywhere.</p>
    <div class="assist">${tiles}<button class="assist__t" data-claude-code><i>On this box</i><b>Claude Code</b><span>The <code>claude</code> command in the Terminal: ask it about this server, let it read the logs, fix a config. Signed in with the church's claude.ai account via <code>/login</code>.</span></button>${S.kiosk && S.me?.claude ? `<button class="assist__t" data-claude-desktop><i>On the monitor</i><b>Claude Desktop</b><span>The Claude app, full screen on the closet monitor. Bradly's only; locking the screen closes it.</span></button>` : ''}</div></div>`;
};
V.assist.after = root => {
  $$('[data-url]', root).forEach(b => b.onclick = async () => {
    // On the monitor Firefox makes this a themed tab that closes back to the desktop (docs/BROWSER.md).
    // The old way, the server opening a window on the monitor, stays as the fallback.
    if (S.kiosk) { const w = window.open(b.dataset.url, '_blank'); if (w) return;
      const r = await api('/kiosk/open', { method: 'POST', body: { url: b.dataset.url } }).catch(e => ({ ok: false, err: e.message })); if (r.ok === false) toast(r.err, 'bad'); else toast(r.demo ? 'Sample: would open on the monitor' : 'Opening on the monitor…'); }
    else window.open(b.dataset.url, '_blank', 'noopener');
  });
  const cd = $('[data-claude-desktop]', root); if (cd) cd.onclick = async () => { const r = await api('/kiosk/claude-desktop', { method: 'POST', body: { action: 'open' } }).catch(e => ({ ok: false, err: e.message })); if (r.ok === false) toast(r.err, 'bad'); else { S.claudeDesktop = true; toast(r.demo ? 'Sample: Claude Desktop would open on the monitor' : 'Opening Claude Desktop…'); } };
  const cc = $('[data-claude-code]', root); if (cc) cc.onclick = () => { openApp('terminal'); setTimeout(() => { const ws = S.termWs; if (ws && ws.readyState === 1) ws.send('claude\r'); else toast('Terminal is opening; type: claude'); }, 1500); };
};
V.sunday = async () => {
  const [c, s] = await Promise.all([api('/church'), api('/sunday')]); S.church = c;
  const n = c.next; const items = s.items || []; const done = items.filter(i => i.done).length;
  return `<div class="fade sun"><div><div class="kicker">Sunday ${esc(s.sunday)}</div><h2 style="margin:0 0 10px">Checklist · ${done} of ${items.length}</h2>
      ${items.map(i => `<label class="sun__item ${i.done ? 'done' : ''}"><input type="checkbox" data-i="${i.i}" ${i.done ? 'checked' : ''}><div><span>${esc(i.text)}</span>${i.done ? `<small>${esc(i.by)} · ${esc(i.at.replace('T', ' '))}</small>` : ''}</div></label>`).join('')}
      <p class="note" style="margin-top:12px">Ticks reset every week. The list is <code>[church] sunday_checklist</code> in arise.toml.${s.demo ? ' Sample.' : ''}</p></div>
    <div><div class="card"><div class="kicker">Next</div>${n ? `<div class="sun__big">${esc(n.in_words)}</div><div style="margin-top:6px">${esc(n.name)} · ${esc(n.site)}<br><small class="muted">${esc(n.day)} ${esc(n.time)}</small></div>` : '<div class="muted">no services configured</div>'}</div>
      <div class="card" style="margin-top:12px"><div class="kicker">Services</div><div class="widget__rows">${(c.services || []).map(x => `<div class="widget__row"><span>${esc(x.name)} · ${esc(x.site)}</span><b>${esc(x.day)} ${esc(x.time)}</b></div>`).join('')}</div></div>
      <div class="card widget--verse" style="margin-top:12px"><div class="kicker">Verse of the day</div><blockquote>${esc(c.verse?.text || '')}<cite>${esc(c.verse?.ref || '')}</cite></blockquote></div>
      <div class="card" style="margin-top:12px"><div class="kicker">Quick doors</div><div class="row" style="gap:8px;flex-wrap:wrap;margin-top:8px"><button class="btn btn--ghost btn--xs" data-open="sermons">Sermons</button><button class="btn btn--ghost btn--xs" data-open="assist">Studio / StreamYard</button>${isMember() ? '' : '<button class="btn btn--ghost btn--xs" data-open="automator">Automator</button><button class="btn btn--ghost btn--xs" data-open="devices">Network</button>'}</div></div></div></div>`;
};
V.sunday.after = root => {
  $$('input[data-i]', root).forEach(cb => cb.onchange = async () => { const r = await api('/sunday/' + cb.dataset.i, { method: 'POST' }).catch(e => ({ ok: false, err: e.message })); if (r.ok === false) return toast(r.err, 'bad'); const all = (r.items || []).every(i => i.done); tone(all ? 'done' : 'click'); if (all) toast('Checklist complete. Have a great service.'); rerender('sunday'); });
  $$('[data-open]', root).forEach(b => b.onclick = () => openApp(b.dataset.open));
};

V.mail = async () => {
  const [st, bc] = await Promise.all([api('/mail'), api('/mail/broadcasts')]); S.mail = st;
  const tab = S.mailTab || 'compose';
  const head = `<div class="row row--between" style="margin-bottom:12px"><div><div class="kicker">Resend · ${st.configured ? '<span style="color:var(--ok)">ready</span>' : '<span style="color:var(--warn)">not set up</span>'}${st.demo ? ' · sample' : ''}</div>
      <h2 style="margin:0">${esc(st.from_name)} &lt;${esc(st.from_email || 'from_email not set')}&gt;</h2><p class="note" style="margin:6px 0 0">Reply-to ${esc(st.reply_to || 'none')}${st.gmail_warning ? ' · <b style="color:var(--bad)">from_email is a gmail.com address: Resend cannot send from a domain you do not verify. Use an address at the church domain and keep the Gmail as reply-to.</b>' : ''}</p></div>
      <div class="tabs">${['compose', 'contacts', 'sent', 'staff'].map(t => `<button class="${tab === t ? 'on' : ''}" data-tab="${t}">${t === 'staff' ? 'Staff addresses' : t[0].toUpperCase() + t.slice(1)}</button>`).join('')}</div></div>`;
  let body = '';
  if (tab === 'compose') body = `<div class="sun"><div><label class="lbl">Subject</label><input id="mlSubj" value="${esc(S.mailDraft?.subject || '')}" placeholder="This week at Arise" style="width:100%">
      <label class="lbl" style="margin-top:10px">Body <small class="muted">(plain text; **bold**, [links](https://…), ## headings, - lists)</small></label><textarea id="mlBody" rows="14" style="width:100%;font:inherit" placeholder="Hi church,&#10;&#10;## This Sunday&#10;- 10:30 at Pineville&#10;- 10:00 at Alexandria">${esc(S.mailDraft?.body || '')}</textarea>
      <div class="row" style="gap:8px;margin-top:10px;flex-wrap:wrap"><button class="btn btn--ghost" id="mlPrev">Preview</button><input id="mlTestTo" placeholder="you@…" style="width:200px"><button class="btn btn--ghost" id="mlTest">Send test</button><span style="flex:1"></span><button class="btn" id="mlSend">Send to everyone…</button></div>
      <p class="note" style="margin-top:10px">Every email starts "Hi {first name}," and ends with the church footer and an unsubscribe link Resend manages. Sending to everyone asks you to type <b>send</b>.</p></div>
      <div><div class="card"><div class="kicker">Preview</div><iframe id="mlFrame" style="width:100%;height:520px;border:0;background:#F4F2F0;margin-top:8px" sandbox=""></iframe></div></div></div>`;
  else if (tab === 'contacts') { const c = await api('/mail/contacts'); const im = st.import || {};
    body = `<div class="row row--between" style="margin-bottom:10px"><div><b>${c.count ?? 0}</b> contacts in the list${c.err ? ` · <span style="color:var(--bad)">${esc(c.err)}</span>` : ''}</div><div class="row" style="gap:8px"><label class="btn btn--ghost btn--xs" for="mlCsv">Import CSV (Wix export)</label><input id="mlCsv" type="file" accept=".csv,text/csv" hidden></div></div>
      ${im.total ? `<p class="note">Import: ${im.done}/${im.total} added, ${im.failed} failed${im.running ? ', running…' : ', done ' + esc(im.finished || '')}${(im.errors || []).length ? '<br>' + im.errors.map(esc).join('<br>') : ''}</p>` : ''}
      <div id="mlImportOut"></div>
      <table class="tbl"><thead><tr><th>Email</th><th>Name</th><th>Added</th><th>Status</th></tr></thead><tbody>${(c.contacts || []).map(x => `<tr class="${x.unsubscribed ? 'dim' : ''}"><td class="mono" style="font-size:12.5px">${esc(x.email)}</td><td>${esc([x.first_name, x.last_name].filter(Boolean).join(' '))}</td><td>${esc((x.created_at || '').slice(0, 10))}</td><td>${x.unsubscribed ? 'unsubscribed' : 'subscribed'}</td></tr>`).join('') || '<tr><td colspan="4" class="muted">No contacts yet. Export from Wix (Contacts → Export → CSV) and import it here.</td></tr>'}</tbody></table>
      <p class="note" style="margin-top:10px">Contacts live in a Resend audience so unsubscribes are honoured automatically. Wix's export keeps its "Email", "First Name" and "Last Name" columns; anything with an email column works.</p>`; }
  else if (tab === 'staff') { const f = await api('/mail/forwarding');
    body = `<p class="note" style="margin:0 0 10px">first.last@${esc(f.domain)} goes on to each person's personal email. Forwarding only: no mailbox is kept on the server, and nothing here listens to the internet: the box fetches what arrived at Resend every five minutes. <b>${f.enabled ? '<span style="color:var(--ok)">On</span>' : '<span style="color:var(--warn)">Off</span>'}</b>${f.enabled ? '' : ': ' + esc(f.how || 'turn on [mailfwd] enabled once the Wix record is in (docs/WIX-DNS.md, part 2)')}</p>
      <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Address</th><th>Goes to</th><th></th></tr></thead><tbody>${(f.aliases || []).map(a => `<tr class="${a.enabled ? '' : 'dim'}"><td class="mono" style="font-size:12.5px">${esc(a.alias)}@${esc(f.domain)}</td><td>${a.to ? esc(a.to) : '<span class="muted">' + esc(a.why || 'nowhere yet') + '</span>'}${a.enabled ? '' : ' <span class="tag">switched off</span>'}</td><td><button class="btn btn--ghost btn--xs" data-mfexp="${esc(a.alias)}">Export</button></td></tr>`).join('') || '<tr><td colspan="3" class="muted">No accounts yet.</td></tr>'}</tbody></table></div>
      <h3 style="margin:16px 0 6px">Recent</h3><div class="tbl-wrap"><table class="tbl"><thead><tr><th>When</th><th>To</th><th>From</th><th>Subject</th><th>Result</th></tr></thead><tbody>${(f.log || []).map(r => `<tr><td class="dim">${esc(fmtT(r.t))}</td><td class="mono" style="font-size:12px">${esc(r.alias)}</td><td style="font-size:12.5px">${esc(r.from)}</td><td>${esc(r.subject)}</td><td><span class="pill ${r.ok ? 'ok' : 'bad'}">${r.ok ? 'forwarded' : esc(r.why || 'not sent')}</span></td></tr>`).join('') || '<tr><td colspan="5" class="muted">Nothing has arrived yet.</td></tr>'}</tbody></table></div>`; }
  else body = `<table class="tbl"><thead><tr><th>Newsletter</th><th>Status</th><th>Created</th><th>Sent</th></tr></thead><tbody>${(bc.broadcasts || []).map(b => `<tr><td><b>${esc(b.subject || b.name)}</b></td><td>${esc(b.status)}</td><td>${esc((b.created_at || '').slice(0, 16).replace('T', ' '))}</td><td>${esc((b.sent_at || '').slice(0, 16).replace('T', ' ') || '—')}</td></tr>`).join('') || '<tr><td colspan="4" class="muted">Nothing sent yet.</td></tr>'}</tbody></table>${bc.err ? `<p class="note" style="color:var(--bad)">${esc(bc.err)}</p>` : ''}`;
  return `<div class="fade">${head}${body}${st.configured ? '' : `<div class="card" style="margin-top:14px;border-left:3px solid var(--warn)"><b>To set up (Friday):</b> 1. Resend account, add and verify the church's domain (DNS records at the domain host). 2. API key → <code>/etc/arise/secrets/resend-api-key</code> (root only). 3. In arise.toml <code>[mail]</code>: from_email at that domain, reply_to the Gmail. 4. Import the Wix CSV. 5. Send yourself a test.</div>`}</div>`;
};
V.mail.after = root => {
  $$('[data-tab]', root).forEach(b => b.onclick = () => { S.mailTab = b.dataset.tab; rerender('mail'); });
  $$('[data-mfexp]', root).forEach(b => b.onclick = async () => { const r = await api(`/mail/forwarding/export/${encodeURIComponent(b.dataset.mfexp)}`).catch(e => ({ ok: false, err: e.message }));
    if (r.ok === false) return toast(r.err, 'bad');
    modal(`<h2>${esc(r.address)}</h2><p class="note">${esc(r.note)}</p><p><b>${r.messages}</b> message${r.messages === 1 ? '' : 's'} on record.</p><textarea readonly rows="10" style="width:100%;font:12px ui-monospace,Menlo,monospace" aria-label="The forwarding log as CSV">${esc(r.csv)}</textarea><div class="acts"><button class="btn" data-close>Done</button></div>`); });
  const draft = () => ({ subject: $('#mlSubj', root)?.value || '', body: $('#mlBody', root)?.value || '' });
  const keep = () => { S.mailDraft = draft(); };
  ['#mlSubj', '#mlBody'].forEach(sel => { const el = $(sel, root); if (el) el.oninput = keep; });
  const prev = async () => { const d = draft(); keep(); const r = await api('/mail/preview', { method: 'POST', body: d }); const f = $('#mlFrame', root); if (f) f.srcdoc = r.html; };
  const bp = $('#mlPrev', root); if (bp) { bp.onclick = prev; if (S.mailDraft?.body) prev(); }
  const bt = $('#mlTest', root); if (bt) bt.onclick = async () => { const d = draft(); const to = $('#mlTestTo', root).value.trim(); if (!to) return toast('Type the address to send the test to', 'warn'); const r = await api('/mail/test', { method: 'POST', body: { ...d, to } }); if (r.ok === false) return toast(r.err, 'bad'); toast(r.demo ? 'Sample: would send a test' : 'Test sent to ' + to); };
  const bs = $('#mlSend', root); if (bs) bs.onclick = () => { const d = draft(); if (!d.subject || !d.body) return toast('Subject and body first', 'warn');
    confirmType('Send to everyone on the list', 'send', `Subject: <b>${esc(d.subject)}</b>. Resend makes a broadcast and sends it to every subscribed contact. There is no un-send.`, async () => { const c = await api('/mail/broadcasts', { method: 'POST', body: d }); if (c.ok === false) throw new Error(c.err); const r = await api(`/mail/broadcasts/${encodeURIComponent(c.id || c.data?.id || '')}/send`, { method: 'POST', body: { confirm: 'send' } }); if (r.ok === false) throw new Error(r.err); toast(r.demo ? 'Sample: would send to everyone' : 'Sent. Resend delivers over the next minutes.'); S.mailDraft = null; S.mailTab = 'sent'; rerender('mail'); }); };
  const csv = $('#mlCsv', root); if (csv) csv.onchange = async () => { const f = csv.files[0]; if (!f) return; const text = await f.text(); const out = $('#mlImportOut', root);
    const pv = await api('/mail/import/preview', { method: 'POST', body: { csv: text } }); if (pv.err) { out.innerHTML = `<p class="note" style="color:var(--bad)">${esc(pv.err)}</p>`; return; }
    out.innerHTML = `<div class="card" style="margin:10px 0"><b>${pv.count}</b> good addresses, ${pv.skipped} skipped (bad or duplicate). Columns: ${esc(JSON.stringify(pv.columns))}.<br><small class="muted">${pv.sample.map(x => esc(x.email + (x.first_name ? ' · ' + x.first_name + ' ' + x.last_name : ''))).join(', ')}…</small><div class="row" style="gap:8px;margin-top:8px"><button class="btn" id="mlGo">Add ${pv.count} to the list</button><button class="btn btn--ghost" id="mlNo">Cancel</button></div></div>`;
    $('#mlGo', root).onclick = async () => { const r = await api('/mail/import', { method: 'POST', body: { csv: text } }); if (r.ok === false) return toast(r.err, 'bad'); toast(r.demo ? 'Sample: would import' : `Importing ${r.queued}; this takes about a second each`); setTimeout(() => rerender('mail'), 1500); };
    $('#mlNo', root).onclick = () => { out.innerHTML = ''; csv.value = ''; }; };
};

V.terminal = async () => `<div class="term" id="termMount"></div>`;
V.terminal.after = root => {
  const mount = $('#termMount'); if (!mount || !window.Terminal) { if (mount) mount.innerHTML = '<p class="note">xterm.js did not load.</p>'; return; }
  const term = new window.Terminal({ cursorBlink: true, fontSize: 13, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', theme: { background: '#000000', foreground: '#e6e6ea', cursor: '#DB3F48', selectionBackground: 'rgba(214,34,45,.4)', red: '#DB3F48', green: '#3DBE7A', yellow: '#E0A32E', blue: '#5CA8E0' }, allowProposedApi: true });
  const fit = new window.FitAddon.FitAddon(); term.loadAddon(fit); term.open(mount); setTimeout(() => { fit.fit(); term.focus(); }, 30);
  const ro = new ResizeObserver(() => { try { fit.fit(); } catch {} }); ro.observe(mount);
  S.termDispose = () => { ro.disconnect(); term.dispose(); if (S.termWs) { S.termWs.close(); S.termWs = null; } };
  if (S.demoOnly) return demoShell(term);
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const connect = () => {
    const ws = new WebSocket(`${proto}://${location.host}/api/terminal`); S.termWs = ws;
    ws.onopen = () => { ws.send(JSON.stringify({ resize: [term.cols, term.rows] })); };
    ws.onmessage = e => term.write(e.data);
    // 4409: signed in with a PIN; the root shell wants the full password again (round 7, 161)
    ws.onclose = ev => { if (ev.code === 4409) { term.write('\r\n\x1b[2m[the Terminal asks for your password, not your PIN]\x1b[0m\r\n'); reauth().then(connect, () => term.write('\x1b[2m[cancelled]\x1b[0m\r\n')); return; }
      term.write(`\r\n\x1b[2m[session closed${ev.code === 4401 ? ': sign in again' : ''}]\x1b[0m\r\n`); };
  };
  connect();
  term.onData(d => { if (S.termWs && S.termWs.readyState === 1) S.termWs.send(d); });
  term.onResize(({ cols, rows }) => { if (S.termWs && S.termWs.readyState === 1) S.termWs.send(JSON.stringify({ resize: [cols, rows] })); });
};
function demoShell(term) {
  const P = '\x1b[31marise-server\x1b[0m:~# ';
  const CMD = { help: 'arisectl info · arisectl doctor · arisectl backup status · arisectl user list · uptime · df -h · clear',
    'arisectl info': `ariseOS (Arise Server) v${S.overview?.version || '0.8.0'} “${S.overview?.codename || 'Exodus'}”\r\n` + '  host      arise-server  (Ubuntu 24.04, 4 cores, 16 GB RAM)\r\n  realm     AD.ARISECENLA.COM / ARISE   directory on\r\n  web       http://arise-server:4147   password set\r\n  automator /srv/arise/automator/ARISE_YouTube_Updater  at 02:05\r\n  backups   /mnt/synology/arise-backups/restic  at 03:00',
    'arisectl doctor': '  \x1b[32m✓\x1b[0m config /etc/arise/arise.toml\r\n  \x1b[32m✓\x1b[0m Samba AD DC answers\r\n  \x1b[32m✓\x1b[0m DNS SRV for ad.arisecenla.com resolves\r\n  \x1b[32m✓\x1b[0m token.json present\r\n  \x1b[32m✓\x1b[0m restic installed\r\n  \x1b[32m✓\x1b[0m Synology /mnt/synology mounted\r\n  \x1b[33m!\x1b[0m 3 apt packages upgradable (1 security)\r\n  \x1b[32m✓\x1b[0m clock synchronised',
    'arisectl backup status': 'repository /mnt/synology/arise-backups/restic\r\n  \x1b[32m✓\x1b[0m 53 snapshots, 296.2 GB stored\r\n  JOB        LAST              RESULT  ADDED\r\n  automator  2026-10-27T03:00  ok      797.1 MB\r\n  homes      2026-10-27T03:04  ok      451.3 MB\r\n  config     2026-10-27T03:16  ok      739.5 MB',
    'arisectl user list': '  USER          NAME             ENABLED  GROUPS\r\n  bradly        Bradly Dyer      yes      Domain Admins, Media, Staff\r\n  media-mac     Media Booth Mac  yes      Media\r\n  office        Church Office    yes      Staff',
    uptime: ' 09:41:12 up 14 days,  3:07,  1 user,  load average: 0.42, 0.58, 0.61', 'df -h': 'Filesystem      Size  Used Avail Use% Mounted on\r\n/dev/sda2       224G   66G  147G  31% /\r\n/dev/sdb1       894G  242G  607G  29% /srv/arise\r\n//synology/arise  15T  4.5T   10T  31% /mnt/synology', whoami: 'root', hostname: 'arise-server' };
  term.write(`\x1b[31m   ▲\x1b[0m  Arise Server \x1b[2mv${S.overview?.version || '0.8.0'} “${S.overview?.codename || 'Exodus'}”\x1b[0m  ·  preview terminal` + '\r\n   A sample shell. On the real server this is a root shell on the box. Type help.\r\n\r\n' + P);
  let buf = '';
  term.onData(d => { for (const ch of d) {
    if (ch === '\r') { const c = buf.trim(); buf = ''; if (c === 'clear') { term.clear(); term.write('\r' + P); continue; } const out = c ? (CMD[c] ?? `bash: ${c}: not in the preview (type help)`) : ''; term.write('\r\n' + (out ? out + '\r\n' : '') + P); }
    else if (ch === '\x7f') { if (buf) { buf = buf.slice(0, -1); term.write('\b \b'); } }
    else if (ch === '\x03') { buf = ''; term.write('^C\r\n' + P); }
    else if (ch >= ' ') { buf += ch; term.write(ch); }
  } });
}

/* ---------------- the apps ---------------- */
const I = {
  overview: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 3h8v8H3zm10 0h8v5h-8zM3 13h8v8H3zm10-3h8v11h-8z"/></svg>',
  directory: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm0 2c-4 0-7 2-7 5v2h14v-2c0-3-3-5-7-5zm8-2a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm0 2c-.7 0-1.4.1-2 .3 1.8 1.1 3 2.8 3 4.7v2h4v-2c0-2.6-2.4-5-5-5z"/></svg>',
  files: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 5h8l2 2h10v13H2z"/></svg>',
  backups: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l9 4v6c0 5-4 9-9 10-5-1-9-5-9-10V6z"/></svg>',
  automator: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 3l15 9-15 9z"/></svg>',
  sermons: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 5h20v14H2zm8 3v8l6-4z" fill-rule="evenodd"/></svg>',
  bible: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 3h13a3 3 0 0 1 3 3v15H7a3 3 0 0 1-3-3zm3 2v13h11V6a1 1 0 0 0-1-1zm4 2h3v3h3v3h-3v3h-3v-3H8V10h3z"/></svg>',
  apps: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 3h5v5H3zm7 0h5v5h-5zm7 0h5v5h-5zM3 10h5v5H3zm7 0h5v5h-5zm7 0h5v5h-5zM3 17h5v5H3zm7 0h5v5h-5zm7 0h5v5h-5z"/></svg>',
  remote: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3a9 9 0 0 1 9 9h-2a7 7 0 0 0-7-7zm0 4a5 5 0 0 1 5 5h-2a3 3 0 0 0-3-3zm0 4a1 1 0 0 1 1 1v9h-2v-9a1 1 0 0 1 1-1zM3 12a9 9 0 0 1 4-7.5l1 1.7A7 7 0 0 0 5 12zm4 0a5 5 0 0 1 2-4l1 1.7A3 3 0 0 0 9 12z"/></svg>',
  sites: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a7 7 0 0 1 7 7c0 5-7 13-7 13S5 14 5 9a7 7 0 0 1 7-7zm0 4a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"/></svg>',
  terminal: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 4h20v16H2zm2 2v12h16V6zm2 2l4 4-4 4-1.4-1.4L7.2 12 4.6 9.4zm6 6h6v2h-6z"/></svg>',
  nas: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 4h18v7H3zm0 9h18v7H3zm3 2h3v3H6zm0-9h3v3H6z"/></svg>',
  services: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm9 5l-2 .4a7 7 0 0 1-.8 2l1.2 1.7-1.4 1.4-1.7-1.2a7 7 0 0 1-2 .8L14 21h-4l-.4-2a7 7 0 0 1-2-.8l-1.7 1.2-1.4-1.4 1.2-1.7a7 7 0 0 1-.8-2L3 14v-4l2-.4a7 7 0 0 1 .8-2L4.6 5.9 6 4.5l1.7 1.2a7 7 0 0 1 2-.8L10 3h4l.4 2a7 7 0 0 1 2 .8l1.7-1.2 1.4 1.4-1.2 1.7a7 7 0 0 1 .8 2l2 .4z"/></svg>',
  logs: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 5h18v3H3zm0 5h18v3H3zm0 5h12v3H3z"/></svg>',
  assist: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.2 5.8L20 10l-5.8 2.2L12 18l-2.2-5.8L4 10l5.8-2.2zM19 16l1 2.6 2.6 1-2.6 1L19 23l-1-2.4-2.6-1 2.6-1z"/></svg>',
  mail: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 5h20v14H2zm2 2v.5l8 5 8-5V7zm0 3v7h16v-7l-8 5z"/></svg>',
  security: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l8 3.5V11c0 5.2-3.4 9.6-8 11-4.6-1.4-8-5.8-8-11V5.5zm0 2.2L6 6.8V11c0 4 2.5 7.6 6 8.9 3.5-1.3 6-4.9 6-8.9V6.8zm-1 4.8h2v2.3l1.6 1.6-1.4 1.4L11 12.1z"/></svg>',
  sunday: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 4h16v16H4zm2 4v10h12V8zm2 3l2 2 4-4 1.4 1.4L10 15.8l-3.4-3.4z"/></svg>',
  devices: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 4h6v5H4zm10 0h6v5h-6zM9 15h6v5H9zM7 9v2h10V9h-1v1H8V9zm4 2h2v4h-2z"/></svg>',
  settings: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 6h12v2H3zm14 0h4v2h-4zM3 11h4v2H3zm6 0h12v2H9zM3 16h10v2H3zm12 0h6v2h-6z"/></svg>',
  calendar: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 5h18v16H3zm2 4v10h14V9zM7 2h2v4H7zm8 0h2v4h-2zM7 11h3v3H7zm5 0h3v3h-3z"/></svg>',
  calc: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 2h16v20H4zm2 2v4h12V4zM6 10v2h3v-2zm5 0v2h3v-2zm5 0v2h2v-2zM6 14v2h3v-2zm5 0v2h3v-2zm5 0v6h2v-6zM6 18v2h3v-2zm5 0v2h3v-2z"/></svg>',
  clock: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20zm0 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16zm-1 3h2v5.6l3.5 2-1 1.7L11 13.6z"/></svg>',
  help: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20zm0 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16zm0 12.5a1.3 1.3 0 1 1 0 2.6 1.3 1.3 0 0 1 0-2.6zM12 6.5c2.2 0 3.8 1.3 3.8 3.2 0 1.3-.7 2-1.8 2.7-.9.6-1.1.9-1.1 1.6h-1.9c0-1.5.6-2.2 1.7-2.9.8-.5 1.1-.8 1.1-1.4 0-.8-.7-1.4-1.8-1.4-1 0-1.7.6-1.8 1.6H8.3c.1-2 1.6-3.4 3.7-3.4z"/></svg>',
  activity: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 12h4l3-8 4 16 3-8h6v2h-4.8L14 22 10 6l-2.2 6H2z"/></svg>',
  automations: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20zm0 2a8 8 0 1 0 0 16 8 8 0 0 0 0-16zm-1 3h2v5.6l3.5 2-1 1.7L11 13.6z"/></svg>',
  storage: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 4h18v6H3zm0 8h18v8H3zm3-6h3v2H6zm0 8h3v2H6zm9-8h3v2h-3zm0 8h3v2h-3z"/></svg>',
  updates: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3l5 5h-3v6h-4V8H7zM4 17h16v4H4z"/></svg>',
  notes: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 3h13l3 3v15H4zm3 5v2h10V8zm0 4v2h10v-2zm0 4v2h7v-2z"/></svg>',
  photos: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 5h18v14H3zm2 2v10h14V7zm2 8l3-4 2 2.5L14 11l3 4z"/></svg>',
  monitor: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 4h20v13H2zm2 2v9h16V6zm5 12h6v2H9z"/></svg>',
  about: '<svg viewBox="0 0 32 32"><path d="M16 2c2 6 8 8 8 15a8 8 0 0 1-16 0c0-3 1.4-5 3-7 0 3 1 5 3 6 0-5 1-10 2-14z" fill="#D6222D"/><path d="M16 12c1 3 4 4 4 7.5A4 4 0 0 1 12 19c0-2 .7-3 1.6-4 .2 1.6.9 2.5 1.8 3 0-2.5.3-4.5.6-6z" fill="#fff"/></svg>',
};
const APPS = [
  { id: 'files', n: '01', name: 'Finder', what: 'The server, the Synology, the shares', whatMember: 'Your files, your shares, your links', tone: 'bone', dock: true, w: 900, h: 560 },
  { id: 'overview', n: '02', name: 'Overview', what: 'Needs you, live stats, tonight', tone: 'red', dock: true },
  { id: 'directory', n: '03', name: 'Directory', what: 'Users, groups, joined computers', dock: true },
  { id: 'backups', n: '04', name: 'Backups', what: 'restic jobs, history, snapshots', dock: true },
  { id: 'automator', n: '05', name: 'Automator', what: 'The channel, the transcripts, the 02:05 job', dock: true, w: 1180, h: 760 },
  { id: 'sermons', n: '06', name: 'Sermons', what: 'The channel, no quota spent', tone: 'bone', dock: true },
  { id: 'bible', n: '07', name: 'Bible', what: 'Read a passage', tone: 'bone', dock: true, w: 820, h: 560 },
  { id: 'apps', n: '08', name: 'Store', what: 'Every app, installed and the catalogue', dock: true, w: 1040, h: 680 },
  { id: 'remote', n: '09', name: 'Remote', what: 'VPN, SSH, remote desktop', dock: true },
  { id: 'sites', n: '10', name: 'Campuses', what: 'Pineville, Alexandria, the Hub', w: 760, h: 520 },
  { id: 'terminal', n: '11', name: 'Terminal', what: 'A shell on the box', dock: true, flush: true, w: 860, h: 500 },
  { id: 'nas', n: '12', name: 'Synology', what: 'Mount, space, DSM health' },
  { id: 'services', n: '13', name: 'Services', what: 'The systemd units' },
  { id: 'logs', n: '14', name: 'Logs', what: 'The journal, the arise logs, the apps; search; the last error', w: 1040, h: 660 },
  { id: 'settings', n: '15', name: 'System Settings', what: 'One window: appearance, users, sharing, backups, updates, time', w: 1000, h: 640 },
  { id: 'devices', n: '16', name: 'Network', what: 'Everything on the switch', w: 980, h: 600 },
  { id: 'assist', n: '17', name: 'Assistants', what: 'Claude, ChatGPT, Grok, Studio', tone: 'bone', dock: true, w: 820, h: 480 },
  { id: 'sunday', n: '18', name: 'Sunday', what: 'The service checklist, what is next', tone: 'red', dock: true, w: 900, h: 600 },
  { id: 'mail', n: '19', name: 'Mail', what: 'The church family list, newsletters (Resend)', w: 980, h: 640 },
  { id: 'calendar', n: '20', name: 'Calendar', what: 'Services and events; every Mac and phone can subscribe', whatMember: 'The services and the church\'s events', tone: 'bone', dock: true, w: 980, h: 640 },
  { id: 'calc', n: '21', name: 'Calculator', what: 'Sums, also in Spotlight', tone: 'bone', w: 420, h: 560 },
  { id: 'clock', n: '22', name: 'Clock', what: 'World clock, timer, stopwatch, alarm', tone: 'bone', w: 760, h: 480 },
  { id: 'help', n: '23', name: 'Help', what: 'The docs, in here; F1', whatMember: 'How the portal works', tone: 'bone', dock: true, w: 1000, h: 660 },
  { id: 'activity', n: '24', name: 'Activity Monitor', what: 'Processes and containers, who is using the box', w: 1040, h: 680 },
  { id: 'automations', n: '25', name: 'Automations', what: 'Every timer: next run, last result, pause', w: 980, h: 620 },
  { id: 'storage', n: '26', name: 'Storage', what: 'What is eating the disk', w: 1040, h: 680 },
  { id: 'updates', n: '27', name: 'Software Update', what: 'Security automatic; the rest on your click, Saturday 03:30', w: 1000, h: 680 },
  { id: 'notes', n: '28', name: 'Notes', what: 'Trilium, in a window', whatMember: 'Trilium, in a window', tone: 'bone', groups: ['Staff', 'Media'], w: 1000, h: 680 },
  { id: 'photos', n: '29', name: 'Photos', what: 'Immich, the church photo library', whatMember: 'Immich, the church photo library', tone: 'bone', groups: ['Staff', 'Media'], w: 1040, h: 700 },
  { id: 'monitor', n: '30', name: 'Monitor', what: 'The closet panel: off at night, Screen Sharing', w: 860, h: 560 },
  { id: 'security', n: '31', name: 'Security', what: 'Encryption, the virus scan, the certificate, two-step', w: 940, h: 640 },
  { id: 'shares', n: '', name: 'Shares', what: 'The shares on the network', hidden: true, w: 980, h: 620 },
  { id: 'about', n: '', name: 'About This Server', what: '', hidden: true, w: 600, h: 640 },
];
const MEMBER_APPS = ['files', 'sermons', 'bible', 'sites', 'about', 'assist', 'sunday', 'calendar', 'calc', 'clock', 'help', 'notes', 'photos'];
const isMember = () => S.role === 'member';
const inGroups = a => !a.groups || a.groups.some(g => (S.me?.groups || []).includes(g));
const visibleApps = () => isMember() ? APPS.filter(a => MEMBER_APPS.includes(a.id) && inGroups(a)) : APPS;
const appOf = id => APPS.find(a => a.id === id);
// Shortcut labels: a Windows keyboard on the closet monitor has no ⌘. Ctrl does the same job in every handler.
const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform);
const kbd = h => !h || IS_MAC ? h : h.replace('⌃⌘', 'Ctrl+Alt+').replace('⇧⌘', 'Ctrl+Shift+').replace('⌘', 'Ctrl+').replace('⌃', 'Ctrl+');
const iconHtml = a => `<span class="dock__icon ${a.tone || ''}">${I[a.id]}</span>`;

V.about = async () => {
  // Members cannot read /overview (the administrator's); their About is built from what they may read.
  const o = S.overview || (isMember() ? await api('/about/whatsnew').then(w => ({ version: w.version, codename: w.codename, hostname: 'arise-server', realm: 'AD.ARISECENLA.COM', profile: 'member portal', machine: {} })).catch(() => ({ machine: {} })) : await api('/overview')); const m = o.machine || S.machine || {};
  let wk = null; try { wk = await api('/about/week'); } catch {}
  let nw = null; try { nw = await api('/about/whatsnew'); } catch {}
  let ch = null; if (!isMember()) { try { ch = await api('/upkeep/changes?limit=12'); } catch {} }
  const changes = ch && (ch.changes || []).length ? `<div class="about__new"><div class="widget__kicker">Changes on this box</div><ul class="about__changes">${ch.changes.map(c => `<li><b>${esc(c.who)}</b> · ${esc(String(c.what || '').replace(/^arisectl\./, 'arisectl '))}${c.target ? ' <span class="dim">' + esc(String(c.target).slice(0, 40)) + '</span>' : ''} <span class="dim">${esc(ago(c.when))}</span></li>`).join('')}</ul></div>` : '';
  const whatsnew = nw && nw.lines?.length ? `<div class="about__new"><div class="widget__kicker">What's new in v${esc(nw.version)} “${esc(nw.codename)}”</div><ul>${nw.lines.map(l => `<li>${esc(l)}</li>`).join('')}</ul></div>` : '';
  const week = wk ? `<div class="about__week">This week: <b>${esc(wk.verse?.ref || '')}</b>${wk.verse?.text ? ' · “' + esc(wk.verse.text.slice(0, 90)) + (wk.verse.text.length > 90 ? '…' : '') + '”' : ''}<br>${wk.services} services on the calendar · ${wk.published_this_week} video${wk.published_this_week === 1 ? '' : 's'} published this week${wk.minutes_this_week ? ' · ' + Math.round(wk.minutes_this_week / 60 * 10) / 10 + ' hours of them' : ''}${wk.latest ? `<br>Latest on the channel: <b>${esc(wk.latest)}</b>` : ''}</div>` : '';
  return `<div class="about"><div class="flame">${I.about.replace('<svg', '<svg width="72" height="72"')}</div><div><div class="kicker">ariseOS · Arise Server</div><h2>v${esc(o.version)} “${esc(o.codename)}”</h2>
    <dl class="kv"><dt>Host</dt><dd>${esc(o.hostname)}</dd><dt>Domain</dt><dd>${esc(o.realm || '—')}</dd><dt>System</dt><dd>${esc(m.os || '')}</dd><dt>Processor</dt><dd>${esc(m.cpu_model || '')} · ${m.cpu_count || '?'} cores</dd><dt>Memory</dt><dd>${esc(m.ram_total_h || '')}</dd><dt>Uptime</dt><dd>${fmtUp(S.stats?.uptime)}</dd><dt>Profile</dt><dd>${esc(o.profile)}</dd></dl>
    ${week}<div class="row" style="margin-top:14px"><button class="btn btn--ghost btn--xs" data-open="settings">System Settings</button><a class="btn btn--ghost btn--xs" href="https://github.com/Rehchu/Church-server-OS-" target="_blank" rel="noopener">Source</a></div></div>${whatsnew}${changes}</div>`;
};
V.about.after = root => $$('[data-open]', root).forEach(b => b.onclick = () => openApp(b.dataset.open));

/* ---------------- Security (31): the safety basics, round 3 ---------------- */
V.security = async () => {
  const o = await api('/security');
  const rows = o.rows || []; const n = { ok: 0, warn: 0, bad: 0 }; rows.forEach(r => n[r.level] = (n[r.level] || 0) + 1);
  const sc = o.scan || {}; const q = sc.quarantined || [];
  return `<div class="fade">
    <div class="grid" style="margin-bottom:14px">
      <div class="c3 panel ${o.worst === 'bad' ? 'panel--bad' : o.worst === 'warn' ? 'panel--warn' : 'panel--ok'}"><div class="stat"><span class="stat__l">Overall</span><span class="stat__v" style="font-size:22px">${o.worst === 'ok' ? 'All good' : o.worst === 'warn' ? 'Look' : 'Act'}</span><span class="stat__n">${n.ok} green · ${n.warn} amber · ${n.bad} red</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Two-step</span><span class="stat__v">${(o.twofa || []).length}<small>on</small></span><span class="stat__n">optional; Microsoft Authenticator</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Virus scan</span><span class="stat__v" style="font-size:22px">${sc.last ? (sc.last.found?.length ? sc.last.found.length + ' found' : 'clean') : 'not yet'}</span><span class="stat__n">${sc.last ? fmtT(sc.last.when) + ' · ' + fmtN(sc.last.scanned) + ' files' : 'first run Sunday 23:30'}</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Padlock</span><span class="stat__v" style="font-size:22px">${o.ca?.present ? 'on' : 'off'}</span><span class="stat__n">${o.ca?.present ? 'the church certificate, expires ' + esc(o.ca.not_after || '') : 'no certificate yet'}</span></div></div>
    </div>
    <div class="panel panel--flat" style="margin-bottom:14px"><div class="panel__hd"><h3>What keeps the box safe</h3><span class="sub">each line: what it is, and the command that fixes it</span></div>
      <div class="sec">${rows.map(r => `<div class="sec__row ${r.level}"><span class="pill ${r.level}">${esc(r.label)}</span><div><div>${esc(r.text)}</div>${r.fix ? `<code class="sec__fix">${esc(r.fix)}</code>` : ''}</div></div>`).join('')}</div></div>
    <div class="grid">
      <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Virus scan</h3><span class="sub">ClamAV · Sunday 23:30 · video and audio skipped</span></div>
        <p class="muted" style="font-size:13px">A found file is moved to <code>${esc(sc.quarantine || '/srv/arise/.quarantine')}</code>, never deleted. Putting one back is a typed name.</p>
        <div class="row" style="gap:8px;margin:10px 0"><button class="btn btn--sm" id="secScan">Scan now</button><span class="muted" style="font-size:12px">refused during a service; takes a while</span></div>
        ${q.length ? `<table class="tbl"><thead><tr><th>Quarantined</th><th>Signature</th><th></th></tr></thead><tbody>${q.map(x => `<tr><td class="mono" style="font-size:12px">${esc(x.file)}</td><td class="dim">${esc(x.sig)}</td><td class="acts"><button class="btn btn--ghost btn--xs" data-restore="${esc(x.file.split('/').pop())}">Put back…</button></td></tr>`).join('')}</tbody></table>` : '<p class="muted" style="font-size:13px">Quarantine is empty.</p>'}
      </div>
      <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Break-glass admin</h3><span class="sub">arise-rescue · the closet monitor only</span></div>
        <p class="muted" style="font-size:13px">For when the domain itself is down. It signs in at the closet monitor (Alt+F2), never over SSH (keys only, and it has none) and never here. Its password is on the safe card. Every sign-in is logged and pushed to Bradly.</p>
        <dl class="kv" style="margin-top:8px"><dt>Exists</dt><dd>${o.rescue?.exists ? 'yes' : 'no'}</dd><dt>Last use</dt><dd>${o.rescue?.last ? esc(o.rescue.last.when + ' · ' + o.rescue.last.via + ' from ' + o.rescue.last.from) : 'never'}</dd><dt>Rotate</dt><dd><code>sudo arisectl rescue rotate</code></dd></dl>
        <div class="panel__hd" style="margin-top:16px"><h3>Two-step sign-in</h3><span class="sub">optional, per person</span></div>
        <p class="muted" style="font-size:13px">${(o.twofa || []).length ? 'On for: ' + (o.twofa || []).map(esc).join(', ') + '.' : 'Nobody has it on yet.'} Anyone turns it on from the flame menu; Microsoft Authenticator scans the code. Lost phone: <code>sudo arisectl twofa reset &lt;user&gt;</code>.</p>
        <div class="row" style="margin-top:8px"><button class="btn btn--ghost btn--xs" id="secTwofa">Two-step for me…</button></div>
      </div>
    </div>
    ${o.demo ? '<p class="note" style="margin-top:14px">Sample data.</p>' : ''}
  </div>`;
};
V.security.after = root => {
  const sc = $('#secScan', root); if (sc) sc.onclick = async () => { const r = await act(sc, () => api('/security/scan/run', { method: 'POST' }), 'Scan started; the result lands here when it finishes'); if (r && r.ok === false) toast(r.err, 'warn'); };
  $$('[data-restore]', root).forEach(b => b.onclick = () => confirmType('Put a quarantined file back', b.dataset.restore, 'The scanner flagged this file. Putting it back means you have looked at it and want it where it was.', async () => { const r = await api('/security/scan/restore', { method: 'POST', body: { name: b.dataset.restore, confirm: b.dataset.restore } }); if (r.ok === false) throw new Error(r.err); toast(r.demo ? 'Sample mode: nothing changed' : r.out || 'Put back'); rerender('security'); }));
  const tf = $('#secTwofa', root); if (tf) tf.onclick = () => twofaModal();
};

/* ---------------- Two-step sign-in, optional (round 2, 11; Oct 28) ---------------- */
async function twofaModal() {
  let st; try { st = await api('/me/2fa'); } catch (e) { return toast(e.message, 'bad'); }
  if (!st.available) return modal(`<h2>Two-step sign-in</h2><p class="note">${esc(st.note || 'Not available on this server yet.')}</p><div class="acts"><button class="btn btn--ghost" data-close>Close</button></div>`);
  if (st.on) {
    return modal(`<h2>Two-step sign-in is on</h2><p class="muted">Since ${esc(st.since || '')}. Every sign-in asks for the six digits from Microsoft Authenticator after your password.</p>
      <form id="tfOff" style="display:grid;gap:8px;margin-top:12px"><input type="password" id="tfPw" placeholder="Your password" autocomplete="current-password"><input id="tfCode" inputmode="numeric" pattern="[0-9 ]*" placeholder="Code from Microsoft Authenticator" autocomplete="one-time-code">
      <div class="acts"><button type="button" class="btn btn--ghost" data-close>Keep it on</button><button class="btn btn--danger" type="submit">Turn it off</button></div></form>`, m => {
      $('#tfOff', m).onsubmit = async e => { e.preventDefault(); const r = await api('/me/2fa/disable', { method: 'POST', body: { password: $('#tfPw', m).value, code: $('#tfCode', m).value } }).catch(er => ({ ok: false, err: er.message })); if (r.ok === false) return toast(r.err, 'bad'); toast(r.demo ? 'Sample mode: nothing changed' : 'Two-step is off'); m.close(); ['security', 'directory'].forEach(id => S.wins[id] && rerender(id)); };
    });
  }
  modal(`<h2>Two-step sign-in</h2><p class="muted">Optional. After your password, a six-digit code from your phone. Nobody is made to use it; if you lose the phone, Bradly turns it off for you on the server.</p>
    <ol class="twofa__steps"><li>Install <b>Microsoft Authenticator</b> on your phone (App Store or Google Play).</li><li>In it: <b>+</b> → <b>Other account</b> → scan this code.</li><li>Type the six digits it shows, below.</li></ol>
    <div class="twofa__qr" id="tfQr"><div class="skeleton" style="width:160px;height:160px"></div></div>
    <p class="muted" style="font-size:12px;text-align:center">Can't scan? Type this key in the app instead: <code id="tfSecret">…</code><br>Shown once. It is not stored anywhere you can see it again.</p>
    <form id="tfOn" style="display:grid;gap:8px;margin-top:10px"><input id="tfCode" inputmode="numeric" pattern="[0-9 ]*" placeholder="The six digits" autocomplete="one-time-code" maxlength="7">
    <div class="acts"><button type="button" class="btn btn--ghost" data-close>Not now</button><button class="btn" type="submit">Turn it on</button></div></form>`, async m => {
    const r = await api('/me/2fa/setup', { method: 'POST' }).catch(er => ({ ok: false, err: er.message }));
    if (r.ok === false) { toast(r.err, 'bad'); return m.close(); }
    $('#tfQr', m).innerHTML = r.qr || `<div class="none">no QR; type the key</div>`; $('#tfSecret', m).textContent = (r.secret || '').replace(/(.{4})/g, '$1 ').trim();
    $('#tfCode', m).focus();
    $('#tfOn', m).onsubmit = async e => { e.preventDefault(); const x = await api('/me/2fa/enable', { method: 'POST', body: { code: $('#tfCode', m).value } }).catch(er => ({ ok: false, err: er.message })); if (x.ok === false) return toast(x.err, 'warn'); tone('done'); toast(x.demo ? 'Sample mode: nothing changed' : 'Two-step is on. Next sign-in asks for a code.'); m.close(); ['security', 'directory'].forEach(id => S.wins[id] && rerender(id)); };
  });
}
/* ---------------- v0.8 Exodus: Calendar, Weather, Calculator, Clock, Help, What's New ---------------- */
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const fmtDay = iso => { const d = new Date(iso); return isNaN(d) ? esc(iso) : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }); };
const fmtClock = iso => { const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); };
const toLocalInput = iso => (iso || '').slice(0, 16);

V.calendar = async () => {
  const now = new Date(); const c = S.cal = S.cal || { y: now.getFullYear(), m: now.getMonth() + 1 };
  const data = await api(`/calendar?year=${c.y}&month=${c.m}`); S.calData = data;
  const items = data.items || [], byDay = {};
  for (const it of items) { const k = it.start.slice(0, 10); (byDay[k] = byDay[k] || []).push(it); }
  const first = new Date(c.y, c.m - 1, 1).getDay(), days = new Date(c.y, c.m, 0).getDate(), today = now.toISOString().slice(0, 10);
  let grid = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(x => `<div class="calm__h">${x}</div>`).join('');
  for (let i = 0; i < first; i++) grid += '<div class="calm__d dim"></div>';
  for (let d = 1; d <= days; d++) {
    const k = `${c.y}-${String(c.m).padStart(2, '0')}-${String(d).padStart(2, '0')}`; const list = byDay[k] || [];
    grid += `<div class="calm__d ${k === today ? 'today' : ''}" data-day="${k}"><b>${d}</b>${list.slice(0, 3).map(it => `<button class="calm__ev ${it.service ? 'svc' : ''}" data-ev="${esc(it.id)}" title="${esc(it.title)}">${esc(fmtClock(it.start))} ${esc(it.title)}</button>`).join('')}${list.length > 3 ? `<span class="calm__more">+${list.length - 3} more</span>` : ''}</div>`;
  }
  const up = (data.upcoming || []).slice(0, 12);
  return `<div class="calapp"><div class="calapp__hd row row--between"><div class="row"><button class="btn btn--ghost btn--xs" id="calPrev" aria-label="Previous month">‹</button><h2 style="min-width:210px;text-align:center">${MONTHS[c.m - 1]} ${c.y}</h2><button class="btn btn--ghost btn--xs" id="calNext" aria-label="Next month">›</button><button class="btn btn--ghost btn--xs" id="calToday">Today</button></div>
      <div class="row">${!isMember() ? '<button class="btn btn--sm" id="calAdd">Add event</button>' : ''}<button class="btn btn--ghost btn--sm" id="calSub">Subscribe</button></div></div>
    <div class="calapp__body"><div class="calm">${grid}</div>
    <aside class="calapp__side"><div class="widget__kicker">Next two weeks</div>${up.length ? up.map(it => `<button class="calup ${it.service ? 'svc' : ''}" data-ev="${esc(it.id)}"><span class="calup__when">${fmtDay(it.start)}<br><b>${fmtClock(it.start)}</b></span><span class="calup__what"><b>${esc(it.title)}</b>${it.where ? `<br><small>${esc(it.where)}</small>` : ''}</span></button>`).join('') : '<p class="muted">Nothing on the calendar for the next two weeks beyond the services.</p>'}
    <p class="muted" style="font-size:12px;margin-top:12px">Services come from the server's settings; events are added here. ${data.demo ? 'Sample events say so in their titles.' : ''}</p></aside></div></div>`;
};
V.calendar.after = root => {
  const c = S.cal; const go = (dy) => { c.m += dy; if (c.m < 1) { c.m = 12; c.y--; } if (c.m > 12) { c.m = 1; c.y++; } rerender('calendar'); };
  $('#calPrev', root).onclick = () => go(-1); $('#calNext', root).onclick = () => go(1); $('#calToday', root).onclick = () => { const n = new Date(); c.y = n.getFullYear(); c.m = n.getMonth() + 1; rerender('calendar'); };
  $('#calSub', root).onclick = subscribeModal; const add = $('#calAdd', root); if (add) add.onclick = () => eventModal(null);
  $$('[data-ev]', root).forEach(b => b.onclick = () => { const it = (S.calData.items || []).concat(S.calData.upcoming || []).find(x => x.id === b.dataset.ev); if (it) eventDetails(it); });
  $$('.calm__d[data-day]', root).forEach(d => d.ondblclick = e => { if (isMember() || e.target.closest('button')) return; eventModal({ start: d.dataset.day + 'T18:30' }, true); });
  // On a phone the month's events are 4 px bars: a tap on the day opens its event, or lists them.
  $$('.calm__d[data-day]', root).forEach(d => d.addEventListener('click', e => {
    if (!isPhone()) return; const evs = $$('[data-ev]', d); if (!evs.length) return; e.preventDefault(); e.stopPropagation();
    if (evs.length === 1) return evs[0].click();
    const m = modal(`<h2>${esc(new Date(d.dataset.day + 'T12:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }))}</h2><div style="display:grid;gap:8px;margin-top:12px">${evs.map((b, i) => `<button class="btn btn--ghost" data-pick="${i}" style="justify-content:flex-start;text-align:left">${esc(b.title || b.textContent)}</button>`).join('')}</div><div class="acts"><button class="btn btn--ghost" data-close>Close</button></div>`);
    $$('[data-pick]', m).forEach(x => x.onclick = () => { m.close(); evs[+x.dataset.pick].click(); });
  }, true));
};
function eventDetails(it) {
  const when = `${fmtDay(it.start)} · ${fmtClock(it.start)}${it.end ? ' to ' + fmtClock(it.end) : ''}`;
  modal(`<h2>${esc(it.title)}</h2><dl class="kv" style="margin-top:12px"><dt>When</dt><dd>${when}</dd>${it.where ? `<dt>Where</dt><dd>${esc(it.where)}</dd>` : ''}${it.note ? `<dt>Note</dt><dd>${esc(it.note)}</dd>` : ''}${it.service ? '<dt>Kind</dt><dd>A service, from the server\'s settings (every week)</dd>' : `${it.is_service ? '<dt>Kind</dt><dd>Counts as a service</dd>' : ''}<dt>Added by</dt><dd>${esc(it.who || '')}</dd>`}</dl>
    <div class="acts">${!isMember() && !it.service ? `<button class="btn btn--danger btn--sm" id="evRm">Remove…</button><button class="btn btn--ghost btn--sm" id="evEd">Edit</button>` : ''}<button class="btn btn--ghost" data-close>Close</button></div>`, m => {
    const ed = $('#evEd', m); if (ed) ed.onclick = () => { m.close(); eventModal(it); };
    const rm = $('#evRm', m); if (rm) rm.onclick = () => { m.close(); confirmType('Remove this event', 'remove', `<b>${esc(it.title)}</b> on ${fmtDay(it.start)} comes off the calendar and the feed every Mac and phone reads.`, async () => { const r = await api(`/calendar/${encodeURIComponent(it.id)}`, { method: 'DELETE' }); if (r.ok === false) throw new Error(r.err); toast(r.demo ? 'Sample mode: nothing changed' : 'Removed'); rerender('calendar'); }); };
  });
}
function eventModal(it, isNew) {
  const e = it || {}; const editing = !!(it && it.id && !isNew);
  modal(`<h2>${editing ? 'Edit event' : 'Add an event'}</h2><form id="evf" style="margin-top:12px">
    <div class="field"><label>Title</label><input id="evT" value="${esc(e.title || '')}" maxlength="120" required autocomplete="off"></div>
    <div class="row"><div class="field" style="flex:1"><label>Starts</label><input id="evS" type="datetime-local" value="${esc(toLocalInput(e.start))}" required></div><div class="field" style="flex:1"><label>Ends (optional)</label><input id="evE" type="datetime-local" value="${esc(toLocalInput(e.end))}"></div></div>
    <div class="field"><label>Where</label><input id="evW" value="${esc(e.where || '')}" maxlength="120" placeholder="Pineville, the fellowship hall…"></div>
    <div class="field"><label>Note</label><textarea id="evN" rows="3" maxlength="1000">${esc(e.note || '')}</textarea></div>
    <div class="field"><label>Who's in it (optional)</label><input id="evP" value="${esc((e.people || []).join(', '))}" placeholder="kristina.robinson, @Media" autocomplete="off"><span class="hint">People and @groups get a reminder 30 minutes before.</span></div>
    <label class="check" style="margin:4px 0 10px"><input type="checkbox" id="evSvc" ${e.is_service ? 'checked' : ''}> Counts as a service <span class="hint">(Easter, The Outpour: no updates, restarts or Mac changes while it runs, and the all-green an hour before)</span></label>
    <div class="acts"><button type="button" class="btn btn--ghost" data-close>Cancel</button><button class="btn" type="submit">${editing ? 'Save' : 'Add'}</button></div></form>`, m => {
    $('#evf', m).onsubmit = async ev => { ev.preventDefault(); const body = { title: $('#evT', m).value, start: $('#evS', m).value, end: $('#evE', m).value, where: $('#evW', m).value, note: $('#evN', m).value, people: $('#evP', m).value.split(/[,\s]+/).filter(Boolean), is_service: $('#evSvc', m).checked };
      const r = await api(editing ? `/calendar/${encodeURIComponent(it.id)}` : '/calendar', { method: editing ? 'PUT' : 'POST', body }).catch(er => ({ ok: false, err: er.message }));
      if (r.ok === false) return toast(r.err, 'bad'); toast(r.demo ? 'Sample mode: nothing changed' : editing ? 'Saved' : 'Added to the calendar'); tone('done'); m.close(); rerender('calendar'); };
    $('#evT', m).focus();
  });
}
async function subscribeModal() {
  let s; try { s = await api('/calendar/subscribe'); } catch (e) { return toast(e.message, 'bad'); }
  modal(`<h2>Subscribe to the church calendar</h2><p class="muted">One calendar, kept on the server. Your Mac or phone checks it every hour; services and events appear by themselves.</p>
    <div class="field" style="margin-top:12px"><label>The address</label><div class="row"><input id="subUrl" readonly value="${esc(s.webcal)}" style="flex:1"><button class="btn btn--ghost btn--sm" id="subCopy">Copy</button></div></div>
    <dl class="kv"><dt>On a Mac</dt><dd>${esc(s.mac)}</dd><dt>On an iPhone</dt><dd>${esc(s.iphone)}</dd><dt>Note</dt><dd>${esc(s.note)}</dd></dl>
    <div class="acts"><a class="btn btn--ghost btn--sm" href="${esc(s.webcal)}">Open in Calendar</a><button class="btn btn--ghost" data-close>Close</button></div>`, m => { $('#subCopy', m).onclick = () => copyText(s.webcal, $('#subCopy', m)); });
}

/* Weather: Open-Meteo for Pineville, cached on the server; offline says so */
const WX = {
  sun: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.5" fill="currentColor"/><g stroke="currentColor" stroke-width="2"><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/></g></svg>',
  'cloud-sun': '<svg viewBox="0 0 24 24"><circle cx="8" cy="8" r="3.5" fill="currentColor" opacity=".7"/><path d="M8 20h10a4 4 0 0 0 .5-8A6 6 0 0 0 7 13a3.5 3.5 0 0 0 1 7z" fill="currentColor"/></svg>',
  cloud: '<svg viewBox="0 0 24 24"><path d="M7 19h11a4 4 0 0 0 .6-8A6 6 0 0 0 7 12a3.5 3.5 0 0 0 0 7z" fill="currentColor"/></svg>',
  fog: '<svg viewBox="0 0 24 24"><g stroke="currentColor" stroke-width="2"><path d="M3 9h18M5 13h14M3 17h18"/></g></svg>',
  rain: '<svg viewBox="0 0 24 24"><path d="M7 15h11a4 4 0 0 0 .6-8A6 6 0 0 0 7 8a3.5 3.5 0 0 0 0 7z" fill="currentColor"/><g stroke="currentColor" stroke-width="2"><path d="M8 18l-1 3M12 18l-1 3M16 18l-1 3"/></g></svg>',
  snow: '<svg viewBox="0 0 24 24"><path d="M7 14h11a4 4 0 0 0 .6-8A6 6 0 0 0 7 7a3.5 3.5 0 0 0 0 7z" fill="currentColor"/><g fill="currentColor"><circle cx="8" cy="19" r="1.3"/><circle cx="12" cy="21" r="1.3"/><circle cx="16" cy="19" r="1.3"/></g></svg>',
  storm: '<svg viewBox="0 0 24 24"><path d="M7 14h11a4 4 0 0 0 .6-8A6 6 0 0 0 7 7a3.5 3.5 0 0 0 0 7z" fill="currentColor"/><path d="M13 13l-3 5h3l-1 5 4-7h-3z" fill="currentColor"/></svg>',
};
const wxIcon = k => `<i class="wx__i">${WX[k] || WX.cloud}</i>`;
async function loadWeather(force) {
  if (!force && S.weather && Date.now() - (S.weatherAt || 0) < 30 * 60000) return S.weather;
  try { S.weather = await api('/weather'); } catch (e) { S.weather = { ok: false, why: e.message }; }
  S.weatherAt = Date.now(); return S.weather;
}
function weatherWidget() {
  const w = S.weather; if (!w) return '';
  if (!w.ok) return `<div class="widget widget--wx"><div class="widget__kicker">Weather · Pineville</div><div class="widget__sub">No weather (offline)</div></div>`;
  const n = w.now || {}; const dayName = d => new Date(d.date + 'T12:00').toLocaleDateString('en-US', { weekday: 'short' });
  return `<div data-wg="weather" class="widget widget--wx"><div class="widget__kicker">Weather · ${esc(w.place)}${w.stale ? ' · from earlier' : ''}${w.demo ? ' · sample' : ''}</div>
    <div class="wx__now">${wxIcon(n.icon)}<span class="widget__big">${n.temp ?? '–'}°</span><span class="widget__sub">${esc(n.words)}<br>feels ${n.feels ?? '–'}° · wind ${n.wind ?? '–'} mph</span></div>
    <div class="wx__days">${(w.days || []).slice(1, 6).map(d => `<div><b>${dayName(d)}</b>${wxIcon(d.icon)}<span>${d.hi ?? '–'}°<i>${d.lo ?? '–'}°</i></span><em>${d.rain >= 20 ? d.rain + '%' : ''}</em></div>`).join('')}</div>
    ${(w.places || []).slice(1).filter(p => p.ok).map(p => `<div class="widget__row wx__also"><span>${esc(p.place)}</span><b>${p.now?.temp ?? '–'}° · ${esc(p.now?.words || '')}</b></div>`).join('')}</div>`;
}

/* Calculator: a safe evaluator (no eval), also behind Spotlight */
function calcEval(src) {
  const s = String(src ?? '').replace(/×/g, '*').replace(/÷/g, '/').replace(/−/g, '-').replace(/,/g, '').trim();
  if (!s || !/^[\d\s.+\-*/%^()]+$/.test(s) || !/\d/.test(s)) return NaN;
  const toks = s.match(/\d+\.?\d*|\.\d+|[+\-*/%^()]/g) || [];
  const out = [], ops = [], prec = { '+': 1, '-': 1, '*': 2, '/': 2, '%': 2, '^': 3, u: 2.5 }, right = { '^': true, u: true };  // -3^2 is -9, as on paper
  let prev = null;
  for (const t of toks) {
    if (/^[\d.]/.test(t)) { if (prev === 'n' || prev === ')') return NaN; out.push(parseFloat(t)); prev = 'n'; continue; }
    if (t === '(') { if (prev === 'n' || prev === ')') return NaN; ops.push(t); prev = '('; continue; }
    if (t === ')') { while (ops.length && ops[ops.length - 1] !== '(') out.push(ops.pop()); if (!ops.length) return NaN; ops.pop(); prev = ')'; continue; }
    let op = t;
    if (t === '-' && (prev === null || prev === 'op' || prev === '(')) op = 'u'; else if (prev !== 'n' && prev !== ')') return NaN;
    while (ops.length) { const o = ops[ops.length - 1]; if (o === '(') break; if (prec[o] > prec[op] || (prec[o] === prec[op] && !right[op])) out.push(ops.pop()); else break; }
    ops.push(op); prev = 'op';
  }
  if (prev === 'op' || prev === '(') return NaN;
  while (ops.length) { const o = ops.pop(); if (o === '(') return NaN; out.push(o); }
  const st = [];
  for (const t of out) {
    if (typeof t === 'number') { st.push(t); continue; }
    if (t === 'u') { st.push(-st.pop()); continue; }
    const b = st.pop(), a = st.pop(); if (a === undefined || b === undefined) return NaN;
    st.push(t === '+' ? a + b : t === '-' ? a - b : t === '*' ? a * b : t === '/' ? a / b : t === '%' ? a % b : Math.pow(a, b));
  }
  return st.length === 1 ? st[0] : NaN;
}
const fmtCalc = v => isNaN(v) ? '' : !isFinite(v) ? '∞' : String(+v.toPrecision(12));
const looksLikeSum = q => /[+\-*/^%×÷−]/.test(q) && /^[\d\s.+\-*/%^()×÷−,]+$/.test(q) && /\d/.test(q) && !isNaN(calcEval(q));
V.calc = async () => { const st = S.calc = S.calc || { expr: '', res: '0' };
  return `<div class="calc"><div class="calc__disp" aria-live="polite"><div class="calc__expr" id="calcExpr">${esc(st.expr)}</div><div class="calc__res" id="calcRes">${esc(st.res)}</div></div>
    <div class="calc__keys">${['C', '(', ')', '÷', '7', '8', '9', '×', '4', '5', '6', '−', '1', '2', '3', '+', '0', '.', '⌫', '='].map(k => `<button data-k="${k}" class="${'÷×−+'.includes(k) ? 'op' : ''} ${k === '=' ? 'eq' : ''}" aria-label="${k === '⌫' ? 'Delete' : k === 'C' ? 'Clear' : k}">${k}</button>`).join('')}</div>
    <p class="muted" style="font-size:12px;margin-top:12px">Type a sum into Spotlight too: ${esc(kbd('⌘Space'))}, then <span class="mono">1250*0.8</span>.</p></div>`; };
V.calc.after = root => {
  const st = S.calc;
  const paint = () => { $('#calcExpr', root).textContent = st.expr; const v = fmtCalc(calcEval(st.expr)); $('#calcRes', root).textContent = st.expr ? (v || '…') : st.res; };
  const press = k => { tone('click'); if (k === 'C') { st.expr = ''; st.res = '0'; } else if (k === '⌫') st.expr = st.expr.slice(0, -1); else if (k === '=') { const v = fmtCalc(calcEval(st.expr)); if (v) { st.res = v; st.expr = ''; } } else st.expr += k; paint(); };
  $$('[data-k]', root).forEach(b => b.onclick = () => press(b.dataset.k));
  root.tabIndex = 0; root.onkeydown = e => { if (e.metaKey || e.ctrlKey) return; const map = { '*': '×', '/': '÷', '-': '−', Enter: '=', '=': '=', Backspace: '⌫', Escape: 'C', Delete: 'C' }; const k = map[e.key] || (/^[\d.+()%^]$/.test(e.key) ? e.key : null); if (k) { e.preventDefault(); e.stopPropagation(); press(k); } };
  paint(); if (!isPhone()) root.focus();
};

/* Clock: world clock, timer, stopwatch, alarm */
const ZONES = [['Pineville', 'America/Chicago'], ['New York', 'America/New_York'], ['Los Angeles', 'America/Los_Angeles'], ['Jerusalem', 'Asia/Jerusalem']];
const mmss = s => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); };
V.clock = async () => { const c = S.clock = S.clock || { tab: 'world', timer: { total: 300, left: 300, on: false, at: 0 }, sw: { el: 0, on: false, t0: 0, laps: [] }, alarm: null };
  return `<div class="clockapp"><div class="tabs" id="clockTabs">${[['world', 'World clock'], ['timer', 'Timer'], ['sw', 'Stopwatch'], ['alarm', 'Alarm']].map(([k, l]) => `<button data-t="${k}" class="${c.tab === k ? 'active' : ''}">${l}</button>`).join('')}</div><div id="clockBody"></div></div>`; };
V.clock.after = root => {
  const c = S.clock; $$('#clockTabs button', root).forEach(b => b.onclick = () => { c.tab = b.dataset.t; $$('#clockTabs button', root).forEach(x => x.classList.toggle('active', x === b)); paintClock(root, true); });
  clearInterval(S.clockT); S.clockT = setInterval(() => { if (!document.body.contains(root)) { clearInterval(S.clockT); return; } clockTick(); paintClock(root, false); }, 250);
  paintClock(root, true);
};
function clockTick() {
  const c = S.clock; if (!c) return; const now = Date.now();
  if (c.timer.on) { c.timer.left = Math.max(0, (c.timer.at - now) / 1000); if (c.timer.left <= 0) { c.timer.on = false; c.timer.left = 0; tone('done'); toast('Timer done', 'ok', 8000); } }
  if (c.alarm && !c.alarm.rang) { const d = new Date(); const hm = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); if (hm === c.alarm.at) { c.alarm.rang = true; tone('done'); setTimeout(() => tone('done'), 700); toast(`Alarm · ${fmtHM(c.alarm.at)}${c.alarm.label ? ' · ' + c.alarm.label : ''}`, 'warn', 15000); } }
}
const fmtHM = hm => { const [h, m] = hm.split(':').map(Number); const d = new Date(); d.setHours(h, m); return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); };
function paintClock(root, full) {
  const c = S.clock, body = $('#clockBody', root); if (!body) return; const now = new Date();
  if (c.tab === 'world') {
    if (full || !$('.world', body)) body.innerHTML = `<div class="world">${ZONES.map(([n, z]) => `<div class="world__z" data-z="${z}"><span class="widget__kicker">${n}</span><b class="world__t"></b><small class="world__d"></small></div>`).join('')}</div>`;
    $$('.world__z', body).forEach(el => { const z = el.dataset.z; $('.world__t', el).textContent = now.toLocaleTimeString('en-US', { timeZone: z, hour: 'numeric', minute: '2-digit' }); $('.world__d', el).textContent = now.toLocaleDateString('en-US', { timeZone: z, weekday: 'long' }) + (z === 'America/Chicago' ? ' · here' : ''); });
  } else if (c.tab === 'timer') {
    const t = c.timer;
    if (full || !$('.timer', body)) { body.innerHTML = `<div class="timer"><div class="clock__big" id="tmLeft"></div><div class="row" style="justify-content:center;gap:8px">${[1, 5, 10, 15, 30].map(m => `<button class="btn btn--ghost btn--xs" data-min="${m}">${m} min</button>`).join('')}<input id="tmIn" type="text" inputmode="numeric" placeholder="mm:ss" style="width:84px" aria-label="Minutes and seconds"></div>
      <div class="row" style="justify-content:center;margin-top:14px"><button class="btn" id="tmGo"></button><button class="btn btn--ghost" id="tmReset">Reset</button></div><p class="muted" style="text-align:center;font-size:12px;margin-top:10px">A quiet chime at zero (if sounds are on) and a note on the screen.</p></div>`;
      $$('[data-min]', body).forEach(b => b.onclick = () => { t.total = t.left = +b.dataset.min * 60; t.on = false; paintClock(root, false); });
      $('#tmIn', body).onchange = e => { const m = e.target.value.match(/^(\d{1,3})(?::(\d{1,2}))?$/); if (!m) return toast('Type minutes, or mm:ss', 'warn'); t.total = t.left = +m[1] * 60 + (+m[2] || 0); t.on = false; e.target.value = ''; paintClock(root, false); };
      $('#tmGo', body).onclick = () => { tone('click'); if (t.on) { t.on = false; } else { if (t.left <= 0) t.left = t.total; t.at = Date.now() + t.left * 1000; t.on = true; } paintClock(root, false); };
      $('#tmReset', body).onclick = () => { t.on = false; t.left = t.total; paintClock(root, false); };
    }
    $('#tmLeft', body).textContent = mmss(t.left); $('#tmGo', body).textContent = t.on ? 'Pause' : t.left < t.total && t.left > 0 ? 'Resume' : 'Start';
  } else if (c.tab === 'sw') {
    const s = c.sw; const el = s.on ? s.el + (Date.now() - s.t0) : s.el;
    if (full || !$('.sw', body)) { body.innerHTML = `<div class="sw"><div class="clock__big" id="swT"></div><div class="row" style="justify-content:center"><button class="btn" id="swGo"></button><button class="btn btn--ghost" id="swLap">Lap</button><button class="btn btn--ghost" id="swReset">Reset</button></div><ol class="sw__laps" id="swLaps"></ol></div>`;
      $('#swGo', body).onclick = () => { tone('click'); if (s.on) { s.el += Date.now() - s.t0; s.on = false; } else { s.t0 = Date.now(); s.on = true; } paintClock(root, false); };
      $('#swLap', body).onclick = () => { const v = s.on ? s.el + (Date.now() - s.t0) : s.el; if (v > 0) { s.laps.unshift(v); paintClock(root, true); } };
      $('#swReset', body).onclick = () => { s.on = false; s.el = 0; s.laps = []; paintClock(root, true); };
      $('#swLaps', body).innerHTML = s.laps.map((l, i) => `<li><span>Lap ${s.laps.length - i}</span><b>${fmtSw(l)}</b></li>`).join('');
    }
    $('#swT', body).textContent = fmtSw(el); $('#swGo', body).textContent = s.on ? 'Stop' : el ? 'Resume' : 'Start'; $('#swLap', body).disabled = !el; $('#swReset', body).disabled = !el && !s.laps.length;
  } else {
    const a = c.alarm;
    if (full || !$('.alarm', body)) { body.innerHTML = `<div class="alarm"><div class="clock__big">${a ? fmtHM(a.at) : '—'}</div><p class="muted" style="text-align:center">${a ? (a.rang ? 'Rang. Set another or clear it.' : `Set${a.label ? ' · ' + esc(a.label) : ''}. It rings while this page is open.`) : 'No alarm set. It rings on this screen while the page is open; it is not a phone alarm.'}</p>
      <form id="alf" class="row" style="justify-content:center;margin-top:12px"><input id="alT" type="time" required aria-label="Time"><input id="alL" placeholder="Label (optional)" maxlength="40" style="width:160px"><button class="btn btn--sm" type="submit">Set</button>${a ? '<button type="button" class="btn btn--ghost btn--sm" id="alClr">Clear</button>' : ''}</form></div>`;
      $('#alf', body).onsubmit = e => { e.preventDefault(); c.alarm = { at: $('#alT', body).value, label: $('#alL', body).value.trim(), rang: false }; tone('click'); paintClock(root, true); };
      const clr = $('#alClr', body); if (clr) clr.onclick = () => { c.alarm = null; paintClock(root, true); };
    }
  }
}
const fmtSw = ms => { const t = Math.floor(ms / 10), cs = t % 100, s = Math.floor(t / 100) % 60, m = Math.floor(t / 6000); return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(cs).padStart(2, '0')}`; };

/* Help: the docs inside the dashboard */
V.help = async () => {
  const h = S.help = S.help || { name: null, q: '' };
  const list = await api('/help'); S.helpList = list;
  let hc = null; try { hc = await api('/help/contacts'); } catch {}
  S.helpCall = hc ? `<div class="help__call"><b>Something not working?</b> <a href="${esc(hc.it_portal)}" target="_blank" rel="noopener">The IT portal</a> takes a request, or call ${esc((hc.call || []).map(c => c.name.replace(/^(Minister|Pastor|Apostle) /, '')).join(', ').replace(/, ([^,]*)$/, ' or $1'))}.</div>` : '';
  const docs = list.docs || []; if (!h.name) h.name = isMember() ? 'PORTAL-GUIDE' : (docs.find(d => d.name === 'README') ? 'README' : docs[0]?.name);
  return `<div class="help"><aside class="help__side">${S.helpCall || ''}<input id="helpQ" class="help__q" placeholder="Search the docs" value="${esc(h.q)}" autocomplete="off" aria-label="Search the docs"><div id="helpList" class="help__list"></div></aside><article class="help__doc" id="helpDoc"><div class="skeleton" style="width:50%"></div></article></div>`;
};
V.help.after = root => {
  const h = S.help, docs = S.helpList.docs || [];
  const paintList = hits => { const q = h.q.trim().toLowerCase(); const el = $('#helpList', root);
    if (hits) { el.innerHTML = hits.length ? hits.map(x => `<button class="help__it ${x.name === h.name ? 'on' : ''}" data-doc="${esc(x.name)}"><b>${esc(x.title)}</b><span>${esc(x.snippet)}</span></button>`).join('') : '<p class="muted" style="padding:10px">Nothing in the docs for that.</p>'; }
    else el.innerHTML = docs.filter(d => !q || d.title.toLowerCase().includes(q) || d.name.toLowerCase().includes(q) || (d.blurb || '').toLowerCase().includes(q)).map(d => `<button class="help__it ${d.name === h.name ? 'on' : ''}" data-doc="${esc(d.name)}"><b>${esc(d.title)}</b><span>${esc(d.blurb || d.name)}</span></button>`).join('');
    $$('[data-doc]', el).forEach(b => b.onclick = () => { h.name = b.dataset.doc; paintList(hits); loadDoc(); }); };
  const loadDoc = async () => { const box = $('#helpDoc', root); if (!h.name) { box.innerHTML = '<p class="muted">No documents.</p>'; return; } try { const d = await api(`/help/${encodeURIComponent(h.name)}`); if (!document.body.contains(box)) return; const html = d.html || `<p class="muted">${esc(d.error?.message || d.err || 'This document did not load.')}</p>`; box.innerHTML = (/^\s*<h1/i.test(html) ? '' : `<h1>${esc(d.title || h.name)}</h1>`) + html; box.scrollTop = 0;
      $$('a', box).forEach(a => { const href = a.getAttribute('href') || ''; const m = href.match(/^(?:\.\.\/|\.\/)?(?:docs\/)?([A-Za-z0-9_-]+)\.md(#.*)?$/); if (m) { a.onclick = e => { e.preventDefault(); h.name = m[1] === 'README' || m[1] ? m[1] : h.name; paintList(); loadDoc(); }; } else if (/^https?:/.test(href)) { a.target = '_blank'; a.rel = 'noopener'; } }); }
    catch (e) { box.innerHTML = `<p class="muted">${esc(e.message)}</p>`; } };
  $('#helpQ', root).oninput = e => { h.q = e.target.value; clearTimeout(S.helpT); if (h.q.trim().length >= 2) S.helpT = setTimeout(async () => { try { const r = await api(`/help?q=${encodeURIComponent(h.q.trim())}`); if ($('#helpQ', root).value === h.q) paintList(r.search?.hits || null); } catch {} }, 250); paintList(); };
  paintList(); loadDoc();
};
function shortcutsSheet() {
  const rows = [['⌘Space', 'Spotlight: apps, people, files, a verse, a sum'], ['F1', 'Help'], ['⌘/', 'This sheet'], ['F3', 'Mission Control'], ['F4', 'Launchpad'], ['⌘Tab', 'Switch windows'], ['⌘W', 'Close the window'], ['⌘M', 'Minimise'], ['⌘R', 'Refresh the window'], ['⌘←  ⌘→', 'Snap the window to the left or right half'], ['⌘↑', 'Fill the screen'], ['⌘↓', 'Put the window back'], ['⌘I', 'Get Info (Finder)'], ['⇧⌘N', 'New folder (Finder)'], ['⌃⌘Q', 'Lock the screen'], ['Esc', 'Close whatever is open']];
  modal(`<h2>Keyboard shortcuts</h2><p class="muted">${IS_MAC ? 'On a Mac keyboard.' : 'On a Windows keyboard: Ctrl does what ⌘ does on a Mac.'}</p><table class="tbl keys" style="margin-top:10px"><tbody>${rows.map(([k, w]) => `<tr><td class="mono">${esc(kbd(k))}</td><td>${esc(w)}</td></tr>`).join('')}</tbody></table><div class="acts"><button class="btn btn--ghost" data-close>Close</button></div>`);
}
const firstName = () => { const d = String(S.me?.display || S.me?.name || '').trim(); const n = d ? d.split(/\s+/)[0] : String(S.user || '').split('.')[0]; return n ? n[0].toUpperCase() + n.slice(1) : ''; };
function greet() {
  if (S.kiosk || !S.user) return;
  try { if (sessionStorage.getItem('arise.greeted') === S.user) return; sessionStorage.setItem('arise.greeted', S.user); } catch {}
  const h = new Date().getHours(); const part = h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening'; const ref = S.church?.verse?.ref;
  toast(`Good ${part}, ${S.me?.greeting || firstName() || 'there'}.${ref ? ' Today: ' + ref + '.' : ''}`, 'ok', 3000);
}
async function whatsNewToast() {
  try { const w = await api('/about/whatsnew'); if (!w.version) return; const seen = PREF.get('seen', ''); if (seen !== w.version) { PREF.set('seen', w.version); if (seen) { toast(`ariseOS is now v${w.version} “${w.codename}”. What's new is in About.`, 'ok', 9000); tone('done'); } } } catch {}
}

/* Snap windows: edges and corners while dragging, ⌘-arrows on the keyboard */
function snapZone(x, y) { const st = $('#stage'), r = st.getBoundingClientRect(); const px = x - r.left, py = y - r.top, W = r.width, H = r.height, m = 12; const L = px < m, R = px > W - m, T = py < m, B = py > H - m; if ((L || R) && T) return L ? 'tl' : 'tr'; if ((L || R) && B) return L ? 'bl' : 'br'; if (T) return 'max'; if (L) return 'left'; if (R) return 'right'; return null; }
function snapRect(zone) { const st = $('#stage'), W = st.clientWidth, H = st.clientHeight - 84, hw = Math.floor(W / 2), hh = Math.floor(H / 2); return { left: [0, 0, hw, H], right: [hw, 0, W - hw, H], max: [0, 0, W, H], tl: [0, 0, hw, hh], tr: [hw, 0, W - hw, hh], bl: [0, hh, hw, H - hh], br: [hw, hh, W - hw, H - hh] }[zone]; }
function snapGhost(zone) { let g = $('#snapGhost'); if (!zone) { if (g) g.hidden = true; return; } if (!g) { g = document.createElement('div'); g.id = 'snapGhost'; g.className = 'snapghost'; $('#stage').appendChild(g); } const [x, y, w, h] = snapRect(zone); Object.assign(g.style, { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px' }); g.hidden = false; }
function snapTo(id, zone) {
  const w = S.wins[id]; if (!w || isPhone()) return; const el = w.el;
  if (zone === 'max') { if (!w.max) { w.max = true; el.classList.add('max'); } w.snap = 'max'; return; }
  if (w.max) { w.max = false; el.classList.remove('max'); }
  if (!w.pre) w.pre = { left: el.style.left, top: el.style.top, width: el.style.width, height: el.style.height };
  const [x, y, ww, hh] = snapRect(zone); Object.assign(el.style, { left: x + 'px', top: y + 'px', width: ww + 'px', height: hh + 'px' }); w.snap = zone;
}
function unsnap(id) { const w = S.wins[id]; if (!w) return false; if (w.max) { w.max = false; w.el.classList.remove('max'); w.snap = null; return true; } if (w.pre) { Object.assign(w.el.style, w.pre); w.pre = null; w.snap = null; return true; } return false; }
function snapKey(id, key) { if (key === 'ArrowLeft') snapTo(id, 'left'); else if (key === 'ArrowRight') snapTo(id, 'right'); else if (key === 'ArrowUp') snapTo(id, 'max'); else if (key === 'ArrowDown') { if (!unsnap(id)) minApp(id); } }

/* Accessibility: larger text, reduce motion, high contrast; menus by keyboard */
const A11Y = [['text', 'Larger text', 'bigger type everywhere'], ['motion', 'Reduce motion', 'no animations, no dock zoom'], ['contrast', 'High contrast', 'brighter text, firmer lines']];
function applyA11y() { const b = document.body; b.classList.toggle('a11y-text', PREF.get('a11y.text', '0') === '1'); b.classList.toggle('a11y-motion', PREF.get('a11y.motion', '0') === '1' || matchMedia('(prefers-reduced-motion: reduce)').matches); b.classList.toggle('a11y-contrast', PREF.get('a11y.contrast', '0') === '1'); }
const reducedMotion = () => document.body.classList.contains('a11y-motion');
function ccA11y() { return A11Y.map(([k, n, w]) => { const on = PREF.get('a11y.' + k, '0') === '1'; return `<button class="${on ? 'ok' : ''}" data-act="a11y-${k}" aria-pressed="${on}"><b>${n}</b><span>${on ? 'on · ' : ''}${w}</span></button>`; }).join(''); }
document.addEventListener('keydown', e => {
  if (!menuOpen) return; const bs = $$('#menuDrop button'); if (!bs.length) return; let i = bs.indexOf(document.activeElement);
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); i = (i + (e.key === 'ArrowDown' ? 1 : -1) + bs.length) % bs.length; bs[i].focus(); }
  else if (e.key === 'Enter' && i >= 0) { e.preventDefault(); bs[i].click(); }
  else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { const ms = [$('#barLogo'), ...$$('#menus button')]; const j = ms.indexOf(menuOpen); if (j >= 0) { e.preventDefault(); ms[(j + (e.key === 'ArrowRight' ? 1 : -1) + ms.length) % ms.length].click(); setTimeout(() => $('#menuDrop button')?.focus(), 0); } }
});

/* The power menu: gentler steps first; the server refuses all of it during a service */
function restartUnit(unit, what, word) {
  confirmType(`Restart ${what}`, word, unit === 'arise-web.service' ? 'The dashboard goes away for a few seconds and this page reloads itself. Nothing else is touched.' : 'Macs signed in keep working on cached accounts; a sign-in during the restart fails once. About twenty seconds. Refused during a service.', async () => {
    const r = await api(`/services/${encodeURIComponent(unit)}/restart`, { method: 'POST' }); if (r.ok === false) throw new Error(r.err);
    toast(r.demo ? 'Sample mode: nothing changed' : `Restarting ${what}…`, 'warn', 6000); if (unit === 'arise-web.service' && !r.demo) setTimeout(() => location.reload(), 4000);
  });
}
const POWER_MENU = () => [{ h: 'Power' }, ['Restart the dashboard', () => restartUnit('arise-web.service', 'the dashboard', 'dashboard')], ['Restart the domain', () => restartUnit('samba-ad-dc.service', 'the domain', 'domain')], ['Restart…', () => powerAsk('reboot')], ['Shut Down…', () => powerAsk('poweroff')]];

/* The password meter and the domain's rules in words */
function pwScore(pw, user) {
  if (!pw) return 0; let s = 0; const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter(r => r.test(pw)).length;
  if (pw.length >= 8) s++; if (pw.length >= 12) s++; if (pw.length >= 16) s++; if (kinds >= 3) s++; if (kinds === 4 && pw.length >= 12) s++;
  const parts = String(user || '').toLowerCase().split(/[.\s_-]+/).filter(p => p.length >= 3); if (parts.some(p => pw.toLowerCase().includes(p))) s = Math.min(s, 1);
  if (/^(.)\1+$/.test(pw) || /^(?:0123|1234|2345|3456|4567|5678|6789|abcd|qwer|pass)/i.test(pw)) s = Math.min(s, 1);
  return Math.min(4, s);
}
const PW_WORDS = ['', 'Weak', 'Fair', 'Good', 'Strong'];

/* ---------------- v0.8 Exodus: the system apps and the Store (round 3) ---------------- */
const mb = n => n == null ? '—' : n >= 1024 ? (n / 1024).toFixed(1) + ' GB' : n + ' MB';
const hl = (text, q) => { const e = esc(text); if (!q) return e; const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'); return e.replace(re, m => `<mark>${m}</mark>`); };
const ago2 = t => t ? ago(t) : 'never';

/* System Settings: one window, like macOS (round 3, 3) */
const SETTINGS_SECTIONS = [['appearance', 'Appearance'], ['users', 'Users'], ['sharing', 'Sharing'], ['backups', 'Backups'], ['updates', 'Software Update'], ['time', 'Time'], ['notifications', 'Notifications'], ['power', 'Power'], ['config', 'Config file'], ['about', 'About']];
V.settings = async () => {
  S.settingsSec = S.settingsSec || 'appearance';
  const q = async (p, d) => { try { return await api(p); } catch { return d; } };
  const [s, u, n, pk, sh, au] = await Promise.all([q('/settings', {}), q('/updates', {}), q('/notify', {}), q('/push/key', {}), q('/shares', { shares: [] }), q('/automations', { timers: [] })]);
  const o = S.overview || {}; const c = S.church || {};
  const bone = PREF.get('theme', 'dark') === 'bone', snd = PREF.get('sounds', '1') === '1';
  const sec = {
    appearance: `<h2>Appearance</h2><p class="note" style="margin-bottom:14px">These live in this browser (and on the closet monitor, which stays dark). Control Center has the same switches.</p>
      <div class="kv"><dt>Theme</dt><dd>${bone ? 'Bone (light paper)' : 'House Lights Down (dark stage)'} <button class="btn btn--ghost btn--xs" data-pref="theme">Switch</button></dd>
      <dt>Sounds</dt><dd>${snd ? 'on, quiet' : 'off'} <button class="btn btn--ghost btn--xs" data-pref="sounds">${snd ? 'Turn off' : 'Turn on'}</button></dd>
      <dt>Accessibility</dt><dd>${A11Y.map(([k, n]) => `${n}: ${PREF.get('a11y.' + k, '0') === '1' ? 'on' : 'off'}`).join(' · ')} <span class="muted">(Control Center)</span></dd>
      <dt>Wallpaper</dt><dd>The ink and red stage (round 2, 33: stays)</dd></div>`,
    users: `<h2>Users</h2><div class="kv"><dt>Directory</dt><dd>${esc(o.realm || s.directory?.realm || '')} · ${o.directory_ok ? 'online' : 'down'}</dd><dt>Users</dt><dd>${o.counts?.users ?? '—'}</dd><dt>Groups</dt><dd>${o.counts?.groups ?? '—'}</dd><dt>Computers</dt><dd>${o.counts?.computers ?? '—'}</dd><dt>Admins</dt><dd>${esc(s.web?.admins_group || 'Domain Admins')} · admin user ${esc(s.web?.admin_user || '')}</dd><dt>Member sign-in</dt><dd>${s.web?.member_login === false ? 'off' : 'on: anyone in the directory gets the portal'}</dd></div>
      <p class="note" style="margin-top:12px">Names are first.last. Two-step sign-in is optional per person (Microsoft Authenticator when they turn it on).</p><div class="row" style="margin-top:12px"><button class="btn btn--xs" data-open="directory">Open Directory</button></div>`,
    sharing: `<h2>Sharing</h2><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Share</th><th>Who</th><th class="num">Used</th></tr></thead><tbody>${(sh.shares || []).filter(x => x.name !== 'sysvol').map(x => `<tr><td><b>${esc(x.name)}</b><br><small class="muted">${esc(x.comment || '')}</small></td><td class="dim">${esc((x.valid_users || []).join(', ') || 'everyone')}</td><td class="num">${fmtB(x.used)}</td></tr>`).join('')}</tbody></table></div>
      <p class="note" style="margin-top:12px">Macs reach every share at <code>smb://${esc(s.system?.hostname || 'arise-server')}</code> with the same password. Share links for anyone else come from Finder.</p><div class="row" style="margin-top:12px"><button class="btn btn--xs" data-open="files">Open Finder</button><button class="btn btn--ghost btn--xs" data-shares>Manage shares</button></div>`,
    backups: `<h2>Backups</h2><div class="kv"><dt>When</dt><dd>${esc(s.backups?.schedule || '03:00')} nightly, restic to the Synology</dd><dt>Kept</dt><dd>${s.backups?.keep_daily ?? 30} daily · ${s.backups?.keep_weekly ?? 12} weekly · ${s.backups?.keep_monthly ?? 24} monthly</dd><dt>Repository</dt><dd class="mono" style="font-size:12px">${esc(s.backups?.restic_repo || '')}</dd><dt>Last</dt><dd>${o.backup?.last ? (o.backup.last.ok ? 'ok' : '<span style="color:var(--redL)">failed</span>') + ' · ' + ago(o.backup.last.started) : '—'}</dd><dt>Drill</dt><dd>monthly, one file back and compared (arise-drill.timer)</dd></div><div class="row" style="margin-top:12px"><button class="btn btn--xs" data-open="backups">Open Backups</button></div>`,
    updates: `<h2>Software Update</h2><div class="kv"><dt>Security</dt><dd>${(u.security || []).length} pending · installed by itself, never a reboot</dd><dt>Waiting for you</dt><dd>${(u.other || []).length} packages · ${(u.apps?.apps || []).filter(x => x.update).length} apps with a newer image</dd><dt>Reboot</dt><dd>${u.reboot_required ? '<span style="color:var(--warn)">needed</span>' : 'not needed'}</dd><dt>Window</dt><dd>${esc(u.window || 'Saturday 03:30')} · a system snapshot first · never during a service</dd><dt>Queued</dt><dd>${(u.queue?.packages || []).length} packages, ${(u.queue?.apps || []).length} apps${u.queue?.reboot ? ', reboot' : ''}</dd></div><div class="row" style="margin-top:12px"><button class="btn btn--xs" data-open="updates">Open Software Update</button></div>`,
    time: `<h2>Time</h2><div class="kv"><dt>Time zone</dt><dd>${esc(s.system?.timezone || 'America/Chicago')} · the domain's clock (chrony), checked by doctor</dd><dt>Services</dt><dd>${(c.services || []).map(x => `${esc(x.day)}s ${esc(fmtSvc(x.time))} · ${esc(x.name)} · ${esc(x.site)}`).join('<br>') || '—'}</dd></div>
      <h3 style="margin:16px 0 8px">The timers</h3><div class="tbl-wrap"><table class="tbl"><thead><tr><th>What</th><th>Next</th><th>Last</th></tr></thead><tbody>${(au.timers || []).map(t => `<tr><td><b>${esc(t.name)}</b><br><small class="muted mono">${esc(t.timer)}</small></td><td class="dim">${t.next ? fmtT(t.next) : '—'}</td><td class="dim">${t.last ? fmtT(t.last) + (t.last_ok === false ? ' · <span style="color:var(--redL)">failed</span>' : '') : '—'}</td></tr>`).join('')}</tbody></table></div><div class="row" style="margin-top:12px"><button class="btn btn--xs" data-open="automations">Open Automations</button></div>`,
    notifications: `<h2>Notifications</h2><div class="kv"><dt>Push</dt><dd>${pk.available ? 'on this server · to ' + esc((pk.users || [S.user]).join(', ') || 'the administrator') : 'not set up (' + esc(pk.note || 'keys missing') + ')'}${pk.enabled_for_me ? ' · <button class="btn btn--ghost btn--xs" data-pref="push">' + (PREF.get('push', '') === '1' ? 'on for this device' : 'turn on here') + '</button>' : ''}</dd>
      <dt>Discord</dt><dd>${n.configured ? 'webhook set (the address stays in arise.toml)' : 'no webhook yet: failures and the Sunday all-green will post once one is set'}</dd><dt>Daily note</dt><dd>${n.configured ? String(n.hour).padStart(2, '0') + ':00' : 'off (Bradly: no daily note)'}</dd><dt>Needs you</dt><dd>${(o.attention || []).length} items now · the menu-bar pill and the first widget</dd></div>
      <div class="row" style="margin-top:12px"><button class="btn btn--ghost btn--xs" id="stNtTest">Send a test note</button></div>`,
    power: `<h2>Power</h2><p class="note" style="margin-bottom:12px">The box lives where nobody can press its button. Both ask you to type the word; both are refused while a service is on. The UPS shuts the box down on its own when the battery is nearly flat.</p>
      <div class="row"><button class="btn btn--ghost btn--xs" id="stReboot">Restart…</button><button class="btn btn--danger btn--xs" id="stOff">Shut Down…</button><button class="btn btn--ghost btn--xs" data-svc="arise-web.service">Restart the dashboard</button><button class="btn btn--ghost btn--xs" data-svc="samba-ad-dc.service">Restart the domain</button></div>
      <h3 style="margin:16px 0 8px">The closet monitor</h3><p class="note">Off 23:00, on 06:00. Screen Sharing through Guacamole, Bradly only.</p><div class="row" style="margin-top:10px"><button class="btn btn--xs" data-open="monitor">Open Monitor</button></div>`,
    config: `<h2>Config file</h2><p class="note" style="margin-bottom:14px">Read from <code>${esc(s._meta?.path)}</code>${s._meta?.found ? '' : ' <b>(not found: these are the defaults)</b>'}. The dashboard never writes this file; change it with <code>sudo nano ${esc(s._meta?.path)}</code> and <code>sudo systemctl restart arise-web</code>, or with <code>arisectl</code>. Secrets are never shown here.</p>
      <div class="grid">${['system', 'web', 'directory', 'automator', 'backups', 'nas', 'apps', 'github', 'paths'].filter(k => s[k]).map(k => `<div class="c6 panel panel--flat"><div class="panel__hd"><h3>${esc(k)}</h3></div><div class="kv">${Object.entries(s[k]).map(([kk, v]) => `<dt>${esc(kk)}</dt><dd class="mono" style="font-size:12.5px">${esc(Array.isArray(v) ? v.join(', ') : typeof v === 'boolean' ? (v ? 'yes' : 'no') : (v === '' ? '—' : v))}</dd>`).join('')}</div></div>`).join('')}</div>`,
    about: `<h2>About</h2><div class="kv"><dt>ariseOS</dt><dd>v${esc(o.version || '')} “${esc(o.codename || '')}”</dd><dt>Host</dt><dd>${esc(o.hostname || '')}</dd><dt>System</dt><dd>${esc(o.machine?.os || '')}</dd></div><div class="row" style="margin-top:12px"><button class="btn btn--xs" data-open="about">About This Server</button></div>`,
  };
  return `<div class="settings"><nav class="settings__nav">${SETTINGS_SECTIONS.map(([id, name]) => `<button class="${S.settingsSec === id ? 'active' : ''}" data-sec="${id}">${esc(name)}</button>`).join('')}</nav><div class="settings__body fade">${sec[S.settingsSec] || ''}</div></div>`;
};
V.settings.after = root => {
  $$('[data-sec]', root).forEach(b => b.onclick = () => { S.settingsSec = b.dataset.sec; rerender('settings'); });
  $$('[data-open]', root).forEach(b => b.onclick = () => openApp(b.dataset.open));
  $$('[data-pref]', root).forEach(b => b.onclick = () => { const k = b.dataset.pref; if (k in CC_FEEL) CC_FEEL[k](); setTimeout(() => rerender('settings'), 150); });
  const t = $('#stNtTest', root); if (t) t.onclick = e => act(e.target, () => api('/notify/test', { method: 'POST' }), 'Test note sent');
  const r = $('#stReboot', root); if (r) r.onclick = () => powerAsk('reboot');
  const o = $('#stOff', root); if (o) o.onclick = () => powerAsk('poweroff');
  $$('[data-svc]', root).forEach(b => b.onclick = () => b.dataset.svc === 'arise-web.service' ? restartUnit('arise-web.service', 'the dashboard', 'dashboard') : restartUnit('samba-ad-dc.service', 'the domain', 'domain'));
  const shb = $('[data-shares]', root); if (shb) shb.onclick = () => { (S.tabs = S.tabs || {}).directory = 'shares'; openApp('directory'); };
};

/* Software Update (round 3, 4 and 25) */
V.updates = async () => {
  const u = await api('/updates'); S.updatesCache = u;
  const q = u.queue || { packages: [], apps: [] }; const apps_ = (u.apps?.apps || []);
  const pkgRow = p => `<label class="up__row"><input type="checkbox" data-pkg="${esc(p.name)}" ${q.packages.includes(p.name) ? 'checked' : ''}><b>${esc(p.name)}</b><span class="mono dim">${esc(p.from || '?')} → ${esc(p.version)}</span><small>${esc(p.suite)}</small></label>`;
  return `<div class="fade">
    ${u.in_service ? `<p class="note" style="margin-bottom:14px;border-left-color:var(--warn)"><b>${esc(u.in_service.name)}</b> is on now (${esc(u.in_service.day)} ${esc(u.in_service.time)}): nothing installs and nothing reboots until it is over.</p>` : ''}
    <div class="grid" style="margin-bottom:14px">
      <div class="c4 panel panel--ok"><div class="stat"><span class="stat__l">Security</span><span class="stat__v">${(u.security || []).length}</span><span class="stat__n">installs itself, never a reboot</span></div></div>
      <div class="c4 panel ${(u.other || []).length || apps_.some(a => a.update) ? 'panel--warn' : 'panel--flat'}"><div class="stat"><span class="stat__l">Waiting for you</span><span class="stat__v">${(u.other || []).length + apps_.filter(a => a.update).length}</span><span class="stat__n">${(u.other || []).length} packages · ${apps_.filter(a => a.update).length} apps</span></div></div>
      <div class="c4 panel ${u.reboot_required ? 'panel--warn' : 'panel--flat'}"><div class="stat"><span class="stat__l">Reboot</span><span class="stat__v" style="font-size:22px">${u.reboot_required ? 'needed' : 'not needed'}</span><span class="stat__n">${(u.reboot_pkgs || []).slice(0, 3).map(esc).join(', ') || 'the kernel has not asked'}</span></div></div>
    </div>
    <div class="toolbar"><button class="btn btn--ghost btn--sm" id="upRefresh">Refresh the lists</button><button class="btn btn--ghost btn--sm" id="upCheckApps">Check apps</button><span class="spacer"></span><span class="sub" style="font-size:12px;color:var(--muted)">window: <b>${esc(u.window)}</b> · snapshot first · ${u.last_check ? 'checked ' + ago(u.last_check) : ''}</span></div>
    <div class="grid">
      <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Packages waiting for you</h3><span class="sub">${(u.other || []).length}</span></div>${(u.other || []).length ? `<div class="up__list">${u.other.map(pkgRow).join('')}</div>` : '<div class="empty">Nothing waiting. Security patches arrive on their own.</div>'}
        ${(u.security || []).length ? `<details style="margin-top:12px"><summary class="muted" style="cursor:pointer;font-size:12.5px">${u.security.length} security patches (automatic)</summary><div class="up__list" style="margin-top:8px">${u.security.map(p => `<div class="up__row"><span></span><b>${esc(p.name)}</b><span class="mono dim">${esc(p.from || '?')} → ${esc(p.version)}</span><small>${esc(p.suite)}</small></div>`).join('')}</div></details>` : ''}</div>
      <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Apps</h3><span class="sub">${u.apps?.checked_at ? 'checked ' + ago(u.apps.checked_at) : 'not checked yet'}</span></div>
        ${apps_.length ? `<div class="up__list">${apps_.map(a => `<label class="up__row"><input type="checkbox" data-appq="${esc(a.name)}" ${q.apps.includes(a.name) ? 'checked' : ''} ${a.update ? '' : 'disabled'}><b>${esc(a.name)}</b><span class="dim">${a.update ? 'newer image pulled, waiting to switch' : 'up to date'}</span>${a.error ? `<small style="color:var(--redL)">${esc(a.error)}</small>` : ''}</label>`).join('')}</div>` : '<div class="empty">Press <b>Check apps</b>: every app\'s image is pulled and compared; nothing is switched until you queue it.</div>'}
        <label class="up__row" style="margin-top:14px;border-top:1px solid var(--line2);padding-top:12px"><input type="checkbox" id="upReboot" ${q.reboot ? 'checked' : ''} ${u.reboot_required ? '' : 'disabled'}><b>Reboot afterwards</b><span class="dim">${u.reboot_required ? 'only if no service is on' : 'nothing asks for one'}</span></label></div>
    </div>
    <div class="panel panel--flat" style="margin-top:14px"><div class="panel__hd"><h3>What is queued</h3><span class="sub">${q.queued_at ? 'by ' + esc(q.by || '') + ' · ' + ago(q.queued_at) : 'nothing yet'}</span></div>
      <p style="font-size:13.5px;color:var(--text2)">${q.packages.length} packages, ${q.apps.length} apps${q.reboot ? ', then a reboot' : ''}. Queued items install <b>${esc(u.window)}</b> after a system snapshot (<code>arisectl snapshot create</code>), and the kernel reboot happens only if no service is on.</p>
      <div class="row" style="margin-top:12px"><button class="btn btn--xs" id="upQueue">Queue the ticked items for ${esc(u.window)}</button><button class="btn btn--ghost btn--xs" id="upNow">Install now…</button><button class="btn btn--ghost btn--xs" id="upClear">Clear the queue</button></div>
      ${u.last_apply ? `<p class="note" style="margin-top:12px">Last apply ${fmtT(u.last_apply.when)}: ${u.last_apply.ok ? 'ok' : '<span style="color:var(--redL)">failed</span>'} · ${esc(u.last_apply.summary || '')}</p>` : ''}
      ${u.arise?.behind ? `<p class="note" style="margin-top:12px">ariseOS itself is ${u.arise.behind} commits behind GitHub. <button class="btn btn--ghost btn--xs" id="upSelf">Update ariseOS</button></p>` : ''}</div>
  </div>`;
};
V.updates.after = root => {
  const sel = () => ({ packages: $$('[data-pkg]:checked', root).map(x => x.dataset.pkg), apps: $$('[data-appq]:checked', root).map(x => x.dataset.appq), reboot: $('#upReboot', root)?.checked || false });
  $('#upRefresh', root).onclick = e => act(e.target, () => api('/updates/refresh', { method: 'POST' }), 'Lists refreshed').then(() => rerender('updates'));
  $('#upCheckApps', root).onclick = e => act(e.target, () => api('/updates/check-apps', { method: 'POST' }), 'Images pulled and compared').then(() => rerender('updates'));
  $('#upQueue', root).onclick = e => act(e.target, () => api('/updates/queue', { method: 'POST', body: sel() }), 'Queued').then(() => rerender('updates'));
  $('#upClear', root).onclick = e => act(e.target, () => api('/updates/queue', { method: 'POST', body: { packages: [], apps: [], reboot: false } }), 'Queue cleared').then(() => rerender('updates'));
  $('#upNow', root).onclick = () => { const s = sel(); confirmType('Install now', 'install', `Queues the ticked items (${s.packages.length} packages, ${s.apps.length} apps${s.reboot ? ', reboot' : ''}) and runs the Saturday apply right now: a system snapshot first, then the installs. Refused while a service is on. Minutes, not seconds.`, async () => { await api('/updates/queue', { method: 'POST', body: s }); const r = await api('/updates/apply', { method: 'POST', body: { confirm: 'install' } }); if (r.ok === false) throw new Error(r.summary || r.err); toast(r.summary || 'Done'); rerender('updates'); }); };
  const self = $('#upSelf', root); if (self) self.onclick = e => act(e.target, () => api('/system/update', { method: 'POST' }), 'ariseOS updating; this page reloads when it is back').then(() => setTimeout(() => location.reload(), 6000));
};

/* The Store (round 3, 5 and 40) */
const CAT_NAMES = { desktop: 'Desktop programs', experiment: 'Experiments', office: 'Office', media: 'Media', monitoring: 'Monitoring', admin: 'Admin', code: 'Code', automation: 'Automation', network: 'Network', knowledge: 'Knowledge', files: 'Files', security: 'Security', remote: 'Remote', streaming: 'Streaming', communication: 'Communication', church: 'Church', learning: 'Learning', ai: 'AI', cameras: 'Cameras', collaboration: 'Collaboration' };
V.apps = async () => {
  S.storeTab = S.storeTab || 'installed'; S.storeQ = S.storeQ || ''; S.storeCat = S.storeCat || '';
  const [a, t, c] = await Promise.all([api('/apps'), api('/apps/templates'), api('/apps/catalog').catch(() => ({ apps: [] }))]);
  const installed = new Map((a.apps || []).map(x => [x.name, x]));
  const all = [...(t.templates || []).map(x => ({ ...x, source: 'template' })), ...(c.apps || []).map(x => ({ ...x, source: 'catalog' }))];
  const running = (a.apps || []).filter(x => x.status === 'running');
  const capSum = running.reduce((s, x) => s + (x.limit_mb || 0), 0), estSum = running.reduce((s, x) => s + (x.ram_mb || 0), 0);
  const total = a.ram_total_mb || 0, budget = Math.max(0, total - (a.reserve_mb || 2048)), p = total ? Math.min(100, Math.round(capSum / total * 100)) : 0;
  const gauge = `<div class="panel panel--flat" style="margin-bottom:14px"><div class="row row--between"><span class="kicker">Memory promised to running apps</span><span class="mono" style="font-size:12px">${mb(capSum)} of ${mb(total)} RAM · about ${mb(estSum)} in use · ${mb(a.reserve_mb || 2048)} kept for the domain and the dashboard</span></div><div class="meter ${capSum > budget ? '' : capSum > budget * 0.8 ? 'meter--warn' : 'meter--ok'}"><i style="width:${p}%"></i></div>${capSum > budget ? '<p class="note" style="margin-top:10px;border-left-color:var(--warn)">Over the budget: if everything running hit its cap at once the domain would feel it. Stop one, or turn autostart off on the heaviest.</p>' : ''}</div>`;
  const badge = (txt, cls = '') => `<span class="pill ${cls}">${esc(txt)}</span>`;
  const card = x => {
    const inst = installed.get(x.id); const th = x.theme || { via: 'none' };
    return `<div class="card store__card ${x.experimental ? 'store__card--exp' : ''}"><div class="row row--between"><span class="cat">${esc(CAT_NAMES[x.category] || x.category)}${x.source === 'catalog' ? ' · catalogue' : ''}</span>${inst ? badge(inst.status === 'running' ? 'running' : 'stopped', inst.status === 'running' ? 'ok' : 'warn') : ''}</div><h3>${esc(x.name)}</h3><p>${esc(x.description)}</p>
      <div class="store__meta"><span title="an honest estimate at rest">~${mb(x.ram_mb)} · cap ${mb(x.limits?.mem_mb)} · ${x.limits?.cpus} CPU</span>${x.idle_stop_minutes ? `<span>stops itself after ${x.idle_stop_minutes} min idle</span>` : ''}<span>${th.via === 'none' ? 'keeps its own look' : 'house look via ' + esc(th.via)}</span>${x.experimental ? '<span style="color:var(--warn)">experiment: expect it not to work</span>' : ''}</div>
      ${x.notes ? `<p style="color:var(--warn);font-size:12px">${esc(x.notes.slice(0, 220))}${x.notes.length > 220 ? '…' : ''}</p>` : ''}${x.source === 'catalog' ? '<p style="color:var(--muted);font-size:11.5px">image tag not pulled from this build: verify before first deploy</p>' : ''}
      <div class="row row--between"><span class="mono dim" style="font-size:11.5px">${(x.ports || []).map(esc).join(' · ')}</span><span class="row">${th.via !== 'none' ? `<button class="btn btn--ghost btn--xs" data-theme="${esc(x.id)}">House look</button>` : ''}${inst ? `<button class="btn btn--ghost btn--xs" data-deploy="${esc(x.id)}">Redeploy</button>` : `<button class="btn btn--xs" data-deploy="${esc(x.id)}">Install</button>`}</span></div></div>`;
  };
  const cats = [...new Set(all.map(x => x.category))].sort();
  const ql = S.storeQ.toLowerCase();
  const shown = all.filter(x => (!S.storeCat || x.category === S.storeCat) && (!ql || x.name.toLowerCase().includes(ql) || x.description.toLowerCase().includes(ql) || x.id.includes(ql)));
  const instRows = (a.apps || []).map(x => `<tr><td><b>${esc(x.name)}</b><br><small class="muted">${esc(x.source === 'catalog' ? 'catalogue' : 'template')} · ~${mb(x.ram_mb)} · cap ${mb(x.limit_mb)}</small></td><td><span class="pill ${x.status === 'running' ? 'ok' : 'warn'}">${esc(x.status)}</span></td><td>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener" style="color:var(--redL)">${esc(x.url)}</a>` : '—'}</td><td class="num">${x.cpu != null ? x.cpu.toFixed(1) + '%' : '—'}</td><td class="num">${fmtB(x.mem)}</td><td><label class="store__auto" title="start with the box"><input type="checkbox" data-auto="${esc(x.name)}" ${x.autostart !== false ? 'checked' : ''}> auto</label></td>
    <td class="acts">${x.status === 'running' ? `<button class="btn btn--ghost btn--xs" data-app="${esc(x.name)}" data-do="restart">Restart</button><button class="btn btn--ghost btn--xs" data-app="${esc(x.name)}" data-do="stop">Stop</button>` : `<button class="btn btn--xs" data-app="${esc(x.name)}" data-do="start">Start</button>`}<button class="btn btn--ghost btn--xs" data-logs="${esc(x.name)}">Logs</button><button class="btn btn--ghost btn--xs" data-rmapp="${esc(x.name)}">Remove</button></td></tr>`).join('');
  return `<div class="fade">
    ${a.docker === false && !a.demo ? '<p class="note" style="margin-bottom:14px">Docker is not running on this server, so apps cannot be deployed. <code>sudo systemctl start docker</code> or run the installer again without --skip-docker.</p>' : ''}
    <div class="tabs" id="storeTabs"><button class="${S.storeTab === 'installed' ? 'active' : ''}" data-t="installed">Installed · ${(a.apps || []).length}</button><button class="${S.storeTab === 'catalog' ? 'active' : ''}" data-t="catalog">Catalogue · ${all.length}</button></div>
    <div data-tab="installed" ${S.storeTab === 'installed' ? '' : 'hidden'}>${gauge}
      ${(a.apps || []).length ? `<div class="panel panel--flat tbl-wrap"><table class="tbl"><thead><tr><th>App</th><th>State</th><th>Address</th><th class="num">CPU</th><th class="num">Memory</th><th></th><th></th></tr></thead><tbody>${instRows}</tbody></table></div>` : '<div class="empty">Nothing installed yet. The Catalogue has everything.</div>'}
      <p class="note" style="margin-top:12px">The core five were installed with the server (Nextcloud, Vaultwarden, Uptime Kuma, Netdata, File Browser); every other template is one Install click away, if the box has room. <b>Remove</b> takes the containers down and keeps the data folder under /srv/arise/apps. Deleting a data folder is your click, by hand.</p>
      <pre class="log" id="appLog" hidden style="margin-top:14px"></pre></div>
    <div data-tab="catalog" ${S.storeTab === 'catalog' ? '' : 'hidden'}>
      <div class="toolbar"><input class="search" id="storeQ" placeholder="Search the catalogue" value="${esc(S.storeQ)}"><select class="search" id="storeCat"><option value="">Every category</option>${cats.map(k => `<option value="${esc(k)}" ${S.storeCat === k ? 'selected' : ''}>${esc(CAT_NAMES[k] || k)}</option>`).join('')}</select><span class="spacer"></span><span class="sub" style="font-size:12px;color:var(--muted)">${shown.length} apps · free, self-hosted, capped</span></div>
      <div class="cards">${shown.map(card).join('') || '<div class="empty">Nothing matches.</div>'}</div></div>
  </div>`;
};
V.apps.after = root => {
  $$('#storeTabs button', root).forEach(b => b.onclick = () => { S.storeTab = b.dataset.t; rerender('apps'); });
  const q = $('#storeQ', root); if (q) { q.oninput = () => { S.storeQ = q.value; clearTimeout(S.storeT); S.storeT = setTimeout(() => rerender('apps'), 350); }; }
  const sc = $('#storeCat', root); if (sc) sc.onchange = () => { S.storeCat = sc.value; rerender('apps'); };
  $$('[data-deploy]', root).forEach(b => b.onclick = async () => { const r = await act(b, () => api('/apps/deploy', { method: 'POST', body: { template: b.dataset.deploy } }), `Installing ${b.dataset.deploy}; the first start pulls the image`); if (r) setTimeout(() => rerender('apps'), 2000); });
  $$('[data-app]', root).forEach(b => b.onclick = async () => { const r = await act(b, () => api(`/apps/${encodeURIComponent(b.dataset.app)}/${b.dataset.do}`, { method: 'POST', body: {} }), `${b.dataset.do} sent`); if (r) setTimeout(() => rerender('apps'), 1500); });
  $$('[data-auto]', root).forEach(cb => cb.onchange = async () => { const r = await api(`/apps/${encodeURIComponent(cb.dataset.auto)}/autostart`, { method: 'POST', body: { on: cb.checked } }); if (r.ok === false) { toast(r.err, 'bad'); cb.checked = !cb.checked; } else toast(`${cb.dataset.auto}: autostart ${cb.checked ? 'on' : 'off'}${r.demo ? ' (sample)' : ''}`); });
  $$('[data-logs]', root).forEach(b => b.onclick = async () => { const r = await api(`/apps/${encodeURIComponent(b.dataset.logs)}/logs`); const p = $('#appLog', root); p.hidden = false; p.textContent = `docker compose logs ${b.dataset.logs}\n\n` + (r.text || '(empty)'); p.scrollIntoView({ behavior: 'smooth' }); });
  $$('[data-rmapp]', root).forEach(b => b.onclick = () => confirmType('Remove app', b.dataset.rmapp, 'Stops and removes the containers. <b>Its data folder is kept</b> under /srv/arise/apps; deleting that is a separate, by-hand decision.', async () => { const r = await api(`/apps/${encodeURIComponent(b.dataset.rmapp)}/remove`, { method: 'POST', body: { confirm: b.dataset.rmapp } }); if (r.ok === false) throw new Error(r.err); toast('Removed; data kept'); rerender('apps'); }));
  $$('[data-theme]', root).forEach(b => b.onclick = async () => {
    const t = await api(`/apps/theme/${encodeURIComponent(b.dataset.theme)}`).catch(e => ({ ok: false, err: e.message })); if (t.ok === false) return toast(t.err, 'bad');
    modal(`<h2>${esc(b.dataset.theme)}: the house look</h2><p class="note" style="margin-bottom:12px">Via <b>${esc(t.via)}</b>${t.accepts?.length ? ' · takes ' + esc(t.accepts.join(', ')) : ''}. House values: red ${esc(t.house?.red)}, ink ${esc(t.house?.ink)}, ${esc(t.house?.fonts)}, the flame logo.</p>${t.note ? `<p style="font-size:13.5px;color:var(--text2)">${esc(t.note)}</p>` : ''}
      ${Object.keys(t.env || {}).length ? `<div class="kv" style="margin-top:10px">${Object.entries(t.env).map(([k, v]) => `<dt>${esc(k)}</dt><dd class="mono" style="font-size:12px">${esc(v)}</dd>`).join('')}</div>` : ''}${(t.files || []).length ? `<p class="muted" style="margin-top:10px;font-size:12.5px">Files written once at deploy: ${t.files.map(esc).join(', ')}</p>` : ''}${(t.commands || []).length ? `<p class="muted" style="margin-top:10px;font-size:12.5px">Run after the first start: ${t.commands.map(esc).join(' · ')}</p>` : ''}
      ${t.css ? `<pre class="log" style="margin-top:12px;max-height:220px">${esc(t.css)}</pre>` : ''}<div class="acts">${t.css ? '<button class="btn btn--ghost" id="thCopy">Copy the CSS</button>' : ''}<button class="btn" data-close>Close</button></div>`, m => { const c2 = $('#thCopy', m); if (c2) c2.onclick = () => copyText(t.css, c2); });
  });
};

/* Activity Monitor (round 3, 6) */
V.activity = async () => {
  const a = await api('/activity'); S.actSort = S.actSort || 'cpu';
  const procs = [...(a.processes || [])].sort((x, y) => S.actSort === 'name' ? x.name.localeCompare(y.name) : S.actSort === 'user' ? x.user.localeCompare(y.user) : (y[S.actSort] || 0) - (x[S.actSort] || 0));
  const th = (k, l, num) => `<th class="${num ? 'num' : ''} ${S.actSort === k ? 'on' : ''}" data-sort="${k}" style="cursor:pointer">${l}${S.actSort === k ? ' ▾' : ''}</th>`;
  const t = a.totals || {};
  return `<div class="fade"><div class="grid" style="margin-bottom:14px">
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">CPU</span><span class="stat__v">${(t.cpu ?? 0).toFixed(0)}%</span><span class="stat__n">${t.cores} cores · load ${(t.load || []).map(x => x.toFixed(2)).join(' · ')}</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Memory</span><span class="stat__v">${(t.mem_pct ?? 0).toFixed(0)}%</span><span class="stat__n">${fmtB(t.mem_used)} of ${fmtB(t.mem_total)}</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Processes</span><span class="stat__v">${fmtN(t.procs)}</span><span class="stat__n">top ${procs.length} shown</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Containers</span><span class="stat__v">${(a.containers || []).length}</span><span class="stat__n">docker stats</span></div></div></div>
    <div class="tabs" id="actTabs"><button class="${S.actTab !== 'containers' ? 'active' : ''}" data-t="procs">Processes</button><button class="${S.actTab === 'containers' ? 'active' : ''}" data-t="containers">Containers</button></div>
    <div data-tab="procs" ${S.actTab === 'containers' ? 'hidden' : ''}><div class="panel panel--flat tbl-wrap"><table class="tbl tbl--tight"><thead><tr>${th('name', 'Process')}${th('pid', 'PID', 1)}${th('user', 'User')}${th('cpu', 'CPU', 1)}${th('mem', 'Memory', 1)}<th class="num">Read / Write</th><th>Container</th><th></th></tr></thead><tbody>
      ${procs.map(p => `<tr><td><b>${esc(p.name)}</b><br><small class="muted mono" title="${esc(p.cmd)}">${esc(p.cmd.slice(0, 70))}</small></td><td class="num mono">${p.pid}</td><td class="dim">${esc(p.user)}</td><td class="num">${p.cpu.toFixed(1)}%</td><td class="num">${fmtB(p.mem)}</td><td class="num dim" style="font-size:12px">${p.io ? fmtB(p.io.read) + ' / ' + fmtB(p.io.write) : '—'}</td><td class="mono dim" style="font-size:11.5px">${esc(p.container || '')}</td><td class="acts">${p.protected ? '<span class="muted" style="font-size:11px" title="the domain, Docker, SSH, the dashboard or systemd">kept</span>' : `<button class="btn btn--ghost btn--xs" data-kill="${p.pid}" data-name="${esc(p.name)}">End</button>`}</td></tr>`).join('')}</tbody></table></div></div>
    <div data-tab="containers" ${S.actTab === 'containers' ? '' : 'hidden'}><div class="panel panel--flat tbl-wrap"><table class="tbl"><thead><tr><th>Container</th><th class="num">CPU</th><th class="num">Memory</th><th class="num">Cap</th><th>Net in / out</th><th>Disk</th><th class="num">PIDs</th></tr></thead><tbody>
      ${(a.containers || []).map(c => `<tr><td><b>${esc(c.name)}</b><br><small class="muted mono">${esc(c.id)}</small></td><td class="num">${c.cpu.toFixed(1)}%</td><td class="num">${fmtB(c.mem)}</td><td class="num dim">${c.mem_limit ? fmtB(c.mem_limit) : '—'}</td><td class="dim">${esc(c.net)}</td><td class="dim">${esc(c.block)}</td><td class="num">${esc(c.pids)}</td></tr>`).join('') || '<tr><td colspan="7" class="empty">No containers running.</td></tr>'}</tbody></table></div></div>
    <p class="note" style="margin-top:12px">Refreshes every 3 seconds while open. <b>End</b> asks for the PID; the domain, Docker, SSH, the dashboard and systemd cannot be ended from here. ${a.demo ? 'Sample data.' : ''}</p></div>`;
};
V.activity.after = root => {
  $$('#actTabs button', root).forEach(b => b.onclick = () => { S.actTab = b.dataset.t; rerender('activity'); });
  $$('[data-sort]', root).forEach(h => h.onclick = () => { S.actSort = h.dataset.sort; rerender('activity'); });
  $$('[data-kill]', root).forEach(b => b.onclick = () => confirmType(`End ${b.dataset.name}`, b.dataset.kill, `Sends TERM to PID ${b.dataset.kill}, then KILL if it does not stop in a second. Unsaved work in it is lost.`, async () => { const r = await api('/activity/kill', { method: 'POST', body: { pid: +b.dataset.kill, confirm: b.dataset.kill } }); if (r.ok === false) throw new Error(r.err); toast(r.out || 'Ended'); rerender('activity'); }));
  clearInterval(S.actT); S.actT = setInterval(() => { if (S.wins.activity && !S.wins.activity.min && $('#modal').open === false && !$('#wb-activity .busy')) rerender('activity'); else if (!S.wins.activity) clearInterval(S.actT); }, 3000);
};

/* Logs (round 3, 7) */
V.logs = async () => {
  const src = await api('/logs/sources').catch(() => ({ groups: [], files: [], apps: [] }));
  S.logUnit = S.logUnit || 'arise-web.service'; S.logLines = S.logLines || 300; S.logQ = S.logQ || '';
  const sel = S.logUnit; const isFile = sel.startsWith('file:'), isApp = sel.startsWith('app:');
  const r = isFile ? await api(`/logs/file/${encodeURIComponent(sel.slice(5))}?lines=${S.logLines}`) : isApp ? await api(`/apps/${encodeURIComponent(sel.slice(4))}/logs?lines=${S.logLines}`) : await api(`/logs/${encodeURIComponent(sel)}?lines=${S.logLines}`);
  const lines = (r.text || '').split('\n'); const errIdx = r.last_error_line ?? (() => { for (let i = lines.length - 1; i >= 0; i--) if (/\b(error|failed|fatal|traceback|exception|denied|refused|timed? ?out)\b/i.test(lines[i])) return i; return null; })();
  const q = S.logQ.trim(); const shown = q ? lines.map((l, i) => [l, i]).filter(([l]) => l.toLowerCase().includes(q.toLowerCase())) : lines.map((l, i) => [l, i]);
  const opt = (v, l) => `<option value="${esc(v)}" ${sel === v ? 'selected' : ''}>${esc(l)}</option>`;
  return `<div class="fade"><div class="toolbar"><select class="search" id="logUnit">${(src.groups || []).map(g => `<optgroup label="${esc(g.name)}">${g.units.map(u => opt(u.unit, `${u.what} · ${u.unit}`)).join('')}</optgroup>`).join('')}${(src.apps || []).length ? `<optgroup label="Apps">${src.apps.map(a => opt('app:' + a.name, a.name + (a.status === 'running' ? '' : ' (stopped)'))).join('')}</optgroup>` : ''}${(src.files || []).length ? `<optgroup label="${esc(src.log_dir || '/var/log/arise')}">${src.files.map(f => opt('file:' + f.name, `${f.name} · ${fmtB(f.size)}`)).join('')}</optgroup>` : ''}</select>
      <select class="search" id="logLines" style="min-width:90px">${[100, 300, 1000].map(n => `<option ${S.logLines === n ? 'selected' : ''}>${n}</option>`).join('')}</select><input class="search" id="logQ" placeholder="Search these lines" value="${esc(S.logQ)}"><button class="btn btn--ghost btn--sm" id="logRefresh">Refresh</button><span class="spacer"></span>
      ${errIdx != null ? `<button class="btn btn--ghost btn--sm" id="logErr">Last error ↓</button>` : '<span class="sub" style="font-size:12px;color:var(--ok)">no error lines</span>'}<button class="btn btn--ghost btn--sm" id="logCopy">Copy</button><button class="btn btn--sm" id="logClaude">Copy for Claude</button></div>
    <p class="sub" style="font-size:12px;color:var(--muted);margin-bottom:8px">${esc(isFile ? sel.slice(5) : isApp ? 'docker compose logs ' + sel.slice(4) : 'journalctl -u ' + sel)} · ${lines.length} lines${q ? ` · ${shown.length} match “${esc(q)}”` : ''}${r.demo ? ' · sample' : ''}</p>
    <pre class="log log--lines" id="logBody">${shown.map(([l, i]) => `<span class="${i === errIdx ? 'err' : ''}" id="ll${i}">${hl(l, q)}</span>`).join('\n') || '(empty)'}</pre></div>`;
};
V.logs.after = root => {
  $('#logUnit', root).onchange = e => { S.logUnit = e.target.value; rerender('logs'); };
  $('#logLines', root).onchange = e => { S.logLines = +e.target.value; rerender('logs'); };
  $('#logQ', root).oninput = e => { S.logQ = e.target.value; clearTimeout(S.logT); S.logT = setTimeout(() => rerender('logs'), 350); };
  $('#logRefresh', root).onclick = () => rerender('logs');
  const er = $('#logErr', root); if (er) er.onclick = () => $('.log--lines .err', root)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  const text = () => $('#logBody', root).innerText;
  $('#logCopy', root).onclick = e => copyText(text(), e.target);
  $('#logClaude', root).onclick = e => { const errL = $('.log--lines .err', root)?.innerText || '(no error line)'; copyText(`On arise-server, ${esc(S.logUnit)} shows this. The last error line is:\n${errL}\n\nWhat went wrong and what should I run? Do not delete anything. The last ${S.logLines} lines:\n\n${text()}`, e.target); };
};

/* Automations (round 3, 8) */
const RUN_NOW = { 'arise-automator.timer': ['Preview (dry run)', () => api('/automator/preview', { method: 'POST' }).then(() => toast('Preview started: a dry run, nothing written'))], 'arise-backup.timer': ['Run every job now', () => runAllBackups()], 'arise-mirror.timer': ['Refresh the mirror', () => api('/backups/mirror', { method: 'POST' }).then(() => toast('Mirror refreshed'))], 'arise-devices.timer': ['Scan now', () => api('/devices/scan', { method: 'POST', body: {} }).then(() => toast('Scan started'))], 'arise-update.timer': ['Open Software Update', () => openApp('updates')], 'arise-monitor-off.timer': ['Open Monitor', () => openApp('monitor')], 'arise-monitor-on.timer': ['Open Monitor', () => openApp('monitor')] };
V.automations = async () => {
  const r = await api('/automations');
  return `<div class="fade"><p class="note" style="margin-bottom:14px"><b>${esc(r.never)}</b> Pausing a timer stops it firing until you resume it; the real automator run is only ever this timer's, never a button here.</p>
    <div class="panel panel--flat tbl-wrap"><table class="tbl"><thead><tr><th>What</th><th>Next</th><th>Last</th><th>State</th><th></th></tr></thead><tbody>
    ${(r.timers || []).map(t => `<tr class="${t.enabled ? '' : 'dim'}"><td><b>${esc(t.name)}</b><br><small class="muted">${esc(t.what)}</small><br><small class="muted mono">${esc(t.timer)}</small></td><td>${t.next ? `${fmtT(t.next)}<br><small class="muted">${ago(t.next).replace(' ago', '')}</small>` : '—'}</td><td>${t.last ? `${fmtT(t.last)}<br>${t.running ? '<span class="pill info">running</span>' : t.last_ok ? '<span class="pill ok">ok</span>' : t.last_ok === false ? `<span class="pill bad">failed${t.exit ? ' · exit ' + esc(t.exit) : ''}</span>` : ''}` : '<span class="muted">never</span>'}</td><td><span class="pill ${t.enabled ? 'ok' : 'warn'}">${t.enabled ? 'on' : 'paused'}</span></td>
      <td class="acts">${RUN_NOW[t.timer] ? `<button class="btn btn--ghost btn--xs" data-run="${esc(t.timer)}">${esc(RUN_NOW[t.timer][0])}</button>` : ''}${t.timer.startsWith('arise-') ? `<button class="btn btn--ghost btn--xs" data-pause="${esc(t.timer)}" data-on="${t.enabled ? 0 : 1}">${t.enabled ? 'Pause' : 'Resume'}</button>` : ''}<a class="btn btn--ghost btn--xs" data-log="${esc(t.service)}">Logs</a></td></tr>`).join('')}</tbody></table></div></div>`;
};
V.automations.after = root => {
  $$('[data-run]', root).forEach(b => b.onclick = e => { const f = RUN_NOW[b.dataset.run]; if (f) act(e.target, () => Promise.resolve(f[1]()), null); });
  $$('[data-pause]', root).forEach(b => b.onclick = () => { const on = b.dataset.on === '1'; confirmType(`${on ? 'Resume' : 'Pause'} ${b.dataset.pause}`, b.dataset.pause, on ? 'The timer fires again at its next time.' : 'The timer stops firing until you resume it. Nothing running now is interrupted.', async () => { const r = await api(`/automations/${encodeURIComponent(b.dataset.pause)}/${on ? 'resume' : 'pause'}`, { method: 'POST', body: { confirm: b.dataset.pause } }); if (r.ok === false) throw new Error(r.err); toast(on ? 'Resumed' : 'Paused'); rerender('automations'); }); });
  $$('[data-log]', root).forEach(a => a.onclick = e => { e.preventDefault(); S.logUnit = a.dataset.log; openApp('logs'); if (S.wins.logs) rerender('logs'); });
};

/* Storage (round 3, 9) */
V.storage = async () => {
  const s = await api('/storage'); const sc = s.scan;
  const bar = (used, total) => `<div class="meter ${pct(used, total) > 90 ? '' : pct(used, total) > 75 ? 'meter--warn' : 'meter--ok'}"><i style="width:${pct(used, total)}%"></i></div>`;
  const maxRoot = Math.max(1, ...(sc?.roots || []).map(r => r.bytes || 0));
  return `<div class="fade"><div class="grid" style="margin-bottom:14px">${(s.mounts || []).map(m => `<div class="c4 panel ${m.pct >= 90 ? 'panel--bad' : m.pct >= 75 ? 'panel--warn' : 'panel--flat'}"><div class="stat"><span class="stat__l">${esc(m.mount)} <span class="muted">${esc(m.fs)}</span></span><span class="stat__v" style="font-size:24px">${fmtB(m.free)}<small>free</small></span><span class="stat__n">${fmtB(m.used)} used of ${fmtB(m.total)} · ${m.pct}%${m.pct >= 75 ? ' · <span style="color:var(--warn)">says so at 75%</span>' : ''}</span></div>${bar(m.used, m.total)}</div>`).join('')}</div>
    <div class="toolbar"><span class="kicker">What is eating the disk</span><span class="spacer"></span><span class="sub" style="font-size:12px;color:var(--muted)">${sc ? 'as of ' + fmtT(sc.as_of) + (sc.truncated ? ' · partial (time cap)' : '') : 'no scan yet'}${s.scanning ? ' · scanning…' : ''}</span><button class="btn btn--ghost btn--sm" id="stScan" ${s.scanning ? 'disabled' : ''}>Rescan</button></div>
    ${sc ? `<div class="grid"><div class="c6 panel panel--flat"><div class="panel__hd"><h3>By share and app</h3></div>${[...sc.roots].sort((a, b) => (b.bytes || 0) - (a.bytes || 0)).map(r => `<div class="st__row"><div class="row row--between"><span><b>${esc(r.name)}</b> <span class="muted" style="font-size:11px">${esc(r.kind)}${r.missing ? ' · missing' : ''}</span></span><span class="mono" style="font-size:12px">${fmtB(r.bytes)} · ${fmtN(r.files)} files</span></div><div class="meter meter--ok"><i style="width:${Math.max(1, (r.bytes || 0) / maxRoot * 100)}%"></i></div></div>`).join('')}</div>
      <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Biggest files</h3><span class="sub">top ${sc.biggest.length}</span></div><div class="tbl-wrap"><table class="tbl tbl--tight"><tbody>${sc.biggest.slice(0, 25).map(f => `<tr><td class="mono" style="font-size:12px;word-break:break-all">${esc(f.path)}</td><td class="num" style="white-space:nowrap">${fmtB(f.bytes)}</td><td class="dim" style="white-space:nowrap">${esc((f.mtime || '').slice(0, 10))}</td></tr>`).join('')}</tbody></table></div></div>
      <div class="c12 panel panel--flat"><div class="panel__hd"><h3>Not changed in a year</h3><span class="sub">${sc.old.length} files over 1 MB</span></div><p class="note" style="margin-bottom:10px">${esc(s.note)} Nothing is deleted from here: open the folder in Finder and decide by hand.</p>${sc.old.length ? `<div class="tbl-wrap"><table class="tbl tbl--tight"><tbody>${sc.old.map(f => `<tr><td class="mono" style="font-size:12px;word-break:break-all">${esc(f.path)}</td><td class="num" style="white-space:nowrap">${fmtB(f.bytes)}</td><td class="dim" style="white-space:nowrap">${esc((f.mtime || '').slice(0, 10))}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Nothing old and large.</div>'}</div></div>` : '<div class="empty">Press Rescan: the shares and app folders are walked once (a minute or two) and the result is kept.</div>'}</div>`;
};
V.storage.after = root => { const b = $('#stScan', root); if (b) b.onclick = e => act(e.target, () => api('/storage/scan', { method: 'POST' }), 'Scan started; this page refreshes in a minute').then(() => setTimeout(() => rerender('storage'), 45000)); };

/* Notes (Trilium) and Photos (Immich): an app in a window (round 3, 11 and 12) */
async function appWindow(id, tmpl, what) {
  const r = await api(`/apps/open/${tmpl}`).catch(e => ({ ok: false, err: e.message }));
  if (!r.installed) return `<div class="fade"><div class="empty">${esc(what)} is not installed yet.${isMember() ? ' Ask the media team.' : ` <button class="btn btn--xs" data-open="apps">Open the Store</button>`}</div></div>`;
  if (!r.running) return `<div class="fade"><div class="empty">${esc(what)} is installed but stopped.${isMember() ? ' Ask the media team to start it.' : ` <button class="btn btn--xs" data-start="${esc(tmpl)}">Start it</button>`}</div></div>`;
  return `<div class="appframe"><div class="appframe__bar"><span class="muted" style="font-size:12px">${esc(what)} · <a href="${esc(r.url)}" target="_blank" rel="noopener" style="color:var(--redL)">${esc(r.url)}</a></span><span class="spacer"></span><a class="btn btn--ghost btn--xs" href="${esc(r.url)}" target="_blank" rel="noopener">Open in a tab</a></div><iframe src="${esc(r.url)}" title="${esc(what)}" referrerpolicy="no-referrer"></iframe><p class="appframe__note muted">If the window stays blank the app refuses to be framed: use <b>Open in a tab</b>.</p></div>`;
}
const appWindowAfter = (tmpl, id) => root => { $$('[data-open]', root).forEach(b => b.onclick = () => openApp(b.dataset.open)); $$('[data-start]', root).forEach(b => b.onclick = e => act(e.target, () => api(`/apps/${tmpl}/start`, { method: 'POST', body: {} }), 'Starting').then(() => setTimeout(() => rerender(id), 2500))); };
V.notes = () => appWindow('notes', 'trilium', 'Notes (Trilium)'); V.notes.after = appWindowAfter('trilium', 'notes');
V.photos = () => appWindow('photos', 'immich', 'Photos (Immich)'); V.photos.after = appWindowAfter('immich', 'photos');

/* The closet monitor: power and Screen Sharing (round 3, 17 and 30) */
V.monitor = async () => {
  const m = await api('/monitor'); const sh = m.share || {};
  return `<div class="fade"><div class="grid">
    <div class="c6 panel ${m.kiosk ? 'panel--ok' : 'panel--warn'}"><div class="panel__hd"><h3>The panel</h3><span class="sub">${m.kiosk ? 'kiosk running' : 'kiosk not running'}</span></div>
      ${(m.outputs || []).map(o => `<div class="widget__row"><span>${esc(o.name)} ${esc(o.description || '')}</span><b>${o.enabled === false ? '<span style="color:var(--warn)">off</span>' : 'on'}</b></div>`).join('') || `<p class="note">${esc(m.error || 'No output reported: is a monitor plugged in?')}</p>`}
      <div class="widget__row"><span>Schedule</span><b>off ${esc(m.schedule?.off)} · on ${esc(m.schedule?.on)}</b></div>${Object.entries(m.timers || {}).map(([t, s]) => `<div class="widget__row"><span class="mono" style="font-size:12px">${esc(t)}</span><b>${esc(s)}</b></div>`).join('')}
      <div class="row" style="margin-top:12px"><button class="btn btn--ghost btn--xs" data-pw="0">Off now</button><button class="btn btn--xs" data-pw="1">On now</button></div>
      <p class="note" style="margin-top:12px">After a scheduled off the panel does not wake on a key; the 06:00 timer or <b>On now</b> brings it back. The screensaver at five idle minutes and the lock at ten stay as they are.</p></div>
    <div class="c6 panel ${sh.on ? 'panel--ok' : 'panel--flat'}"><div class="panel__hd"><h3>Screen Sharing</h3><span class="sub">${sh.on ? 'on · ' + esc(sh.user || '') + ' only' : 'off'}</span></div>
      <p style="font-size:13.5px;color:var(--text2)">See the closet monitor from your phone or Mac, over Tailscale, without walking to the closet. wayvnc shares cage's display to Guacamole only (the Docker network, a password, TLS); Guacamole shows it in a tab as the connection <b>${esc(sh.connection || 'Closet monitor')}</b>, for <b>${esc(sh.user || 'bradly.dyer')}</b> alone.</p>
      ${sh.on ? `<div class="kv" style="margin-top:10px"><dt>wayvnc</dt><dd class="mono" style="font-size:12px">${esc(sh.address || '')}:${sh.port} · ${esc(sh.service || '')}</dd><dt>Guacamole</dt><dd>${sh.guacamole ? `<a href="${esc(sh.guacamole)}" target="_blank" rel="noopener" style="color:var(--redL)">${esc(sh.guacamole)}</a>` : 'not deployed'}</dd></div>` : '<p class="note" style="margin-top:10px">Turn it on from the box: <code>sudo arisectl monitor share on</code> (it makes the password, the certificate and the Guacamole user; the Guacamole password is shown once there, root only).</p>'}
      ${sh.guacamole ? `<div class="row" style="margin-top:12px"><a class="btn btn--xs" href="${esc(sh.guacamole)}" target="_blank" rel="noopener">Open Guacamole</a></div>` : ''}</div></div>${m.demo ? '<p class="muted" style="margin-top:12px;font-size:12px">Sample data.</p>' : ''}</div>`;
};
V.monitor.after = root => { $$('[data-pw]', root).forEach(b => b.onclick = e => act(e.target, () => api('/monitor/power', { method: 'POST', body: { on: b.dataset.pw === '1' } }), b.dataset.pw === '1' ? 'Panel on' : 'Panel off').then(() => setTimeout(() => rerender('monitor'), 800))); };

/* The menu-bar badge for Software Update (pending or a reboot) */
async function updatesBadge() {
  if (isMember()) return;
  let b = $('#barUp'); if (!b) { b = document.createElement('button'); b.id = 'barUp'; b.className = 'bar__pill bar__pill--up'; b.hidden = true; b.title = 'Software Update'; b.onclick = () => openApp('updates'); $('#barAtt').before(b); }
  try { const u = S.updatesCache && Date.now() - (S.updatesAt || 0) < 600000 ? S.updatesCache : await api('/updates'); S.updatesCache = u; S.updatesAt = Date.now();
    const n = (u.other || []).length + (u.apps?.apps || []).filter(x => x.update).length; const rb = u.reboot_required;
    b.hidden = !n && !rb; b.innerHTML = `<i></i><b>${n || ''}</b><span class="bar__pilltxt">${rb ? (n ? 'updates · reboot' : 'reboot needed') : 'updates'}</span>`; } catch { b.hidden = true; }
}

/* ---------------- window manager ---------------- */
// Tabs inside a window. With a key, the window opens again on the tab you left it on.
function tabs(sel, key) {
  const root = $(sel); if (!root) return; const panels = $$(':scope > [data-tab]', root.parentElement);
  const show = t => { $$('button', root).forEach(x => x.classList.toggle('active', x.dataset.t === t)); panels.forEach(p => p.hidden = p.dataset.tab !== t); if (key) (S.tabs = S.tabs || {})[key] = t; };
  $$('button', root).forEach(b => b.onclick = () => show(b.dataset.t));
  const want = key && S.tabs?.[key]; if (want && $$('button', root).some(b => b.dataset.t === want)) show(want);
}
let cascade = 0;
function openApp(id, focusOnly) {
  const a = appOf(id); if (!a) return;
  if (isMember() && (!MEMBER_APPS.includes(id) || !inGroups(a))) { toast(a.groups ? 'That app is for the ' + a.groups.join(' and ') + ' groups' : 'That app is for the administrator', 'warn'); return; }
  closeOverlays();
  let w = S.wins[id];
  if (w) { w.min = false; w.el.classList.remove('min'); focusWin(id); if (!focusOnly) rerender(id); return; }
  const el = document.createElement('section'); el.className = 'win' + (a.flush ? ' win--term' : ''); el.dataset.app = id;
  el.innerHTML = `<div class="win__bar"><div class="win__dots"><button class="x" title="Close ${kbd('⌘W')}" aria-label="Close"></button><button class="m" title="Minimise ${kbd('⌘M')}" aria-label="Minimise"></button><button class="z" title="Zoom" aria-label="Zoom"></button></div><span class="win__folio">${a.n}</span><span class="win__title">${esc(a.name)}</span><span class="win__sub" id="ws-${id}">${esc(isMember() && a.whatMember ? a.whatMember : a.what)}</span></div><div class="win__body${a.flush ? ' win__body--flush' : ''}" id="wb-${id}"></div>`;
  const stage = $('#stage');
  if (!isPhone()) { const n = cascade++ % 6; const W = Math.min(a.w || 980, stage.clientWidth - 36), H = Math.min(a.h || 680, stage.clientHeight - 110); el.style.width = W + 'px'; el.style.height = H + 'px'; el.style.left = Math.max(20, Math.min(stage.clientWidth - W - 20, 330 + n * 28)) + 'px'; el.style.top = (20 + n * 24) + 'px'; }
  stage.appendChild(el);
  w = S.wins[id] = { el, min: false, max: false };
  $('.x', el).onclick = () => closeApp(id); $('.m', el).onclick = () => minApp(id); $('.z', el).onclick = () => { w.max = !w.max; el.classList.toggle('max', w.max); };
  $('.win__bar', el).ondblclick = () => $('.z', el).click();
  el.addEventListener('pointerdown', () => { if (!$('#stage').classList.contains('mc')) focusWin(id); }, true);
  el.addEventListener('click', () => { if ($('#stage').classList.contains('mc')) { missionControl(false); focusWin(id); } }, true);
  drag(el, $('.win__bar', el));
  focusWin(id); rerender(id); if (!a.hidden) location.hash = '#' + id;
  const di = $(`#dock [data-app="${id}"]`); if (di) { di.classList.add('bounce'); setTimeout(() => di.classList.remove('bounce'), 1100); } dockShow(true); dockShow(false, 1400);
  updateDock(); $('#widgets').classList.toggle('dim', !isPhone() && Object.keys(S.wins).length > 0);
}
function closeApp(id) {
  const w = S.wins[id]; if (!w) return;
  if (id === 'terminal' && S.termDispose) { S.termDispose(); S.termDispose = null; }
  w.el.remove(); delete S.wins[id]; updateDock();
  const rest = Object.keys(S.wins).filter(k => !S.wins[k].min); if (rest.length) focusWin(rest[rest.length - 1]); else { setAppMenus(null); history.replaceState(null, '', location.pathname); }
  $('#widgets').classList.toggle('dim', Object.keys(S.wins).length > 0 && !isPhone());
}
function minApp(id) { const w = S.wins[id]; if (!w) return; w.min = true; w.el.classList.add('min'); updateDock(); const rest = Object.keys(S.wins).filter(k => !S.wins[k].min); if (rest.length) focusWin(rest[rest.length - 1]); else setAppMenus(null); }
function focusWin(id) { const w = S.wins[id]; if (!w) return; $$('.win').forEach(e => e.classList.remove('focus')); w.el.classList.add('focus'); w.el.style.zIndex = ++S.z; S.focused = id; setAppMenus(id); updateDock(); }
function focusedApp() { return S.focused && S.wins[S.focused] && !S.wins[S.focused].min ? S.focused : null; }
function drag(el, handle) {
  let sx, sy, ox, oy, on = false;
  handle.addEventListener('pointerdown', e => { if (isPhone() || e.target.closest('button') || el.classList.contains('max') || $('#stage').classList.contains('mc')) return; const sw = S.wins[el.dataset.app]; if (sw && sw.pre && sw.snap) { el.style.width = sw.pre.width; el.style.height = sw.pre.height; sw.pre = null; sw.snap = null; } on = true; sx = e.clientX; sy = e.clientY; ox = el.offsetLeft; oy = el.offsetTop; handle.setPointerCapture(e.pointerId); });
  handle.addEventListener('pointermove', e => { if (!on) return; snapGhost(snapZone(e.clientX, e.clientY)); const st = $('#stage'); el.style.left = Math.max(-el.offsetWidth + 80, Math.min(st.clientWidth - 80, ox + e.clientX - sx)) + 'px'; el.style.top = Math.max(0, Math.min(st.clientHeight - 40, oy + e.clientY - sy)) + 'px'; });
  handle.addEventListener('pointerup', e => { if (!on) return; on = false; const z = snapZone(e.clientX, e.clientY); snapGhost(null); if (z) snapTo(el.dataset.app, z); }); handle.addEventListener('pointercancel', () => { on = false; snapGhost(null); });
}
const seqs = {};
// Every table in a window scrolls sideways inside its own box when it is wider than the window
// (a phone), instead of pushing the window wider or running off its edge. Tables drawn later by
// a tab or a search are caught too.
function wrapTables(root) {
  for (const t of root.querySelectorAll('.win__body table.tbl')) {
    if (t.parentElement.classList.contains('tbl-wrap')) continue;
    const w = document.createElement('div'); w.className = 'tbl-wrap'; t.replaceWith(w); w.appendChild(t);
  }
}
let wrapRaf = 0;
new MutationObserver(() => { if (wrapRaf) return; wrapRaf = requestAnimationFrame(() => { wrapRaf = 0; wrapTables(document); }); }).observe(document.documentElement, { childList: true, subtree: true });
async function rerender(id) {
  const w = S.wins[id]; const fn = V[id]; if (!w || !fn) return;
  S.lastView = id;
  const body = $('#wb-' + id); const seq = seqs[id] = (seqs[id] || 0) + 1;
  if (id === 'terminal' && S.termDispose) return;
  body.innerHTML = '<div class="grid"><div class="c12 panel panel--flat"><div class="skeleton" style="width:40%"></div><div class="skeleton" style="width:70%;margin-top:10px"></div><div class="skeleton" style="width:55%;margin-top:10px"></div></div></div>';
  try {
    const html = await fn();
    if (seq !== seqs[id] || !S.wins[id]) return;
    body.innerHTML = html; fn.after && fn.after(body);
    if (id === 'overview' && S.stats) paintLive(S.stats);
  } catch (e) {
    if (e.status === 401) return showLogin(e);
    body.innerHTML = `<div class="panel panel--bad"><div class="panel__hd"><h3>Could not load</h3></div><p>${esc(e.message)}</p><div class="row" style="margin-top:12px"><button class="btn btn--sm" onclick="location.reload()">Reload</button></div></div>`;
  }
}
const render = () => rerender(S.lastView);

/* ---------------- menu bar menus ---------------- */
let menuOpen = null;
function menuItems(id) {
  const a = id ? appOf(id) : null;
  const win = [['Minimise', () => id && minApp(id), '⌘M'], ['Zoom', () => id && $('.z', S.wins[id].el).click()], ['Close Window', () => id && closeApp(id), '⌘W'], null, ['Mission Control', () => missionControl(true), 'F3'], ['Launchpad', () => toggleLaunchpad(true)], null, { h: 'Open' }, ...Object.keys(S.wins).map(k => [appOf(k).name + (S.wins[k].min ? ' (minimised)' : ''), () => openApp(k, true)])];
  const help = [['ariseOS Help', () => openApp('help'), 'F1'], ['Keyboard Shortcuts', () => shortcutsSheet(), '⌘/'], ['Show me around', () => walkthrough(true)], null, ...(isMember() ? [] : [['Dashboard guide', () => { S.help = { name: 'DASHBOARD', q: '' }; openApp('help'); }], ['Remote access guide', () => { S.help = { name: 'REMOTE-ACCESS', q: '' }; openApp('help'); }], ['Install guide', () => { S.help = { name: 'INSTALL', q: '' }; openApp('help'); }], ['On GitHub', () => window.open('https://github.com/Rehchu/Church-server-OS-')], null]), ['About This Server', () => openApp('about')]];
  const file = { files: [['New Folder', () => $('#fNew')?.click(), '⇧⌘N'], ['Upload Here', () => $('#fsUp')?.click()], null, ['Share Link…', () => { const el = $('#fMain .sel'); if (el) shareLink(S.fs.root, (S.fs.path === '/' ? '' : S.fs.path) + '/' + el.dataset.n, el.dataset.n); else toast('Select a file or folder first', 'warn'); }], ['Shared Links…', () => linksModal()], null, ['Quick Look', () => { const el = $('#fMain .sel'); if (el && el.dataset.dir !== '1') quickLook(S.fs.root, (S.fs.path === '/' ? '' : S.fs.path) + '/' + el.dataset.n, el.dataset.n); }, 'Space'], ['Get Info', () => { const el = $('#fMain .sel'); if (el) getInfo(el.dataset.n, el.dataset.dir === '1', (S.fs.path === '/' ? '' : S.fs.path) + '/' + el.dataset.n, S.fs.root); else toast('Select a file or folder first', 'warn'); }, '⌘I'], ['Previous Versions…', () => { const el = $('#fMain .sel'); if (el) versionsModal(S.fs.root, (S.fs.path === '/' ? '' : S.fs.path) + '/' + el.dataset.n, el.dataset.n); else toast('Select a file first', 'warn'); }], ['Compress', () => { const el = $('#fMain .sel'); if (el) finderZip(S.fs.root, (S.fs.path === '/' ? '' : S.fs.path) + '/' + el.dataset.n, el.dataset.n); else toast('Select a file or folder first', 'warn'); }], ...(IS_MAC ? [['Open on my Mac', () => openOnMac(S.fs.root, S.fs.path)]] : []), null, ['Recents', () => fsNav('@recent', '/')], ['Trash', () => fsNav('@trash', '/')], null, ['Move to Trash', () => { const el = $('#fMain .sel'); if (el) trashIt(S.fs.root, (S.fs.path === '/' ? '' : S.fs.path) + '/' + el.dataset.n, el.dataset.n); else toast('Select a file or folder first', 'warn'); }, '⌘⌫'], null, ['Close Window', () => closeApp('files'), '⌘W']],
    backups: [['Run all jobs now', () => act($('#next') || document.body, () => api('/backups/run/automator', { method: 'POST' }), 'Started the automator job')], ['Refresh GitHub mirror', () => api('/backups/mirror', { method: 'POST' }).then(() => toast('Mirror refreshed'))], null, ['Close Window', () => closeApp(id), '⌘W']],
    automator: [['Preview tonight (dry run)', () => api('/automator/preview', { method: 'POST' }).then(() => toast('Preview started'))], null, ['Close Window', () => closeApp(id), '⌘W']],
    terminal: [['New shell (reopen)', () => { closeApp('terminal'); openApp('terminal'); }], null, ['Close Window', () => closeApp(id), '⌘W']],
    devices: [['Scan now', () => $('#devScan')?.click()], null, ['Close Window', () => closeApp(id), '⌘W']],
    sunday: [['Refresh', () => rerender('sunday'), '⌘R'], null, ['Close Window', () => closeApp(id), '⌘W']],
    mail: [['Compose', () => { S.mailTab = 'compose'; rerender('mail'); }], ['Contacts', () => { S.mailTab = 'contacts'; rerender('mail'); }], ['Sent', () => { S.mailTab = 'sent'; rerender('mail'); }], null, ['Close Window', () => closeApp(id), '⌘W']],
    calendar: [['Add Event…', () => !isMember() && eventModal(null)], ['Subscribe…', () => subscribeModal()], ['Today', () => $('#calToday')?.click()], null, ['Close Window', () => closeApp(id), '⌘W']],
    clock: [['World clock', () => { S.clock.tab = 'world'; rerender('clock'); }], ['Timer', () => { S.clock.tab = 'timer'; rerender('clock'); }], ['Stopwatch', () => { S.clock.tab = 'sw'; rerender('clock'); }], ['Alarm', () => { S.clock.tab = 'alarm'; rerender('clock'); }], null, ['Close Window', () => closeApp(id), '⌘W']],
    calc: [['Clear', () => { S.calc = { expr: '', res: '0' }; rerender('calc'); }], ['Copy result', () => copyText(S.calc?.res || '0')], null, ['Close Window', () => closeApp(id), '⌘W']],
    help: [['Portal guide', () => { S.help.name = 'PORTAL-GUIDE'; rerender('help'); }], ['Keyboard Shortcuts', () => shortcutsSheet(), '⌘/'], null, ['Close Window', () => closeApp(id), '⌘W']],
    apps: [['Installed', () => { S.storeTab = 'installed'; rerender('apps'); }], ['Catalogue', () => { S.storeTab = 'catalog'; rerender('apps'); }], null, ['Close Window', () => closeApp(id), '⌘W']],
    updates: [['Refresh the lists', () => $('#upRefresh')?.click()], ['Check apps', () => $('#upCheckApps')?.click()], null, ['Close Window', () => closeApp(id), '⌘W']],
    logs: [['Last error', () => $('#logErr')?.click()], ['Copy for Claude', () => $('#logClaude')?.click()], null, ['Close Window', () => closeApp(id), '⌘W']],
    storage: [['Rescan', () => $('#stScan')?.click()], null, ['Close Window', () => closeApp(id), '⌘W']],
    settings: SETTINGS_SECTIONS.map(([sid, name]) => [name, () => { S.settingsSec = sid; rerender('settings'); }]).concat([null, ['Close Window', () => closeApp(id), '⌘W']]),
    assist: [['Open Claude', () => $$('[data-url]').find(b => b.dataset.url.includes('claude'))?.click()], ['Claude Code in Terminal', () => $('[data-claude-code]')?.click()], null, ['Close Window', () => closeApp(id), '⌘W']],
  }[id] || [['Close Window', () => id && closeApp(id), '⌘W']];
  const view = [['Refresh', () => id && rerender(id), '⌘R'], null, ['Show Widgets', () => toggleNC(true)], ['Control Center', () => toggleCC(true)], ['Spotlight', () => toggleSpot(true), '⌘Space']];
  return [[a ? a.name : 'ariseOS', a ? [['About ' + a.name, () => toast(a.what)], null, ['Hide ' + a.name, () => minApp(id), '⌘H'], ['Quit ' + a.name, () => closeApp(id), '⌘Q']] : [['About This Server', () => openApp('about')]]], ['File', file], ['View', view], ['Window', win], ['Help', help]];
}
const FLAME_MENU = () => isMember() ? [['About This Server', () => openApp('about')], null, ['My Profile…', () => profileSheet()], ['Change Password…', () => changePassword()], ['Two-step sign-in…', () => twofaModal()], ['Shared Links…', () => linksModal()], ['Launchpad', () => toggleLaunchpad(true)], null, ['Lock Screen', () => lockScreen(), '⌃⌘Q'], ['Sign Out ' + (S.user || ''), () => signOut()], ...(S.demoOnly ? [null, { h: 'Preview' }, ...previewMenu().slice(2)] : [])]
  : [['About This Server', () => openApp('about')], null, ['System Settings…', () => openApp('settings')], ['My Profile…', () => profileSheet()], ['Change Password…', () => changePassword()], ['Two-step sign-in…', () => twofaModal()], ['Security', () => openApp('security')], ['Launchpad', () => toggleLaunchpad(true)], null, ['Run backups now', () => runAllBackups()], ['Preview tonight\'s automator', () => api('/automator/preview', { method: 'POST' }).then(() => toast('Preview started: a dry run, nothing written'))], null, ['Lock Screen', () => lockScreen(), '⌃⌘Q'], ['Sign Out ' + (S.user || ''), () => signOut()], null, ...POWER_MENU(), ...(S.demoOnly ? [null, { h: 'Preview' }, ...previewMenu().slice(2)] : [])];
function setAppMenus(id) {
  const m = $('#menus'); const list = menuItems(id);
  m.innerHTML = list.map((g, i) => `<button class="${i === 0 ? 'app' : ''}" data-m="${i}">${esc(g[0])}</button>`).join('');
  // On a phone only the app's name shows in the bar (File, View, Window and Help would push the
  // clock off the screen), so its menu carries every group, each under its own heading.
  const all = () => list.flatMap((g, i) => i === 0 ? g[1] : [null, { h: g[0] }, ...g[1].filter(x => x !== null)]);
  $$('button', m).forEach(b => { b.onclick = e => { e.stopPropagation(); openMenu(b, +b.dataset.m === 0 && matchMedia('(max-width: 520px)').matches ? all() : list[+b.dataset.m][1]); }; b.onmouseenter = () => { if (menuOpen && menuOpen !== b) openMenu(b, list[+b.dataset.m][1]); }; });
}
function openMenu(btn, items) {
  const d = $('#menuDrop');
  if (menuOpen === btn) { closeMenu(); return; }
  closeMenu(); menuOpen = btn; btn.classList.add('open');
  d.innerHTML = items.map(it => it === null ? '<hr>' : it.h ? `<div class="h">${esc(it.h)}</div>` : `<button>${esc(it[0])}${it[2] ? `<kbd>${esc(kbd(it[2]))}</kbd>` : ''}</button>`).join('');
  const fns = items.filter(it => Array.isArray(it)); $$('button', d).forEach((b, i) => b.onclick = () => { closeMenu(); fns[i][1](); });
  const r = btn.getBoundingClientRect(); d.style.left = Math.min(r.left, innerWidth - 240) + 'px'; d.style.top = r.bottom + 'px'; d.hidden = false;
}
function closeMenu() { if (menuOpen) menuOpen.classList.remove('open'); menuOpen = null; $('#menuDrop').hidden = true; $('#barLogo').classList.remove('open'); }
document.addEventListener('pointerdown', e => { if (!$('#stage')) return; if (menuOpen && !e.target.closest('#menuDrop') && !e.target.closest('#menus') && !e.target.closest('#barLogo')) closeMenu(); if (!$('#cc').hidden && !e.target.closest('#cc') && !e.target.closest('#ccBtn')) toggleCC(false); }, true);

/* ---------------- overlays: launchpad, spotlight, mission control, NC, CC, switcher ---------------- */
function closeOverlays() { toggleLaunchpad(false); toggleSpot(false); toggleCC(false); closeMenu(); $('#ctx').hidden = true; }
function toggleLaunchpad(force) { const lp = $('#launchpad'); const open = force !== undefined ? force : lp.hidden; lp.hidden = !open; if (open) { toggleSpot(false); toggleNC(false); $('#lpQ').value = ''; $$('.lp').forEach(b => b.hidden = false); $('#lpQ').focus(); } }
function toggleNC(force) { const nc = $('#nc'); const open = force !== undefined ? force : nc.hidden; nc.hidden = !open; $('#barClock').classList.toggle('open', open); if (open) { toggleCC(false); buildNC(); } }
function toggleCC(force) { const cc = $('#cc'); const open = force !== undefined ? force : cc.hidden; cc.hidden = !open; $('#ccBtn').classList.toggle('open', open); if (open) buildCC(); }
function toggleSpot(force) { const sp = $('#spot'); const open = force !== undefined ? force : sp.hidden; sp.hidden = !open; if (open) { toggleLaunchpad(false); $('#spotQ').value = ''; $('#spotRes').innerHTML = spotResults(''); $('#spotQ').focus(); } }
function missionControl(force) {
  const st = $('#stage'); const on = force !== undefined ? force : !st.classList.contains('mc');
  const wins = Object.values(S.wins).filter(w => !w.min).map(w => w.el);
  if (!on) { st.classList.remove('mc'); wins.forEach(el => { el.style.transform = ''; }); return; }
  if (!wins.length) { toast('No windows open', 'warn'); return; }
  closeOverlays(); st.classList.add('mc');
  const n = wins.length, cols = Math.ceil(Math.sqrt(n)), rows = Math.ceil(n / cols), W = st.clientWidth, H = st.clientHeight - 90, pad = 24;
  const cw = (W - pad * (cols + 1)) / cols, ch = (H - pad * (rows + 1)) / rows;
  wins.forEach((el, i) => { const c = i % cols, r = Math.floor(i / cols); const sc = Math.min(cw / el.offsetWidth, ch / el.offsetHeight, 1); const x = pad + c * (cw + pad) + (cw - el.offsetWidth * sc) / 2, y = 40 + pad + r * (ch + pad) + (ch - el.offsetHeight * sc) / 2; el.style.transform = `translate(${x - el.offsetLeft}px, ${y - el.offsetTop}px) scale(${sc})`; el.style.transformOrigin = 'top left'; });
}
let swIdx = 0;
function switcher(step) {
  const ids = Object.keys(S.wins); if (!ids.length) return; const sw = $('#switcher');
  if (sw.hidden) { swIdx = Math.max(0, ids.indexOf(S.focused)); sw.hidden = false; }
  swIdx = (swIdx + step + ids.length) % ids.length;
  sw.innerHTML = `<div>${ids.map((id, i) => `<span class="dock__icon ${appOf(id).tone || ''} ${i === swIdx ? 'on' : ''}">${I[id]}</span>`).join('')}</div>`;
  clearTimeout(S.swT); S.swT = setTimeout(() => { sw.hidden = true; openApp(ids[swIdx], true); }, 900);
}

/* Spotlight */
const ACTIONS_ALL = [['Run backups now', () => runAllBackups(), 'backups'], ['Preview tonight\'s automator', () => api('/automator/preview', { method: 'POST' }).then(() => toast('Preview started')), 'automator'], ['Lock screen', () => lockScreen(), 'about'], ['Restart the server', () => powerAsk('reboot'), 'settings'], ['Shut down the server', () => powerAsk('poweroff'), 'settings'], ['Mission Control', () => missionControl(true), 'overview'], ['About This Server', () => openApp('about'), 'about'], ['Check for updates', () => openApp('updates'), 'updates'], ['Rescan storage', () => { openApp('storage'); setTimeout(() => $('#stScan')?.click(), 1500); }, 'storage'], ['Turn the monitor off', () => api('/monitor/power', { method: 'POST', body: { on: false } }).then(r => toast(r.ok === false ? r.err : 'Panel off', r.ok === false ? 'bad' : 'ok')), 'monitor']];
const ACTIONS_ANY = [['Help', () => openApp('help'), 'help'], ['Keyboard shortcuts', () => shortcutsSheet(), 'help'], ['Subscribe to the calendar', () => subscribeModal(), 'calendar'], ['Set a timer', () => { S.clock = S.clock || { tab: 'timer', timer: { total: 300, left: 300, on: false, at: 0 }, sw: { el: 0, on: false, t0: 0, laps: [] }, alarm: null }; S.clock.tab = 'timer'; openApp('clock'); }, 'clock']];
const actions = () => (isMember() ? [['Change password…', () => changePassword(), 'about'], ['Shared links…', () => linksModal(), 'files']] : ACTIONS_ALL).concat(ACTIONS_ANY);
function spotResults(q, remote) {
  q = q.trim(); const ql = q.toLowerCase(); let out = ''; const row = (icon, label, small, data) => `<button data-s='${esc(JSON.stringify(data))}'><span class="dock__icon">${icon}</span>${esc(label)}${small ? `<small>${esc(small)}</small>` : ''}</button>`;
  if (q && looksLikeSum(q)) out += `<div class="h">Calculator</div>` + row(I.calc, `= ${fmtCalc(calcEval(q))}`, q, { calc: q });
  const bible = q.match(/^([1-3]?\s?[a-z]{2,20})\s?(\d{1,3})(?::(\d{1,3})(?:-(\d{1,3}))?)?$/i);
  if (bible) out += `<div class="h">Bible</div>` + row(I.bible, `Read ${q}`, 'Bible', { bible: q });
  const apps = visibleApps().filter(a => !a.hidden && (!ql || a.name.toLowerCase().includes(ql) || a.what.toLowerCase().includes(ql)));
  if (apps.length) out += `<div class="h">Apps</div>` + apps.slice(0, ql ? 6 : 8).map(a => row(I[a.id], a.name, a.what, { app: a.id })).join('');
  const acts = actions().filter(a => ql && a[0].toLowerCase().includes(ql)); if (acts.length) out += `<div class="h">Actions</div>` + acts.map((a, i) => row(I[a[2]], a[0], 'Action', { act: actions().indexOf(a) })).join('');
  if (remote) {
    if (remote.users?.length) out += `<div class="h">People</div>` + remote.users.map(u => row(I.directory, u.display || u.name, u.name, { app: 'directory' })).join('');
    if (remote.computers?.length) out += `<div class="h">Computers</div>` + remote.computers.map(c => row(I.sites, c.name, c.os || c.kind, { app: 'sites' })).join('');
    if (remote.transcripts?.length) out += `<div class="h">Sermons · transcripts</div>` + remote.transcripts.map(t => row(I.sermons, t.title, t.snippet, S.role === 'admin' ? { chsearch: q } : { app: 'sermons' })).join('');
    if (remote.hits?.length) out += `<div class="h">Files</div>` + remote.hits.slice(0, 10).map(h => row(I.files, h.name, h.path, { file: h })).join('');
  }
  if (!out) out = `<div class="h">Nothing for “${esc(q)}”</div>`;
  return out;
}
function spotGo(data) {
  toggleSpot(false);
  if (data.app) openApp(data.app);
  else if (data.chsearch != null) { CH.sq = data.chsearch; CH.skind = 'transcript'; CH.open = null; (S.tabs = S.tabs || {}).automator = 'search'; if (S.wins?.automator) rerender('automator'); else openApp('automator'); }
  else if (data.bible) { S.bible = { ref: data.bible, tr: S.bible?.tr || 'web' }; openApp('bible'); }
  else if (data.calc) { S.calc = { expr: '', res: fmtCalc(calcEval(data.calc)) }; copyText(S.calc.res); openApp('calc'); }
  else if (data.act != null) actions()[data.act][1]();
  else if (data.file) { const f = data.file; const dir = f.dir ? f.path : f.path.replace(/\/[^/]*$/, '') || '/'; S.fs = Object.assign(S.fs || { view: 'icon', hist: [], fwd: [], q: '' }, { root: f.root, path: dir, sel: f.dir ? null : f.name, q: '' }); openApp('files'); }
}

/* Notification Center widgets */
function fmtSvc(t) { const [h, m] = String(t).split(':').map(Number); const d = new Date(); d.setHours(h, m || 0); return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); }
function weekWidget() {
  const c = S.church; const n = c?.next;
  const rows = (c?.services || [{ name: 'Sunday Service', site: 'Pineville', day: 'Sunday', time: '10:30' }, { name: 'Sunday Service', site: 'Alexandria', day: 'Sunday', time: '10:00' }, { name: 'Glory Night', site: 'Pineville', day: 'Monday', time: '19:00' }]);
  return `<div data-wg="week" class="widget"><div class="widget__kicker">This week${n ? ` · next in ${esc(n.in_words)}` : ''}</div><div class="widget__rows">${rows.map(x => `<div class="widget__row"><span>${esc(x.name === 'Sunday Service' ? 'Sunday · ' + x.site : x.name + ' · ' + x.day)}</span><b>${esc(fmtSvc(x.time))}</b></div>`).join('')}</div></div>`;
}
function verseWidget() { const v = S.church?.verse; if (!v || !v.text) return ''; return `<div data-wg="verse" class="widget widget--verse"><div class="widget__kicker">Verse of the day</div><blockquote>${esc(v.text)}<cite>${esc(v.ref)}</cite></blockquote></div>`; }
async function loadChurch() { try { S.church = await api('/church'); } catch { S.church = S.church || null; } }
async function buildMemberWidgets() {
  await loadWeather();
  const w = $('#widgets'); const roots = S.me?.roots || []; let links = [];
  try { links = (await api('/links')).links || []; } catch {}
  const live = links.filter(l => !l.expired);
  w.innerHTML = `<div class="widget widget--clear"><div class="widget__kicker">Signed in</div><div class="widget__title" style="font-size:18px">${esc(S.user)}</div><div class="widget__sub">${(S.me?.groups || []).join(' · ') || 'member'}</div></div>
    <div class="widget"><div class="widget__kicker">Your places</div><div class="widget__rows">${roots.map(r => `<button class="widget__row" data-root="${esc(r.id)}"><span>${esc(r.name)}</span><b>${r.home ? 'your home folder' : r.writable === false ? 'read only' : 'share'}</b></button>`).join('')}</div></div>
    <div class="widget"><div class="widget__kicker">Shared links</div><div class="widget__rows"><div class="widget__row"><span>Live</span><b>${live.length}</b></div><div class="widget__row"><span>Downloads</span><b>${links.reduce((a, l) => a + (l.downloads || 0), 0)}</b></div></div><button class="btn btn--ghost btn--xs" data-act="links" style="margin-top:8px">Manage</button></div>
    ${weekWidget()}${weatherWidget()}${verseWidget()}`;
  $$('[data-root]', w).forEach(b => b.onclick = () => { S.fs = Object.assign(S.fs || { view: 'icon', hist: [], fwd: [], q: '' }, { root: b.dataset.root, path: '/', sel: null }); openApp('files'); if (S.wins.files) rerender('files'); });
  $$('[data-act="links"]', w).forEach(b => b.onclick = () => linksModal());
}
async function buildNC() {
  const body = $('#ncBody'); body.innerHTML = $('#widgets').innerHTML + '<div class="widget" id="ncCal"></div><div class="widget" id="ncSermon"><div class="widget__kicker">Latest on the channel</div><div class="skeleton"></div></div>';
  $$('[data-open]', body).forEach(x => x.onclick = () => { toggleNC(false); openApp(x.dataset.open); });
  const d = new Date(), y = d.getFullYear(), m = d.getMonth(); const first = new Date(y, m, 1).getDay(), days = new Date(y, m + 1, 0).getDate();
  let cal = `<div class="widget__kicker">${d.toLocaleString('en-US', { month: 'long', year: 'numeric' })}</div><div class="cal">${['S', 'M', 'T', 'W', 'T', 'F', 'S'].map(x => `<b>${x}</b>`).join('')}`;
  for (let i = 0; i < first; i++) cal += '<span class="dim"></span>';
  for (let i = 1; i <= days; i++) { const wd = new Date(y, m, i).getDay(); cal += `<span class="${wd === 0 || wd === 1 ? 'svc' : ''} ${i === d.getDate() ? 'today' : ''}">${i}</span>`; }
  cal += `</div><div class="widget__sub" style="margin-top:8px">● ${(S.church?.services || []).map(x => `${x.day}s ${fmtSvc(x.time)} ${x.name === 'Sunday Service' ? x.site : x.name}`).join(' · ') || 'Sundays 10:30 Pineville · 10:00 Alexandria · Mondays 7 PM Glory Night'}</div>`;
  $('#ncCal').innerHTML = cal;
  try { const c = await api('/calendar'); const up = (c.upcoming || []).filter(x => new Date(x.start) - Date.now() < 7 * 86400000).slice(0, 6); if (up.length && $('#ncCal')) $('#ncCal').insertAdjacentHTML('beforeend', `<div class="widget__rows" style="margin-top:10px">${up.map(x => `<button class="widget__row" data-open="calendar"><span>${esc(fmtDay(x.start))} · ${esc(x.title)}</span><b>${esc(fmtClock(x.start))}</b></button>`).join('')}</div>`); $$('#ncCal [data-open]').forEach(b => b.onclick = () => { toggleNC(false); openApp('calendar'); }); } catch {}
  try { const s = await api('/sermons?limit=1'); const v = (s.videos || [])[0]; if (v) $('#ncSermon').innerHTML = `<div class="widget__kicker">Latest on the channel</div><div class="widget__title" style="font-size:15px">${esc(v.title)}</div><div class="widget__sub">${esc(v.kind)} · ${esc(v.published)}${v.views ? ' · ' + fmtN(v.views) + ' views' : ''}</div><div class="row" style="margin-top:8px"><button class="btn btn--ghost btn--xs" data-open="sermons">Sermons</button></div>`; $$('[data-open]', $('#ncSermon')).forEach(x => x.onclick = () => { toggleNC(false); openApp(x.dataset.open); }); } catch {}
}
/* Control Center */
/* ---- feel: quiet sounds, the Bone theme, push, the first-sign-in walkthrough (v0.7 Genesis) ---- */
const PREF = { get: (k, d) => { try { const v = localStorage.getItem('arise.' + k); return v === null ? d : v; } catch { return d; } }, set: (k, v) => { try { localStorage.setItem('arise.' + k, v); } catch {} } };
let _ac = null;
function tone(kind) {
  if (PREF.get('sounds', '1') !== '1') return;
  try { _ac = _ac || new (window.AudioContext || window.webkitAudioContext)(); const t = _ac.currentTime; const g = _ac.createGain(); g.connect(_ac.destination);
    const note = (f, start, len, vol, type = 'sine') => { const o = _ac.createOscillator(); o.type = type; o.frequency.value = f; const gg = _ac.createGain(); gg.gain.setValueAtTime(0, t + start); gg.gain.linearRampToValueAtTime(vol, t + start + 0.01); gg.gain.exponentialRampToValueAtTime(0.0001, t + start + len); o.connect(gg); gg.connect(_ac.destination); o.start(t + start); o.stop(t + start + len + 0.05); };
    if (kind === 'click') note(1800, 0, 0.04, 0.06, 'triangle');
    else if (kind === 'done') { note(660, 0, 0.18, 0.08); note(880, 0.14, 0.22, 0.08); note(1320, 0.3, 0.35, 0.07); }
    else if (kind === 'bad') { note(220, 0, 0.35, 0.09, 'sawtooth'); note(165, 0.3, 0.5, 0.08, 'sawtooth'); }
    else if (kind === 'open') note(1200, 0, 0.06, 0.04, 'triangle');
  } catch {}
}
function applyTheme() { const bone = PREF.get('theme', 'dark') === 'bone' && !S.kiosk; document.body.classList.toggle('bone', bone); const m = document.querySelector('meta[name=theme-color]'); if (m) m.content = bone ? '#F4F2F0' : '#0A0A0C'; }
function toggleTheme() { PREF.set('theme', PREF.get('theme', 'dark') === 'bone' ? 'dark' : 'bone'); applyTheme(); buildCC(); }
async function enablePush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return toast('This browser cannot do push', 'warn');
  const k = await api('/push/key'); if (!k.available) return toast(k.note || 'Push is not available on this server', 'warn'); if (!k.enabled_for_me) return toast('Push goes to the administrator only', 'warn');
  const perm = await Notification.requestPermission(); if (perm !== 'granted') return toast('Notifications were not allowed', 'warn');
  const reg = await navigator.serviceWorker.ready; const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: (b => { const s = atob(b.replace(/-/g, '+').replace(/_/g, '/')); return Uint8Array.from(s, ch => ch.charCodeAt(0)); })(k.key) });
  const r = await api('/push/subscribe', { method: 'POST', body: { subscription: sub.toJSON(), label: navigator.userAgent.slice(0, 60) } }); if (r.ok === false) return toast(r.err, 'bad');
  PREF.set('push', '1'); toast('Push on for this device. Sending a test…'); await api('/push/test', { method: 'POST' }).catch(() => {}); buildCC();
}
function walkthrough(force) {
  const key = 'walk.' + (S.user || 'x'); if (!force && PREF.get(key, '') === 'done') return;
  const m = isMember();
  const steps = m ? [
    ['Welcome to ariseOS', 'This is the church\'s own server. Sign in from anywhere with the same password you use on the Macs. Nothing here needs an app store.'],
    ['Your files', 'Finder opens on <b>My files</b>, your home folder on the server. The shares your groups allow sit under it. Drag a file onto a folder to upload, or press <span class="walk__k">Upload</span>.'],
    ['Share a link', 'Right-click any file or folder and pick <b>Share Link…</b>. Anyone with the link can download it for 7 days. <b>Shared Links…</b> in the flame menu lists yours.'],
    ['Sunday and Sermons', 'The <b>Sunday</b> app has the service checklist and the countdown. <b>Sermons</b> is the channel. Spotlight (<span class="walk__k">' + kbd('⌘Space') + '</span>) finds anything.'],
    ['Your password', 'Flame menu → <b>Change Password…</b>. One password for the Macs, the shares and this. If you forget it, Bradly resets it.'],
  ] : [
    ['Welcome to ariseOS', 'The desktop on the closet monitor and in every browser. The flame menu holds the box: settings, backups, lock, power.'],
    ['Needs You', 'The first widget is the only alarm: red items are things to fix, amber are things to know. The Overview app has the rest, and <b>Why?</b> explains a failure in plain English.'],
    ['People and shares', '<b>Directory</b> makes accounts (first.last), groups and shares. Members sign in here with the same password the Macs use.'],
    ['Sunday', 'The <b>Sunday</b> app: the checklist, the countdown, the verse. On Sunday morning the desktop turns the house lights down by itself.'],
    ['When it breaks', '<span class="walk__k">sudo arisectl doctor</span> over SSH, <b>Cockpit</b> on :9090, and Claude on the box (<b>Assistants</b> → Claude Code). The closet card on the door has the three commands.'],
  ];
  let i = 0; const box = document.createElement('div'); box.className = 'walk'; document.body.appendChild(box);
  const paint = () => { const [h, t] = steps[i]; box.innerHTML = `<div class="walk__box"><div class="walk__dots">${steps.map((_, j) => `<i class="${j <= i ? 'on' : ''}"></i>`).join('')}</div><h2>${h}</h2><p>${t}</p><div class="row row--between"><button class="btn btn--ghost btn--xs" id="wkSkip">Skip</button><button class="btn" id="wkNext">${i === steps.length - 1 ? 'Done' : 'Next'}</button></div></div>`;
    $('#wkSkip').onclick = done; $('#wkNext').onclick = () => { tone('click'); if (++i >= steps.length) done(); else paint(); }; };
  const done = () => { PREF.set(key, 'done'); box.remove(); tone('done'); };
  paint();
}
function buildCC() {
  const o = S.overview || {}; const r = S.remoteCache || {};
  if (isMember()) {
    $('#cc').innerHTML = `<button class="wide" data-open="files"><b>My files</b><span>${(S.me?.roots || []).map(x => esc(x.name)).join(' · ')}</span></button>
    <button data-act="links"><b>Shared links</b><span>what you have shared</span></button><button data-act="pw"><b>Change password</b><span>your directory password</span></button>
    <button data-act="mc"><b>Mission Control</b><span>all windows</span></button><button data-act="lock"><b>Lock screen</b><span>${kbd('⌃⌘Q')}</span></button>
    ${ccFeel()}`;
    $$('[data-open]', $('#cc')).forEach(b => b.onclick = () => { toggleCC(false); openApp(b.dataset.open); });
    $$('[data-act]', $('#cc')).forEach(b => b.onclick = () => { const a = b.dataset.act; if (a in CC_FEEL) return CC_FEEL[a](); toggleCC(false); ({ links: linksModal, pw: changePassword, mc: () => missionControl(true), lock: lockScreen })[a](); });
    return;
  }
  const vpnOn = r.tailscale?.up || r.wireguard?.up;
  $('#cc').innerHTML = `<button class="${vpnOn ? 'ok' : 'bad'}" data-open="remote"><b>VPN</b><span>${vpnOn ? (r.tailscale?.up ? 'Tailscale connected' : 'WireGuard up') : 'not connected'}</span></button>
    <button class="${o.backup?.failed_recent ? 'bad' : 'ok'}" data-open="backups"><b>Backups</b><span>${o.backup?.last ? (o.backup.last.ok ? 'last ok · ' : 'FAILED · ') + ago(o.backup.last.started) : 'none yet'}</span></button>
    <button data-act="backup"><b>Back up now</b><span>every job, then prune</span></button>
    <button data-act="preview"><b>Preview tonight</b><span>automator dry run</span></button>
    <button data-act="mc"><b>Mission Control</b><span>all windows</span></button>
    <button data-act="lock"><b>Lock screen</b><span>${kbd('⌃⌘Q')}</span></button>
    ${ccFeel()}
    <button class="wide" data-open="settings"><b>System Settings</b><span>updates · power · note</span></button>`;
  $$('[data-open]', $('#cc')).forEach(b => b.onclick = () => { toggleCC(false); openApp(b.dataset.open); });
  $$('[data-act]', $('#cc')).forEach(b => b.onclick = () => { const a = b.dataset.act; if (a in CC_FEEL) return CC_FEEL[a](); toggleCC(false); ({ backup: runAllBackups, preview: () => api('/automator/preview', { method: 'POST' }).then(() => toast('Preview started')), mc: () => missionControl(true), lock: lockScreen })[a](); });
}
const CC_FEEL = { dockhide: () => { PREF.set('dock.hide', PREF.get('dock.hide', '1') === '1' ? '0' : '1'); applyDockHide(); buildCC(); }, 'a11y-text': () => { PREF.set('a11y.text', PREF.get('a11y.text', '0') === '1' ? '0' : '1'); applyA11y(); buildCC(); }, 'a11y-motion': () => { PREF.set('a11y.motion', PREF.get('a11y.motion', '0') === '1' ? '0' : '1'); applyA11y(); buildCC(); }, 'a11y-contrast': () => { PREF.set('a11y.contrast', PREF.get('a11y.contrast', '0') === '1' ? '0' : '1'); applyA11y(); buildCC(); }, theme: toggleTheme, sounds: () => { PREF.set('sounds', PREF.get('sounds', '1') === '1' ? '0' : '1'); tone('click'); buildCC(); }, push: () => { toggleCC(false); enablePush(); }, walk: () => { toggleCC(false); walkthrough(true); } };
function ccFeel() {
  const bone = PREF.get('theme', 'dark') === 'bone', snd = PREF.get('sounds', '1') === '1', pushOn = PREF.get('push', '') === '1';
  return `<button class="${bone ? 'ok' : ''}" data-act="theme" ${S.kiosk ? 'disabled title="the monitor stays dark"' : ''}><b>${bone ? 'Bone' : 'House Lights Down'}</b><span>${S.kiosk ? 'the monitor stays dark' : bone ? 'light paper · tap for dark' : 'dark stage · tap for light'}</span></button>
    <button class="${snd ? 'ok' : ''}" data-act="sounds"><b>Sounds ${snd ? 'on' : 'off'}</b><span>quiet clicks and chimes</span></button>
    ${S.me && S.me.user && !S.kiosk ? `<button class="${pushOn ? 'ok' : ''}" data-act="push"><b>Push ${pushOn ? 'on' : 'off'}</b><span>${pushOn ? 'this device gets alerts' : 'alerts to this phone'}</span></button>` : ''}
    <button data-act="walk"><b>Show me around</b><span>the five-step tour</span></button>
    ${isPhone() ? '' : `<button class="${PREF.get('dock.hide', '1') === '1' ? 'ok' : ''}" data-act="dockhide"><b>Dock ${PREF.get('dock.hide', '1') === '1' ? 'hides' : 'stays'}</b><span>${PREF.get('dock.hide', '1') === '1' ? 'slides away; mouse at the bottom edge brings it back' : 'always on screen'}</span></button>`}
    ${ccA11y()}`;
}
async function runAllBackups() { const jobs = (await api('/backups/jobs')).jobs || []; for (const j of jobs) await api(`/backups/run/${encodeURIComponent(j.id)}`, { method: 'POST' }); toast(`Started ${jobs.length} backup jobs; rows appear in Backups as they finish`); }
function powerAsk(action) { confirmType(action === 'reboot' ? 'Restart the server' : 'Shut the server down', action, action === 'reboot' ? 'Everything stops for about a minute. Logged-in Macs keep working on cached accounts. The desktop comes back by itself.' : '<b>Someone has to walk to the closet to turn it back on.</b> No domain logins, no 02:05 automator, no backups until then.', async () => { const r = await withReauth(() => api('/system/power', { method: 'POST', body: { action, confirm: action } })); if (r.ok === false) throw new Error(r.err); toast(r.demo ? (r.out || 'Sample mode: nothing restarted') : action === 'reboot' ? 'Restarting…' : 'Shutting down.', 'warn', 8000); }); }

/* ---------------- dock + launchpad + desktop icons ---------------- */
const DOCK_DEFAULT = { admin: ['files', 'overview', 'sunday', 'sermons', 'calendar', 'mail', 'apps', 'settings', 'terminal'], member: ['files', 'sermons', 'bible', 'sunday', 'calendar', 'assist', 'help'] };
function dockPins() { const k = 'dock.' + (isMember() ? 'member' : 'admin'); try { const v = JSON.parse(PREF.get(k, 'null')); if (Array.isArray(v)) return v.filter(id => appOf(id) && (!isMember() || MEMBER_APPS.includes(id))); } catch {} return DOCK_DEFAULT[isMember() ? 'member' : 'admin']; }
function pinApp(id, on) { const pins = dockPins().filter(x => x !== id); if (on) pins.push(id); PREF.set('dock.' + (isMember() ? 'member' : 'admin'), JSON.stringify(pins)); buildDock(); tone('click'); toast(on ? `${appOf(id).name} kept in the Dock` : `${appOf(id).name} removed from the Dock (it still shows while open)`); }
const dockApps = () => { const pins = dockPins(); const vis = visibleApps().filter(a => !a.hidden); return vis.filter(a => pins.includes(a.id)).sort((a, b) => pins.indexOf(a.id) - pins.indexOf(b.id)).concat(vis.filter(a => !pins.includes(a.id) && S.wins[a.id])); };
function applyDockHide() { const on = PREF.get('dock.hide', '1') === '1' && !isPhone(); document.body.classList.toggle('dockhide', on); let edge = $('#dockEdge'); if (!edge) { edge = document.createElement('div'); edge.id = 'dockEdge'; edge.setAttribute('aria-hidden', 'true'); $('#desk').appendChild(edge); edge.onmouseenter = () => dockShow(true); $('#dock').onmouseleave = () => dockShow(false, 400); $('#dock').onmouseenter = () => dockShow(true); } }
function dockShow(on, after) { clearTimeout(S.dockT); if (on) { $('#dock')?.classList.add('show'); return; } S.dockT = setTimeout(() => $('#dock')?.classList.remove('show'), after || 0); }   // the sign-in page may have replaced the desktop by then
function buildDock() {
  const d = $('#dock');
  d.innerHTML = dockApps().map(a => `<button class="dock__i" data-app="${a.id}" aria-label="${esc(a.name)}">${iconHtml(a)}<span class="lbl">${a.n} · ${esc(a.name)}</span></button>`).join('') +
    `<span class="dock__sep"></span><button class="dock__i" id="dockLp" aria-label="Launchpad"><span class="dock__icon">${I.apps}</span><span class="lbl">Launchpad</span></button>`;
  $$('[data-app]', d).forEach(b => { b.onclick = () => { tone('click'); const id = b.dataset.app; const w = S.wins[id]; if (w && !w.min && w.el.classList.contains('focus') && !isPhone()) minApp(id); else openApp(id, true); };
    b.oncontextmenu = e => { e.preventDefault(); const id = b.dataset.app, pinned = dockPins().includes(id), w = S.wins[id]; ctxMenu(e.clientX, e.clientY, [[pinned ? 'Remove from Dock' : 'Keep in Dock', () => pinApp(id, !pinned)], null, [w ? 'Close' : 'Open', () => w ? closeApp(id) : openApp(id)]]); }; });
  $('#dockLp').onclick = () => toggleLaunchpad();
  if (d.dataset.bound) { updateDock(); } else { d.dataset.bound = '1';
  // magnification
  d.addEventListener('mousemove', e => { if (isPhone() || reducedMotion()) return; const items = $$('.dock__i', d); items.forEach(it => { const r = it.getBoundingClientRect(); const dist = Math.abs(e.clientX - (r.left + r.width / 2)); const s = Math.max(1, 1.55 - dist / 120); it.style.transform = `scale(${s.toFixed(3)}) translateY(${(-(s - 1) * 10).toFixed(1)}px)`; }); });
  d.addEventListener('mouseleave', () => $$('.dock__i', d).forEach(it => it.style.transform = '')); }
  const lp = $('#lpGrid'); lp.innerHTML = visibleApps().filter(a => !a.hidden && !lpHidden().includes(a.id)).map(a => `<button class="lp" data-lp="${a.id}">${iconHtml(a)}<b>${esc(a.name)}</b><i>${a.n}</i><span>${esc(isMember() && a.whatMember ? a.whatMember : a.what)}</span></button>`).join('');
  $$('[data-lp]', lp).forEach(b => { b.onclick = () => { toggleLaunchpad(false); openApp(b.dataset.lp); }; b.oncontextmenu = e => { e.preventDefault(); const id = b.dataset.lp, pinned = dockPins().includes(id); ctxMenu(e.clientX, e.clientY, [[pinned ? 'Remove from Dock' : 'Keep in Dock', () => pinApp(id, !pinned)], ['Hide from my Launchpad', () => lpHide(id, true)], null, ['Open', () => { toggleLaunchpad(false); openApp(id); }]]); }; });
  $('#lpQ').oninput = e => { const q = e.target.value.toLowerCase(); $$('.lp', lp).forEach(b => b.hidden = q && !b.textContent.toLowerCase().includes(q)); };
  $('#launchpad').onclick = e => { if (e.target.id === 'launchpad') toggleLaunchpad(false); };
}
function updateDock() {
  const shown = $$('#dock [data-app]').map(b => b.dataset.app), want = dockApps().map(a => a.id); if (shown.join() !== want.join()) { buildDock(); return; }
  $$('#dock [data-app]').forEach(b => { const w = S.wins[b.dataset.app]; b.classList.toggle('run', !!w); b.classList.toggle('active', !!w && w.el.classList.contains('focus') && !w.min); }); }
async function buildIcons() {
  let roots = []; try { roots = (await api('/files/roots')).roots || []; } catch {}
  $('#icons').innerHTML = roots.map(r => `<button class="ico" data-root="${esc(r.id)}"><span class="dock__icon" style="background:${r.id === 'nas' ? ICONURL.nas : ICONURL.server} center/80% no-repeat #000"></span><span>${esc(r.name)}</span></button>`).join('');
  $$('.ico').forEach(b => { b.onclick = () => { $$('.ico').forEach(x => x.classList.remove('sel')); b.classList.add('sel'); }; b.ondblclick = () => { S.fs = Object.assign(S.fs || { view: 'icon', hist: [], fwd: [], q: '' }, { root: b.dataset.root, path: '/', sel: null }); openApp('files'); }; });
  $('#stage').addEventListener('click', e => { if (e.target === $('#stage')) $$('.ico').forEach(x => x.classList.remove('sel')); });
  $('#stage').oncontextmenu = e => { if (e.target !== $('#stage')) return; e.preventDefault(); ctxMenu(e.clientX, e.clientY, [['New Finder window', () => openApp('files')], ['Show widgets', () => toggleNC(true)], null, ['Mission Control', () => missionControl(true)], ['Launchpad', () => toggleLaunchpad(true)], null, ['About This Server', () => openApp('about')]]); };
}

/* ---------------- desktop widgets ---------------- */
async function buildWidgets() {
  if (isMember()) return buildMemberWidgets();
  await loadWeather();
  let o; try { o = await api('/overview'); } catch (e) { if (e.status === 401) return showLogin(e); o = null; }
  S.overview = o;
  const w = $('#widgets'); if (!o) { w.innerHTML = ''; return; }
  if (o.demo) { S.demo = true; $('#demoBadge').hidden = false; if (!S.demoOnly) $('#demoBadge').textContent = 'Sample data'; }
  const att = o.attention || [], bad = att.some(x => x.level === 'bad');
  const badKey = att.filter(x => x.level === 'bad').map(x => x.text).join('|'); if (bad && S.badKey !== undefined && S.badKey !== badKey) tone('bad'); S.badKey = badKey;
  $('#barAtt').hidden = !att.length; $('#barAttN').textContent = att.length;
  updatesBadge();
  const a = o.automator || {}, b = o.backup || {}, n = o.nas || {};
  const bk = $('#stBk'); bk.className = 'bar__item ' + (b.failed_recent ? 'bad' : b.last ? 'ok' : ''); $('b', bk).textContent = b.last ? (b.last.ok ? 'ok' : 'failed') : '—';
  try { const r = await api('/remote'); S.remoteCache = r; const on = r.tailscale?.up || r.wireguard?.up; const v = $('#stVpn'); v.className = 'bar__item ' + (on ? 'ok' : 'warn'); $('b', v).textContent = on ? (r.tailscale?.up ? `${(r.tailscale.peers || []).filter(p => p.online).length} online` : 'up') : 'off'; } catch {}
  const nowH = new Date().getHours();
  const next = nowH < 2 ? '02:05 automator' : nowH < 3 ? '03:00 backups' : nowH < 4 ? '04:00 GitHub mirror' : nowH < 7 ? '07:00 daily note' : '02:05 automator (tonight)';
  w.innerHTML = `
    <div data-wg="needs" class="widget ${att.length ? (bad ? 'widget--bad' : 'widget--warn') : 'widget--clear'}"><div class="widget__kicker">${att.length ? 'Needs you' : 'All clear'}</div>
      ${att.length ? `<div class="att">${att.slice(0, 4).map(x => `<div class="att__i ${x.level}">${esc(x.text)}</div>`).join('')}${att.length > 4 ? `<button class="btn btn--ghost btn--xs" data-open="overview">${att.length - 4} more</button>` : ''}</div>` : '<div class="widget__sub">Services up, last automator run clean, backups ok, Synology mounted.</div>'}</div>
    <div data-wg="live" class="widget"><div class="widget__kicker">Live</div><div class="row row--between"><span class="widget__big" id="wgCpu">–</span><span class="widget__sub" style="text-align:right">CPU<br><span id="wgNet" class="mono" style="font-size:11px">–</span></span></div><div class="meter"><i id="wgCpuM"></i></div><svg class="spark" id="wgSpark" style="height:34px"></svg><div class="row row--between" style="margin-top:6px"><span class="widget__sub">Memory <b id="wgRam" style="color:#fff">–</b></span></div><div class="meter meter--warn"><i id="wgRamM"></i></div></div>
    <div data-wg="box" class="widget"><div class="widget__kicker">The box</div>
      <div class="widget__row"><span>Directory</span><b>${o.directory_ok ? 'online' : '<span style="color:var(--redL)">down</span>'} · ${o.counts?.users} users</b></div>
      <div class="widget__row"><span>Automator</span><b>${a.last_run ? ago(a.last_run) : 'never'} · ${a.last_ok === false ? '<span style="color:var(--redL)">failures</span>' : a.last_ok ? 'clean' : '—'}</b></div>
      <div class="widget__row"><span>Quota</span><b>${fmtN(a.quota_today)} / ${fmtN(a.quota_daily)}</b></div>
      <div class="widget__row"><span>Backups</span><b>${b.last ? (b.last.ok ? 'ok' : '<span style="color:var(--redL)">failed</span>') + ' · ' + ago(b.last.started) : 'none'}</b></div>
      <div class="widget__row"><span>Synology</span><b>${n.mounted ? fmtB(n.free) + ' free' : '<span style="color:var(--warn)">not mounted</span>'}</b></div>
      <div class="widget__row"><span>Next</span><b>${esc(next)}</b></div></div>
    ${weekWidget()}${weatherWidget()}${verseWidget()}${notesWidget()}`;
  $$('[data-open]', w).forEach(x => x.onclick = () => openApp(x.dataset.open));
  applyWidgetPrefs(w); notesWidgetAfter(w);
  if (S.stats) paintWidgetLive(S.stats);
}

/* ---------------- lock, login, sign out ---------------- */
function lockScreen(idle) {
  saver(false);
  lockReset(); if (S.kiosk) api('/kiosk/claude-desktop', { method: 'POST', body: { action: 'close' } }).catch(() => {}); S.claudeDesktop = false; kioskNeutral(); const l = $('#lock'); l.hidden = false; l.classList.toggle('idle', !!idle); $('#lockName').textContent = S.user || 'bradly'; closeOverlays(); tickLock();
  if (idle) { const wake = () => { l.classList.remove('idle'); $('#lockPw').focus(); document.removeEventListener('keydown', wake); l.removeEventListener('pointerdown', wake); }; document.addEventListener('keydown', wake); l.addEventListener('pointerdown', wake); } else $('#lockPw').focus();
  lockPinOffer();
}
// Round 7, 160: an admin with a PIN unlocks with it (the password always works too).
async function lockPinOffer() {
  const t = $('#lockPinT'); if (!t) return; t.hidden = true;
  try { const st = await api('/auth/pin/status'); S.pin = st;
    if (st.set && !st.off && st.kind === 'full') { t.hidden = false; lockMode(true); } }
  catch { S.pin = null; }
}
function lockMode(byPin) {
  S.lockByPin = !!byPin; const b = $('#lockPw'), t = $('#lockPinT'); if (!b) return;
  b.value = ''; b.type = 'password'; b.inputMode = byPin ? 'numeric' : ''; b.maxLength = byPin ? 8 : 524288;
  b.autocomplete = byPin ? 'off' : 'current-password'; b.placeholder = byPin ? 'PIN' : 'Password';
  if (t) t.textContent = byPin ? 'Use my password' : 'Use my PIN';
}
// The next service names its campus when it is not the home one (Alexandria's 10:00 is not Pineville's 10:30).
function nextLine(n, city) { if (!n) return ''; const home = (city || 'Pineville').split(',')[0]; return ` · next: ${n.name}${n.site && n.site !== home ? ' in ' + n.site : ''}, ${n.day} ${fmtSvc(n.time)}`; }
function churchLine() { const c = S.church; return `${c?.name || 'Arise Church'} · ${(c?.city || 'Pineville').split(',')[0]}${nextLine(c?.next, c?.city)}`; }
function tickLock() { const d = new Date(); $('#lockTime').textContent = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); $('#lockDate').textContent = d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }); const h = $('#lock .lock__hint'); if (h) h.textContent = churchLine() + ($('#lock').classList.contains('idle') ? ' · press a key' : ''); }
$('#lockForm').onsubmit = async e => { e.preventDefault(); const pw = $('#lockPw').value; $('#lockPw').value = '';
  if (S.demo && !(S.demoOnly && window.AriseMock)) { $('#lock').hidden = true; return; }
  const pwBox = $('#lockPw');
  // Two-step users: the password alone is not an unlock. Ask for the six digits here (round 3: Microsoft Authenticator).
  if (S.lockPending) {
    try { await api('/auth/login/code', { method: 'POST', body: { pending: S.lockPending, code: pw } }); lockReset(); $('#lock').hidden = true; }
    catch (er) { if (/Sign in again|more than five|Three wrong/.test(er.message)) lockReset(); toast(er.message, 'bad'); pwBox.focus(); }
    return;
  }
  if (S.lockByPin) {
    try { const r = await api('/auth/pin', { method: 'POST', body: { user: S.user, pin: pw } });
      if (r && r.need_code) { S.lockByPin = false; S.lockPending = r.pending; pwBox.type = 'text'; pwBox.inputMode = 'numeric'; pwBox.maxLength = 7; pwBox.autocomplete = 'one-time-code'; pwBox.placeholder = '6 digits from Authenticator'; const t = $('#lockPinT'); if (t) t.hidden = true; pwBox.focus(); return; }
      lockReset(); $('#lock').hidden = true; }
    catch (er) { if (/switched off/.test(er.message)) { const t = $('#lockPinT'); if (t) t.hidden = true; lockMode(false); } toast(er.message, 'bad'); pwBox.focus(); }
    return;
  }
  try { const r = await api('/auth/login', { method: 'POST', body: { user: S.user, password: pw } });
    if (r && r.need_new_password) { showLogin({ newpw: true, user: r.user || S.user, old: pw, rules: r.rules }); return; }   // an admin's reset since they locked
    if (r && r.need_code) { S.lockPending = r.pending; pwBox.type = 'text'; pwBox.inputMode = 'numeric'; pwBox.autocomplete = 'one-time-code'; pwBox.placeholder = '6 digits from Authenticator'; pwBox.focus(); return; }
    $('#lock').hidden = true; } catch (er) { toast(er.message, 'bad'); } };
function lockReset() { S.lockPending = null; S.lockByPin = false; const b = $('#lockPw'); b.type = 'password'; b.inputMode = ''; b.maxLength = 524288; b.autocomplete = 'current-password'; b.placeholder = 'Password'; const t = $('#lockPinT'); if (t) t.textContent = 'Use my PIN'; }
{ const t = document.getElementById('lockPinT'); if (t) t.onclick = () => { lockMode(!S.lockByPin); $('#lockPw').focus(); }; }
async function signOut() { await api('/auth/logout', { method: 'POST' }).catch(() => {}); location.reload(); }
// The desktop's timers, so the sign-in screen can stop them all (it replaces the desktop).
function every(fn, ms) { const id = setInterval(fn, ms); (S.timers = S.timers || []).push(id); return id; }
function stopDesktop() { for (const id of S.timers || []) clearInterval(id); S.timers = []; ['demoTimer', 'actT', 'clockT', 'saverT', 'saverA'].forEach(k => { clearInterval(S[k]); S[k] = null; }); if (S.sse) { S.sse.close(); S.sse = null; } }
function showLogin(err) {
  stopDesktop();
  const remembered = '';   // round 5, 31: nobody is preselected; nothing shows who used it last
  try { localStorage.removeItem('arise.user'); } catch {}
  const codeStep = !!(err && err.code);
  if (err && (err.newpw || err.forgot || err.reset)) return loginStep(err);   // round 5: profiles block below
  document.body.innerHTML = `<div class="login"><div class="login__box">
    <div class="lock__avatar">${I.about.replace('<svg', '<svg width="44" height="44"').replace('#D6222D', '#fff')}</div><h1>ariseOS</h1>
    ${err?.setup ? `<p>No admin password has been set yet. On the server run:</p><pre class="log pre">sudo arisectl admin set-password</pre><p style="margin-top:12px">then reload this page.</p>`
    : codeStep ? `<p>Two-step sign-in is on for <b>${esc(err.user || remembered)}</b>. Open <b>Microsoft Authenticator</b> and type the six digits it shows for ariseOS.</p>
    <form id="lf" class="lock__form"><input id="lc" inputmode="numeric" pattern="[0-9 ]*" placeholder="6 digits" autocomplete="one-time-code" maxlength="7" style="width:160px;text-align:center;letter-spacing:.3em"><button type="submit" aria-label="Continue">→</button></form><button class="btn btn--ghost btn--xs" id="lback" style="margin-top:10px">Start over</button>`
    : `<p>${esc(err?.message && err.message !== 'Sign in' ? err.message : 'Arise Church · Pineville, LA')}</p>
    <form id="lf" class="lock__form"><input id="lu" value="${esc(remembered)}" placeholder="Name" autocomplete="username" style="width:110px"><input id="lp" type="password" placeholder="Password" autocomplete="current-password"><button type="submit" aria-label="Sign in">→</button></form><div><button class="btn btn--ghost btn--xs" id="lpin" type="button" style="margin-top:12px">Use my PIN</button> <button class="btn btn--ghost btn--xs" id="lforgot" style="margin-top:12px">Forgot your password?</button></div>`}
    ${S.demoOnly && window.AriseMock ? `<p class="login__preview">Preview: sign in as ${window.AriseMock.sampleNames().slice(0, 4).map(u => `<b>${esc(u.name)}</b> (${u.role})`).join(', ')} with any password, or as someone you added, with theirs.</p>` : ''}
    <div class="lock__hint" id="loginNext">Arise Church · Pineville</div><div class="lock__hint" style="margin-top:8px" id="loginRealm">arise-server</div></div></div>`;
  api('/public/sign-in').then(si => { const el = $('#loginRealm'); if (el && si.realm) el.textContent = `${si.host || 'arise-server'} · ${si.realm}`; }).catch(() => {});
  const lfg = $('#lforgot'); if (lfg) lfg.onclick = () => showLogin({ forgot: true, user: ($('#lu')?.value || remembered).trim() });
  api('/public/signage').then(sg => { const n = sg.next; const el = $('#loginNext'); if (el) el.textContent = `${sg.name || 'Arise Church'} · ${(sg.city || 'Pineville').split(',')[0]}${nextLine(n, sg.city)}`; }).catch(() => {});
  const f = $('#lf'); if (!f) return;
  const fail = msg => { let t = $('.login .toast'); if (!t) { t = document.createElement('div'); t.className = 'toast bad'; t.style.marginTop = '12px'; $('.login__box').appendChild(t); } t.textContent = msg; };
  if (codeStep) {
    $('#lc').focus(); $('#lback').onclick = () => showLogin(null);
    f.onsubmit = async e => { e.preventDefault(); const b = $('button', f); b.classList.add('busy');
      try { await api('/auth/login/code', { method: 'POST', body: { pending: err.pending, code: $('#lc').value } }); afterSignIn(); }
      catch (er) { if (/Sign in again|more than five|Three wrong/.test(er.message)) { showLogin({ message: er.message }); return; } fail(er.message); $('#lc').value = ''; $('#lc').focus(); }
      finally { b.classList.remove('busy'); } };
    return;
  }
  $('#lu').focus(); loginFaces();
  // Round 7, 160: an admin's PIN instead of the password, anywhere. The password always works.
  let byPin = false; const lpin = $('#lpin');
  if (lpin) lpin.onclick = () => { byPin = !byPin; const p = $('#lp'); p.value = ''; p.placeholder = byPin ? 'PIN' : 'Password'; p.inputMode = byPin ? 'numeric' : ''; p.maxLength = byPin ? 8 : 524288; p.autocomplete = byPin ? 'off' : 'current-password'; lpin.textContent = byPin ? 'Use my password' : 'Use my PIN'; ($('#lu').value ? p : $('#lu')).focus(); };
  f.onsubmit = async e => { e.preventDefault(); const b = $('button', f); b.classList.add('busy');
    try { const user = $('#lu').value;
      const pw = $('#lp').value;
      const r = byPin ? await api('/auth/pin', { method: 'POST', body: { user, pin: pw } })
        : await api('/auth/login', { method: 'POST', body: { user, password: pw } });
      if (r && r.pin === 'checklist') { location.href = '/checklist'; return; }   // a staff PIN opens the checklist only (162)
      if (r && r.need_new_password) { showLogin({ newpw: true, user: r.user || user, old: pw, rules: r.rules }); return; }
      if (r && r.need_code) { showLogin({ code: true, pending: r.pending, user: r.user || user }); return; }
      afterSignIn(); }
    catch (er) { fail(er.message); }
    finally { b.classList.remove('busy'); } };
}
function clock() { const d = new Date(); $('#barClock').textContent = d.toLocaleString('en-US', matchMedia('(max-width: 520px)').matches ? { hour: 'numeric', minute: '2-digit' } : { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); if (!$('#lock').hidden) tickLock(); }

/* ---------------- keyboard + kiosk + boot ---------------- */
document.addEventListener('keydown', e => {
  if (!$('#stage')) return;   // the sign-in screen has none of the desktop
  const cmd = e.metaKey || e.ctrlKey; const inField = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName) || e.target.closest('.xterm');
  if (e.key === 'Escape') { if (!$('#spot').hidden) { toggleSpot(false); return; } if (!$('#ql').hidden) { $('#ql').hidden = true; return; } if ($('#stage').classList.contains('mc')) { missionControl(false); return; } closeOverlays(); toggleNC(false); $('#switcher').hidden = true; return; }
  if (cmd && e.code === 'Space') { e.preventDefault(); toggleSpot(); return; }
  if (e.key === 'F3') { e.preventDefault(); missionControl(); return; }
  if (cmd && e.key === 'Tab') { e.preventDefault(); switcher(e.shiftKey ? -1 : 1); return; }
  if (inField) return;
  if (e.key === 'F4') { e.preventDefault(); toggleLaunchpad(); return; }
  if (e.key === 'F1' || (cmd && (e.key === '?' || (e.shiftKey && e.key === '/')))) { e.preventDefault(); openApp('help'); return; }
  if (cmd && e.key === '/') { e.preventDefault(); shortcutsSheet(); return; }
  const id = focusedApp();
  if (cmd && id && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key) && !isPhone()) { e.preventDefault(); snapKey(id, e.key); return; }
  // Lock first: ⌃⌘Q (Ctrl+Alt+Q on a Windows keyboard) must lock, not quit the window in front.
  if (cmd && (e.ctrlKey && e.metaKey || e.altKey) && e.key.toLowerCase() === 'q') { e.preventDefault(); lockScreen(); return; }
  if (cmd && (e.key === 'w' || e.key === 'q') && id) { e.preventDefault(); closeApp(id); }
  else if (cmd && e.key === 'm' && id) { e.preventDefault(); minApp(id); }
  else if (cmd && e.key === 'r' && id) { e.preventDefault(); rerender(id); }
  else if (cmd && e.key === 'i' && id === 'files') { e.preventDefault(); const el = $('#fMain .sel'); if (el) getInfo(el.dataset.n, el.dataset.dir === '1', (S.fs.path === '/' ? '' : S.fs.path) + '/' + el.dataset.n); }
  else if (cmd && e.shiftKey && e.key.toLowerCase() === 'n' && id === 'files') { e.preventDefault(); $('#fNew')?.click(); }
  else if (cmd && (e.ctrlKey || e.altKey) && e.key === 'q') { lockScreen(); }
});
$('#spotQ').addEventListener('input', () => { const q = $('#spotQ').value; $('#spotRes').innerHTML = spotResults(q); clearTimeout(S.spT); if (q.trim().length >= 2) S.spT = setTimeout(async () => { try { const r = await api(`/search?q=${encodeURIComponent(q.trim())}`); if ($('#spotQ').value === q) $('#spotRes').innerHTML = spotResults(q, r); bindSpot(); } catch {} }, 250); bindSpot(); });
function bindSpot() { const bs = $$('#spotRes button'); bs.forEach((b, i) => { b.onclick = () => spotGo(JSON.parse(b.dataset.s)); }); if (bs[0]) bs[0].classList.add('on'); }
$('#spotQ').addEventListener('keydown', e => { const bs = $$('#spotRes button'); let i = bs.findIndex(b => b.classList.contains('on')); if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); bs[i]?.classList.remove('on'); i = (i + (e.key === 'ArrowDown' ? 1 : -1) + bs.length) % bs.length; bs[i]?.classList.add('on'); bs[i]?.scrollIntoView({ block: 'nearest' }); } if (e.key === 'Enter' && bs[i]) bs[i].click(); });
$('#spot').onclick = e => { if (e.target.id === 'spot') toggleSpot(false); };
$('#qlClose').onclick = () => $('#ql').hidden = true;
$('#spotBtn').onclick = () => toggleSpot();
$('#ccBtn').onclick = e => { e.stopPropagation(); toggleCC(); };
$('#barClock').onclick = () => toggleNC();
$('#barAtt').onclick = () => openApp('overview');
$('#barLogo').onclick = e => { e.stopPropagation(); const b = $('#barLogo'); if (menuOpen === b) { closeMenu(); return; } openMenu(b, FLAME_MENU()); };
function saver(on) {
  const sv = $('#saver'); if (!sv) return;
  if (!on) { sv.hidden = true; clearInterval(S.saverT); return; }
  if (!sv.hidden) return;
  sv.hidden = false;
  const paint = () => { const d = new Date(); $('#saverTime').textContent = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); const c = S.church; const n = c?.next;
    $('#saverNext').textContent = n ? `${n.name} · ${n.site} · ${n.day} ${fmtSvc(n.time)} · in ${n.in_words}` : d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
    $('#saverVerse').innerHTML = c?.verse?.text ? `${esc(c.verse.text)}<cite>${esc(c.verse.ref)}</cite>` : ''; $('#saverName').textContent = (c?.name || 'Arise Church') + ' · ' + (c?.city || ''); };
  paint(); S.saverT = setInterval(paint, 30000); saverExtras();
  // a slow slideshow of the channel's thumbnails behind the clock
  api('/sermons?limit=12').then(r => { const th = (r.videos || []).map(v => v.thumbnail).filter(Boolean); if (!th.length) return; let i = 0; const art = $('#saverArt'); const step = () => { if (sv.hidden) return; art.style.backgroundImage = `url(${th[i % th.length]})`; i++; }; step(); S.saverA = setInterval(step, 20000); }).catch(() => {});
}
function kioskSetup() {
  const q = new URLSearchParams(location.search);
  if (q.has('signage')) { document.body.classList.add('kiosk', 'signage'); S.kiosk = true; S.signage = true; loadChurch().then(() => saver(true)); setInterval(() => loadChurch(), 10 * 60000); return; }
  if (!q.has('kiosk')) return;
  document.body.classList.add('kiosk'); S.kiosk = true;
  // Firefox's ariseOS new tab (web/newtab.html) asks the desktop tab to open an app: {open: id}; null = just come back.
  try { const bc = new BroadcastChannel('arise-kiosk'); bc.onmessage = ev => { const id = ev.data && ev.data.open; if (id && appOf(id)) openApp(id); }; S.kioskBC = bc; } catch {}
  let idle = 0; const reset = () => { idle = 0; document.body.classList.remove('idle'); if (!$('#saver').hidden) saver(false); };
  ['pointermove', 'keydown', 'pointerdown', 'wheel'].forEach(ev => document.addEventListener(ev, reset, { passive: true }));
  // 5 minutes idle: the screensaver (clock, next service, the verse, the channel's art); 10: the lock on top of it.
  every(() => { idle += 5; if (idle >= 5) document.body.classList.add('idle'); if (idle >= 300 && $('#lock').hidden) saver(true); if (idle >= 600 && $('#lock').hidden) lockScreen(true); }, 5000);
}
async function boot() {
  if (window.ARISE_FORCE_DEMO) setDemoOnly();
  clock(); every(clock, 15000);
  buildDock(); setAppMenus(null); kioskSetup(); applyTheme(); applyA11y(); applyDockHide();
  await kioskHandoff();   // round 6: the monitor's Firefox restarted into an admin's own profile
  try {
    const me = await api('/auth/me');
    if (me.error) { if (me.error.setup) return showLogin({ setup: true }); return showLogin(me.error); }
    S.authed = true; S.user = me.user || 'bradly'; S.role = me.role || 'admin'; S.me = me;
    await prefsPull();   // settings that follow the account (round 5, 11)
    applyTheme();
    if ('serviceWorker' in navigator && location.protocol !== 'file:' && !S.demoOnly) navigator.serviceWorker.register('/sw.js').catch(() => {});
    if (!S.kiosk && !me.demo) setTimeout(() => walkthrough(false), 1200);
    if (!S.kiosk) setTimeout(whatsNewToast, 2500);
    // After round 5: the OS is for the admins in the closet; staff and volunteers use their Macs.
    if (S.role !== 'admin' && (me.staff_access || 'none') === 'none') return onYourMac(me);
    if (isMember()) { document.body.classList.add('member'); buildDock(); setAppMenus(null); }
    if (me.demo) { S.demo = true; $('#demoBadge').hidden = false; }
  } catch (e) { if (S.kiosk && !S.demoOnly && e.status === 401 && await kioskAutologin()) return; if (!S.demoOnly) return showLogin(e); S.user = 'bradly'; }
  if (!isMember()) startStats();
  await loadChurch();
  await Promise.all([buildWidgets(), isMember() ? Promise.resolve() : buildIcons()]);
  buildDeskIcons(); notifyStart(); setupMaybe(); serviceWatch();
  greet();
  every(loadChurch, 15 * 60000); every(() => loadWeather(true), 30 * 60000);
  every(buildWidgets, 60000);
  const first = (location.hash || '').replace('#', '').split('/')[0];
  if (first && appOf(first)) openApp(first); else if (!isPhone()) openApp('files');
  window.addEventListener('hashchange', () => { const id = (location.hash || '').replace('#', ''); if (appOf(id) && !S.wins[id]) openApp(id); });
}
/* ---- macs (round 6) ----
   The church Macs (docs/MACS.md): the server is the church's own Active Directory (Samba).
   Only a Mac enrolled with the one Terminal line is a church Mac; the helper on it makes
   every server user's account, and an existing local account waits for an admin's choice:
   Convert, Link or Leave alone. Admins only. */
I.macs = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 4h18v12H3zm2 2v8h14V6zM9 18h6l1 2H8z"/></svg>';
APPS.splice(APPS.findIndex(a => a.id === 'shares'), 0, { id: 'macs', n: '32', name: 'Macs', what: 'The church Macs: accounts, the helper, enrol', w: 1040, h: 680 });
const MAC_KIND = { add_account: 'Make account', remove_profile: 'Remove profile (checked)', convert_local: 'Convert local account', link_local: 'Link local account', unconvert: 'Undo a conversion',
  login_window: 'Login window', ariseadmin: 'Hidden admin password', filevault: 'FileVault', printers: 'Printers', bookmarks: 'Church bookmarks', certificate: 'Church certificate',
  updates: 'Security updates', tailscale: 'Tailscale', nextcloud: 'Nextcloud (the files)', retire: 'Retire',
  welcome: 'Welcome page at first sign-in', mac_settings: 'Guest User on, App Store asks an admin', apps: 'The church apps', dnsfilter: 'DNS filter (malware, adult)', notice: 'A notice' };
const macState = (s, watch, kind) => watch && s === 'queued' && kind !== 'notice' ? '<span class="macs-st macs-st--wait">would do</span>'
  : `<span class="macs-st macs-st--${({ done: 'ok', queued: 'wait', sent: 'wait', failed: 'bad', refused: 'bad', skipped: 'dim', cancelled: 'dim' })[s] || 'dim'}">${esc(s)}</span>`;
// Round 7, 4: the helper starts in watch mode. One switch for the whole box; password again, audited.
const macWatchBar = (watch, n) => watch
  ? `<div class="macs-watch" id="macWatch"><div><b>Watch mode.</b> The helper on each Mac checks in and reports; the server plans ${n ? `<b>${n}</b> task${n === 1 ? '' : 's'}` : 'its tasks'} and sends none of them (notices aside). Read what each Mac would do, then switch it on.</div><button class="btn btn--sm" id="macLive">Switch on…</button></div>`
  : `<p class="note" style="margin:0 0 10px">The helper is on: tasks go out at each Mac's next check-in. <button class="btn btn--ghost btn--xs" id="macToWatch">Back to watch mode</button></p>`;
function macSwitch(on) {
  confirmType(on ? 'Switch the Mac helper on' : 'Back to watch mode', on ? 'on' : 'watch', on
    ? 'Every task the Macs page lists as <b>would do</b> goes out at each Mac\'s next check-in: the accounts, the default links (a server user is made for a local account that matches nobody), the apps, the DNS filter, the Guest User, the welcome page.'
    : 'The helpers keep checking in and the server keeps planning, but nothing more goes out until you switch on again.', async () => {
    const r = await withReauth(() => api('/macs/live', { method: 'POST', body: { on } })); if (r.ok === false) throw new Error(r.err);
    toast(on ? 'Switched on: the Macs get their tasks at the next check-in' : 'Watch mode: nothing goes out'); rerender('macs'); });
}
function macEnrol() {
  modal(`<h2>Enrol a church Mac</h2><p class="note" style="margin-bottom:12px">Only for a Mac the church owns. A personal Mac is never enrolled and the server never touches it. The line works once, for an hour.</p>
    <div class="field"><label>A new name (optional)</label><input id="meName" placeholder="leave empty: the Mac keeps its own name" maxlength="15" autocomplete="off"></div>
    <div id="meOut"></div><div class="acts"><button class="btn btn--ghost" data-close>Close</button><button class="btn" id="meGo">Make the line</button></div>`, m => {
    $('#meGo', m).onclick = async e => {
      const r = await act(e.target, () => api('/macs/enrol-token', { method: 'POST', body: { name: $('#meName', m).value.trim() } }));
      if (!r || r.ok === false) return;
      $('#meOut', m).innerHTML = `<div class="kicker" style="margin-top:12px">On the Mac: open Terminal, paste, press Return</div><pre class="macs-line" id="meLine">${esc(r.command)}</pre>
        <div class="row" style="gap:8px;margin-top:8px"><button class="btn btn--sm" id="meCopy">Copy</button><span class="note">Good until ${new Date(Date.now() + (r.expires_in || 3600) * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}. It asks for the Mac's password, then the domain administrator's.${r.demo ? ' (sample: the token is not real)' : ''}</span></div>`;
      $('#meCopy', m).onclick = ev => copyText(r.command, ev.target);
    };
    $('#meName', m).focus();
  });
}
V.macs = async () => {
  if (S.macSel) return macDetailHtml(await api('/macs/' + encodeURIComponent(S.macSel)));
  const r = await api('/macs'); const ms = r.macs || [];
  const row = x => `<tr data-mac="${esc(x.id)}" class="macs-row ${x.status !== 'active' ? 'dim' : ''}"><td><b>${esc(x.name)}</b><br><small class="muted">${esc(x.model || '')}</small></td><td>${esc(x.macos || '')}</td>
    <td>${x.mobile} server${x.local ? ` · <b>${x.local} local</b>` : ''}</td><td>${esc(x.filevault || 'not yet')}</td><td>${esc(x.tailscale || 'not yet')}</td>
    <td>${x.status === 'cut_off' ? '<span class="macs-st macs-st--bad">cut off</span>' : x.status === 'retired' ? '<span class="macs-st macs-st--dim">retired</span>' : x.online ? '<span class="macs-st macs-st--ok">online</span>' : esc(ago(x.last_checkin))}</td>
    <td>${x.pending ? `${x.pending} ${r.watch ? 'would run' : 'waiting'}` : ''}${x.failed ? ` <span class="macs-st macs-st--bad">${x.failed} failed</span>` : ''}${(x.disk_used || 0) >= 90 ? ` <span class="macs-st macs-st--bad">disk ${x.disk_used}%</span>` : ''}</td></tr>`;
  return `<div class="fade"><div class="row row--between" style="margin-bottom:12px"><div><div class="kicker">The church Macs</div><h2 style="margin:0">${ms.length} Macs · ${ms.filter(x => x.online).length} online${r.demo ? ' · sample' : ''}</h2>
      <p class="note" style="margin:6px 0 0">The server is the church's own Active Directory: no Microsoft licence. Every server user gets an account on every church Mac; a local account already there is linked to its server user; a disabled account comes off once the server has all its files. ${esc(r.note || '')}</p></div>
      <button class="btn" id="macEnrol">Enrol a Mac</button></div>
    ${macWatchBar(r.watch, r.would)}
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Mac</th><th>macOS</th><th>Accounts</th><th>FileVault</th><th>Tailscale</th><th>Seen</th><th>Tasks</th></tr></thead><tbody>${ms.map(row).join('') || '<tr><td colspan="7" class="muted">No church Macs yet. Enrol a Mac.</td></tr>'}</tbody></table></div>
    <p class="note" style="margin-top:12px">Never given an account on the Macs: ${(r.exclude || []).map(esc).join(', ')}. Add names to <code>[macs] exclude</code> in arise.toml.</p></div>`;
};
function macDetailHtml(d) {
  if (d.ok === false) { S.macSel = null; return `<p class="note">${esc(d.err)}</p>`; }
  S.macName = d.name;
  const live = d.status === 'active';
  const acc = a => `<tr><td><b>${esc(a.user)}</b>${a.realname ? `<br><small class="muted">${esc(a.realname)}</small>` : ''}</td><td>${a.kind === 'mobile' ? 'server account' : '<b>local</b>'}</td><td>${a.admin ? 'admin' : 'standard'}</td><td>${a.signed_in ? 'signed in' : ''}</td>
    <td>${a.kind === 'local' ? esc(a.state || '') : ''}</td><td class="macs-acts">${a.kind === 'local' && live ? (a.choice
      ? (a.choice.action === 'convert' ? `<button class="btn btn--ghost btn--xs" data-mlocal="undo" data-l="${esc(a.user)}">Undo</button>` : `<button class="btn btn--ghost btn--xs" data-mchoose="${esc(a.user)}">Change</button>`)
      : `<button class="btn btn--xs" data-mchoose="${esc(a.user)}">Choose…</button>`) : ''}</td></tr>`;
  const tk = t => `<tr><td class="mono">${esc(t.id)}</td><td>${esc(MAC_KIND[t.kind] || t.kind)}${t.args?.user ? ` · ${esc(t.args.user)}` : ''}${t.args?.local ? ` (${esc(t.args.local)})` : ''}${t.kind === 'notice' && t.args?.title ? ` · ${esc(t.args.title)}` : ''}</td><td>${macState(t.state, d.watch, t.kind)}</td><td>${esc(t.by || '')}</td><td>${esc(ago(t.finished || t.made))}</td><td><small>${esc(t.detail || '')}</small></td></tr>`;
  const temps = (d.temp_waiting || []).map(u => `<div class="macs-temp"><span><b>${esc(u)}</b> was made on the server for a local account here: their temporary password is waiting to be shown once.</span><button class="btn btn--sm" data-mtemp="${esc(u)}">Show it once</button></div>`).join('');
  return `<div class="fade"><button class="btn btn--ghost btn--sm" id="macBack">‹ All Macs</button>
    <div class="row row--between" style="margin:10px 0 12px"><div><div class="kicker">${esc(d.model || 'Mac')} · ${esc(d.serial || '')}</div><h2 style="margin:0">${esc(d.name)} ${d.online ? '<span class="macs-st macs-st--ok">online</span>' : `<span class="macs-st macs-st--dim">seen ${esc(ago(d.last_checkin))}</span>`}${live ? '' : ` <span class="macs-st macs-st--bad">${esc(d.status)}</span>`}</h2>
      <p class="note" style="margin:6px 0 0">${esc(d.macos || '')} · enrolled ${esc(ago(d.enrolled))} by ${esc(d.enrolled_by || '?')} · helper ${esc(d.helper || '')} · FileVault ${esc(d.filevault || 'not yet')} · Tailscale ${esc(d.tailscale || 'not yet')}${d.disk_used != null ? ` · disk ${esc(d.disk_used)}% full` : ''}</p>${(d.disk_used || 0) >= 90 ? `<p class="note" style="margin:6px 0 0;color:var(--warn)">The disk is ${esc(d.disk_used)}% full: the person signed in was told, and so were you.</p>` : ''}${d.full_disk_access === 'no' ? `<p class="note" style="margin:6px 0 0;color:var(--warn)">The helper has no Full Disk Access, so it cannot check anyone's Desktop or Documents: no profile is removed from this Mac until it does. On the Mac: System Settings > Privacy &amp; Security > Full Disk Access > + > /usr/local/arise/helper/arise-mac-helper (and /bin/bash).</p>` : ''}</div></div>
    ${live ? `<div class="row macs-bar"><button class="btn btn--ghost btn--sm" data-mtask="ariseadmin">Rotate admin password</button><button class="btn btn--ghost btn--sm" data-mshow="ariseadmin"${d.has_secret?.ariseadmin ? '' : ' disabled'}>Show admin password</button><button class="btn btn--ghost btn--sm" data-mshow="filevault"${d.has_secret?.filevault ? '' : ' disabled'}>Show FileVault key</button>
      <button class="btn btn--ghost btn--sm" data-mtask="printers">Printers again</button><button class="btn btn--ghost btn--sm" data-mtask="bookmarks">Bookmarks again</button><button class="btn btn--ghost btn--sm" data-mtask="updates">Security updates tonight</button><button class="btn btn--ghost btn--sm" data-mtask="tailscale">Tailscale</button>
      <button class="btn btn--ghost btn--sm" data-mtask="apps">Apps again</button><button class="btn btn--ghost btn--sm" data-mtask="dnsfilter">DNS filter on</button><button class="btn btn--ghost btn--sm" data-mtask="dnsfilter" data-mmode="off">DNS filter off</button><button class="btn btn--ghost btn--sm" data-mtask="welcome">Welcome page again</button>
      <label class="chk macs-media"><input type="checkbox" id="macMedia"${d.media ? ' checked' : ''}> The media Mac (gets Proclaim)</label>
      <span style="flex:1"></span><button class="btn btn--ghost btn--sm" id="macRetire">Retire…</button><button class="btn btn--danger btn--sm" id="macCut">Cut off…</button></div>` : ''}
    ${d.watch ? `<div class="macs-watch"><div><b>Watch mode: nothing here has run.</b> ${(d.would || []).length ? (d.would || []).map(esc).join('; ') + '. ' : ''}Every task below marked <b>would do</b> goes out once you press Switch on in the list of Macs.</div></div>` : ''}
    ${temps}
    <h3 class="macs-h">Accounts on this Mac</h3>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Account</th><th>Kind</th><th>Rights</th><th></th><th>Your choice</th><th></th></tr></thead><tbody>${(d.accounts || []).map(acc).join('') || '<tr><td colspan="6" class="muted">The helper has not reported yet.</td></tr>'}</tbody></table></div>
    <p class="note" style="margin-top:8px">A local account is <b>linked</b> to its server user by default (round 7): it stays as it is, with its own password, and its files sync as that user. One that matches nobody gets a new first.last server user first. You can still choose per account: <b>Convert</b> (it becomes the server user, files kept, can be undone) or <b>Leave alone</b>.</p>
    <h3 class="macs-h">Tasks</h3>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>#</th><th>What</th><th>State</th><th>By</th><th>When</th><th>Result</th></tr></thead><tbody>${(d.tasks || []).map(tk).join('') || '<tr><td colspan="6" class="muted">None yet.</td></tr>'}</tbody></table></div></div>`;
}
function macChoose(d, a) {
  modal(`<h2>${esc(a.user)} on ${esc(d.name)}</h2><p class="note" style="margin-bottom:12px">${esc(a.realname || '')}${a.admin ? ' · an admin on this Mac' : ''}${a.signed_in ? ' · <b>signed in now</b>: Convert waits until they sign out' : ''}</p>
    <div class="macs-pick"><label class="chk"><input type="radio" name="mcA" value="convert" checked> <b>Convert</b>: becomes the server user. Files stay; admin rights carry over only if it had them. A rollback record is kept on the Mac.</label>
      <label class="chk"><input type="radio" name="mcA" value="link"> <b>Link</b>: stays as it is, and signs in to the server's files as the server user.</label>
      <label class="chk"><input type="radio" name="mcA" value="leave"> <b>Leave alone</b>: nothing happens to it.</label></div>
    <div class="field" id="mcUserF" style="margin-top:12px"><label>The server user</label><input id="mcUser" list="mcUsers" value="${esc(a.suggest || '')}" placeholder="first.last" autocomplete="off"><datalist id="mcUsers"></datalist>
      <small class="note" id="mcNew"></small><input id="mcDisp" placeholder="Their name, for a new user" value="${esc(a.realname || '')}" style="margin-top:6px;display:none"></div>
    <div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="mcGo">Do it</button></div>`, async m => {
    let names = [];
    try { names = ((await api('/directory/users')).users || []).map(u => u.name); } catch { }
    $('#mcUsers', m).innerHTML = names.map(n => `<option value="${esc(n)}">`).join('');
    const sync = () => { const act_ = $('input[name=mcA]:checked', m).value, u = $('#mcUser', m).value.trim().toLowerCase(), isNew = act_ !== 'leave' && u && !names.includes(u);
      $('#mcUserF', m).style.display = act_ === 'leave' ? 'none' : ''; $('#mcDisp', m).style.display = isNew ? '' : 'none';
      $('#mcNew', m).textContent = isNew ? `${u} is not on the server yet: it is made first, with a temporary password you will see once.` : ''; };
    $$('input[name=mcA]', m).forEach(i => i.onchange = sync); $('#mcUser', m).oninput = sync; sync();
    $('#mcGo', m).onclick = async e => {
      const body = { local: a.user, action: $('input[name=mcA]:checked', m).value, user: $('#mcUser', m).value.trim().toLowerCase(), display: $('#mcDisp', m).value.trim() };
      const r = await act(e.target, () => api(`/macs/${encodeURIComponent(d.id)}/local`, { method: 'POST', body }), body.action === 'leave' ? 'Left alone' : body.action === 'convert' ? 'Queued: the Mac converts it at its next check-in' : 'Queued: linked at the Mac\'s next check-in');
      if (!r || r.ok === false) return;
      m.close(); rerender('macs');
      if (r.made) macShowSecret(`${r.made.user} is on the server now`, 'Their temporary password. They choose their own at the first sign-in. It is shown once.', r.made.temporary_password);
    };
  });
}
function macShowSecret(title, text, value) {
  modal(`<h2>${esc(title)}</h2><p class="note" style="margin-bottom:10px">${text}</p><pre class="macs-line macs-secret">${esc(value)}</pre>
    <div class="acts"><button class="btn btn--ghost" id="msCopy">Copy</button><button class="btn" data-close>Done</button></div>`, m => { $('#msCopy', m).onclick = e => copyText(value, e.target); });
}
V.macs.after = root => {
  const e = $('#macEnrol', root); if (e) e.onclick = macEnrol;
  const lv = $('#macLive', root); if (lv) lv.onclick = () => macSwitch(true);
  const tw = $('#macToWatch', root); if (tw) tw.onclick = () => macSwitch(false);
  $$('.macs-row', root).forEach(tr => tr.onclick = () => { S.macSel = tr.dataset.mac; rerender('macs'); });
  const back = $('#macBack', root); if (!back) return;
  back.onclick = () => { S.macSel = null; rerender('macs'); };
  const id = S.macSel, get = () => api('/macs/' + encodeURIComponent(id));
  $$('[data-mtask]', root).forEach(b => b.onclick = () => act(b, () => api(`/macs/${encodeURIComponent(id)}/task`, { method: 'POST', body: { kind: b.dataset.mtask, ...(b.dataset.mmode ? { mode: b.dataset.mmode } : {}) } }), 'Queued for the Mac\'s next check-in').then(() => rerender('macs')));
  const md = $('#macMedia', root); if (md) md.onchange = () => act(md, () => api(`/macs/${encodeURIComponent(id)}/media`, { method: 'POST', body: { on: md.checked } }), md.checked ? 'The media Mac: Proclaim is queued for it' : 'Not the media Mac').then(() => rerender('macs'));
  $$('[data-mtemp]', root).forEach(b => b.onclick = async () => {
    try { const r = await withReauth(() => api(`/macs/${encodeURIComponent(id)}/temp-password`, { method: 'POST', body: { user: b.dataset.mtemp } })); if (r.ok === false) throw new Error(r.err);
      macShowSecret(`${r.user}'s temporary password`, 'Shown once, and gone from the server now. They choose their own at the first sign-in.', r.temporary_password); rerender('macs'); }
    catch (er) { if (er.message !== 'cancelled') toast(er.message, 'bad'); }
  });
  $$('[data-mchoose]', root).forEach(b => b.onclick = async () => { const d = await get(); const a = (d.accounts || []).find(x => x.user === b.dataset.mchoose); if (a) macChoose(d, a); });
  $$('[data-mlocal]', root).forEach(b => b.onclick = () => act(b, () => api(`/macs/${encodeURIComponent(id)}/local`, { method: 'POST', body: { local: b.dataset.l, action: 'undo' } }), 'Queued: the conversion is undone at the next check-in').then(() => rerender('macs')));
  $$('[data-mshow]', root).forEach(b => b.onclick = async () => {
    try { const r = await withReauth(() => api(`/macs/${encodeURIComponent(id)}/reveal`, { method: 'POST', body: { kind: b.dataset.mshow } })); if (r.ok === false) throw new Error(r.err);
      macShowSecret(b.dataset.mshow === 'filevault' ? 'FileVault recovery key' : 'The hidden admin (ariseadmin)', `Seen by you now, and written in the audit log.${r.demo ? ' (sample value)' : ''}`, r.value + ((r.previous || []).length ? '\n\nEarlier, newest first (if the one above does not work):\n' + r.previous.map(x => `${x.value}  (${x.at || '?'})`).join('\n') : '')); }
    catch (er) { if (er.message !== 'cancelled') toast(er.message, 'bad'); }
  });
  const nm = S.macName || '';
  const rt = $('#macRetire', root); if (rt) rt.onclick = () => confirmType(`Retire ${nm}`, nm, 'Refused until every local account has your choice and every server account\'s files are on the server. Then the Mac leaves the domain and the helper removes itself. Erasing it is yours to do afterwards.', async () => {
    const r = await withReauth(() => api(`/macs/${encodeURIComponent(id)}/retire`, { method: 'POST', body: { confirm: nm } })); if (r.ok === false) throw new Error(r.err); toast(r.next || 'Retiring'); rerender('macs'); });
  const ct = $('#macCut', root); if (ct) ct.onclick = () => confirmType(`Cut off ${nm}`, nm, 'For a lost or stolen Mac. Its key stops working at once, its waiting tasks are cancelled and its computer account is disabled. Nothing on the Mac is erased from here.', async () => {
    const r = await withReauth(() => api(`/macs/${encodeURIComponent(id)}/cutoff`, { method: 'POST', body: { confirm: nm } })); if (r.ok === false) throw new Error(r.err);
    modal(`<h2>${esc(nm)} is cut off</h2><p class="note">Also, by hand:</p><ul>${(r.also || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul><div class="acts"><button class="btn" data-close>Done</button></div>`); rerender('macs'); });
};
/* ---- end macs ---- */

boot();
// A small console handle: `arise.openApp('files')` from the browser devtools, Playwright, or the kiosk.
/* ---------------- Offboarding in Directory, the audit log in Security (round 2, 23 and 24) ---------------- */
// Added as wrappers so the Directory and Security views stay as they are and these parts stand on their own.
{
  const dirAfter = V.directory.after;
  V.directory.after = root => { dirAfter(root); leavingWire(); };
  async function leavingWire() {
    let st; try { st = await api('/directory/leaving'); } catch { return; }
    const open = new Map((st.entries || []).filter(e => !e.done).map(e => [e.name, e]));
    const names = $$('#uTable tbody tr [data-tog]').map(b => b.dataset.tog);
    $$('#uTable tbody tr').forEach(tr => {
      const tog = $('[data-tog]', tr); if (!tog) return; const name = tog.dataset.tog; const acts = tog.parentElement; const e = open.get(name);
      if (e) {
        const cell = $('td b', tr); if (cell && !$('.pill.leave', tr)) cell.insertAdjacentHTML('afterend', ` <span class="pill warn leave" title="Files go to ${esc(e.move_to)}">leaving ${esc(e.disable_on)}</span>`);
        const c = document.createElement('button'); c.className = 'btn btn--ghost btn--xs'; c.textContent = 'Not leaving'; c.onclick = async () => { const r = await act(c, () => api(`/directory/users/${encodeURIComponent(name)}/leaving`, { method: 'DELETE' }), `${name} is staying`); if (r && r.ok !== false) rerender('directory'); }; acts.prepend(c);
      } else {
        const b = document.createElement('button'); b.className = 'btn btn--ghost btn--xs'; b.textContent = 'Leaving…'; b.onclick = () => leavingModal(name, names.filter(n => n !== name), st.grace_days || 30); acts.prepend(b);
      }
    });
  }
  function leavingModal(name, others, days) {
    const on = new Date(Date.now() + days * 864e5).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
    modal(`<h2>${esc(name)} is leaving</h2>
      <p class="note" style="margin-bottom:12px">Nothing changes for ${days} days, so they can still finish up. On <b>${esc(on)}</b> their sign-in is turned off and everything in their home folder moves to the person you pick, in a folder called “From ${esc(name)}”. The account itself stays until you delete it yourself.</p>
      <div class="field"><label>Who takes their files</label><select id="lvTo">${others.map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join('')}</select></div>
      <div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="lvGo">Mark as leaving</button></div>`, m => {
      $('#lvGo', m).onclick = async e => { const r = await act(e.target, () => api(`/directory/users/${encodeURIComponent(name)}/leaving`, { method: 'POST', body: { move_to: $('#lvTo', m).value, days } }), `${name}: sign-in off on ${on}`); if (r && r.ok !== false) { m.close(); rerender('directory'); } };
    });
  }
  const secView = V.security, secAfter = V.security.after;
  V.security = async () => {
    const html = await secView();
    let a = { events: [] }; try { a = await api('/audit?limit=60'); } catch {}
    return html.replace(/<\/div>\s*$/, '') + `<div class="panel panel--flat" style="margin-top:14px"><div class="panel__hd"><h3>Audit log</h3><span class="sub">who did what · kept forever · nothing here deletes it</span></div>
      <div class="toolbar"><input class="search" id="auQ" placeholder="Find: a name, an action, a file"><label class="row" style="gap:6px;font-size:13px"><input type="checkbox" id="auFail"> failed only</label></div>
      <div class="tbl-wrap"><table class="tbl" id="auT"><thead><tr><th>When</th><th>Who</th><th>What</th><th>On</th><th></th></tr></thead><tbody>${auditRows(a.events)}</tbody></table></div></div></div></div>`;
  };
  V.security.after = root => {
    secAfter && secAfter(root);
    const q = $('#auQ', root), f = $('#auFail', root); if (!q) return; let t;
    const go = () => { clearTimeout(t); t = setTimeout(async () => { try { const a = await api(`/audit?limit=200&q=${encodeURIComponent(q.value)}&failed=${f.checked}`); $('#auT tbody', root).innerHTML = auditRows(a.events); } catch (e) { toast(e.message, 'bad'); } }, 250); };
    q.oninput = go; f.onchange = go;
  };
  function auditRows(ev) {
    return (ev || []).map(e => `<tr><td class="dim">${fmtT(e.t)}</td><td><b>${esc(e.who || '?')}</b></td><td class="mono" style="font-size:12px">${esc(e.action || '')}${e.detail ? `<br><span class="dim">${esc(e.detail)}</span>` : ''}</td><td class="mono dim" style="font-size:12px">${esc(e.target || '')}</td><td>${e.ok === false ? '<span class="pill bad">failed</span>' : ''}</td></tr>`).join('') || '<tr><td colspan="5" class="dim">Nothing yet.</td></tr>';
  }
}


/* ---- profiles (round 5): the first-login password, "Forgot your password?", the profile,
   settings that follow the account, the day-one people list ---- */
// Settings that follow the account (round 5, 11): the same localStorage keys, kept on the server too.
const SYNC_RE = /^(theme|sounds|wallpaper|textsize|dock\.(hide|admin|member|staff)|a11y\.(contrast|motion|text)|widgets\.off|lp\.hidden)$/;
let _prefsT = null, _prefsLive = false;
const _prefSet = PREF.set;
PREF.set = (k, v) => { _prefSet(k, v); if (_prefsLive && SYNC_RE.test(k)) { clearTimeout(_prefsT); _prefsT = setTimeout(prefsPush, 800); } };
function localPrefs() { const out = {}; try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k && k.startsWith('arise.') && SYNC_RE.test(k.slice(6))) out[k.slice(6)] = localStorage.getItem(k); } } catch {} return out; }
async function prefsPush() { if (!S.authed) return; try { await api('/me/prefs', { method: 'PUT', body: { prefs: localPrefs() } }); } catch {} }   // offline: localStorage still has them
async function prefsPull() {
  try {
    const r = await api('/me/prefs'); const srv = r.prefs || {};
    if (!Object.keys(srv).length) { _prefsLive = true; if (Object.keys(localPrefs()).length) prefsPush(); return; }   // the first device sets them
    for (const [k, v] of Object.entries(srv)) if (SYNC_RE.test(k)) _prefSet(k, v);
    _prefsLive = true;
    try { applyA11y(); applyDockHide(); buildDock(); } catch {}
  } catch { _prefsLive = true; }
}

// The sign-in's extra steps: a temporary password replaced, a reset asked for, a reset finished.
function loginStep(st) {
  stopDesktop();
  const box = inner => { document.body.innerHTML = `<div class="login"><div class="login__box"><div class="lock__avatar">${I.about.replace('<svg', '<svg width="44" height="44"').replace('#D6222D', '#fff')}</div><h1>ariseOS</h1>${inner}<div class="lock__hint" id="loginRealm" style="margin-top:14px">arise-server</div></div></div>`;
    api('/public/sign-in').then(si => { const el = $('#loginRealm'); if (el && si.realm) el.textContent = `${si.host} · ${si.realm}`; }).catch(() => {}); };
  const fail = (msg, rules) => { let t = $('.login .toast'); if (!t) { t = document.createElement('div'); t.className = 'toast bad'; t.style.marginTop = '12px'; $('.login__box').insertBefore(t, $('#loginRealm')); } t.innerHTML = esc(msg) + ((rules || []).length ? `<ul class="login__rules">${rules.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : ''); };
  const rulesHtml = r => (r || []).length ? `<ul class="login__rules">${r.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : '';
  if (st.newpw) {
    box(`<p>Welcome, <b>${esc(st.user)}</b>. That was a temporary password: choose your own now. It is the one for your Mac and everything else at church.</p>${rulesHtml(st.rules)}
      <form id="lf" class="login__stack"><input id="ln1" type="password" placeholder="New password" autocomplete="new-password"><input id="ln2" type="password" placeholder="The same again" autocomplete="new-password"><button class="btn" type="submit">Set it and sign in</button></form>
      <button class="btn btn--ghost btn--xs" id="lback" style="margin-top:10px">Start over</button>`);
    $('#ln1').focus(); $('#lback').onclick = () => showLogin(null);
    $('#lf').onsubmit = async e => { e.preventDefault(); if ($('#ln1').value !== $('#ln2').value) return fail('The two passwords are not the same.');
      const b = $('#lf button'); b.classList.add('busy');
      try { const r = await api('/auth/login/new-password', { method: 'POST', body: { user: st.user, old: st.old, new: $('#ln1').value } });
        if (r.ok === false) return fail(r.err, r.rules);
        if (r.need_code) return showLogin({ code: true, pending: r.pending, user: r.user });
        afterSignIn(); }
      catch (er) { fail(er.message); } finally { b.classList.remove('busy'); } };
    return;
  }
  if (st.forgot) {
    box(`<p>Type your user name (first.last). If your profile has a personal email, a link to choose a new password goes there. It works for 30 minutes.</p>
      <form id="lf" class="lock__form"><input id="lfu" value="${esc(st.user || '')}" placeholder="first.last" autocomplete="username" autocapitalize="none" spellcheck="false" style="width:200px"><button type="submit" aria-label="Send">→</button></form><div id="lfOut"></div>
      <button class="btn btn--ghost btn--xs" id="lback" style="margin-top:10px">Back to sign-in</button>`);
    $('#lfu').focus(); $('#lback').onclick = () => showLogin(null);
    $('#lf').onsubmit = async e => { e.preventDefault(); const b = $('#lf button'); b.classList.add('busy');
      try { const r = await api('/auth/forgot', { method: 'POST', body: { user: $('#lfu').value.trim() } });
        $('#lfOut').innerHTML = `<p class="login__ok">${esc(r.message || '')}</p>` + (r.sample_link ? `<p class="login__preview">Sample: there is no mail here. The email would carry this link. <button class="btn btn--xs" id="lfOpen">Open it</button></p>` : '');
        const o = $('#lfOpen'); if (o) o.onclick = () => showLogin({ reset: r.sample_link.split('t=')[1] }); }
      catch (er) { fail(er.message); } finally { b.classList.remove('busy'); } };
    return;
  }
  if (st.reset) {   // on the box people open /reset; here for the preview, which has only this page
    box(`<p>Checking the link…</p>`);
    api('/auth/reset/check?t=' + encodeURIComponent(st.reset)).then(async c => {
      if (!c.ok) { box(`<p>${esc(c.err)}</p><button class="btn btn--ghost btn--xs" id="lback">Back to sign-in</button>`); $('#lback').onclick = () => showLogin(null); return; }
      const si = await api('/public/sign-in').catch(() => ({}));
      box(`<p>A new password for <b>${esc(c.name)}</b>.</p>${rulesHtml(si.rules)}<form id="lf" class="login__stack"><input id="ln1" type="password" placeholder="New password" autocomplete="new-password"><input id="ln2" type="password" placeholder="The same again" autocomplete="new-password"><button class="btn" type="submit">Set my password</button></form>`);
      $('#ln1').focus();
      $('#lf').onsubmit = async e => { e.preventDefault(); if ($('#ln1').value !== $('#ln2').value) return fail('The two passwords are not the same.');
        const r = await api('/auth/reset', { method: 'POST', body: { token: st.reset, new: $('#ln1').value } }).catch(er => ({ ok: false, err: er.message }));
        if (r.ok === false) return fail(r.err, r.rules);
        box(`<p class="login__ok">${esc(r.message)}</p><button class="btn btn--xs" id="lback">Sign in</button>`); $('#lback').onclick = () => showLogin(null); };
    });
  }
}

// My Profile (round 5, 9 to 11, 22): the details, and the last ten sign-ins.
async function profileSheet(user) {
  const self = !user || user === S.user;
  const [p, si] = await Promise.all([api(self ? '/me/profile' : `/directory/users/${encodeURIComponent(user)}/profile`), self ? api('/me/signins').catch(() => ({ signins: [] })) : Promise.resolve(null)]);
  if (p.ok === false) return toast(p.err, 'bad');
  const can = new Set(p.can_edit || []);
  const fld = (k, label, ph, hint) => `<div class="field"><label>${label}</label><input id="pf_${k}" value="${esc(p[k] || '')}" placeholder="${esc(ph)}" ${can.has(k) ? '' : 'disabled'} autocomplete="off">${hint ? `<span class="hint">${hint}</span>` : ''}</div>`;
  modal(`<h2>${esc(p.name)}</h2><p class="muted mono" style="font-size:12px">${esc(p.user)} · ${esc(p.mail)}</p>
    <div class="row" style="gap:10px;align-items:flex-start">${fld('title', 'Title', 'Pastor', can.has('title') ? 'Shown before the name: faces, Directory, mail, the greeting.' : 'Set by an administrator.')}
    <div class="field" style="flex:1"><label>Departments</label><input id="pf_departments" value="${esc((p.departments || []).join(', '))}" placeholder="Media, Worship" ${can.has('departments') ? '' : 'disabled'}></div></div>
    ${fld('personal_email', 'Personal email', 'name@gmail.com', 'Church mail forwards here, and "Forgot your password?" sends its link here. Staff do not use the dashboard, so an admin enters it for them.')}
    <div class="row" style="gap:10px;align-items:flex-start">${fld('mobile', 'Mobile phone', '318-555-0100', '')}${fld('birthday', 'Birthday', 'March 14', 'Month and day only, for the Monday weekly.')}</div>
    <p class="note">Staff and administrators see these details; members never do.</p>
    ${self ? `<div class="row" style="gap:10px;align-items:center;margin-top:12px"><div style="flex:1"><b>Sign-in PIN</b><div class="muted" id="pfPinSt" style="font-size:12px">…</div></div><button class="btn btn--ghost btn--xs" id="pfPin">Sign-in PIN</button></div>` : ''}
    ${si ? `<h3 style="margin:16px 0 6px">Your last sign-ins</h3><div class="tbl-wrap"><table class="tbl" id="pfSignins"><tbody>${(si.signins || []).map(x => `<tr><td class="dim">${fmtT(x.t)}</td><td>${esc(x.how || '')}</td><td class="mono dim" style="font-size:12px">${esc(x.ip || '')}</td><td>${x.ok === false ? '<span class="pill warn">not signed in</span>' : ''}</td></tr>`).join('') || '<tr><td class="dim">None recorded yet</td></tr>'}</tbody></table></div></div><p class="note">One that was not you? Change your password and tell Bradly.</p>` : ''}
    <div class="acts"><button class="btn btn--ghost" data-close>Close</button>${can.size ? '<button class="btn" id="pfSave">Save</button>' : ''}</div>`, m => {
    const pb = $('#pfPin', m);
    if (pb) { pb.onclick = () => { m.close(); pinSheet(); };
      api('/auth/pin/status').then(st => { const el = $('#pfPinSt', m); if (el) el.textContent = pinWords(st); }).catch(() => {}); }
    const sv = $('#pfSave', m); if (!sv) return;
    sv.onclick = async e => { const body = {};
      for (const k of ['title', 'personal_email', 'mobile', 'birthday']) if (can.has(k)) body[k] = $('#pf_' + k, m).value.trim();
      if (can.has('departments')) body.departments = $('#pf_departments', m).value.split(',').map(x => x.trim()).filter(Boolean);
      const r = await act(e.target, () => api(self ? '/me/profile' : `/directory/users/${encodeURIComponent(user)}/profile`, { method: 'PUT', body }), 'Profile saved');
      if (r && r.ok !== false) { m.close(); if (!self && S.wins?.directory) rerender('directory'); } };
  });
}

// The Directory's Profile buttons and the day-one people list (round 5, 8).
function profilesWire(root) {
  $$('[data-prof]', root).forEach(b => b.onclick = () => profileSheet(b.dataset.prof));
  const imp = $('#importPeople', root); if (!imp) return;
  imp.onclick = () => modal(`<h2>Import a people list</h2><p class="note">A CSV with these columns, the first line naming them: <code>first, last, title, departments, personal_email, mobile, birthday, role</code> (role: admin, staff or member; departments separated by ; ). Every account gets a temporary password; each person chooses their own at their first login, on their Mac or here.</p>
    <div class="field"><label>The list</label><textarea id="ipCsv" rows="7" spellcheck="false" placeholder="first,last,title,departments,personal_email,mobile,birthday,role&#10;Bryant,Sanders,Apostle,Leadership,,,,admin"></textarea><label class="btn btn--ghost btn--xs" for="ipFile" style="margin-top:8px">Choose a CSV file</label><input type="file" id="ipFile" accept=".csv,text/csv" hidden></div>
    <div id="ipOut"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn btn--ghost" id="ipCheck">Check</button><button class="btn" id="ipGo" disabled>Create the accounts</button></div>`, m => {
    const out = $('#ipOut', m), go = $('#ipGo', m);
    $('#ipFile', m).onchange = async e => { const f = e.target.files[0]; if (f) $('#ipCsv', m).value = await f.text(); };
    const paint = r => { out.innerHTML = `<div class="tbl-wrap" style="max-height:40vh"><div class="tbl-wrap"><table class="tbl" id="ipRows"><thead><tr><th>Line</th><th>User</th><th>Name</th><th>Groups</th><th>Result</th>${r.apply ? '<th>Temporary password</th>' : ''}</tr></thead><tbody>${r.rows.map(x => `<tr><td class="dim">${x.line}</td><td class="mono">${esc(x.user)}</td><td>${esc((x.title ? x.title + ' ' : '') + x.display)}</td><td>${(x.groups || []).map(g => `<span class="tag">${esc(g)}</span>`).join('')}</td><td>${x.ok ? `<span class="pill ok">${x.created ? 'created' : 'ready'}</span>` : `<span class="pill bad">refused</span> ${esc(x.err)}`}${(x.warnings || []).map(w => `<br><small class="muted">${esc(w)}</small>`).join('')}</td>${r.apply ? `<td class="mono">${esc(x.temporary_password || '')}</td>` : ''}</tr>`).join('')}</tbody></table></div></div>
      <p class="note">${r.apply ? `${r.created} created. The temporary passwords are shown here once and are not kept anywhere: print this window or copy them before you close it.` : `${r.rows.filter(x => x.ok).length} ready, ${r.refused} refused. Mail addresses are first.last@${esc(r.mail_domain)}.`}</p>${r.apply ? '<button class="btn btn--ghost btn--xs" id="ipPrint">Print</button>' : ''}`;
      const pr = $('#ipPrint', m); if (pr) pr.onclick = () => window.print(); };
    $('#ipCheck', m).onclick = async e => { const r = await act(e.target, () => api('/directory/import', { method: 'POST', body: { csv: $('#ipCsv', m).value, apply: false } })); if (!r) return; paint(r); go.disabled = !r.rows.some(x => x.ok); };
    go.onclick = async e => { const r = await act(e.target, () => api('/directory/import', { method: 'POST', body: { csv: $('#ipCsv', m).value, apply: true } }), 'Accounts created'); if (!r) return; paint(r); go.disabled = true; $('#ipCheck', m).disabled = true; m.addEventListener('close', () => rerender('directory'), { once: true }); };
  });
}
{ const _dirAfterR5 = V.directory.after; V.directory.after = root => { _dirAfterR5(root); profilesWire(root); }; }

/* ---- storage & folders (round 5) ----
   Storage: every home against its 50 GB quota (row 13). Backups: where tonight's backup goes,
   the Synology or Arise-Home over Tailscale (row 15). Shares: the Church, department, Pastors
   and Shared-with-me shares and their ACLs, written from arise.toml (rows 16-18, 36). */
{
  const stAfter = V.storage.after;
  V.storage.after = async root => {
    stAfter && stAfter(root);
    const q = await api('/storage/quotas').catch(() => null); if (!q || !root.isConnected) return;
    const box = document.createElement('div'); box.className = 'panel panel--flat'; box.id = 'stQuotas'; box.style.marginTop = '14px';
    box.innerHTML = `<div class="panel__hd"><h3>Home folders against the quota</h3><span class="sub">${q.quota ? fmtB(q.quota) + ' each' : 'no quota'} · enforced by ${esc(q.enforced_by)} · homes on the ${esc(q.homes_on)} (${esc(q.homes_path)})</span></div>
      ${(q.homes || []).map(h => `<div class="st__row"><div class="row row--between"><span><b>${esc(h.user)}</b>${h.full ? ' <span class="tag" style="background:var(--red);color:#fff">full</span>' : h.warn ? ' <span class="tag">nearly full</span>' : ''}</span><span class="mono" style="font-size:12px">${fmtB(h.used)}${h.quota ? ' of ' + fmtB(h.quota) + ' · ' + h.pct + '%' : ''}</span></div><div class="meter ${h.full ? '' : h.warn ? 'meter--warn' : 'meter--ok'}"><i style="width:${Math.min(100, h.pct || 0)}%"></i></div></div>`).join('') || '<div class="empty">No home folders yet</div>'}`;
    ($('.fade', root) || root).appendChild(box);
  };
  const bkAfter = V.backups.after;
  V.backups.after = async root => {
    bkAfter && bkAfter(root);
    const t = await api('/backups/targets').catch(() => null); if (!t || !root.isConnected) return;
    const box = document.createElement('div'); box.className = 'panel ' + (t.live ? 'panel--flat' : 'panel--bad'); box.id = 'bkTarget'; box.style.marginBottom = '14px';
    box.innerHTML = `<div class="panel__hd"><h3>Where tonight's backup goes</h3><span class="sub">${t.live ? esc(t.name) : 'nowhere yet'}</span></div>
      ${(t.targets || []).map(x => `<div class="row row--between" style="padding:6px 0;border-top:1px solid var(--line)"><span><span class="pill ${x.ready ? 'ok' : 'bad'}">${x.ready ? 'ready' : 'not ready'}</span> <b>${esc(x.name)}</b> <span class="mono muted" style="font-size:12px">${esc(x.repo || '')}</span></span><span class="muted" style="font-size:12px">${esc(x.why)}${t.live === x.id ? ' · <b>live</b>' : ''}</span></div>`).join('')}
      ${t.error ? `<p class="note" style="color:var(--redL);margin-top:8px">${esc(t.error)}</p>` : '<p class="note" style="margin-top:8px">The first ready one is used, in this order. When the Synology has its drives it takes over by itself (docs/BACKUPS.md).</p>'}`;
    const fade = $('.fade', root); if (fade) fade.insertBefore(box, fade.children[1] || null); else root.appendChild(box);
  };
  // Both the Directory's Shares tab and the Shares window draw with sharesAfter.
  const shAfter = sharesAfter;
  sharesAfter = (root, view) => {
    shAfter(root, view);
    const tb = $('#addShare', root)?.parentElement; if (!tb || $('#shFolders', root)) return;
    const b = document.createElement('button'); b.className = 'btn btn--ghost btn--sm'; b.id = 'shFolders'; b.textContent = 'Folders and permissions…'; tb.insertBefore(b, $('#addShare', root));
    b.onclick = async () => {
      const r = await api('/shares/folders', { method: 'POST', body: { dry_run: true } }).catch(e => ({ ok: false, err: e.message }));
      modal(`<h2>The Church, department and Pastors folders</h2><p class="muted">Written from arise.toml [storage]: the Church folder everyone writes; department folders all staff and the department's own account write, the department reads; the Pastors folder is the two pastors' alone; Shared with me. The ACLs on the server are the rule, so the Macs get the same answer as this dashboard.</p>
        ${r.ok === false ? `<p class="note" style="color:var(--redL)">${esc(r.err || 'failed')}</p>` : `<pre class="log pre" style="max-height:280px;overflow:auto">${esc(r.conf || '')}</pre><h3 style="margin-top:10px">ACLs</h3><pre class="log pre" style="max-height:160px;overflow:auto">${esc((r.acls || []).map(c => c.join(' ')).join('\n'))}</pre>`}
        <div class="acts"><button class="btn btn--ghost" data-close>Close</button><button class="btn" id="shApply">Apply</button></div>`, m => {
        $('#shApply', m).onclick = async e => { const x = await act(e.target, () => withReauth(() => api('/shares/folders', { method: 'POST', body: { dry_run: false } })), 'Folders and permissions applied (testparm passed)'); if (x && x.ok !== false) m.close(); };
      });
    };
  };
}

/* ---- desktop (round 5): the Desktop folder on the wallpaper, notifications, department checklists,
   the guided setup, the monitor's text size, the sign-in faces, and staff access (docs/ANSWERS.md round 5) ---- */

// Staff and volunteers use their Macs; the OS is the admins' (Bradly, after round 5). [web] staff_access = "none".
function onYourMac(me) {
  stopDesktop();
  const name = me.display || me.user || 'there';
  document.body.innerHTML = `<div class="login"><div class="login__box onmac">
    <div class="lock__avatar">${I.about.replace('<svg', '<svg width="44" height="44"').replace('#D6222D', '#fff')}</div><h1>Hello, ${esc(name)}</h1>
    <p>Your files are on your Mac. Everything you save there reaches the church's server by itself, and the nightly backup from there.</p>
    <p class="muted">The server's own desktop is for the administrators, in the closet. Anything you need from it: ask Bradly.</p>
    <p><a class="btn" href="/checklist">Your department's checklist</a></p>
    <div class="row" style="justify-content:center;margin-top:16px"><button class="btn" id="omOut">Sign out</button></div>
    <div class="lock__hint" style="margin-top:18px">Arise Church · Pineville</div></div></div>`;
  $('#omOut').onclick = () => signOut();
}

// The sign-in faces on the closet monitor only (round 4, 14 and 16), nobody preselected (round 5, 31).
async function loginFaces() {
  if (!S.kiosk) return;
  const r = await api('/public/faces').catch(() => ({ faces: [] }));
  const f = $('#lf'); if (!f || !(r.faces || []).length) return;
  const row = document.createElement('div'); row.className = 'faces'; row.setAttribute('role', 'listbox'); row.setAttribute('aria-label', 'Who is signing in');
  row.innerHTML = r.faces.map(x => `<button type="button" class="face" data-user="${esc(x.user)}" aria-label="${esc(x.name)}"><span class="face__i">${esc(x.initials)}</span><span class="face__n">${esc(x.name)}</span></button>`).join('');
  f.before(row);
  $$('.face', row).forEach(b => b.onclick = () => { $$('.face', row).forEach(x => x.classList.toggle('on', x === b)); $('#lu').value = b.dataset.user; $('#lp').value = ''; $('#lp').focus(); });
}

// ---- the Desktop folder on the wallpaper (round 5, 24) ----
const DESK = { loc: null, pos: {}, entries: [] };
const DESK_W = 96, DESK_H = 92;
async function buildDeskIcons() {
  let box = $('#deskIcons');
  if (!box) { box = document.createElement('div'); box.id = 'deskIcons'; box.className = 'deskicons'; box.setAttribute('aria-label', 'Your Desktop folder'); $('#stage').prepend(box); deskDropTarget(); }
  try {
    const d = await api('/desktop'); DESK.loc = { root: d.root, path: d.path }; DESK.pos = d.positions || {};
    const l = await api(`/files/list?root=${encodeURIComponent(d.root)}&path=${encodeURIComponent(d.path)}`);
    DESK.entries = l.error ? [] : (l.entries || []);
  } catch { DESK.entries = []; }
  paintDesk();
}
function deskAuto(i) {
  // Mac-like: from the top right, in columns, under the drive icons.
  const st = $('#stage'); const W = st.clientWidth, H = Math.max(300, st.clientHeight - 120);
  const top = 14 + ($$('#icons .ico').length * 102);
  const perCol = Math.max(1, Math.floor((H - top) / DESK_H));
  const col = Math.floor(i / perCol), row = i % perCol;
  return [Math.max(0, W - 22 - DESK_W - col * DESK_W), top + row * DESK_H];
}
// On a phone the stage is the scrolling column of widgets, so the Desktop's files sit in a row
// at its top instead of at their large-screen positions (where they landed on the widgets).
let deskRz = 0;
window.addEventListener('resize', () => { clearTimeout(deskRz); deskRz = setTimeout(paintDesk, 200); });
function paintDesk() {
  const box = $('#deskIcons'); if (!box) return;
  const host = isPhone() ? $('#widgets') : $('#stage');
  if (host && box.parentElement !== host) host.prepend(box);
  const p = DESK.loc ? DESK.loc.path : '';
  let auto = 0;
  box.innerHTML = DESK.entries.map(e => {
    const pos = DESK.pos[e.name] || deskAuto(auto++);
    const ico = e.dir ? ICONURL.folder : fileIcon(e.name);
    return `<button class="ico deskico" draggable="true" data-dn="${esc(e.name)}" data-dir="${e.dir ? 1 : 0}" style="left:${pos[0]}px;top:${pos[1]}px" title="${esc(e.name)}"><span class="dock__icon" style="background:${ico} center/70% no-repeat #000"></span><span>${esc(e.name)}</span></button>`;
  }).join('');
  $$('.deskico', box).forEach(b => {
    const name = b.dataset.dn, dir = b.dataset.dir === '1', path = (p === '/' ? '' : p) + '/' + name;
    const open = () => { if (dir) { S.fs = Object.assign(S.fs || { view: 'icon', hist: [], fwd: [], q: '' }, { root: DESK.loc.root, path, sel: null }); openApp('files'); } else if (isText(name)) editText(DESK.loc.root, path, name); else quickLook(DESK.loc.root, path, name); };
    b.onclick = e => { e.stopPropagation(); if (isPhone()) return open(); $$('.ico').forEach(x => x.classList.remove('sel')); b.classList.add('sel'); };
    b.ondblclick = open;
    b.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); open(); } };
    b.oncontextmenu = e => { e.preventDefault(); e.stopPropagation(); ctxMenu(e.clientX, e.clientY, [['Open', open], ['Get Info', () => getInfo(name, dir, path, DESK.loc.root)], null, ['Move to Trash…', () => deskTrash(path, name)]]); };
    b.ondragstart = e => { const r = b.getBoundingClientRect(); e.dataTransfer.setData('application/x-arise-desk', JSON.stringify({ name, dx: e.clientX - r.left, dy: e.clientY - r.top })); e.dataTransfer.effectAllowed = 'move'; };
  });
}
function deskTrash(path, name) {
  confirmType(`Move “${name}” to the Trash`, name, 'It sits in the Trash for 30 days, where Put Back brings it home.', async () => {
    const x = await api('/files/trash', { method: 'POST', body: { root: DESK.loc.root, path, confirm: name } });
    if (x.ok === false) throw new Error(x.err);
    toast(`${name} is in the Trash`); delete DESK.pos[name]; await api('/desktop/positions', { method: 'PUT', body: { positions: DESK.pos } }).catch(() => {}); buildDeskIcons();
  });
}
function deskDropTarget() {
  const st = $('#stage');
  st.addEventListener('dragover', e => { const t = e.dataTransfer.types; if (t.includes('application/x-arise-desk') || t.includes('application/x-arise-file')) { if (e.target === st || e.target.closest('#deskIcons')) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; } } });
  st.addEventListener('drop', async e => {
    const sr = st.getBoundingClientRect();
    const own = e.dataTransfer.getData('application/x-arise-desk');
    if (own) {   // an icon dragged on the wallpaper: remember where it was put
      e.preventDefault(); const d = JSON.parse(own);
      DESK.pos[d.name] = [Math.max(0, Math.round(e.clientX - sr.left - d.dx)), Math.max(0, Math.round(e.clientY - sr.top - d.dy))];
      paintDesk(); api('/desktop/positions', { method: 'PUT', body: { positions: DESK.pos } }).catch(() => {}); return;
    }
    const f = e.dataTransfer.getData('application/x-arise-file');
    if (f && DESK.loc) {   // a file dragged out of Finder: move it onto the Desktop
      e.preventDefault(); const d = JSON.parse(f);
      if (d.root !== DESK.loc.root) return toast('That file is in another place: copy it with Finder instead', 'warn');
      const r = await api('/files/move', { method: 'POST', body: { root: d.root, path: d.path, to: DESK.loc.path } }).catch(er => ({ ok: false, err: er.message }));
      if (r.ok === false) return toast(r.err, 'bad');
      if (!r.unchanged) { DESK.pos[d.name] = [Math.max(0, Math.round(e.clientX - sr.left - 44)), Math.max(0, Math.round(e.clientY - sr.top - 30))]; await api('/desktop/positions', { method: 'PUT', body: { positions: DESK.pos } }).catch(() => {}); toast(`${d.name} is on your Desktop`); }
      buildDeskIcons(); if (S.wins.files) rerender('files');
    }
  });
}
// Finder items can be dragged onto the wallpaper.
{
  const filesAfter = V.files.after;
  V.files.after = root => {
    filesAfter(root);
    const fs = S.fs || {}; if (!fs.root || String(fs.root).startsWith('@')) return;
    $$('#fMain [data-n]', root).forEach(el => {
      el.draggable = true;
      el.addEventListener('dragstart', e => { const n = el.dataset.n; e.dataTransfer.setData('application/x-arise-file', JSON.stringify({ root: fs.root, path: (fs.path === '/' ? '' : fs.path) + '/' + n, name: n })); e.dataTransfer.effectAllowed = 'move'; });
    });
    // Anything Finder changes in the Desktop folder shows on the wallpaper too.
    if (DESK.loc && fs.root === DESK.loc.root && (fs.path === DESK.loc.path)) buildDeskIcons();
  };
}

// ---- notifications (round 5, 28): the person's own feed in the notification centre ----
const NOTE_ICON = { calendar: 'calendar', shared: 'files', mail: 'mail', sunday: 'sunday', checklist: 'sunday', system: 'about' };
let notifySeen = 0;
async function notifyStart() { await notifyBadge(true); every(() => notifyBadge(false), 60000); }
async function notifyBadge(first) {
  let r; try { r = await api('/notifications?limit=20'); } catch { return; }
  S.notes = r; const clock = $('#barClock'); if (!clock) return;
  clock.dataset.unread = r.unread ? String(r.unread) : ''; clock.classList.toggle('has-unread', !!r.unread);
  const newest = (r.items || [])[0];
  if (!first && newest && !newest.read && Date.parse(newest.at) > notifySeen) { toast(newest.text); tone('done'); }
  if (newest) notifySeen = Math.max(notifySeen, Date.parse(newest.at) || 0);
}
{
  const ncBuild = buildNC;
  buildNC = async function () {
    await ncBuild();
    const body = $('#ncBody'); if (!body) return;
    const r = S.notes || await api('/notifications?limit=20').catch(() => ({ items: [] }));
    const items = (r.items || []).slice(0, 8);
    const box = document.createElement('div'); box.className = 'widget ncnotes'; box.id = 'ncNotes';
    box.innerHTML = `<div class="widget__kicker">Notifications${r.unread ? ` · ${r.unread} new` : ''}</div>${items.length ? `<div class="widget__rows">${items.map(n => `<button class="widget__row ${n.read ? '' : 'unread'}" data-nlink="${esc(n.link || '')}"><span>${esc(n.text)}</span><b>${esc(ago(n.at))}</b></button>`).join('')}</div>` : '<div class="widget__sub">Nothing new.</div>'}`;
    body.prepend(box);
    $$('[data-nlink]', box).forEach(b => b.onclick = () => { const l = b.dataset.nlink; toggleNC(false); const id = (l.split('#')[1] || '').split('/')[0]; if (id && appOf(id)) openApp(id); });
    if (r.unread) api('/notifications/read', { method: 'POST', body: {} }).then(x => { S.notes = Object.assign({}, S.notes, { unread: 0 }); const c = $('#barClock'); if (c) { c.dataset.unread = ''; c.classList.remove('has-unread'); } }).catch(() => {});
  };
}

// ---- department checklists in the Sunday app (round 5, 28 to 30) ----
{
  const sunView = V.sunday, sunAfter = V.sunday.after;
  V.sunday = async () => {
    const html = await sunView();
    if (isMember()) return html;   // staff tick from their Macs once Bradly decides how (after round 5)
    return html.replace(/<\/div>\s*$/, '') + `<div class="deptlists" id="deptLists"><div class="kicker">Department checklists</div><div class="empty">Loading…</div></div></div>`;
  };
  V.sunday.after = root => { sunAfter(root); deptLists(root); };
}
async function deptLists(root) {
  const box = $('#deptLists', root); if (!box) return;
  let r; try { r = await api('/checklists'); } catch (e) { box.innerHTML = `<div class="kicker">Department checklists</div><p class="note">${esc(e.message)}</p>`; return; }
  const lists = r.lists || [];
  box.innerHTML = `<div class="kicker">Department checklists</div><p class="note" style="margin:6px 0 12px">Each department's own list, ready before each service. A list moves on at 8 PM the night before; the finished round goes to its history. Staff tick theirs on their phones at <a href="/checklist" target="_blank" rel="noopener"><code>/checklist</code></a> (church Wi-Fi or Tailscale); a list opens at call time${S.church?.call_times ? ': ' + Object.entries(S.church.call_times).map(([k, v]) => `${esc(k)} ${esc(fmtSvc(v))}`).join(', ') : ''}.${r.demo ? ' Sample.' : ''}</p>
    <div class="deptgrid">${lists.map(l => `<div class="card dept" data-dept="${esc(l.dept)}"><div class="row row--between"><div><b>${esc(deptName(l.dept))}</b><div class="muted" style="font-size:12px">${l.round ? `for ${esc(l.round.service)} · ${esc(fmtDay(l.round.at))}` : 'no service ahead'} · ${l.done} of ${l.items.length}</div></div>${l.can_edit ? `<button class="btn btn--ghost btn--xs" data-dedit="${esc(l.dept)}">Edit</button>` : ''}</div>
      ${l.items.length ? l.items.map(i => `<label class="sun__item ${i.done ? 'done' : ''}"><input type="checkbox" data-dept-i="${i.i}" ${i.done ? 'checked' : ''} ${l.can_tick ? '' : 'disabled'}><div><span>${esc(i.text)}</span>${i.done ? `<small>${esc(i.by)} · ${esc(i.at.replace('T', ' '))}</small>` : ''}</div></label>`).join('') : `<p class="note">No items yet.${l.can_edit ? ' Edit to add them.' : ''}</p>`}
      <div class="muted" style="font-size:12px;margin-top:8px">Leader: ${esc(l.leader || 'none yet')} · nudge ${Object.entries(l.nudge || {}).map(([s, t]) => `${esc(s)} ${esc(fmtSvc(t))}`).join(', ')}</div>
      ${(l.history || []).length ? `<details style="margin-top:6px"><summary class="muted" style="font-size:12px">History</summary>${l.history.map(h => `<div class="widget__row"><span>${esc(h.round)}</span><b>${h.done} of ${h.total}</b></div>`).join('')}</details>` : ''}</div>`).join('')}</div>`;
  $$('.dept', box).forEach(card => {
    const dept = card.dataset.dept;
    $$('input[data-dept-i]', card).forEach(cb => cb.onchange = async () => { const x = await api(`/checklists/${encodeURIComponent(dept)}/tick`, { method: 'POST', body: { i: +cb.dataset.deptI } }).catch(e => ({ ok: false, err: e.message })); if (x.ok === false) { toast(x.err, 'bad'); cb.checked = !cb.checked; return; } tone(x.done === x.items.length ? 'done' : 'click'); deptLists(root); });
    const ed = $('[data-dedit]', card); if (ed) ed.onclick = () => deptEdit(lists.find(l => l.dept === dept), root);
  });
}
function deptEdit(l, root) {
  const svc = (S.church?.services || []).map(s => s.name).filter((v, i, a) => a.indexOf(v) === i);
  const admin = S.role === 'admin';
  modal(`<h2>${esc(deptName(l.dept))} checklist</h2><form id="deF" style="margin-top:12px">
    <div class="field"><label>Items, one per line</label><textarea id="deItems" rows="7">${esc(l.items.map(i => i.text).join('\n'))}</textarea><span class="hint">Changing the items clears this round's ticks.</span></div>
    ${admin ? `<div class="field"><label>Leader (edits the items)</label><input id="deLead" value="${esc(l.leader || '')}" placeholder="first.last" autocomplete="off"></div>
    <div class="field"><label>For which services</label>${svc.map(s => `<label class="row" style="gap:6px;font-size:13px"><input type="checkbox" data-desvc="${esc(s)}" ${l.services.includes(s) ? 'checked' : ''}> ${esc(s)}</label>`).join('')}</div>
    <div class="row">${svc.map(s => `<div class="field" style="flex:1"><label>Nudge before ${esc(s)}</label><input type="time" data-denudge="${esc(s)}" value="${esc((l.nudge || {})[s] || '')}"></div>`).join('')}</div>` : ''}
    <div class="acts"><button type="button" class="btn btn--ghost" data-close>Cancel</button><button class="btn" type="submit">Save</button></div></form>`, m => {
    $('#deF', m).onsubmit = async ev => { ev.preventDefault();
      const body = { items: $('#deItems', m).value.split('\n').map(x => x.trim()).filter(Boolean) };
      if (admin) { body.leader = $('#deLead', m).value.trim(); body.services = $$('[data-desvc]', m).filter(x => x.checked).map(x => x.dataset.desvc); body.nudge = Object.fromEntries($$('[data-denudge]', m).filter(x => x.value && body.services.includes(x.dataset.denudge)).map(x => [x.dataset.denudge, x.value])); }
      const r = await api(`/checklists/${encodeURIComponent(l.dept)}`, { method: 'PUT', body }).catch(e => ({ ok: false, err: e.message }));
      if (r.ok === false) return toast(r.err, 'bad'); toast('Checklist saved'); m.close(); deptLists(root); };
  });
}

// ---- the guided setup (round 5, 33) ----
async function setupMaybe() {
  // The first admin sign-in after the install opens it by itself; in sample mode it waits in Settings.
  if (S.role !== 'admin' || S.demo || S.demoOnly) return;
  let s; try { s = await api('/setup'); } catch { return; }
  if (s.show) setTimeout(() => setupWizard(s), 900);
}
async function setupWizard(s) {
  s = s || await api('/setup');
  const step = s.steps.find(x => x.status === 'todo') || s.steps[0];
  const cur = S.setupStep && s.steps.find(x => x.id === S.setupStep) || step;
  S.setupStep = cur.id;
  const chip = st => st === 'done' ? '<span class="pill ok">done</span>' : st === 'skipped' ? '<span class="pill">skipped</span>' : '<span class="pill warn">to do</span>';
  const doors = { people: 'directory', shares: 'directory', synology: 'nas', discord: 'settings', resend: 'mail', tailscale: 'remote' };
  modal(`<div class="wiz"><h2>Set up ariseOS</h2><p class="muted" style="margin-bottom:12px">${s.left ? `${s.left} of ${s.steps.length} steps left.` : 'Every step is done.'} Skip anything; it carries on where you stopped, and Settings → The monitor & setup opens it again.</p>
    <div class="wiz__grid"><nav class="wiz__nav">${s.steps.map((x, i) => `<button class="${x.id === cur.id ? 'on' : ''}" data-wstep="${x.id}"><b>${i + 1}. ${esc(x.title)}</b>${chip(x.status)}</button>`).join('')}</nav>
    <div class="wiz__body"><h3>${esc(cur.title)}</h3><p>${esc(cur.what)}</p>${cur.looks_done ? '<p class="note">This already looks done on the box.</p>' : ''}
      ${cur.id === 'people' ? `<div class="field" style="margin-top:10px"><label>The list (CSV: name, title, departments, personal email, mobile, birthday)</label><textarea id="wzCsv" rows="6" placeholder="first.last,Title,Media;Worship,someone@gmail.com,318-555-0100,03-14"></textarea>
        <div class="row" style="gap:8px;margin-top:8px"><label class="btn btn--ghost btn--xs" for="wzFile">Upload a CSV</label><input type="file" id="wzFile" accept=".csv,.txt" hidden><button class="btn btn--ghost btn--xs" id="wzCheck">Check the list</button><button class="btn btn--xs" id="wzApply">Create the accounts</button></div><div id="wzOut" class="note" style="margin-top:8px" hidden></div></div>` : ''}
      <div class="row" style="gap:8px;margin-top:14px;flex-wrap:wrap"><button class="btn btn--ghost btn--xs" data-wopen="${doors[cur.id]}">Open ${esc(appOf(doors[cur.id])?.name || 'it')}</button><button class="btn btn--xs" data-wmark="done">Mark done</button><button class="btn btn--ghost btn--xs" data-wmark="skipped">Skip</button>${cur.status !== 'todo' ? '<button class="btn btn--ghost btn--xs" data-wmark="todo">Back to to-do</button>' : ''}</div></div></div>
    <div class="acts"><button class="btn btn--ghost" id="wzLater">Later</button><button class="btn" data-close>Close</button></div></div>`, m => {
    $$('[data-wstep]', m).forEach(b => b.onclick = () => { S.setupStep = b.dataset.wstep; m.close(); setupWizard(s); });
    $$('[data-wmark]', m).forEach(b => b.onclick = async () => { const r = await api(`/setup/${cur.id}`, { method: 'POST', body: { status: b.dataset.wmark } }).catch(e => ({ ok: false, err: e.message })); if (r.ok === false) return toast(r.err, 'bad'); const nxt = r.steps.find(x => x.status === 'todo'); S.setupStep = nxt ? nxt.id : cur.id; m.close(); if (r.left) setupWizard(r); else toast('Setup finished. Settings → The monitor & setup opens it again.'); });
    const op = $('[data-wopen]', m); if (op) op.onclick = () => { m.close(); openApp(op.dataset.wopen); };
    $('#wzLater', m).onclick = async () => { await api('/setup/dismiss', { method: 'POST' }).catch(() => {}); m.close(); toast('Later it is: Settings → The monitor & setup opens it again'); };
    if (cur.id === 'people') {
      const out = $('#wzOut', m);
      const send = async apply => { const csv = $('#wzCsv', m).value; if (!csv.trim()) return toast('Paste or upload the list first', 'warn');
        const r = await api('/directory/import', { method: 'POST', body: { csv, apply } }).catch(e => ({ ok: false, err: /no such route|404|Not Found/i.test(e.message) ? 'not available yet: the import arrives with the accounts update' : e.message }));
        out.hidden = false; out.innerHTML = r.ok === false ? esc(r.err) : esc(r.summary || `${(r.rows || r.people || []).length} people ${apply ? 'created' : 'read; nothing created yet'}`); };
      $('#wzCheck', m).onclick = () => send(false);
      $('#wzApply', m).onclick = () => send(true);
      $('#wzFile', m).onchange = async e => { const f = e.target.files[0]; if (f) $('#wzCsv', m).value = await f.text(); };
    }
  });
}

// ---- Settings: The monitor & setup (round 5, 27 and 33) ----
{
  SETTINGS_SECTIONS.splice(SETTINGS_SECTIONS.findIndex(x => x[0] === 'power'), 0, ['monitor', 'The monitor & setup']);
  const setView = V.settings, setAfter = V.settings.after;
  V.settings = async () => {
    if (S.settingsSec !== 'monitor') return setView();
    let k = { scale: 1.25, choices: [1, 1.15, 1.25, 1.4, 1.5] }, su = { steps: [], left: 0 };
    try { k = await api('/kiosk/scale'); } catch {} try { su = await api('/setup'); } catch {}
    const body = `<h2>The monitor &amp; setup</h2>
      <h3 style="margin:6px 0 8px">Text size on the closet monitor</h3><p class="note" style="margin-bottom:10px">Read from the doorway. Only the monitor changes; Macs and phones keep their own size. Saving restarts the monitor's browser (about five seconds), never during a service.</p>
      <div class="seg" id="stScale">${k.choices.map(c => `<button class="${Math.abs(c - k.scale) < 0.001 ? 'active' : ''}" data-scale="${c}">${Math.round(c * 100)}%</button>`).join('')}</div>
      <h3 style="margin:18px 0 8px">The guided setup</h3><p class="note" style="margin-bottom:10px">${su.left ? `${su.left} of ${su.steps.length} steps left.` : 'Every step is done.'} People, shares, the Synology, Discord, Resend, Tailscale.</p>
      <div class="row"><button class="btn btn--xs" id="stSetup">Open the guided setup</button></div>`;
    return `<div class="settings"><nav class="settings__nav">${SETTINGS_SECTIONS.map(([id, name]) => `<button class="${S.settingsSec === id ? 'active' : ''}" data-sec="${id}">${esc(name)}</button>`).join('')}</nav><div class="settings__body fade">${body}</div></div>`;
  };
  V.settings.after = root => {
    setAfter(root);
    $$('[data-scale]', root).forEach(b => b.onclick = async () => { const r = await act(b, () => api('/kiosk/scale', { method: 'POST', body: { scale: +b.dataset.scale } }), `The monitor's text is now ${Math.round(+b.dataset.scale * 100)}%`); if (r && r.ok !== false) rerender('settings'); });
    const so = $('#stSetup', root); if (so) so.onclick = async () => { await api('/setup/reopen', { method: 'POST' }).catch(() => {}); S.setupStep = null; setupWizard(); };
  };
}

/* ---- closet OS (round 6) ---- */
/* Rows 21-22, 29-33: the four admins get the desktop at the monitor, each with their own Firefox
   profile. Signing in there asks the server to restart Firefox into that admin's profile; the new
   Firefox opens /?kiosk=1&handoff=<token> and trades the one-time token for the session. Locking
   puts the monitor back on a fresh neutral profile. Anywhere but the monitor this is a reload. */
async function afterSignIn() {
  if (S.kiosk) {
    try {
      const me = await api('/auth/me');
      if (me.role === 'admin') {
        const k = await api('/kiosk/profile');
        if (k.current !== me.user) {
          const r = await api('/kiosk/profile', { method: 'POST', body: { action: 'switch' } });
          if (r && r.ok !== false && !r.demo && !r.already) { toast('Opening your browser…', 'info', 8000); return; }
        }
      }
    } catch (e) { /* the old shared browser: a reload is still right */ }
  }
  location.reload();
}
async function kioskHandoff() {
  const q = new URLSearchParams(location.search); const tok = q.get('handoff'); if (!tok) return;
  q.delete('handoff'); history.replaceState(null, '', location.pathname + (q.toString() ? '?' + q : '') + location.hash);
  try { await api('/auth/handoff', { method: 'POST', body: { token: tok } }); } catch (e) { toast(e.message || 'Sign in again', 'warn'); }
}
function kioskNeutral() {
  if (!S.kiosk || S.role !== 'admin') return;
  api('/kiosk/profile', { method: 'POST', body: { action: 'neutral' } }).catch(() => {});
}
/* Row 20: staff never sign in to the OS, so an admin turns two-step on and off for them here. */
function staffTwofaOn(name) {
  modal(`<h2>Two-step for ${esc(name)}</h2><p class="muted">With them beside you: they install <b>Microsoft Authenticator</b>, tap <b>+</b> → <b>Other account</b>, and scan this code from your screen. Then type the six digits their phone shows.</p>
    <div class="twofa__qr" id="dtQr"><div class="skeleton" style="width:160px;height:160px"></div></div>
    <p class="muted" style="font-size:12px;text-align:center">Can't scan? They type this key instead: <code id="dtSecret">…</code><br>Shown once.</p>
    <form id="dtOn" style="display:grid;gap:8px;margin-top:10px"><input id="dtCode" inputmode="numeric" pattern="[0-9 ]*" placeholder="The six digits on their phone" autocomplete="off" maxlength="7">
    <div class="acts"><button type="button" class="btn btn--ghost" data-close>Not now</button><button class="btn" type="submit">Turn it on</button></div></form>`, async m => {
    const r = await api(`/directory/users/${encodeURIComponent(name)}/2fa/setup`, { method: 'POST' }).catch(er => ({ ok: false, err: er.message }));
    if (r.ok === false) { toast(r.err, 'bad'); return m.close(); }
    $('#dtQr', m).innerHTML = r.qr || `<div class="none">no QR; type the key</div>`; $('#dtSecret', m).textContent = (r.secret || '').replace(/(.{4})/g, '$1 ').trim();
    $('#dtCode', m).focus();
    $('#dtOn', m).onsubmit = async e => { e.preventDefault(); const x = await api(`/directory/users/${encodeURIComponent(name)}/2fa/enable`, { method: 'POST', body: { code: $('#dtCode', m).value } }).catch(er => ({ ok: false, err: er.message })); if (x.ok === false) return toast(x.err, 'warn'); tone('done'); toast(x.demo ? 'Sample mode: nothing changed' : `Two-step is on for ${name}`); m.close(); rerender('directory'); };
  });
}
{ const _dirAfterR6 = V.directory.after; V.directory.after = root => { _dirAfterR6(root);
  $$('[data-2fa]', root).forEach(b => b.onclick = async () => {
    const name = b.dataset['2fa'];
    if (b.dataset.on !== '1') return staffTwofaOn(name);
    const r = await act(b, () => withReauth(() => api(`/directory/users/${encodeURIComponent(name)}/2fa/disable`, { method: 'POST' })), `Two-step is off for ${name}`);
    if (r && r.ok !== false) rerender('directory');
  });
}; }

// ===== R6-SYNC: the Sync panel (round 6, rows 13-19, 39, 40; docs/SYNC.md) =====
// Admins only: per person, last sync, devices, conflicts settled, storage against the quota.
// A device password is shown once; Cut off revokes one device or every sign-in a person has.
{
  I.sync = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 4a8 8 0 0 1 7.4 5H22l-3.5 4L15 9h2.2A6 6 0 0 0 6.3 8.3L4.6 7.2A8 8 0 0 1 12 4zM5.5 11L9 15H6.8a6 6 0 0 0 10.9.7l1.7 1.1A8 8 0 0 1 4.6 15H2z"/></svg>';
  APPS.splice(APPS.findIndex(a => a.id === 'shares'), 0, { id: 'sync', n: '33', name: 'Sync', what: 'Nextcloud: every Mac and phone, last sync, conflicts, storage', w: 1040, h: 680 });
  const lastOf = p => p.last_sync ? `${fmtT(p.last_sync)} <span class="dim">(${ago(p.last_sync)})</span>` : '<span class="dim">never</span>';
  V.sync = async () => {
    const [st, pp, cf] = await Promise.all([api('/cloud'), api('/cloud/people'), api('/cloud/conflicts?limit=20')]);
    const people = pp.people || [], cs = cf.conflicts || [];
    S.syncPeople = people;
    const nDev = people.reduce((n, p) => n + p.devices.filter(d => !d.revoked).length, 0);
    const synced = people.filter(p => p.devices.some(d => !d.revoked));
    const full = people.filter(p => p.storage?.warn || p.storage?.full);
    const qgb = pp.quota_gb ? `${pp.quota_gb} GB` : 'no limit';
    const row = p => {
      const s = p.storage || {}, pc = s.pct ?? 0;
      const devs = p.devices.length ? p.devices.map(d => `<div class="row" style="gap:6px;align-items:center;margin:2px 0"><span class="${d.revoked ? 'dim' : ''}">${esc(d.device)}</span>${d.revoked ? '<span class="pill">cut off</span>' : `<span class="dim" style="font-size:12px">${d.last_sync ? ago(d.last_sync) : 'not yet'}</span><button class="btn btn--ghost btn--xs" data-cut="${esc(p.user)}" data-dev="${esc(d.device)}">Cut off</button>`}</div>`).join('') : '<span class="dim">no devices</span>';
      return `<tr><td><b>${esc(p.user)}</b></td><td>${devs}</td><td>${lastOf(p)}</td><td>${p.conflicts || 0}</td>
        <td style="min-width:150px"><div style="font-size:12.5px">${fmtB(s.used)} of ${s.quota ? fmtB(s.quota) : 'no limit'}</div><div class="meter ${s.full ? '' : s.warn ? 'meter--warn' : 'meter--ok'}" style="margin-top:6px"><i style="width:${Math.min(100, pc)}%"></i></div></td>
        <td class="acts"><button class="btn btn--ghost btn--xs" data-newdev="${esc(p.user)}">New device…</button>${p.devices.some(d => !d.revoked) ? `<button class="btn btn--ghost btn--xs" data-cutall="${esc(p.user)}">Cut off all…</button>` : ''}</td></tr>`;
    };
    return `<div class="fade">
      <div class="grid" style="margin-bottom:14px">
        <div class="c3 panel ${st.running === false ? 'panel--bad' : 'panel--ok'}"><div class="stat"><span class="stat__l">Nextcloud</span><span class="stat__v" style="font-size:22px">${st.running ? 'running' : st.running === false ? 'stopped' : 'unknown'}</span><span class="stat__n mono" style="font-size:11.5px;overflow-wrap:anywhere">${esc(st.url || '')}</span></div></div>
        <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Devices</span><span class="stat__v">${nDev}</span><span class="stat__n">${synced.length} of ${people.length} people syncing</span></div></div>
        <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Conflicts settled</span><span class="stat__v">${cs.length}</span><span class="stat__n">newest wins; the older copy is in the Trash</span></div></div>
        <div class="c3 panel ${full.length ? 'panel--warn' : 'panel--flat'}"><div class="stat"><span class="stat__l">Storage</span><span class="stat__v">${full.length}<small>near ${esc(qgb)}</small></span><span class="stat__n">each home against its quota</span></div></div>
      </div>
      <div class="panel panel--flat" style="margin-bottom:14px"><div class="panel__hd"><h3>People</h3><span class="sub">${esc((st.sync_folders || []).join(' and '))} in full on every Mac · the shares on demand in Finder's sidebar · phones in the Nextcloud app</span>
        <div class="row" style="margin-left:auto;gap:6px"><button class="btn btn--ghost btn--xs" id="syncSweep">Settle conflicts now</button></div></div>
        <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Person</th><th>Devices</th><th>Last sync</th><th>Conflicts</th><th>Storage</th><th></th></tr></thead><tbody>${people.map(row).join('')}</tbody></table></div></div>
      <div class="panel panel--flat"><div class="panel__hd"><h3>Recent conflicts</h3><span class="sub">two copies changed at once: the newer keeps the name, the older goes to that folder's Trash (Put Back works)</span></div>
        ${cs.length ? `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>When</th><th>File</th><th>Kept</th><th>Older copy</th></tr></thead><tbody>${cs.map(c => `<tr><td>${fmtT(c.t)}</td><td class="mono" style="font-size:12px">${esc(c.file)}</td><td>${esc(c.kept)}</td><td class="mono dim" style="font-size:12px">${esc(c.trash || '—')}</td></tr>`).join('')}</tbody></table></div>` : '<p class="muted" style="font-size:13px">No conflicts yet.</p>'}
      </div></div>`;
  };
  V.sync.after = root => {
    $$('[data-cut]', root).forEach(b => b.onclick = async () => { const r = await act(b, () => api('/cloud/revoke', { method: 'POST', body: { user: b.dataset.cut, device: b.dataset.dev } }), `${b.dataset.dev} is cut off; ${b.dataset.cut} was told`); if (r && r.ok !== false) rerender('sync'); });
    $$('[data-cutall]', root).forEach(b => b.onclick = () => confirmType(`Cut off every device of ${b.dataset.cutall}`, b.dataset.cutall,
      `Every Mac, phone and web sign-in ${esc(b.dataset.cutall)} has in Nextcloud stops at once. Their files stay, on the server and on each Mac. A lost Mac, or someone leaving.`,
      async () => { const r = await api('/cloud/revoke', { method: 'POST', body: { user: b.dataset.cutall } }); if (r.ok === false) throw new Error(r.err); toast(`${b.dataset.cutall}: every device cut off, and they were told`); rerender('sync'); }));
    $$('[data-newdev]', root).forEach(b => b.onclick = () => modal(`<h2>A device password for ${esc(b.dataset.newdev)}</h2>
      <p class="note" style="margin-bottom:12px">For a phone or a Mac set up by hand. Church Macs get theirs from the helper by themselves. It is shown once and signs in that one device; never their domain password.</p>
      <div class="field"><label>Device name</label><input id="ndName" placeholder="Kristina's iPhone" maxlength="60" autocomplete="off"></div>
      <div id="ndOut"></div>
      <div class="acts"><button class="btn btn--ghost" data-close>Close</button><button class="btn" id="ndGo">Make the password</button></div>`, m => {
      $('#ndName', m).focus();
      $('#ndGo', m).onclick = async e => {
        const r = await act(e.target, () => api('/cloud/app-password', { method: 'POST', body: { user: b.dataset.newdev, device: $('#ndName', m).value.trim() } }));
        if (!r || r.ok === false) return;
        $('#ndOut', m).innerHTML = `<dl class="kv" style="margin:10px 0"><dt>Server</dt><dd class="mono">${esc(r.server)}</dd><dt>Login</dt><dd class="mono">${esc(r.login)}</dd><dt>Password</dt><dd class="mono" id="ndPw">${esc(r.app_password)}</dd></dl>
          <div class="row" style="gap:6px"><button class="btn btn--ghost btn--xs" id="ndCopy">Copy</button><span class="muted" style="font-size:12px">In the Nextcloud app: the server, then “Log in with an app password”.</span></div>`;
        $('#ndCopy', m).onclick = ev => copyText(r.app_password, ev.target);
        e.target.disabled = true; rerender('sync');
      };
    }));
    const sw = $('#syncSweep', root); if (sw) sw.onclick = async () => { const r = await act(sw, () => api('/cloud/sweep', { method: 'POST' })); if (r && r.ok !== false) { toast(`${(r.moved || []).length} conflict(s) settled` + (r.demo ? ' (sample mode: nothing changed)' : '')); rerender('sync'); } };
  };
}
// ===== end R6-SYNC =====

/* ---------------- Round 7: accounts and privacy in Directory (docs/ANSWERS.md, round 7) ---------------- */
// Rename (13), the photo (20), the church contacts address book (21, 152), accounts nobody uses (17)
// and Bradly's emergency look into the Pastors folder (69). Wrapped so Directory itself stays as it is.
{
  const dirAfter7 = V.directory.after;
  V.directory.after = root => { dirAfter7(root); r7Wire(root); };
  async function r7Wire(root) {
    const bar = $('#addUser', root)?.parentElement;
    if (bar && !$('#r7Contacts', root)) {
      bar.insertAdjacentHTML('afterbegin', `<button class="btn btn--ghost btn--sm" id="r7Contacts">Church contacts</button><button class="btn btn--ghost btn--sm" id="r7Pastors" hidden>Pastors folder…</button><button class="btn btn--ghost btn--sm" id="r7Pins">Sign-in PINs</button>`);
      $('#r7Contacts', root).onclick = contactsModal;
      $('#r7Pins', root).onclick = () => pinsModal();
      api('/pastors/breakglass').then(g => { const b = $('#r7Pastors', root); if (!b || !g.allowed) return; b.hidden = false; b.textContent = g.open ? `Pastors folder open until ${fmtT(g.until)}` : 'Pastors folder…'; b.onclick = () => breakglassModal(g); }).catch(() => {});
    }
    api('/directory/unused').then(u => {
      if (!(u.unused || []).length || $('#r7Unused', root)) return;
      const t = $('#uTable', root); if (!t) return;
      t.closest('.panel').insertAdjacentHTML('beforebegin', `<div class="note" id="r7Unused" style="margin-bottom:10px">No sign-in for ${u.days} days: ${u.unused.map(x => `<b>${esc(x.user)}</b> (${x.days} days)`).join(', ')}. Still needed? Switch them off, or mark them as leaving.</div>`);
    }).catch(() => {});
    $$('#uTable tbody tr', root).forEach(tr => {
      const tog = $('[data-tog]', tr); if (!tog || $('[data-rn]', tr)) return; const name = tog.dataset.tog; const acts = tog.parentElement;
      const rn = document.createElement('button'); rn.className = 'btn btn--ghost btn--xs'; rn.textContent = 'Rename…'; rn.dataset.rn = name; rn.onclick = () => renameModal(name);
      const ph = document.createElement('button'); ph.className = 'btn btn--ghost btn--xs'; ph.textContent = 'Photo…'; ph.dataset.ph = name; ph.onclick = () => photoModal(name);
      acts.prepend(ph); acts.prepend(rn);
    });
  }
  function renameModal(name) {
    modal(`<h2>Rename ${esc(name)}</h2><p class="note" style="margin-bottom:12px">A married name or a correction. Their groups, files and permissions stay with the account; the login, the home folder's name and the church address change. Mail to the old address keeps arriving. On each church Mac the old Mac account stays until it is renamed there: the person signs in with the new name and their files come back from the server.</p>
      <div class="field"><label>New user name</label><input id="rnNew" placeholder="first.last" autocomplete="off"></div>
      <div class="field"><label>Type <b>${esc(name)}</b> to confirm</label><input id="rnOk" autocomplete="off"></div>
      <div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="rnGo">Rename</button></div>`, m => {
      $('#rnNew', m).focus();
      $('#rnGo', m).onclick = async e => { const r = await act(e.target, () => withReauth(() => api(`/directory/users/${encodeURIComponent(name)}/rename`, { method: 'POST', body: { new: $('#rnNew', m).value.trim(), confirm: $('#rnOk', m).value.trim() } })), 'Renamed');
        if (r && r.ok !== false) { m.close(); (r.notes || []).forEach(n => toast(n, 'warn', 9000)); rerender('directory'); } };
    });
  }
  function photoModal(name) {
    modal(`<h2>Photo for ${esc(name)}</h2><p class="note" style="margin-bottom:12px">The photo they chose: it shows on the closet monitor's faces and, from the domain, in Nextcloud and Contacts. A JPEG or PNG, at most 200 KB. Until there is one, their initials show.</p>
      <div class="field"><label class="btn btn--ghost btn--sm" for="phFile">Choose a photo</label><input type="file" id="phFile" accept="image/jpeg,image/png" hidden><span class="hint" id="phName"></span></div>
      <div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="phGo" disabled>Save</button></div>`, m => {
      let data = '';
      $('#phFile', m).onchange = e => { const f = e.target.files[0]; if (!f) return; $('#phName', m).textContent = `${f.name} · ${fmtB(f.size)}`; const rd = new FileReader(); rd.onload = () => { data = String(rd.result); $('#phGo', m).disabled = false; }; rd.readAsDataURL(f); };
      $('#phGo', m).onclick = async e => { const r = await act(e.target, () => api(`/directory/users/${encodeURIComponent(name)}/photo`, { method: 'POST', body: { data } }), 'Photo saved'); if (r && r.ok !== false) m.close(); };
    });
  }
  async function contactsModal() {
    let c; try { c = await api('/contacts'); } catch (e) { return toast(e.message, 'bad'); }
    modal(`<h2>Church contacts</h2><p class="note" style="margin-bottom:12px">Everyone's details, in Contacts on church Macs and on staff phones, read-only: the staff directory (with titles, departments and mobile numbers) and the Mail app's contacts list. ${c.cards} cards now. You keep the people here in Directory and the list in Mail; nobody edits it on their phone.</p>
      <div class="kv"><dt>Address</dt><dd class="mono" style="user-select:all">${esc(c.url)}</dd><dt>On a Mac</dt><dd>${esc(c.how_mac)}</dd><dt>On a phone</dt><dd>${esc(c.how_phone)}</dd><dt>One tap</dt><dd>Open <span class="mono" style="user-select:all">https://${esc(c.host)}${esc(c.profile)}</span> on the Mac or iPhone and approve it in Settings; it asks for the church login.</dd></div>
      <p class="note" style="margin-top:10px">${esc(c.note)} Phones off church Wi-Fi need Tailscale on.</p>
      <div class="acts"><button class="btn" data-close>Done</button></div>`);
  }
  function breakglassModal(g) {
    if (g.open) return confirmType('Close the Pastors folder', 'close', `It is open to you until ${esc(fmtT(g.until))}. Close it now?`, async () => { const r = await api('/pastors/breakglass', { method: 'DELETE' }); if (r.ok === false) throw new Error(r.err); toast('The Pastors folder is closed to you again'); rerender('directory'); });
    modal(`<h2>The Pastors folder, in an emergency</h2><p class="note" style="margin-bottom:12px">It is the two pastors' alone. In an emergency you can see it for ${g.hours} hours, in Finder here. Both pastors are emailed the moment you open it, with your reason, and every file you open is in the audit log. Claude never can.</p>
      <div class="field"><label>Why (the pastors read this)</label><textarea id="bgWhy" rows="3"></textarea></div>
      <div class="field"><label>Type <b>pastors</b> to confirm</label><input id="bgOk" autocomplete="off"></div>
      <div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn btn--danger" id="bgGo">Open it for ${g.hours} hours</button></div>`, m => {
      $('#bgGo', m).onclick = async e => { const r = await act(e.target, () => withReauth(() => api('/pastors/breakglass', { method: 'POST', body: { reason: $('#bgWhy', m).value, confirm: $('#bgOk', m).value } })), 'Open; both pastors were told');
        if (r && r.ok !== false) { m.close(); rerender('directory'); } };
    });
  }
}

// ===== R7-C: services, the closet desktop and the channel (round 7; docs/ANSWERS.md) =====
// Service mode on the monitor (87), the admins' notes board (116), widgets and Launchpad apps
// each admin chooses (114, 115), both campuses' weather (111), the screensaver's announcements
// from the Calendar (110), the owner's desktop after a restart (107), Reports in Settings
// (Discord, the Monday report, the pastors' note: 78-81, 85, 144), the speed test (121), and
// the Songs tab's Lyrics inbox and CCLI usage (99, 100, 106).
const WIDGETS = [['needs', 'Needs you'], ['live', 'Live'], ['box', 'The box'], ['week', 'This week'], ['weather', 'Weather'], ['verse', 'Verse of the day'], ['notes', 'Notes board']];
function jsonPref(k) { try { const v = JSON.parse(PREF.get(k, '[]')); return Array.isArray(v) ? v : []; } catch { return []; } }
function widgetsOff() { return jsonPref('widgets.off'); }
function lpHidden() { return jsonPref('lp.hidden'); }
function applyWidgetPrefs(w) { const off = widgetsOff(); $$('[data-wg]', w).forEach(el => { el.hidden = off.includes(el.dataset.wg); }); }
function lpHide(id, hide) { const cur = lpHidden().filter(x => x !== id); if (hide) cur.push(id); PREF.set('lp.hidden', JSON.stringify(cur)); buildDock(); toast(hide ? 'Hidden from your Launchpad (Settings → My desktop brings it back)' : 'Back on your Launchpad'); }
function widgetSet(id, on) { const cur = widgetsOff().filter(x => x !== id); if (!on) cur.push(id); PREF.set('widgets.off', JSON.stringify(cur)); const w = $('#widgets'); if (w) applyWidgetPrefs(w); }

/* the notes board (116) */
const NOTE_COLOURS = ['ink', 'red', 'amber', 'green'];
function notesWidget() {
  if (isMember()) return '';
  const b = S.board || { notes: [] };
  return `<div data-wg="notes" class="widget widget--notes"><div class="row row--between"><div class="widget__kicker">Notes board</div><button class="btn btn--ghost btn--xs" id="nbAdd">Add a note</button></div>
    <div class="nb">${(b.notes || []).slice(0, 6).map(n => `<div class="nb__n nb--${esc(n.colour || 'ink')}" data-note="${esc(n.id)}"><p>${esc(n.text)}</p><div class="nb__f"><span>${esc(n.by)} · ${esc(ago(n.at))}${n.pinned ? ' · pinned' : ''}</span><span><button class="btn btn--ghost btn--xs" data-nbpin="${esc(n.id)}">${n.pinned ? 'Unpin' : 'Pin'}</button><button class="btn btn--ghost btn--xs" data-nbedit="${esc(n.id)}">Edit</button><button class="btn btn--ghost btn--xs" data-nbaway="${esc(n.id)}">Put away</button></span></div></div>`).join('') || '<div class="widget__sub">Nothing on the board. The four admins see the same notes.</div>'}</div>
    ${(b.notes || []).length > 6 ? `<div class="widget__sub">${b.notes.length - 6} more</div>` : ''}${(b.away || []).length ? `<button class="btn btn--ghost btn--xs" id="nbAway" style="margin-top:6px">Put away (${b.away.length})</button>` : ''}</div>`;
}
function notesWidgetAfter(w) {
  if (isMember()) return;
  if (!S.boardAt || Date.now() - S.boardAt > 30000) { S.boardAt = Date.now(); api('/notes-board').then(b => { S.board = b; const el = $('[data-wg="notes"]', w); if (el) { el.outerHTML = notesWidget(); applyWidgetPrefs(w); notesWidgetAfter(w); } }).catch(() => {}); }
  const box = $('[data-wg="notes"]', w); if (!box) return;
  const redraw = b => { S.board = b; S.boardAt = Date.now(); const el = $('[data-wg="notes"]', w); if (el) { el.outerHTML = notesWidget(); applyWidgetPrefs(w); notesWidgetAfter(w); } };
  const add = $('#nbAdd', box); if (add) add.onclick = () => noteModal(null, redraw);
  $$('[data-nbedit]', box).forEach(b => b.onclick = () => noteModal((S.board.notes || []).find(n => n.id === b.dataset.nbedit), redraw));
  $$('[data-nbpin]', box).forEach(b => b.onclick = async () => { const n = (S.board.notes || []).find(x => x.id === b.dataset.nbpin); const r = await api(`/notes-board/${encodeURIComponent(n.id)}`, { method: 'PUT', body: { pinned: !n.pinned } }).catch(e => ({ ok: false, err: e.message })); if (r.ok === false) return toast(r.err, 'bad'); redraw(r); });
  $$('[data-nbaway]', box).forEach(b => b.onclick = async () => { const r = await api(`/notes-board/${encodeURIComponent(b.dataset.nbaway)}/away`, { method: 'POST' }).catch(e => ({ ok: false, err: e.message })); if (r.ok === false) return toast(r.err, 'bad'); toast('Put away (it is kept: Put away brings it back)'); redraw(r); });
  const aw = $('#nbAway', box); if (aw) aw.onclick = () => modal(`<h2>Put away</h2><p class="muted">Notes the admins put away. Nothing here is deleted.</p><div style="margin-top:10px">${(S.board.away || []).map(n => `<div class="widget__row"><span>${esc(n.text)}<br><small class="muted">${esc(n.away_by || '')} · ${esc(ago(n.away_at))}</small></span><button class="btn btn--ghost btn--xs" data-nbback="${esc(n.id)}">Bring back</button></div>`).join('')}</div><div class="acts"><button class="btn btn--ghost" data-close>Close</button></div>`, m => {
    $$('[data-nbback]', m).forEach(b => b.onclick = async () => { const r = await api(`/notes-board/${encodeURIComponent(b.dataset.nbback)}/back`, { method: 'POST' }).catch(e => ({ ok: false, err: e.message })); if (r.ok === false) return toast(r.err, 'bad'); m.close(); redraw(r); });
  });
}
function noteModal(n, done) {
  modal(`<h2>${n ? 'Edit the note' : 'A note for the board'}</h2><form id="nbf" style="margin-top:12px"><div class="field"><label for="nbT">Note</label><textarea id="nbT" rows="4" maxlength="600" required>${esc(n?.text || '')}</textarea><span class="hint">All four admins see it on their desktops.</span></div>
    <div class="field"><label>Colour</label><div class="seg" id="nbC">${NOTE_COLOURS.map(c => `<button type="button" data-c="${c}" class="${(n?.colour || 'ink') === c ? 'active' : ''}">${c}</button>`).join('')}</div></div>
    <div class="acts"><button type="button" class="btn btn--ghost" data-close>Cancel</button><button class="btn" type="submit">${n ? 'Save' : 'Add'}</button></div></form>`, m => {
    let colour = n?.colour || 'ink';
    $$('#nbC button', m).forEach(b => b.onclick = () => { colour = b.dataset.c; $$('#nbC button', m).forEach(x => x.classList.toggle('active', x === b)); });
    $('#nbf', m).onsubmit = async e => { e.preventDefault(); const text = $('#nbT', m).value;
      const r = await api(n ? `/notes-board/${encodeURIComponent(n.id)}` : '/notes-board', { method: n ? 'PUT' : 'POST', body: { text, colour } }).catch(er => ({ ok: false, err: er.message }));
      if (r.ok === false) return toast(r.err, 'bad'); toast(n ? 'Saved' : 'On the board'); m.close(); done(r); };
    $('#nbT', m).focus();
  });
}

/* the screensaver: announcements from the Calendar (110), both campuses' weather (111) */
async function saverExtras() {
  const sv = $('#saver'); if (!sv) return;
  let box = $('#saverAnn'); if (!box) { box = document.createElement('div'); box.id = 'saverAnn'; box.className = 'saver__ann'; ($('#saverVerse') || sv).after(box); }
  const lines = [];
  try {
    const n = new Date(); const cal = await api(`/calendar?year=${n.getFullYear()}&month=${n.getMonth() + 1}`);
    const soon = (cal.upcoming || []).filter(e => !e.service && new Date(e.start) - n < 8 * 86400000).slice(0, 6);
    lines.push(...soon.map(e => `${fmtDay(e.start)} · ${fmtClock(e.start)} · ${e.title}${e.where ? ' · ' + e.where : ''}`));
  } catch {}
  try { const w = await loadWeather(); const ps = (w.places || [w]).filter(p => p && p.ok); if (ps.length) lines.push(ps.map(p => `${p.place.split(',')[0]} ${p.now?.temp ?? '–'}° ${p.now?.words || ''}`).join('  ·  ')); } catch {}
  if (!lines.length) { box.textContent = ''; return; }
  let i = 0; const step = () => { if (sv.hidden) return clearInterval(S.saverN); box.textContent = lines[i % lines.length]; i++; };
  clearInterval(S.saverN); step(); S.saverN = setInterval(step, 12000);
}

/* after a restart, the owner's desktop on the monitor (107) */
async function kioskAutologin() {
  try {
    const r = await api('/auth/kiosk-autologin', { method: 'POST' });
    if (!r || r.ok === false) return false;
    try { await api('/kiosk/profile', { method: 'POST', body: { action: 'switch' } }); } catch {}
    location.reload(); return true;
  } catch { return false; }
}

/* service mode (87): the monitor opens it by itself while a service runs */
I.servicemode = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4 5h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-6v2h3v2H7v-2h3v-2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zm0 2v8h16V7zm6 1.5 5 2.5-5 2.5z"/></svg>';
APPS.push({ id: 'servicemode', n: '34', name: 'Service mode', what: 'During a service: the stream, every checklist, the run sheet', w: 1100, h: 720 });
async function serviceWatch() {
  if (isMember() || S.svcWatch) return; S.svcWatch = true;
  const look = async () => {
    let v; try { v = await api('/service/now'); } catch { return; }
    S.svcNow = v;
    const key = v.in_service ? `${v.service.name}|${v.service.started}` : '';
    if (v.in_service && S.kiosk && S.svcOpened !== key) { S.svcOpened = key; openApp('servicemode'); const w = S.wins.servicemode; if (w && typeof snapTo === 'function') try { snapTo('servicemode', 'max'); } catch {} }
    if (S.wins.servicemode) rerender('servicemode');
  };
  look(); every(look, 60000);
}
V.servicemode = async () => {
  const v = S.svcNow = await api('/service/now');
  if (!v.in_service) {
    const n = v.next;
    return `<div class="fade svm svm--off"><div class="kicker">Service mode</div><h2>No service on right now</h2><p class="note">During a service the closet monitor opens this by itself: the stream, every department's checklist and the run sheet. Updates, restarts, Mac changes and heavy syncing wait until it ends.</p>
      ${n ? `<p style="margin-top:10px">Next: <b>${esc(n.name)}</b> · ${esc(n.site || '')} · ${esc(n.day)} ${esc(fmtSvc(n.time))} · in ${esc(n.in_words)}</p>` : ''}
      ${v.demo ? '<div class="row" style="margin-top:14px"><button class="btn btn--ghost btn--xs" id="svmDemo">Show it as during a service (preview)</button></div>' : ''}</div>`;
  }
  const s = v.service, st = v.stream || {}, net = v.internet || {}, rs = v.run_sheet || {};
  const live = st.live === true ? '<span class="pill ok">LIVE</span>' : st.live === false ? '<span class="pill warn">not live</span>' : '<span class="pill">could not tell</span>';
  return `<div class="fade svm"><div class="row row--between"><div><div class="kicker">Service mode${s.sample ? ' · preview' : ''}</div><h2 style="margin:0">${esc(s.name)}${s.site ? ' · ' + esc(s.site) : ''}</h2><div class="muted">until ${esc(s.ends_at || '')} · updates, restarts, Mac changes and heavy syncing wait</div></div>${v.demo && s.sample ? '<button class="btn btn--ghost btn--xs" id="svmDemoOff">End the preview</button>' : ''}</div>
    <div class="grid" style="margin-top:14px">
      <div class="c4 panel panel--flat"><div class="panel__hd"><h3>The stream</h3></div><div class="svm__big">${live}</div><div class="muted" style="margin-top:6px">checked ${esc(fmtClock(st.checked || ''))}${st.why ? ' · ' + esc(st.why) : ''}</div>
        <div class="widget__row" style="margin-top:10px"><span>Internet</span><b>${net.down != null ? `${esc(net.down)} down · ${esc(net.up)} up · ${esc(net.ping)} ms` : 'no test yet'}</b></div>${st.url ? `<a class="btn btn--ghost btn--xs" href="${esc(st.url)}" target="_blank" rel="noopener" style="margin-top:10px">Open the live page</a>` : ''}</div>
      <div class="c4 panel panel--flat"><div class="panel__hd"><h3>Checklists</h3></div>${(v.checklists || []).map(c => `<div class="svm__cl"><div class="widget__row"><span>${esc(deptName(c.dept))}</span><b class="${c.total && c.done === c.total ? 'ok' : ''}">${c.done} of ${c.total}</b></div><div class="meter"><i style="width:${c.total ? Math.round(100 * c.done / c.total) : 0}%"></i></div>${c.left.length ? `<small class="muted">${c.left.map(esc).join(' · ')}</small>` : ''}</div>`).join('') || '<p class="muted">No department lists for this service.</p>'}</div>
      <div class="c4 panel panel--flat svm__sheet"><div class="panel__hd"><h3>Run sheet</h3>${rs.name ? `<span class="muted mono" style="font-size:11px">${esc(rs.name)}</span>` : ''}</div>${rs.ok ? `<div class="md">${md(rs.text)}</div>` : `<p class="muted">${esc(rs.why || 'none')}</p>`}</div>
    </div></div>`;
};
V.servicemode.after = root => {
  const on = $('#svmDemo', root); if (on) on.onclick = async () => { await api('/service/demo', { method: 'POST', body: { on: true } }).catch(() => {}); rerender('servicemode'); };
  const off = $('#svmDemoOff', root); if (off) off.onclick = async () => { await api('/service/demo', { method: 'POST', body: { on: false } }).catch(() => {}); rerender('servicemode'); };
};

/* Settings: My desktop (114, 115) and Reports (78-81, 85, 144) */
{
  SETTINGS_SECTIONS.splice(SETTINGS_SECTIONS.findIndex(x => x[0] === 'notifications') + 1, 0, ['reports', 'Reports'], ['mydesktop', 'My desktop']);
  const setView = V.settings, setAfter = V.settings.after;
  const wrap = body => `<div class="settings"><nav class="settings__nav">${SETTINGS_SECTIONS.map(([id, name]) => `<button class="${S.settingsSec === id ? 'active' : ''}" data-sec="${id}">${esc(name)}</button>`).join('')}</nav><div class="settings__body fade">${body}</div></div>`;
  V.settings = async () => {
    if (S.settingsSec === 'mydesktop') {
      const off = widgetsOff(), hid = lpHidden();
      return wrap(`<h2>My desktop</h2><p class="note" style="margin-bottom:12px">Yours alone: they follow your account to the closet monitor and any browser.</p>
        <h3 style="margin:6px 0 8px">Widgets</h3><div class="mdsk">${WIDGETS.map(([id, name]) => `<label class="check"><input type="checkbox" data-wgset="${id}" ${off.includes(id) ? '' : 'checked'}> ${esc(name)}</label>`).join('')}</div>
        <h3 style="margin:16px 0 8px">Hidden from my Launchpad</h3>${hid.length ? hid.map(id => { const a = APPS.find(x => x.id === id); return `<div class="widget__row"><span>${esc(a ? a.name : id)}</span><button class="btn btn--ghost btn--xs" data-lpshow="${esc(id)}">Show</button></div>`; }).join('') : '<p class="muted">Nothing hidden. Right-click an app in Launchpad → Hide from my Launchpad.</p>'}`);
    }
    if (S.settingsSec === 'reports') {
      let r = {}, p = {}; try { r = await api('/reports'); } catch (e) { r = { error: e.message }; } try { p = await api('/reports/pastors'); } catch (e) { p = { ok: false, err: e.message }; }
      const ch = (r.discord || {}).channels || {}; const c = r.channel || {};
      return wrap(`<h2>Reports</h2>
        <h3 style="margin:6px 0 8px">Discord</h3><p class="note" style="margin-bottom:8px">Four channels through four webhooks in <code>/etc/arise/secrets/discord.toml</code> (docs/DISCORD.md). The addresses never reach this page.</p>
        <div class="kv">${['alerts', 'sunday', 'weekly', 'daily'].map(k => `<dt>#${k}</dt><dd>${ch[k] ? 'set' : '<span class="muted">not set</span>'} <button class="btn btn--ghost btn--xs" data-dtest="${k}">Test</button></dd>`).join('')}</div>
        <p class="note" style="margin-top:8px">#sunday gets the all-green an hour before each service, Glory Night and Alexandria included. #weekly gets the Monday report at 07:30.</p>
        <h3 style="margin:16px 0 8px">The Monday report</h3><pre class="log pre" id="rpWeekly">${esc(r.weekly || r.error || '')}</pre><div class="row" style="margin-top:8px"><button class="btn btn--ghost btn--xs" id="rpSend">Post it to #weekly now</button></div>
        <p class="note" style="margin-top:6px">Channel: ${c.ok ? `${fmtN(c.subscribers)} subscribers (${fmtN(c.subs_left)} to 1,000) · ${fmtN(c.watch_hours)} public watch hours (${fmtN(c.hours_left)} to 4,000)${c.as_of ? ', as of ' + esc(c.as_of) : ''}${c.demo ? ' · sample' : ''}` : 'numbers not available yet (the automator keeps none on this box)'}</p>
        <h3 style="margin:16px 0 8px">The pastors' monthly note</h3><p class="note" style="margin-bottom:8px">Drafted from the month's own facts. Read it, change anything, then send it: nothing goes to the pastors until you press Send.</p>
        ${p.ok === false ? `<p class="note" style="color:var(--warn)">${esc(p.err)}</p>` : `<div class="row" style="gap:8px;margin-bottom:8px"><span class="muted">${esc(p.month)} · to ${esc((p.to || []).join(', ') || 'the pastors in [storage] pastors')}${p.sent ? ` · sent ${esc(p.sent)} by ${esc(p.sent_by)}` : ''}</span></div>
        <textarea id="rpNote" data-month="${esc(p.month || '')}" rows="8" style="width:100%" ${p.sent ? 'readonly' : ''}>${esc(p.draft || '')}</textarea>
        <div class="row" style="margin-top:8px;gap:8px">${p.sent ? '' : '<button class="btn btn--ghost btn--xs" id="rpSave">Save</button><button class="btn btn--xs" id="rpPastors">Send to the pastors…</button>'}</div>`}`);
    }
    return setView();
  };
  V.settings.after = root => {
    setAfter(root);
    $$('[data-wgset]', root).forEach(cb => cb.onchange = () => widgetSet(cb.dataset.wgset, cb.checked));
    $$('[data-lpshow]', root).forEach(b => b.onclick = () => { lpHide(b.dataset.lpshow, false); rerender('settings'); });
    $$('[data-dtest]', root).forEach(b => b.onclick = () => act(b, () => api('/reports/discord/test', { method: 'POST', body: { channel: b.dataset.dtest } }), `A test line went to #${b.dataset.dtest}`));
    const send = $('#rpSend', root); if (send) send.onclick = () => act(send, () => api('/reports/weekly', { method: 'POST' }), 'Posted to #weekly');
    const sv = $('#rpSave', root); if (sv) sv.onclick = () => act(sv, () => api('/reports/pastors', { method: 'PUT', body: { month: $('#rpNote', root).dataset.month, text: $('#rpNote', root).value } }).then(r => { if (r.ok === false) throw new Error(r.err); return r; }), 'Saved');
    const ps = $('#rpPastors', root); if (ps) ps.onclick = async () => {
      const p = await api('/reports/pastors').catch(() => ({})); const text = $('#rpNote', root).value;
      confirmType('Send the note to the pastors', 'send', `It goes by email to ${esc((p.to || []).join(' and '))}, as you see it. Type <b>send</b> to send it.`, async () => {
        const r = await api('/reports/pastors/send', { method: 'POST', body: { month: p.month, text } }); if (r.ok === false) throw new Error(r.err);
        toast(r.demo ? 'Sample mode: nothing was emailed' : `Sent to ${r.sent_to.join(', ')}${r.no_email.length ? ' (no email for ' + r.no_email.join(', ') + ')' : ''}`); rerender('settings'); });
    };
  };
}

/* Activity Monitor → Network: the hourly speed test (121) */
{
  const actView = V.activity, actAfter = V.activity.after;
  V.activity = async () => {
    let html = await actView();
    if (!S.speed || Date.now() - (S.speedAt || 0) > 60000) { try { S.speed = await api('/speedtest'); S.speedAt = Date.now(); } catch { S.speed = S.speed || { runs: [] }; } }
    const on = S.actTab === 'network';
    html = html.replace(/(<div class="tabs" id="actTabs">)([\s\S]*?)(<\/div>)/, (m0, a, b, c) => a + b.replace(/class="active"/g, on ? 'class=""' : 'class="active"') + `<button class="${on ? 'active' : ''}" data-t="network">Network</button>` + c);
    if (on) html = html.replace(/<div data-tab="procs"(?![^>]*hidden)/, '<div data-tab="procs" hidden').replace(/<div data-tab="containers"(?![^>]*hidden)/, '<div data-tab="containers" hidden');
    const sp = S.speed || {}, last = sp.last, wk = sp.week || {};
    const net = `<div data-tab="network" ${on ? '' : 'hidden'}><div class="panel panel--flat"><div class="panel__hd"><h3>Internet speed, every hour</h3><span class="muted">${esc(sp.plan || '')}</span></div>
      ${last ? `<div class="grid" style="margin-bottom:10px"><div class="c4"><div class="stat"><span class="stat__l">Down</span><span class="stat__v">${esc(last.down ?? '—')}<small> Mb/s</small></span><span class="stat__n">week median ${esc(wk.down ?? '—')}</span></div></div>
        <div class="c4"><div class="stat"><span class="stat__l">Up</span><span class="stat__v">${esc(last.up ?? '—')}<small> Mb/s</small></span><span class="stat__n">week median ${esc(wk.up ?? '—')}</span></div></div>
        <div class="c4"><div class="stat"><span class="stat__l">Ping</span><span class="stat__v">${esc(last.ping ?? '—')}<small> ms</small></span><span class="stat__n">${wk.failed ? wk.failed + ' failed this week' : 'none failed this week'}</span></div></div></div>
        <svg class="spdchart" id="spdChart" viewBox="0 0 700 160" preserveAspectRatio="none" role="img" aria-label="Download speed over the last week"></svg>` : '<p class="muted">No test yet: the first runs within the hour.</p>'}
      <div class="row" style="margin-top:10px"><button class="btn btn--ghost btn--xs" id="spdRun">Test now</button><span class="muted" style="font-size:12px">Cloudflare's speed test, about 25 MB down and 5 MB up; never during a service.${sp.demo ? ' Sample.' : ''}</span></div></div></div>`;
    return html.replace(/(<p class="note" style="margin-top:12px">Refreshes every 3 seconds)/, net + '$1');
  };
  V.activity.after = root => {
    actAfter(root);
    $$('#actTabs button', root).forEach(b => b.onclick = () => { S.actTab = b.dataset.t === 'procs' ? undefined : b.dataset.t; rerender('activity'); });
    const run = $('#spdRun', root); if (run) run.onclick = () => act(run, () => api('/speedtest', { method: 'POST' }).then(r => { S.speedAt = 0; return r; }), 'Tested');
    const svg = $('#spdChart', root); const runs = (S.speed?.runs || []).filter(r => r.down != null); if (!svg || runs.length < 2) return;
    const max = Math.max(...runs.map(r => r.down)) * 1.1, W = 700, H = 160, step = W / (runs.length - 1);
    const pts = runs.map((r, i) => `${(i * step).toFixed(1)},${(H - (r.down / max) * (H - 14)).toFixed(1)}`).join(' ');
    svg.innerHTML = `<polyline points="0,${H} ${pts} ${W},${H}" fill="rgba(214,34,45,.18)" stroke="none"/><polyline points="${pts}" fill="none" stroke="var(--red)" stroke-width="2"/><text x="4" y="12" fill="var(--text2)" font-size="11">${Math.round(max / 1.1)} Mb/s</text>`;
  };
}

/* Songs → the Lyrics inbox (99, 100) and the CCLI usage report (106) */
{
  const songsList = chSongs;
  chSongs = async function () {
    await songsList();
    if (SG.open) return;
    const bar = $('#chSongs .chbar'); if (!bar || $('#sgInbox', bar)) return;
    bar.insertAdjacentHTML('beforeend', '<button class="btn btn--ghost btn--xs" id="sgInbox">Lyrics inbox</button><button class="btn btn--ghost btn--xs" id="sgUsage">CCLI usage</button>');
    $('#sgInbox', bar).onclick = async () => {
      const r = await api('/songs/inbox').catch(e => ({ runs: [], error: e.message }));
      modal(`<h2>Lyrics inbox</h2><p class="muted">Export songs from Proclaim (or SongSelect) and drop the files into <b>${esc(r.folder || 'Lyrics inbox')}</b> in Nextcloud. Every 15 minutes they come into this list, matched by CCLI number, and the file moves to Imported. ${(r.users || []).length ? esc(r.users.join(' and ')) : 'Bradly and the worship leader ([songs] inbox_users)'} see the folder.</p>
        ${(r.runs || []).length ? r.runs.slice(0, 6).map(x => `<div class="panel panel--flat" style="margin-top:10px"><div class="row row--between"><b>${esc(fmtDay(x.at))} ${esc(fmtClock(x.at))}</b><span class="muted">${x.files} file(s) · ${x.linked} linked · ${x.unlinked} kept unlinked · ${x.failed} not imported</span></div>${(x.results || []).map(y => `<div class="widget__row"><span>${esc(y.name)}</span><b class="${y.ok ? '' : 'bad'}">${esc(y.ok ? (y.matched_by ? 'linked by ' + y.matched_by : y.note || 'kept') : y.err || 'not imported')}</b></div>`).join('')}</div>`).join('') : '<p class="note" style="margin-top:10px">Nothing has come through yet.</p>'}
        <div class="acts"><button class="btn btn--ghost" id="sgInRun">Check the inbox now</button><button class="btn btn--ghost" data-close>Close</button></div>`, m => { $('#sgInRun', m).onclick = () => act($('#sgInRun', m), () => api('/songs/inbox', { method: 'POST' }), 'Checked'); });
    };
    $('#sgUsage', bar).onclick = async () => {
      const r = await api('/songs/usage').catch(e => ({ songs: [], error: e.message }));
      modal(`<h2>CCLI song usage · ${esc(r.label || '')}</h2><p class="muted">From the set lists: ${r.services ?? 0} services. Titles and numbers as song_bank.json has them; no lyrics. The quarterly copy is written to <code>songs/reports/</code> on the first of January, April, July and October.</p>
        <div class="tbl-wrap" style="margin-top:10px"><table class="tbl"><thead><tr><th>Song</th><th>CCLI</th><th class="num">Times</th></tr></thead><tbody>${(r.songs || []).map(x => `<tr><td>${esc(x.title)}</td><td class="mono">${esc(x.ccli || (x.original ? 'Arise original' : '—'))}</td><td class="num">${x.times}</td></tr>`).join('') || '<tr><td colspan="3" class="muted">No set lists in this quarter.</td></tr>'}</tbody></table></div>
        ${(r.no_number || []).length ? `<p class="note" style="color:var(--warn);margin-top:8px">No CCLI number banked for: ${r.no_number.map(esc).join(', ')}. Look them up in SongSelect; nothing is guessed.</p>` : ''}
        <div class="acts"><button class="btn btn--ghost" data-close>Close</button></div>`);
    };
  };
}
// ===== end R7-C =====

/* ---------------- sign-in PINs (round 7, rows 160 to 162) ---------------- */
// Never the PIN in a page, a toast or a log: the server keeps a hash only, and admins can remove one, never see it.
function pinWords(st) {
  if (!st || !st.set) return st && st.kind === 'checklist' ? 'Off. A PIN opens the phone checklist, on the phone you set it on.' : 'Off. A PIN signs you in instead of your password; the risky clicks still ask for the password.';
  const where = st.scope === 'checklist' ? (st.this_device ? 'the phone checklist, on this phone' : 'the phone checklist, on the phone you set it on') : 'the sign-in page and the lock screen';
  return st.off ? `Switched off (${st.reason || 'too many wrong PINs'}). Your next password sign-in switches it back on.` : `On since ${fmtT(st.since)}: ${where}.`;
}
async function pinSheet() {
  let st; try { st = await api('/auth/pin/status'); } catch (er) { return toast(er.message, 'bad'); }
  modal(`<h2>Sign-in PIN</h2><p class="note" id="pnSt">${esc(pinWords(st))}</p>
    <p class="note" style="margin-top:8px">4 to 8 digits. Not one digit again and again, not a run like 1234, not your birthday or the end of your mobile number. ${st.kind === 'checklist' ? 'It works on the phone checklist, on the phone you set it on.' : 'It works on the sign-in page and the lock screen.'} The password always works too, and it is still asked for reauthorising, the Pastors folder, the FileVault and ariseadmin reveals, deletes, emptying the Trash and the YouTube renewal.</p>
    <div class="row" style="gap:10px;align-items:flex-start;margin-top:12px"><div class="field" style="flex:1"><label>New PIN</label><input id="pnA" type="password" inputmode="numeric" maxlength="8" autocomplete="off"></div><div class="field" style="flex:1"><label>The same again</label><input id="pnB" type="password" inputmode="numeric" maxlength="8" autocomplete="off"></div></div>
    ${st.password_needed ? '<div class="field"><label>Your password (not a PIN)</label><input id="pnPw" type="password" autocomplete="current-password"><span class="hint">Setting a PIN asks for your full password unless you typed it in the last ten minutes.</span></div>' : ''}
    <div class="acts"><button class="btn btn--ghost" data-close>Close</button>${st.set ? '<button class="btn btn--ghost" id="pnRm">Remove my PIN</button>' : ''}<button class="btn" id="pnGo">${st.set ? 'Change the PIN' : 'Set the PIN'}</button></div>`, m => {
    $('#pnA', m).focus();
    $('#pnGo', m).onclick = async e => { const a = $('#pnA', m).value, b = $('#pnB', m).value;
      if (!/^\d{4,8}$/.test(a)) return toast('A PIN is 4 to 8 digits, nothing else.', 'bad');
      if (a !== b) return toast('The two PINs are not the same.', 'bad');
      const body = { pin: a }; const pw = $('#pnPw', m); if (pw) body.password = pw.value;
      const r = await act(e.target, () => api('/auth/pin/set', { method: 'POST', body }), 'PIN set');
      $('#pnA', m).value = ''; $('#pnB', m).value = ''; if (pw) pw.value = '';
      if (r && r.ok !== false) m.close(); };
    const rm = $('#pnRm', m); if (rm) rm.onclick = async e => { const r = await act(e.target, () => api('/auth/pin', { method: 'DELETE' }), 'PIN removed'); if (r && r.ok !== false) m.close(); };
  });
}
async function pinsModal() {
  let d; try { d = await api('/directory/pins'); } catch (er) { return toast(er.message, 'bad'); }
  const rows = Object.entries(d.pins || {});
  modal(`<h2>Sign-in PINs</h2><p class="note">Who has a PIN. You can remove one (it is recorded in the audit log); nobody can see or set someone else's PIN.</p>
    <div class="tbl-wrap"><table class="tbl" id="pinsTable"><thead><tr><th>User</th><th>Works on</th><th>Since</th><th></th></tr></thead><tbody>${rows.map(([u, x]) => `<tr><td class="mono">${esc(u)}</td><td>${x.scope === 'checklist' ? 'the phone checklist, one phone' : 'sign-in and lock screen'}${x.off ? ' <span class="pill warn">switched off</span>' : ''}</td><td class="dim">${fmtT(x.since)}</td><td><button class="btn btn--ghost btn--xs" data-pinrm="${esc(u)}">Remove</button></td></tr>`).join('') || '<tr><td class="dim" colspan="4">Nobody has a PIN yet.</td></tr>'}</tbody></table></div>
    <div class="acts"><button class="btn btn--ghost" data-close>Close</button></div>`, m => {
    $$('[data-pinrm]', m).forEach(b => b.onclick = async e => { const u = b.dataset.pinrm;
      const r = await act(e.target, () => api(`/directory/users/${encodeURIComponent(u)}/pin`, { method: 'DELETE' }), `${u}'s PIN removed`);
      if (r && r.ok !== false) { m.close(); pinsModal(); } });
  });
}

window.arise = { api, cleanDesc, profileSheet, pinSheet, pinsModal, updatesBadge, pinApp, dockPins, applyDockHide, greet, openApp, closeApp, minApp, focusWin, rerender, toggleLaunchpad, toggleNC, toggleCC, toggleSpot, missionControl, switcher, lockScreen, showLogin, signOut, saver, toast, tone, walkthrough, toggleTheme, calcEval, shortcutsSheet, snapTo, applyA11y, twofaModal, reauth, withReauth, S, APPS, buildDeskIcons, setupWizard, notifyBadge };
})();
