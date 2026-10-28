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
  if (S.demoOnly) { const d = demoLookup(method, path); if (d) return structuredClone(d); return { demo: true, error: { message: 'not in the preview' } }; }
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
  $('#demoBadge').hidden = false; $('#demoBadge').textContent = 'Preview · sample data';
}

/* ---------------- toasts / modal ---------------- */
function toast(msg, kind = 'ok', ms = 4200) {
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
      <p class="note" style="margin-top:14px">A missed night is skipped, not lost: every job is resumable. If the PC was off, the timers run when it next boots (Persistent=true).</p></div>
  </div>`;
};

V.directory = async () => {
  const [st, us, gs, cs, tf] = await Promise.all([api('/directory/status'), api('/directory/users'), api('/directory/groups'), api('/directory/computers'), api('/directory/2fa').catch(() => ({ users: [] }))]);
  const users = us.users || [], groups = gs.groups || [], comps = cs.computers || []; const twofaOn = new Set(tf.users || []);
  const kind = k => ({ mac: '', windows: '⊞', nas: '▤', pc: '▣' })[k] || '▣';
  return `
  <div class="fade">
    <div class="grid" style="margin-bottom:14px">
      <div class="c3 panel ${st.ldap_ok ? 'panel--ok' : 'panel--bad'}"><div class="stat"><span class="stat__l">Domain</span><span class="stat__v" style="font-size:22px">${esc(st.netbios)}</span><span class="stat__n">${esc(st.realm)}<br>${esc(st.dc || '')}</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Health</span><div class="row" style="margin-top:6px"><span class="pill ${st.ldap_ok ? 'ok' : 'bad'}">LDAP</span><span class="pill ${st.kerberos_ok ? 'ok' : 'bad'}">Kerberos</span><span class="pill ${st.dns_ok ? 'ok' : 'bad'}">DNS</span></div><span class="stat__n">forest level ${esc(st.forest_level || '—')}</span>${st.error ? `<span class="stat__n" style="color:var(--redL)">${esc(st.error)}</span>` : ''}</div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Accounts</span><span class="stat__v">${users.length}<small>users</small></span><span class="stat__n">${groups.length} groups · ${comps.length} computers</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Join a Mac</span><span class="stat__n" style="margin-top:4px">On the Mac: <code>sudo ./mac/bind-mac.sh --computer-name MEDIA-MAC</code><br>Then log in as a domain user. Full steps in docs/MAC-MIGRATION.md.</span></div></div>
    </div>
    <div class="tabs" id="dirTabs"><button class="active" data-t="users">Users</button><button data-t="groups">Groups</button><button data-t="computers">Computers</button></div>
    <div data-tab="users">
      <div class="toolbar"><input class="search" placeholder="Find a user" id="uq"><span class="spacer"></span><button class="btn btn--sm" id="addUser">+ New user</button></div>
      <div class="panel panel--flat tbl-wrap"><table class="tbl" id="uTable"><thead><tr><th>User</th><th>Name</th><th>Groups</th><th>Last login</th><th>Home</th><th></th></tr></thead><tbody>
      ${users.map(u => `<tr data-q="${esc((u.name + ' ' + u.display).toLowerCase())}"><td><b>${esc(u.name)}</b> ${u.enabled ? '' : '<span class="pill warn">disabled</span>'}${twofaOn.has(u.name) ? ' <span class="pill info" title="Two-step sign-in is on">two-step</span>' : ''}</td><td>${esc(u.display)}</td><td>${(u.groups || []).map(g => `<span class="tag">${esc(g)}</span>`).join('')}</td><td class="dim">${u.last_logon ? fmtT(u.last_logon) : 'never'}</td><td class="mono dim" style="font-size:12px">${esc(u.home || '')}</td>
        <td class="acts"><button class="btn btn--ghost btn--xs" data-pw="${esc(u.name)}">Password</button><button class="btn btn--ghost btn--xs" data-tog="${esc(u.name)}" data-en="${u.enabled ? 0 : 1}">${u.enabled ? 'Disable' : 'Enable'}</button><button class="btn btn--danger btn--xs" data-del="${esc(u.name)}">Delete</button></td></tr>`).join('') || '<tr><td colspan="6" class="empty">No users yet</td></tr>'}
      </tbody></table></div>
    </div>
    <div data-tab="groups" hidden>
      <div class="toolbar"><span class="spacer"></span><button class="btn btn--sm" id="addGroup">+ New group</button></div>
      <div class="cards">${groups.map(g => `<div class="card"><h3>${esc(g.name)}</h3><p>${esc(g.description || '')}<br><span style="color:var(--muted)">${g.members.length} member${g.members.length === 1 ? '' : 's'}</span></p><div>${g.members.map(m => `<span class="tag">${esc(m)}</span>`).join('') || '<span class="tag" style="opacity:.5">empty</span>'}</div><div class="row"><button class="btn btn--ghost btn--xs" data-addm="${esc(g.name)}">+ Add member</button></div></div>`).join('')}</div>
    </div>
    <div data-tab="computers" hidden>
      <div class="panel panel--flat tbl-wrap"><table class="tbl"><thead><tr><th>Computer</th><th>Type</th><th>OS</th><th>IP</th><th>Last seen</th></tr></thead><tbody>
      ${comps.map(c => `<tr><td><b>${esc(c.name)}</b></td><td>${kind(c.kind)} ${esc(c.kind)}</td><td>${esc(c.os || '—')}</td><td class="mono dim">${esc(c.ip || '—')}</td><td class="dim">${c.last_seen ? fmtT(c.last_seen) : '—'}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">Nothing has joined the domain yet</td></tr>'}
      </tbody></table></div>
      <p class="note" style="margin-top:14px">Windows: Settings → System → About → <b>Domain or workgroup</b> → join <b>${esc(st.realm)}</b>. Synology: Control Panel → Domain/LDAP → Join Domain (see docs/SYNOLOGY.md). Macs: the bind script above.</p>
    </div>
  </div>`;
};
V.directory.after = () => {
  tabs('#dirTabs');
  $('#uq').oninput = e => { const q = e.target.value.toLowerCase(); $$('#uTable tbody tr').forEach(tr => tr.hidden = q && !(tr.dataset.q || '').includes(q)); };
  $('#addUser').onclick = () => modal(`<h2>New user</h2>
    <div class="field"><label>User name</label><input id="nuName" placeholder="firstname" autocomplete="off"><span class="hint">Lowercase, no spaces. This is what they type on the Mac.</span></div>
    <div class="field"><label>Full name</label><input id="nuDisp" placeholder="Shown on the Mac login"></div>
    <div class="field"><label>Password</label><input id="nuPw" type="password" autocomplete="new-password"><span class="hint">8+ characters. They can change it on the Mac after first login.</span></div>
    <div class="field"><label>Groups</label><input id="nuGroups" placeholder="Staff, Media"><span class="hint">Comma-separated, existing groups only.</span></div>
    <div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="nuGo">Create</button></div>`, m => {
    $('#nuGo', m).onclick = async e => { const r = await act(e.target, () => api('/directory/users', { method: 'POST', body: { name: $('#nuName', m).value.trim(), display: $('#nuDisp', m).value.trim(), password: $('#nuPw', m).value, groups: $('#nuGroups', m).value.split(',').map(s => s.trim()).filter(Boolean) } }), 'User created'); if (r && r.ok !== false) { m.close(); rerender('directory'); } };
  });
  $$('[data-pw]').forEach(b => b.onclick = () => modal(`<h2>Reset password</h2><p class="note" style="margin-bottom:14px">For <b>${esc(b.dataset.pw)}</b>. Their Mac asks for the new one at next login; the cached mobile account updates then.</p><div class="field"><label>New password</label><input id="rpPw" type="password"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="rpGo">Set</button></div>`, m => { $('#rpGo', m).onclick = async e => { const r = await act(e.target, () => api(`/directory/users/${encodeURIComponent(b.dataset.pw)}/reset-password`, { method: 'POST', body: { password: $('#rpPw', m).value } }), 'Password set'); if (r && r.ok !== false) m.close(); }; }));
  $$('[data-tog]').forEach(b => b.onclick = async () => { const r = await act(b, () => api(`/directory/users/${encodeURIComponent(b.dataset.tog)}/${b.dataset.en === '1' ? 'enable' : 'disable'}`, { method: 'POST' }), b.dataset.en === '1' ? 'Enabled' : 'Disabled'); if (r && r.ok !== false) rerender('directory'); });
  $$('[data-del]').forEach(b => b.onclick = () => confirmType('Delete user', b.dataset.del, `This removes the account from the domain. <b>The home folder stays on disk</b> - nothing in it is deleted. Deleting is your click, not the server's.`, async () => { const r = await withReauth(() => api(`/directory/users/${encodeURIComponent(b.dataset.del)}`, { method: 'DELETE', body: { confirm: b.dataset.del } })); if (r.ok === false) throw new Error(r.err); toast('User deleted'); rerender('directory'); }));
  $('#addGroup').onclick = () => modal(`<h2>New group</h2><div class="field"><label>Name</label><input id="ngName" placeholder="Praise-Team"></div><div class="field"><label>Description</label><input id="ngDesc"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="ngGo">Create</button></div>`, m => { $('#ngGo', m).onclick = async e => { const r = await act(e.target, () => api('/directory/groups', { method: 'POST', body: { name: $('#ngName', m).value.trim(), description: $('#ngDesc', m).value.trim() } }), 'Group created'); if (r && r.ok !== false) { m.close(); rerender('directory'); } }; });
  $$('[data-addm]').forEach(b => b.onclick = () => modal(`<h2>Add to ${esc(b.dataset.addm)}</h2><div class="field"><label>User name</label><input id="amUser"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="amGo">Add</button></div>`, m => { $('#amGo', m).onclick = async e => { const r = await act(e.target, () => api(`/directory/groups/${encodeURIComponent(b.dataset.addm)}/members`, { method: 'POST', body: { user: $('#amUser', m).value.trim() } }), 'Added'); if (r && r.ok !== false) { m.close(); rerender('directory'); } }; }));
};

V.shares = async () => {
  const r = await api('/shares');
  const shares = r.shares || [];
  return `<div class="fade">
    <div class="toolbar"><span class="note" style="flex:1 1 auto">On a Mac: Finder → Go → Connect to Server → <b>smb://arise-server</b>. On Windows: <b>\\\\arise-server</b>. Sign in with the domain account.</span><button class="btn btn--sm" id="addShare">+ New share</button></div>
    <div class="cards">${shares.map(s => `<div class="card"><div class="row row--between"><h3>${esc(s.name)}</h3>${s.mac ? '<span class="pill info">Mac-ready</span>' : ''}</div><p>${esc(s.comment || '')}<br><span class="mono" style="font-size:12px;color:var(--muted)">${esc(s.path)}</span></p>
      <div class="kv"><dt>Used</dt><dd>${s.used != null ? fmtB(s.used) : '—'}</dd><dt>Access</dt><dd>${s.writable ? 'read & write' : 'read only'}${s.browseable ? '' : ' · hidden'}</dd></div>
      ${['homes', 'sysvol', 'netlogon'].includes(s.name) ? '' : `<div class="row"><button class="btn btn--danger btn--xs" data-rm="${esc(s.name)}">Remove share</button></div>`}</div>`).join('') || '<div class="empty">No shares defined</div>'}</div>
    <div class="grid" style="margin-top:14px"><div class="c6 panel panel--flat"><div class="panel__hd"><h3>How homes work</h3></div><p style="font-size:13.5px;color:var(--text2)">Every domain user gets <code>homes/&lt;user&gt;</code>, visible to them alone. A Mac with a mobile account keeps a cached copy and syncs Desktop and Documents to it. Move an old Mac's data in with <code>mac/migrate-mac-user.sh</code>.</p></div>
    <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Where the big files go</h3></div><p style="font-size:13.5px;color:var(--text2)">Service recordings, graphics and the podcast masters belong on the Synology's <code>media</code> share: four drives with redundancy. The old PC's single disk holds the directory, the automator and the apps, and is backed up to the NAS nightly.</p></div></div>
  </div>`;
};
V.shares.after = () => {
  $('#addShare').onclick = () => modal(`<h2>New share</h2><div class="field"><label>Name</label><input id="nsName" placeholder="graphics"></div><div class="field"><label>Folder on the server</label><input id="nsPath" placeholder="/srv/arise/shares/graphics"></div><div class="field"><label>Who can use it</label><input id="nsGroup" value="Domain Users"><span class="hint">A group name. "Domain Users" is everyone.</span></div><div class="field"><label>Description</label><input id="nsComment"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="nsGo">Create</button></div>`, m => { $('#nsGo', m).onclick = async e => { const r = await act(e.target, () => api('/shares', { method: 'POST', body: { name: $('#nsName', m).value.trim(), path: $('#nsPath', m).value.trim(), group: $('#nsGroup', m).value.trim(), comment: $('#nsComment', m).value.trim(), mac: true } }), 'Share created'); if (r && r.ok !== false) { m.close(); rerender('files'); } }; });
  $$('[data-rm]').forEach(b => b.onclick = () => confirmType('Remove share', b.dataset.rm, 'The share stops being visible on the network. <b>The folder and its files stay on disk.</b>', async () => { const r = await api(`/shares/${encodeURIComponent(b.dataset.rm)}`, { method: 'DELETE', body: { confirm: b.dataset.rm } }); if (r.ok === false) throw new Error(r.err); toast('Share removed'); rerender('files'); }));
};

V.backups = async () => {
  const [jobs, hist, repo, snaps] = await Promise.all([api('/backups/jobs'), api('/backups/history?limit=120'), api('/backups/repo'), api('/backups/snapshots?limit=40')]);
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
    <div class="panel panel--flat" style="margin-bottom:14px"><div class="panel__hd"><h3>Jobs</h3><span class="sub">${esc(jobs.file || '')}</span></div><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Job</th><th>What</th><th>Last run</th><th>Result</th><th class="num">Added</th><th></th></tr></thead><tbody>
    ${(jobs.jobs || []).map(j => { const l = lastOf(j.id), run = running.find(r => r.job === j.id); return `<tr><td><b>${esc(j.name || j.id)}</b><br><span class="dim" style="font-size:11px">${(j.tags || []).map(t => `<span class="tag">${esc(t)}</span>`).join('')}</span></td><td class="mono dim" style="font-size:12px">${(j.paths || []).map(esc).join('<br>')}</td><td class="dim">${l ? fmtT(l.started) : 'never'}</td><td>${run ? '<span class="pill info">running</span>' : l ? `<span class="pill ${l.ok ? 'ok' : 'bad'}">${l.ok ? 'ok' : 'failed'}</span>` : '<span class="pill">—</span>'}</td><td class="num">${l?.ok ? fmtB(l.bytes_added) : '—'}</td><td class="acts"><button class="btn btn--ghost btn--xs" data-run="${esc(j.id)}" ${run ? 'disabled' : ''}>Run now</button></td></tr>`; }).join('')}
    </tbody></table></div></div>
    <div class="tabs" id="bkTabs"><button class="active" data-t="hist">History</button><button data-t="snaps">Snapshots</button><button data-t="restore">Restore</button></div>
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
  tabs('#bkTabs');
  $$('[data-run]').forEach(b => b.onclick = async () => { const r = await act(b, () => api(`/backups/run/${encodeURIComponent(b.dataset.run)}`, { method: 'POST' }), `Started ${b.dataset.run}; the row appears when it finishes`); if (r) setTimeout(render, 2500); });
  $('#bkCheck').onclick = e => act(e.target, () => api('/backups/check', { method: 'POST' }), 'Check started; it can take a while on a big repo');
  $('#bkMirror').onclick = e => act(e.target, () => api('/backups/mirror', { method: 'POST' }), 'Mirror refreshed');
};

V.automator = async () => {
  const [a, wl, h] = await Promise.all([api('/automator'), api('/automator/worklist'), api('/automator/holds')]);
  const q = pct(a.quota_today, a.quota_daily);
  return `<div class="fade">
    <div class="grid" style="margin-bottom:14px">
      <div class="c3 panel ${a.last_ok === false ? 'panel--bad' : a.last_ok ? 'panel--ok' : 'panel--warn'}"><div class="stat"><span class="stat__l">Last run</span><span class="stat__v" style="font-size:22px">${a.last_run ? ago(a.last_run) : 'never'}</span><span class="stat__n">${esc(a.last_summary || 'no report on this server yet')}</span></div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Quota today</span><span class="stat__v">${fmtN(a.quota_today ?? 0)}<small>/ ${fmtN(a.quota_daily)}</small></span><span class="stat__n">resets ${esc(a.quota_reset || '2 AM Central')} · next run ${fmtT(a.next_run)}</span></div><div class="meter ${q > 75 ? 'meter--warn' : 'meter--ok'}"><i style="width:${q}%"></i></div></div>
      <div class="c3 panel ${a.token_ok ? (a.token_days_left != null && a.token_days_left <= 2 ? 'panel--warn' : 'panel--ok') : 'panel--bad'}"><div class="stat"><span class="stat__l">Sign-in</span><span class="stat__v" style="font-size:22px">${a.token_ok ? 'token ok' : 'no token'}</span><span class="stat__n">${esc(a.signed_in_as || '')}${a.token_days_left != null ? ` · ~${a.token_days_left} days before Google expires it` : ''}</span>${a.token_note ? `<span class="stat__n" style="color:var(--warn)">${esc(a.token_note)}</span>` : ''}</div></div>
      <div class="c3 panel panel--flat"><div class="stat"><span class="stat__l">Guard rails</span><span class="stat__v">${a.holds}<small>on hold</small></span><span class="stat__n">${a.rules} standing rules · ${a.worklist_enabled} of ${a.worklist_total} jobs enabled</span></div><div class="row" style="margin-top:10px"><button class="btn btn--ghost btn--xs" id="auPreview">Preview tonight</button><button class="btn btn--xs" id="auRun">Run now</button></div></div>
    </div>
    ${a.manual?.started ? `<p class="note" style="margin-bottom:14px"><b>${esc(a.manual.mode)}</b> started ${fmtT(a.manual.started)} · ${a.manual.finished ? (a.manual.ok ? 'finished ok' : `failed: ${esc(a.manual.error || 'exit ' + a.manual.code)}`) : 'still running'} · output in last-run.log</p>` : ''}
    <div class="tabs" id="auTabs"><button class="active" data-t="report">Latest report</button><button data-t="work">Worklist</button><button data-t="holds">Hold list</button><button data-t="reports">Past reports</button></div>
    <div data-tab="report" class="panel panel--flat"><div class="md">${md(a.latest_report)}</div></div>
    <div data-tab="work" hidden class="panel panel--flat tbl-wrap"><table class="tbl"><thead><tr><th>#</th><th>Job</th><th>Note</th><th class="num">Est. units</th><th>State</th></tr></thead><tbody>
      ${(wl.jobs || []).map(j => `<tr><td class="num dim">${esc(j.priority ?? '')}</td><td><b>${esc(j.id)}</b></td><td style="font-size:13px;color:var(--text2)">${esc(j.note || j.why || '')}</td><td class="num">${j.cost_estimate != null ? fmtN(j.cost_estimate) : '—'}</td><td>${j.enabled === false ? '<span class="pill warn">off</span>' : '<span class="pill ok">on</span>'}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">No worklist.json found</td></tr>'}
    </tbody></table><p class="note" style="margin-top:12px">The automator runs only what is in <code>worklist.json</code>, in priority order. To stop a job for a night set its <code>enabled</code> to false in that file - don't delete it; the note saying why it exists is worth keeping.</p></div>
    <div data-tab="holds" hidden><div class="grid"><div class="c6 panel panel--flat"><div class="panel__hd"><h3>Videos no script may write to</h3></div><table class="tbl"><tbody>${(h.videos || []).map(v => `<tr><td class="mono">${esc(v.id)}</td><td style="font-size:13px;color:var(--text2)">${esc(v.reason || '')}</td></tr>`).join('') || '<tr><td class="empty">none</td></tr>'}</tbody></table></div>
      <div class="c6 panel panel--flat"><div class="panel__hd"><h3>Standing rules</h3></div><ul style="padding-left:18px;font-size:13.5px;color:var(--text2)">${(h.rules || []).map(r => `<li style="margin:6px 0">${esc(typeof r === 'string' ? r : JSON.stringify(r))}</li>`).join('')}</ul><p class="note" style="margin-top:12px">Edited only in <code>holds.json</code>, read on every write by <code>hold_gate.py</code>. A missing hold file refuses every write - it fails closed.</p></div></div></div>
    <div data-tab="reports" hidden class="panel panel--flat"><div class="row" style="flex-wrap:wrap;gap:8px">${(a.reports || []).map(r => `<button class="btn btn--ghost btn--xs" data-rep="${esc(r)}">${esc(r.replace('.md', ''))}</button>`).join('') || '<span class="empty" style="width:100%">no reports yet</span>'}</div><div id="repBody" class="md" style="margin-top:16px"></div></div>
  </div>`;
};
V.automator.after = () => {
  tabs('#auTabs');
  $('#auPreview').onclick = e => act(e.target, () => api('/automator/preview', { method: 'POST' }), 'Preview started: a dry run, nothing is written to YouTube');
  $('#auRun').onclick = e => modal(`<h2>Run the automator now?</h2><p class="note" style="margin-bottom:14px">This spends real quota and writes to the channel exactly as the 02:05 run would. The hold list still applies. If a chat session is also working today, remember the 10,000 units are shared.</p><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="auGo">Run</button></div>`, m => { $('#auGo', m).onclick = async ev => { const r = await act(ev.target, () => api('/automator/run', { method: 'POST' }), 'Run started; the report appears when it finishes'); if (r) { m.close(); setTimeout(render, 3000); } }; });
  $$('[data-rep]').forEach(b => b.onclick = async () => { const r = await api(`/automator/reports/${encodeURIComponent(b.dataset.rep)}`); $('#repBody').innerHTML = md(r.text); });
};

V.apps = async () => {
  const [a, t] = await Promise.all([api('/apps'), api('/apps/templates')]);
  const installed = new Set((a.apps || []).map(x => x.template));
  return `<div class="fade">
    ${a.docker === false && !a.demo ? '<p class="note" style="margin-bottom:14px">Docker is not running on this server, so apps cannot be deployed. <code>sudo systemctl start docker</code> or run the installer again without --skip-docker.</p>' : ''}
    <div class="panel panel--flat" style="margin-bottom:14px"><div class="panel__hd"><h3>Installed</h3><span class="sub">${(a.apps || []).filter(x => x.status === 'running').length} running</span></div>
    ${(a.apps || []).length ? `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>App</th><th>State</th><th>Address</th><th class="num">CPU</th><th class="num">Memory</th><th></th></tr></thead><tbody>
      ${a.apps.map(x => `<tr><td><b>${esc(x.name)}</b></td><td><span class="pill ${x.status === 'running' ? 'ok' : 'warn'}">${esc(x.status)}</span></td><td>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener" style="color:var(--redL)">${esc(x.url)}</a>` : '—'}</td><td class="num">${x.cpu != null ? x.cpu.toFixed(1) + '%' : '—'}</td><td class="num">${fmtB(x.mem)}</td>
        <td class="acts">${x.status === 'running' ? `<button class="btn btn--ghost btn--xs" data-app="${esc(x.name)}" data-do="restart">Restart</button><button class="btn btn--ghost btn--xs" data-app="${esc(x.name)}" data-do="stop">Stop</button>` : `<button class="btn btn--ghost btn--xs" data-app="${esc(x.name)}" data-do="start">Start</button>`}<button class="btn btn--ghost btn--xs" data-app="${esc(x.name)}" data-do="update">Update</button><button class="btn btn--ghost btn--xs" data-logs="${esc(x.name)}">Logs</button><button class="btn btn--danger btn--xs" data-rmapp="${esc(x.name)}">Remove</button></td></tr>`).join('')}
    </tbody></table></div>` : '<div class="empty">Nothing installed yet. Pick one below.</div>'}</div>
    <div class="mark"><span class="kicker">App store · what the church uses</span></div>
    <div class="cards">${(t.templates || []).map(x => `<div class="card"><span class="cat">${esc(x.category)}</span><h3>${esc(x.name)}</h3><p>${esc(x.description)}</p>${x.notes ? `<p style="color:var(--warn);font-size:12px">${esc(x.notes)}</p>` : ''}<div class="row row--between"><span class="mono dim" style="font-size:11.5px">${(x.ports || []).map(esc).join(' · ')}</span>${installed.has(x.id) ? '<span class="pill ok">installed</span>' : `<button class="btn btn--sm" data-deploy="${esc(x.id)}">Install</button>`}</div></div>`).join('')}</div>
    <pre class="log" id="appLog" hidden style="margin-top:14px"></pre>
  </div>`;
};
V.apps.after = () => {
  $$('[data-deploy]').forEach(b => b.onclick = async () => { const r = await act(b, () => api('/apps/deploy', { method: 'POST', body: { template: b.dataset.deploy } }), `Installing ${b.dataset.deploy}; first start pulls the image`); if (r) setTimeout(render, 2000); });
  $$('[data-app]').forEach(b => b.onclick = async () => { const r = await act(b, () => api(`/apps/${encodeURIComponent(b.dataset.app)}/${b.dataset.do}`, { method: 'POST', body: {} }), `${b.dataset.do} sent`); if (r) setTimeout(render, 1500); });
  $$('[data-logs]').forEach(b => b.onclick = async () => { const r = await api(`/apps/${encodeURIComponent(b.dataset.logs)}/logs`); const p = $('#appLog'); p.hidden = false; p.textContent = r.text || '(empty)'; p.scrollIntoView({ behavior: 'smooth' }); });
  $$('[data-rmapp]').forEach(b => b.onclick = () => confirmType('Remove app', b.dataset.rmapp, 'Stops and removes the containers. <b>Its data folder is kept</b> under /srv/arise/apps.', async () => { const r = await api(`/apps/${encodeURIComponent(b.dataset.rmapp)}/remove`, { method: 'POST', body: { confirm: b.dataset.rmapp } }); if (r.ok === false) throw new Error(r.err); toast('Removed'); rerender('apps'); }));
};

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
V.nas.after = () => { const m = $('#nasMount'); if (m) m.onclick = e => act(e.target, () => api('/nas/mount', { method: 'POST' }), 'Mounted').then(render); const u = $('#nasUn'); if (u) u.onclick = e => act(e.target, () => api('/nas/unmount', { method: 'POST' }), 'Unmounted').then(render); };

V.services = async () => {
  const r = await api('/services');
  return `<div class="fade panel panel--flat tbl-wrap"><table class="tbl"><thead><tr><th>Service</th><th>Unit</th><th>State</th><th>Since</th><th></th></tr></thead><tbody>
    ${(r.services || []).map(s => `<tr><td><b>${esc(s.name)}</b></td><td class="mono dim" style="font-size:12px">${esc(s.unit)}</td><td><span class="pill ${s.active === 'active' ? 'ok' : s.active === 'failed' ? 'bad' : 'warn'}">${esc(s.active)}${s.sub ? ' · ' + esc(s.sub) : ''}</span></td><td class="dim">${s.since ? fmtT(s.since) : '—'}</td>
      <td class="acts"><button class="btn btn--ghost btn--xs" data-svc="${esc(s.unit)}" data-do="restart">Restart</button>${s.active === 'active' ? `<button class="btn btn--ghost btn--xs" data-svc="${esc(s.unit)}" data-do="stop">Stop</button>` : `<button class="btn btn--xs" data-svc="${esc(s.unit)}" data-do="start">Start</button>`}<a class="btn btn--ghost btn--xs" data-log="${esc(s.unit)}">Logs</a></td></tr>`).join('')}
  </tbody></table></div>`;
};
V.services.after = () => { $$('[data-log]').forEach(a => a.onclick = e => { e.preventDefault(); S.logUnit = a.dataset.log; openApp('logs'); }); $$('[data-svc]').forEach(b => b.onclick = async () => { if (b.dataset.svc === 'arise-web.service' && b.dataset.do !== 'restart') { toast('Stopping the dashboard from the dashboard is a bad idea', 'warn'); return; } const r = await act(b, () => api(`/services/${encodeURIComponent(b.dataset.svc)}/${b.dataset.do}`, { method: 'POST' }), `${b.dataset.do} ${b.dataset.svc}`); if (r) setTimeout(render, 1200); }); };

V.logs = async () => {
  const arg = S.logUnit;
  const units = ['arise-web.service', 'arise-automator.service', 'arise-backup.service', 'arise-mirror.service', 'samba-ad-dc.service', 'docker.service', 'arise-nas-mount.service'];
  const unit = decodeURIComponent(arg || units[0]);
  const r = await api(`/logs/${encodeURIComponent(unit)}?lines=300`);
  return `<div class="fade"><div class="toolbar"><select class="search" id="logUnit">${units.map(u => `<option ${u === unit ? 'selected' : ''}>${esc(u)}</option>`).join('')}</select><button class="btn btn--ghost btn--sm" id="logRefresh">Refresh</button><span class="spacer"></span><span class="sub" style="font-size:12px;color:var(--muted)">last 300 lines · journalctl -u ${esc(unit)}</span></div><pre class="log" style="max-height:72vh">${esc(r.text || '(empty)')}</pre></div>`;
};
V.logs.after = () => { $('#logUnit').onchange = e => { S.logUnit = e.target.value; rerender('logs'); }; $('#logRefresh').onclick = render; };

V.settings = async () => {
  const s = await api('/settings');
  const sec = (name, d) => `<div class="c6 panel panel--flat"><div class="panel__hd"><h3>${esc(name)}</h3></div><div class="kv">${Object.entries(d).map(([k, v]) => `<dt>${esc(k)}</dt><dd class="mono" style="font-size:12.5px">${esc(Array.isArray(v) ? v.join(', ') : typeof v === 'boolean' ? (v ? 'yes' : 'no') : (v === '' ? '—' : v))}</dd>`).join('')}</div></div>`;
  const [u, n] = await Promise.all([api('/system/updates').catch(() => ({})), api('/notify').catch(() => ({}))]);
  const sys = `<div class="grid" style="margin-bottom:14px">
    <div class="c4 panel ${u.apt_upgradable || u.arise_behind ? 'panel--warn' : 'panel--ok'}"><div class="panel__hd"><h3>Updates</h3><span class="sub">${u.last_check ? ago(u.last_check) : ''}</span></div>
      <div class="kv"><dt>Packages</dt><dd>${fmtN(u.apt_upgradable)} upgradable${u.security ? ` · <span style="color:var(--warn)">${u.security} security</span>` : ''}</dd><dt>Arise Server</dt><dd>${u.arise_behind == null ? 'not a git checkout' : u.arise_behind ? `${u.arise_behind} commit${u.arise_behind === 1 ? '' : 's'} behind` : 'up to date'}</dd></div>
      <div class="row" style="margin-top:12px"><button class="btn btn--xs" id="upArise">Update Arise Server</button><button class="btn btn--ghost btn--xs" id="upApt">Upgrade packages</button></div>
      <p class="note" style="margin-top:10px;font-size:12px">Updating Arise Server restarts the dashboard; the timers keep running. Package upgrades can take minutes.</p></div>
    <div class="c4 panel panel--flat"><div class="panel__hd"><h3>Daily note</h3><span class="pill ${n.configured ? 'ok' : ''}">${n.configured ? `webhook set · ${String(n.hour).padStart(2, '0')}:00` : 'not configured'}</span></div>
      <p style="font-size:13px;color:var(--text2)">Every morning the server sends what needs you (or nothing, when all is clear) to a Discord or Slack webhook, so a failed backup is known before anyone opens this page.</p>
      ${n.last ? `<div class="kv" style="margin-top:10px"><dt>Last</dt><dd>${fmtT(n.last.when)} · ${n.last.sent ? 'sent' : 'not sent'}${n.last.error ? ` · ${esc(n.last.error)}` : ''}</dd></div>` : ''}
      <div class="row" style="margin-top:12px"><button class="btn btn--ghost btn--xs" id="ntTest">Send a test</button></div>
      <p class="note" style="margin-top:10px;font-size:12px">Set <code>webhook_url</code> under <code>[notify]</code> in arise.toml.</p></div>
    <div class="c4 panel panel--bad"><div class="panel__hd"><h3>Power</h3><span class="sub">locked closet</span></div>
      <p style="font-size:13px;color:var(--text2)">The box lives where nobody can press its button. Both of these ask you to type the word. A reboot takes about a minute; the dashboard comes back on its own.</p>
      <div class="row" style="margin-top:12px"><button class="btn btn--ghost btn--xs" id="pwReboot">Reboot</button><button class="btn btn--danger btn--xs" id="pwOff">Shut down</button></div></div>
  </div>`;
  return sys + `<div class="fade"><p class="note" style="margin-bottom:14px">Read from <code>${esc(s._meta?.path)}</code>${s._meta?.found ? '' : ' <b>(not found: these are the defaults)</b>'}. The dashboard never writes this file; change it with <code>sudo nano ${esc(s._meta?.path)}</code> and <code>sudo systemctl restart arise-web</code>, or with <code>arisectl</code>. Secrets are never shown here.</p>
    <div class="grid">${['system', 'web', 'directory', 'automator', 'backups', 'nas', 'apps', 'github', 'paths'].filter(k => s[k]).map(k => sec(k, s[k])).join('')}</div></div>`;
};
V.settings.after = () => {
  $('#upArise').onclick = e => modal(`<h2>Update Arise Server?</h2><p class="note" style="margin-bottom:14px">Pulls the latest code from GitHub, installs any new Python libraries, reinstalls arisectl and the units, and restarts the dashboard. This page reloads when it is back.</p><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="upGo">Update</button></div>`, m => { $('#upGo', m).onclick = async ev => { const r = await act(ev.target, () => api('/system/update', { method: 'POST' }), 'Updated; reloading'); if (r) { m.close(); setTimeout(() => location.reload(), 4000); } }; });
  $('#upApt').onclick = e => act(e.target, () => api('/system/apt-upgrade', { method: 'POST' }), 'Packages upgraded');
  $('#ntTest').onclick = e => act(e.target, () => api('/notify/test', { method: 'POST' }), 'Test note sent');
  $('#pwReboot').onclick = () => confirmType('Reboot the server', 'reboot', 'Everything stops for about a minute: the directory, the shares, the apps. Logged-in Macs keep working on cached accounts. The dashboard comes back by itself.', async () => { const r = await api('/system/power', { method: 'POST', body: { action: 'reboot', confirm: 'reboot' } }); if (r.ok === false) throw new Error(r.err); toast('Rebooting…', 'warn', 8000); });
  $('#pwOff').onclick = () => confirmType('Shut the server down', 'poweroff', '<b>Someone has to walk to the closet to turn it back on.</b> Nothing on it runs until then: no logins against the domain, no 02:05 automator, no backups.', async () => { const r = await api('/system/power', { method: 'POST', body: { action: 'poweroff', confirm: 'poweroff' } }); if (r.ok === false) throw new Error(r.err); toast('Shutting down.', 'warn', 8000); });
};


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
  if (S.me?.roots?.length && !S.me.roots.some(r => r.id === fs.root)) Object.assign(fs, { root: S.me.roots[0].id, path: '/', hist: [], fwd: [] });
  const [roots, list] = await Promise.all([api('/files/roots'), api(`/files/list?root=${encodeURIComponent(fs.root)}&path=${encodeURIComponent(fs.path)}`)]);
  S.roots = roots.roots || []; S.fsDemo = !!list.demo;
  const entries = (list.entries || []).filter(e => !fs.q || e.name.toLowerCase().includes(fs.q.toLowerCase()));
  const parts = fs.path.split('/').filter(Boolean);
  const rootName = S.roots.find(r => r.id === fs.root)?.name || fs.root;
  const title = parts.length ? parts[parts.length - 1] : rootName;
  const FAV = isMember() ? [] : [['Home folders', 'data', '/homes', 'users'], ['Shares', 'data', '/shares', 'folder'], ['Media', 'nas', '/arise/media', 'sermons'], ['Automator', 'data', '/automator/ARISE_YouTube_Updater', 'automator'], ['Apps', 'data', '/apps', 'apps'], ['Backups', 'data', '/backups', 'backups']];
  const side = `<div class="finder__side"><h4>Favorites</h4>${FAV.map(f => `<button data-go="${f[1]}|${f[2]}" class="${fs.root === f[1] && fs.path === f[2] ? 'on' : ''}"><i style="--i:${ICONURL[f[3]]}"></i>${esc(f[0])}</button>`).join('')}
    <h4>${isMember() ? 'Your places' : 'Locations'}</h4>${S.roots.map(r => `<button data-go="${r.id}|/" class="${fs.root === r.id && fs.path === '/' ? 'on' : ''}"><i style="--i:${ICONURL[r.id === 'nas' ? 'nas' : r.home ? 'users' : r.share ? 'folder' : 'server']}"></i>${esc(r.name)}</button>`).join('')}
    <h4>Sharing</h4><button id="fLinks"><i style="--i:${ICONURL.backups}"></i>Shared links</button></div>`;
  const tb = `<div class="finder__tb"><span class="nav"><button id="fBack" ${fs.hist.length ? '' : 'disabled'} title="Back">‹</button><button id="fFwd" ${fs.fwd.length ? '' : 'disabled'} title="Forward">›</button></span><span class="title">${esc(title)}</span>
    <span class="views"><button id="fIcon" class="${fs.view === 'icon' ? 'on' : ''}" title="Icons">▦</button><button id="fList" class="${fs.view === 'list' ? 'on' : ''}" title="List">☰</button></span>
    <input class="search" id="fQ" placeholder="Filter this folder" value="${esc(fs.q)}"><label class="btn btn--ghost btn--xs" for="fsUp">Upload</label><input id="fsUp" type="file" hidden><button class="btn btn--ghost btn--xs" id="fNew">New folder</button></div>`;
  const icon = e => e.dir ? ICONURL.folder : fileIcon(e.name);
  let main;
  if (list.error) main = `<div class="finder__main empty">${esc(list.error)}</div>`;
  else if (!entries.length) main = `<div class="finder__main empty">${fs.q ? 'Nothing matches' : 'Empty folder'}</div>`;
  else if (fs.view === 'icon') main = `<div class="finder__main" id="fMain">${entries.map((e, i) => `<div class="fi ${fs.sel === e.name ? 'sel' : ''}" data-n="${esc(e.name)}" data-dir="${e.dir ? 1 : 0}" tabindex="0"><i class="fico" style="--i:${icon(e)}"></i><span>${esc(e.name)}</span></div>`).join('')}</div>`;
  else main = `<div class="finder__main" id="fMain" style="padding:0"><table class="tbl"><thead><tr><th>Name</th><th>Date modified</th><th class="num">Size</th><th>Kind</th></tr></thead><tbody>${entries.map(e => `<tr class="${fs.sel === e.name ? 'sel' : ''}" data-n="${esc(e.name)}" data-dir="${e.dir ? 1 : 0}" tabindex="0"><td class="fname"><i style="--i:${icon(e)}"></i>${esc(e.name)}</td><td class="dim">${fmtT(e.mtime)}</td><td class="num dim">${e.dir ? '—' : fmtB(e.size)}</td><td class="dim">${e.dir ? 'Folder' : kindOf(e.name)}</td></tr>`).join('')}</tbody></table></div>`;
  const crumbs = [`<button data-go="${fs.root}|/">${esc(rootName)}</button>`].concat(parts.map((p, i) => `<span>›</span><button data-go="${fs.root}|/${parts.slice(0, i + 1).join('/')}">${esc(p)}</button>`)).join('');
  const path = `<div class="finder__path">${crumbs}<span class="st">${entries.length} item${entries.length === 1 ? '' : 's'}${list.demo ? ' · sample' : ''}</span></div>`;
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
  $$('[data-go]', root).forEach(b => b.onclick = () => { const [r, p] = b.dataset.go.split('|'); fsNav(r, p); });
  const fl = $('#fLinks', root); if (fl) fl.onclick = () => linksModal();
  $('#fBack', root).onclick = () => { const h = fs.hist.pop(); if (!h) return; fs.fwd.push({ root: fs.root, path: fs.path }); fs.root = h.root; fs.path = h.path; fs.sel = null; rerender('files'); };
  $('#fFwd', root).onclick = () => { const h = fs.fwd.pop(); if (!h) return; fs.hist.push({ root: fs.root, path: fs.path }); fs.root = h.root; fs.path = h.path; fs.sel = null; rerender('files'); };
  $('#fIcon', root).onclick = () => { fs.view = 'icon'; rerender('files'); }; $('#fList', root).onclick = () => { fs.view = 'list'; rerender('files'); };
  const q = $('#fQ', root); q.oninput = () => { fs.q = q.value; clearTimeout(S.fqT); S.fqT = setTimeout(() => rerender('files'), 250); };
  $('#fsUp', root).onchange = async e => { const f = e.target.files[0]; if (!f) return; const fd = new FormData(); fd.append('root', fs.root); fd.append('path', fs.path); fd.append('file', f); const r = await act($('label[for=fsUp]', root), () => api('/files/upload', { method: 'POST', body: fd }), `Uploaded ${f.name}`); if (r) rerender('files'); };
  $('#fNew', root).onclick = () => modal(`<h2>New folder</h2><div class="field"><label>Name</label><input id="nfName" placeholder="untitled folder"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="nfGo">Create</button></div>`, m => { $('#nfGo', m).onclick = async e => { const r = await act(e.target, () => api('/files/mkdir', { method: 'POST', body: { root: fs.root, path: fs.path, name: $('#nfName', m).value.trim() } }), 'Folder created'); if (r && r.ok !== false) { m.close(); rerender('files'); } }; $('#nfName', m).focus(); });
  const items = $$('[data-n]', root);
  const open = el => { const n = el.dataset.n; if (el.dataset.dir === '1') fsNav(fs.root, (fs.path === '/' ? '' : fs.path) + '/' + n); else quickLook(fs.root, (fs.path === '/' ? '' : fs.path) + '/' + n, n); };
  items.forEach(el => {
    el.onclick = e => { items.forEach(x => x.classList.remove('sel')); el.classList.add('sel'); fs.sel = el.dataset.n; };
    el.ondblclick = () => open(el);
    el.onkeydown = e => { if (e.key === 'Enter') open(el); if (e.key === ' ' && !e.metaKey && !e.ctrlKey) { e.preventDefault(); if (el.dataset.dir !== '1') quickLook(fs.root, (fs.path === '/' ? '' : fs.path) + '/' + el.dataset.n, el.dataset.n); } };
    el.oncontextmenu = e => { e.preventDefault(); el.click(); const p = (fs.path === '/' ? '' : fs.path) + '/' + el.dataset.n; const dl = `/api/files/download?root=${encodeURIComponent(fs.root)}&path=${encodeURIComponent(p)}`;
      ctxMenu(e.clientX, e.clientY, [['Open', () => open(el)], el.dataset.dir === '1' ? null : ['Quick Look', () => quickLook(fs.root, p, el.dataset.n)], el.dataset.dir === '1' ? null : ['Download', () => { if (!S.demoOnly) location.href = dl; else toast('Preview: nothing to download'); }], ['Get Info', () => getInfo(el.dataset.n, el.dataset.dir === '1', p)], null, ['Share Link…', () => shareLink(fs.root, p, el.dataset.n)], null, ['Copy path', () => copyText((S.roots.find(r => r.id === fs.root)?.path || '') + p)], ['Copy smb:// address', () => copyText(`smb://arise-server/${fs.root === 'nas' ? 'synology' : p.split('/')[1] || ''}${p.split('/').slice(fs.root === 'nas' ? 1 : 2).map(x => '/' + x).join('')}`)]]); };
  });
  const main = $('#fMain', root); if (main) main.oncontextmenu = e => { if (e.target !== main) return; e.preventDefault(); ctxMenu(e.clientX, e.clientY, [['New folder', () => $('#fNew', root).click()], ['Upload here', () => $('#fsUp', root).click()], null, ['Show as icons', () => { fs.view = 'icon'; rerender('files'); }], ['Show as list', () => { fs.view = 'list'; rerender('files'); }], null, ['Refresh', () => rerender('files')]]); };
};
function shareLink(root, p, name) {
  const days = S.me?.links_days || 7;
  modal(`<h2>Share “${esc(name)}”</h2><p class="muted">Anyone with the link can download it, no sign-in, until it expires. Folders arrive as a zip.</p>
    <div class="row" style="gap:10px;margin:12px 0"><label>Expires in <select id="slDays"><option value="1">1 day</option><option value="3">3 days</option><option value="7" ${days === 7 ? 'selected' : ''}>7 days</option><option value="14">14 days</option><option value="30">30 days</option></select></label><input id="slNote" placeholder="Note to yourself (optional)" style="flex:1"></div>
    <div id="slOut"></div><div class="acts"><button class="btn btn--ghost" data-close>Close</button><button class="btn" id="slGo">Make link</button></div>`, () => {
    $('#slGo').onclick = async () => { const b = $('#slGo'); b.disabled = true; try { const r = await api('/links', { method: 'POST', body: { root, path: p, days: +$('#slDays').value, note: $('#slNote').value } });
      if (r.ok === false) throw new Error(r.err); const url = r.url || (location.origin + '/s/' + r.token);
      $('#slOut').innerHTML = `<div class="log pre" style="user-select:all;word-break:break-all">${esc(url)}</div><div class="row" style="gap:8px;margin-top:8px"><button class="btn btn--xs" id="slCopy">Copy link</button><span class="muted">${r.demo ? 'sample: this link is not real' : 'until ' + esc(r.link.expires)}</span></div>`;
      $('#slCopy').onclick = e => copyText(url, e.target); b.textContent = 'Made'; } catch (e) { toast(e.message, 'bad'); b.disabled = false; } };
  });
}
async function linksModal() {
  let r; try { r = await api('/links'); } catch (e) { return toast(e.message, 'bad'); }
  const rows = r.links || [];
  modal(`<h2>Shared links</h2><p class="muted">${rows.length ? 'Remove a link and it stops working at once.' : 'Nothing shared yet. Right-click a file in Finder and pick Share Link.'}</p>
    <table class="tbl" style="margin-top:10px"><thead><tr><th>File</th><th>Until</th><th class="num">Downloads</th>${S.role === 'admin' ? '<th>By</th>' : ''}<th></th></tr></thead><tbody>${rows.map(l => `<tr class="${l.expired ? 'dim' : ''}"><td>${esc(l.name)}<br><small class="muted">${esc(l.note || l.root + l.path)}</small></td><td>${l.expired ? 'expired' : esc(l.expires.replace('T', ' '))}</td><td class="num">${l.downloads || 0}</td>${S.role === 'admin' ? `<td>${esc(l.user)}</td>` : ''}<td><button class="btn btn--ghost btn--xs" data-copy="${esc(l.token)}">Copy</button> <button class="btn btn--ghost btn--xs" data-rm="${esc(l.token)}">Remove</button></td></tr>`).join('')}</tbody></table>
    <div class="acts"><button class="btn btn--ghost" data-close>Close</button></div>`, () => {
    $$('[data-copy]').forEach(b => b.onclick = e => copyText(location.origin + '/s/' + b.dataset.copy, e.target));
    $$('[data-rm]').forEach(b => b.onclick = async () => { const x = await api('/links/' + b.dataset.rm, { method: 'DELETE' }); if (x.ok === false) return toast(x.err, 'bad'); toast('Link removed'); linksModal(); });
  });
}
function changePassword() {
  modal(`<h2>Change your password</h2><p class="muted">This is your directory password: the same one for the Macs, the shares and this dashboard.</p>
    <form id="pwf" style="display:grid;gap:8px;margin-top:12px"><input type="password" id="pwOld" placeholder="Current password" autocomplete="current-password"><input type="password" id="pwNew" placeholder="New password (8 or more)" autocomplete="new-password"><input type="password" id="pwNew2" placeholder="New password again" autocomplete="new-password">
    <div class="acts"><button type="button" class="btn btn--ghost" data-close>Cancel</button><button class="btn" type="submit">Change</button></div></form>`, () => {
    $('#pwf').onsubmit = async e => { e.preventDefault(); if ($('#pwNew').value !== $('#pwNew2').value) return toast('The two new passwords differ', 'warn');
      const r = await api('/me/password', { method: 'POST', body: { old: $('#pwOld').value, new: $('#pwNew').value } }).catch(er => ({ ok: false, err: er.message }));
      if (r.ok === false) return toast(r.err, 'bad'); toast(r.demo ? 'Sample mode: nothing changed' : 'Password changed'); $('[data-close]').click(); };
  });
}
function getInfo(name, dir, p) { modal(`<div class="about"><div class="flame" style="background:${dir ? ICONURL.folder : fileIcon(name)} center/70% no-repeat #000"></div><div><h2 style="font-size:20px">${esc(name)}</h2><dl class="kv"><dt>Kind</dt><dd>${dir ? 'Folder' : kindOf(name)}</dd><dt>Where</dt><dd class="mono" style="font-size:12px">${esc((S.roots.find(r => r.id === S.fs.root)?.path || '') + p)}</dd><dt>Share</dt><dd class="mono" style="font-size:12px">smb://arise-server${esc(p)}</dd></dl></div></div><div class="acts"><button class="btn btn--ghost" data-close>Close</button></div>`); }
async function quickLook(root, p, name) {
  const ql = $('#ql'); $('#qlTitle').textContent = name; const url = `/api/files/view?root=${encodeURIComponent(root)}&path=${encodeURIComponent(p)}`;
  $('#qlDl').href = `/api/files/download?root=${encodeURIComponent(root)}&path=${encodeURIComponent(p)}`; $('#qlDl').onclick = e => { if (S.demoOnly || S.fsDemo) { e.preventDefault(); toast('Preview: nothing to download'); } };
  const body = $('#qlBody'); ql.hidden = false;
  const e = (name.split('.').pop() || '').toLowerCase();
  if (S.demoOnly || S.fsDemo) { body.innerHTML = `<div class="none"><div class="fico" style="--i:${fileIcon(name)}"></div>${esc(kindOf(name))}<br><span style="font-size:12px">Quick Look shows the real file on the server: images, text, markdown, JSON, PDFs.</span></div>`; return; }
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
      <div class="chips">${chips.map(c => `<button class="chip" data-ref="${esc(c)}">${esc(c)}</button>`).join('')}</div></div>
    ${r.ok ? `<div class="mark"><span class="kicker">${esc(r.translation_name || r.translation)}</span></div><h2 style="color:#fff">${esc(r.reference)}</h2>
      <p class="passage">${(r.verses || []).map(v => `<b>${v.verse}</b>${esc(v.text)}`).join(' ')}</p>
      <div class="row" style="margin-top:18px"><button class="btn btn--ghost btn--sm" id="bbCopy">Copy</button><a class="btn btn--ghost btn--sm" href="https://arisecenla.church/arise-bible?ref=${encodeURIComponent(r.reference)}" target="_blank" rel="noopener">Open on arisecenla.church</a></div>
      <p class="note" style="margin-top:14px;font-size:12px">${esc(r.copyright || '')}${r.demo ? ' · Preview text is the King James Version whatever Bible is picked; the server reads bible-api.com.' : ' · Read on the server from bible-api.com, no key needed. Study notes, the dictionary and audio are on the website\'s Bible Search.'}</p>` : `<div class="empty">${esc(r.error || 'Nothing found')}</div>`}
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
  tabs('#rmTabs');
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
    <div class="assist">${tiles}<button class="assist__t" data-claude-code><i>On this box</i><b>Claude Code</b><span>The <code>claude</code> command in the Terminal: ask it about this server, let it read the logs, fix a config. Signed in with the church's claude.ai account via <code>/login</code>.</span></button></div></div>`;
};
V.assist.after = root => {
  $$('[data-url]', root).forEach(b => b.onclick = async () => {
    if (S.kiosk) { const r = await api('/kiosk/open', { method: 'POST', body: { url: b.dataset.url } }).catch(e => ({ ok: false, err: e.message })); if (r.ok === false) toast(r.err, 'bad'); else toast(r.demo ? 'Sample: would open on the monitor' : 'Opening on the monitor…'); }
    else window.open(b.dataset.url, '_blank', 'noopener');
  });
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
      <div class="tabs">${['compose', 'contacts', 'sent'].map(t => `<button class="${tab === t ? 'on' : ''}" data-tab="${t}">${t[0].toUpperCase() + t.slice(1)}</button>`).join('')}</div></div>`;
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
  else body = `<table class="tbl"><thead><tr><th>Newsletter</th><th>Status</th><th>Created</th><th>Sent</th></tr></thead><tbody>${(bc.broadcasts || []).map(b => `<tr><td><b>${esc(b.subject || b.name)}</b></td><td>${esc(b.status)}</td><td>${esc((b.created_at || '').slice(0, 16).replace('T', ' '))}</td><td>${esc((b.sent_at || '').slice(0, 16).replace('T', ' ') || '—')}</td></tr>`).join('') || '<tr><td colspan="4" class="muted">Nothing sent yet.</td></tr>'}</tbody></table>${bc.err ? `<p class="note" style="color:var(--bad)">${esc(bc.err)}</p>` : ''}`;
  return `<div class="fade">${head}${body}${st.configured ? '' : `<div class="card" style="margin-top:14px;border-left:3px solid var(--warn)"><b>To set up (Friday):</b> 1. Resend account, add and verify the church's domain (DNS records at the domain host). 2. API key → <code>/etc/arise/secrets/resend-api-key</code> (root only). 3. In arise.toml <code>[mail]</code>: from_email at that domain, reply_to the Gmail. 4. Import the Wix CSV. 5. Send yourself a test.</div>`}</div>`;
};
V.mail.after = root => {
  $$('[data-tab]', root).forEach(b => b.onclick = () => { S.mailTab = b.dataset.tab; rerender('mail'); });
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
  const ws = new WebSocket(`${proto}://${location.host}/api/terminal`); S.termWs = ws;
  ws.onopen = () => { ws.send(JSON.stringify({ resize: [term.cols, term.rows] })); };
  ws.onmessage = e => term.write(e.data);
  ws.onclose = ev => term.write(`\r\n\x1b[2m[session closed${ev.code === 4401 ? ': sign in again' : ''}]\x1b[0m\r\n`);
  term.onData(d => { if (ws.readyState === 1) ws.send(d); });
  term.onResize(({ cols, rows }) => { if (ws.readyState === 1) ws.send(JSON.stringify({ resize: [cols, rows] })); });
};
function demoShell(term) {
  const P = '\x1b[31marise-server\x1b[0m:~# ';
  const CMD = { help: 'arisectl info · arisectl doctor · arisectl backup status · arisectl user list · uptime · df -h · clear',
    'arisectl info': 'ariseOS (Arise Server) v0.7.0 “Genesis”\r\n  host      arise-server  (Ubuntu 24.04, 4 cores, 16 GB RAM)\r\n  realm     AD.ARISECENLA.CHURCH / ARISE   directory on\r\n  web       http://arise-server:4147   password set\r\n  automator /srv/arise/automator/ARISE_YouTube_Updater  at 02:05\r\n  backups   /mnt/synology/arise-backups/restic  at 03:00',
    'arisectl doctor': '  \x1b[32m✓\x1b[0m config /etc/arise/arise.toml\r\n  \x1b[32m✓\x1b[0m Samba AD DC answers\r\n  \x1b[32m✓\x1b[0m DNS SRV for ad.arisecenla.church resolves\r\n  \x1b[32m✓\x1b[0m token.json present\r\n  \x1b[32m✓\x1b[0m restic installed\r\n  \x1b[32m✓\x1b[0m Synology /mnt/synology mounted\r\n  \x1b[33m!\x1b[0m 3 apt packages upgradable (1 security)\r\n  \x1b[32m✓\x1b[0m clock synchronised',
    'arisectl backup status': 'repository /mnt/synology/arise-backups/restic\r\n  \x1b[32m✓\x1b[0m 53 snapshots, 296.2 GB stored\r\n  JOB        LAST              RESULT  ADDED\r\n  automator  2026-10-27T03:00  ok      797.1 MB\r\n  homes      2026-10-27T03:04  ok      451.3 MB\r\n  config     2026-10-27T03:16  ok      739.5 MB',
    'arisectl user list': '  USER          NAME             ENABLED  GROUPS\r\n  bradly        Bradly Dyer      yes      Domain Admins, Media, Staff\r\n  media-mac     Media Booth Mac  yes      Media\r\n  office        Church Office    yes      Staff',
    uptime: ' 09:41:12 up 14 days,  3:07,  1 user,  load average: 0.42, 0.58, 0.61', 'df -h': 'Filesystem      Size  Used Avail Use% Mounted on\r\n/dev/sda2       224G   66G  147G  31% /\r\n/dev/sdb1       894G  242G  607G  29% /srv/arise\r\n//synology/arise  15T  4.5T   10T  31% /mnt/synology', whoami: 'root', hostname: 'arise-server' };
  term.write('\x1b[31m   ▲\x1b[0m  Arise Server \x1b[2mv0.7.0 “Genesis”\x1b[0m  ·  preview terminal\r\n   A sample shell. On the real server this is a root shell on the box. Type help.\r\n\r\n' + P);
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
  about: '<svg viewBox="0 0 32 32"><path d="M16 2c2 6 8 8 8 15a8 8 0 0 1-16 0c0-3 1.4-5 3-7 0 3 1 5 3 6 0-5 1-10 2-14z" fill="#D6222D"/><path d="M16 12c1 3 4 4 4 7.5A4 4 0 0 1 12 19c0-2 .7-3 1.6-4 .2 1.6.9 2.5 1.8 3 0-2.5.3-4.5.6-6z" fill="#fff"/></svg>',
};
const APPS = [
  { id: 'files', n: '01', name: 'Finder', what: 'The server, the Synology, the shares', whatMember: 'Your files, your shares, your links', tone: 'bone', dock: true, w: 900, h: 560 },
  { id: 'overview', n: '02', name: 'Overview', what: 'Needs you, live stats, tonight', tone: 'red', dock: true },
  { id: 'directory', n: '03', name: 'Directory', what: 'Users, groups, joined computers', dock: true },
  { id: 'backups', n: '04', name: 'Backups', what: 'restic jobs, history, snapshots', dock: true },
  { id: 'automator', n: '05', name: 'Automator', what: 'The 02:05 YouTube job', dock: true },
  { id: 'sermons', n: '06', name: 'Sermons', what: 'The channel, no quota spent', tone: 'bone', dock: true },
  { id: 'bible', n: '07', name: 'Bible', what: 'Read a passage', tone: 'bone', dock: true, w: 820, h: 560 },
  { id: 'apps', n: '08', name: 'Apps', what: 'Docker templates the church uses', dock: true },
  { id: 'remote', n: '09', name: 'Remote', what: 'VPN, SSH, remote desktop', dock: true },
  { id: 'sites', n: '10', name: 'Campuses', what: 'Pineville, Alexandria, the Hub', w: 760, h: 520 },
  { id: 'terminal', n: '11', name: 'Terminal', what: 'A shell on the box', dock: true, flush: true, w: 860, h: 500 },
  { id: 'nas', n: '12', name: 'Synology', what: 'Mount, space, DSM health' },
  { id: 'services', n: '13', name: 'Services', what: 'The systemd units' },
  { id: 'logs', n: '14', name: 'Logs', what: 'journalctl, last 300 lines' },
  { id: 'settings', n: '15', name: 'System Settings', what: 'arise.toml, updates, power' },
  { id: 'devices', n: '16', name: 'Network', what: 'Everything on the switch', w: 980, h: 600 },
  { id: 'assist', n: '17', name: 'Assistants', what: 'Claude, ChatGPT, Grok, Studio', tone: 'bone', dock: true, w: 820, h: 480 },
  { id: 'sunday', n: '18', name: 'Sunday', what: 'The service checklist, what is next', tone: 'red', dock: true, w: 900, h: 600 },
  { id: 'mail', n: '19', name: 'Mail', what: 'The church family list, newsletters (Resend)', w: 980, h: 640 },
  { id: 'security', n: '31', name: 'Security', what: 'Encryption, the virus scan, the certificate, two-step', w: 940, h: 640 },
  { id: 'about', n: '', name: 'About This Server', what: '', hidden: true, w: 560, h: 380 },
];
const MEMBER_APPS = ['files', 'sermons', 'bible', 'sites', 'about', 'assist', 'sunday'];
const isMember = () => S.role === 'member';
const visibleApps = () => isMember() ? APPS.filter(a => MEMBER_APPS.includes(a.id)) : APPS;
const appOf = id => APPS.find(a => a.id === id);
// Shortcut labels: a Windows keyboard on the closet monitor has no ⌘. Ctrl does the same job in every handler.
const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform);
const kbd = h => !h || IS_MAC ? h : h.replace('⌃⌘', 'Ctrl+Alt+').replace('⇧⌘', 'Ctrl+Shift+').replace('⌘', 'Ctrl+').replace('⌃', 'Ctrl+');
const iconHtml = a => `<span class="dock__icon ${a.tone || ''}">${I[a.id]}</span>`;

V.about = async () => {
  const o = S.overview || await api('/overview'); const m = o.machine || S.machine || {};
  let wk = null; try { wk = await api('/about/week'); } catch {}
  const week = wk ? `<div class="about__week">This week: <b>${esc(wk.verse?.ref || '')}</b>${wk.verse?.text ? ' · “' + esc(wk.verse.text.slice(0, 90)) + (wk.verse.text.length > 90 ? '…' : '') + '”' : ''}<br>${wk.services} services on the calendar · ${wk.published_this_week} video${wk.published_this_week === 1 ? '' : 's'} published this week${wk.minutes_this_week ? ' · ' + Math.round(wk.minutes_this_week / 60 * 10) / 10 + ' hours of them' : ''}${wk.latest ? `<br>Latest on the channel: <b>${esc(wk.latest)}</b>` : ''}</div>` : '';
  return `<div class="about"><div class="flame">${I.about.replace('<svg', '<svg width="72" height="72"')}</div><div><div class="kicker">ariseOS · Arise Server</div><h2>v${esc(o.version)} “${esc(o.codename)}”</h2>
    <dl class="kv"><dt>Host</dt><dd>${esc(o.hostname)}</dd><dt>Domain</dt><dd>${esc(o.realm || '—')}</dd><dt>System</dt><dd>${esc(m.os || '')}</dd><dt>Processor</dt><dd>${esc(m.cpu_model || '')} · ${m.cpu_count || '?'} cores</dd><dt>Memory</dt><dd>${esc(m.ram_total_h || '')}</dd><dt>Uptime</dt><dd>${fmtUp(S.stats?.uptime)}</dd><dt>Profile</dt><dd>${esc(o.profile)}</dd></dl>
    ${week}<div class="row" style="margin-top:14px"><button class="btn btn--ghost btn--xs" data-open="settings">System Settings</button><a class="btn btn--ghost btn--xs" href="https://github.com/Rehchu/Church-server-OS-" target="_blank" rel="noopener">Source</a></div></div></div>`;
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
      $('#tfOff', m).onsubmit = async e => { e.preventDefault(); const r = await api('/me/2fa/disable', { method: 'POST', body: { password: $('#tfPw', m).value, code: $('#tfCode', m).value } }).catch(er => ({ ok: false, err: er.message })); if (r.ok === false) return toast(r.err, 'bad'); toast(r.demo ? 'Sample mode: nothing changed' : 'Two-step is off'); m.close(); };
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
    $('#tfOn', m).onsubmit = async e => { e.preventDefault(); const x = await api('/me/2fa/enable', { method: 'POST', body: { code: $('#tfCode', m).value } }).catch(er => ({ ok: false, err: er.message })); if (x.ok === false) return toast(x.err, 'warn'); tone('done'); toast(x.demo ? 'Sample mode: nothing changed' : 'Two-step is on. Next sign-in asks for a code.'); m.close(); };
  });
}

/* ---------------- window manager ---------------- */
function tabs(sel) {
  const root = $(sel); if (!root) return; const panels = $$('[data-tab]', root.parentElement);
  $$('button', root).forEach(b => b.onclick = () => { $$('button', root).forEach(x => x.classList.toggle('active', x === b)); panels.forEach(p => p.hidden = p.dataset.tab !== b.dataset.t); });
}
let cascade = 0;
function openApp(id, focusOnly) {
  const a = appOf(id); if (!a) return;
  if (isMember() && !MEMBER_APPS.includes(id)) { toast('That app is for the administrator', 'warn'); return; }
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
  const di = $(`#dock [data-app="${id}"]`); if (di) { di.classList.add('bounce'); setTimeout(() => di.classList.remove('bounce'), 1100); }
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
  handle.addEventListener('pointerdown', e => { if (isPhone() || e.target.closest('button') || el.classList.contains('max') || $('#stage').classList.contains('mc')) return; on = true; sx = e.clientX; sy = e.clientY; ox = el.offsetLeft; oy = el.offsetTop; handle.setPointerCapture(e.pointerId); });
  handle.addEventListener('pointermove', e => { if (!on) return; const st = $('#stage'); el.style.left = Math.max(-el.offsetWidth + 80, Math.min(st.clientWidth - 80, ox + e.clientX - sx)) + 'px'; el.style.top = Math.max(0, Math.min(st.clientHeight - 40, oy + e.clientY - sy)) + 'px'; });
  handle.addEventListener('pointerup', () => on = false); handle.addEventListener('pointercancel', () => on = false);
}
const seqs = {};
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
  const help = [['Dashboard guide', () => window.open('https://github.com/Rehchu/Church-server-OS-/blob/main/docs/DASHBOARD.md')], ['Remote access guide', () => window.open('https://github.com/Rehchu/Church-server-OS-/blob/main/docs/REMOTE-ACCESS.md')], ['Install guide', () => window.open('https://github.com/Rehchu/Church-server-OS-/blob/main/INSTALL.md')], null, ['About This Server', () => openApp('about')]];
  const file = { files: [['New Folder', () => $('#fNew')?.click(), '⇧⌘N'], ['Upload Here', () => $('#fsUp')?.click()], null, ['Share Link…', () => { const el = $('#fMain .sel'); if (el) shareLink(S.fs.root, (S.fs.path === '/' ? '' : S.fs.path) + '/' + el.dataset.n, el.dataset.n); else toast('Select a file or folder first', 'warn'); }], ['Shared Links…', () => linksModal()], null, ['Quick Look', () => { const el = $('#fMain .sel'); if (el && el.dataset.dir !== '1') quickLook(S.fs.root, (S.fs.path === '/' ? '' : S.fs.path) + '/' + el.dataset.n, el.dataset.n); }, 'Space'], ['Get Info', () => { const el = $('#fMain .sel'); if (el) getInfo(el.dataset.n, el.dataset.dir === '1', (S.fs.path === '/' ? '' : S.fs.path) + '/' + el.dataset.n); }, '⌘I'], null, ['Close Window', () => closeApp('files'), '⌘W']],
    backups: [['Run all jobs now', () => act($('#next') || document.body, () => api('/backups/run/automator', { method: 'POST' }), 'Started the automator job')], ['Refresh GitHub mirror', () => api('/backups/mirror', { method: 'POST' }).then(() => toast('Mirror refreshed'))], null, ['Close Window', () => closeApp(id), '⌘W']],
    automator: [['Preview tonight (dry run)', () => api('/automator/preview', { method: 'POST' }).then(() => toast('Preview started'))], null, ['Close Window', () => closeApp(id), '⌘W']],
    terminal: [['New shell (reopen)', () => { closeApp('terminal'); openApp('terminal'); }], null, ['Close Window', () => closeApp(id), '⌘W']],
    devices: [['Scan now', () => $('#devScan')?.click()], null, ['Close Window', () => closeApp(id), '⌘W']],
    sunday: [['Refresh', () => rerender('sunday'), '⌘R'], null, ['Close Window', () => closeApp(id), '⌘W']],
    mail: [['Compose', () => { S.mailTab = 'compose'; rerender('mail'); }], ['Contacts', () => { S.mailTab = 'contacts'; rerender('mail'); }], ['Sent', () => { S.mailTab = 'sent'; rerender('mail'); }], null, ['Close Window', () => closeApp(id), '⌘W']],
    assist: [['Open Claude', () => $$('[data-url]').find(b => b.dataset.url.includes('claude'))?.click()], ['Claude Code in Terminal', () => $('[data-claude-code]')?.click()], null, ['Close Window', () => closeApp(id), '⌘W']],
  }[id] || [['Close Window', () => id && closeApp(id), '⌘W']];
  const view = [['Refresh', () => id && rerender(id), '⌘R'], null, ['Show Widgets', () => toggleNC(true)], ['Control Center', () => toggleCC(true)], ['Spotlight', () => toggleSpot(true), '⌘Space']];
  return [[a ? a.name : 'ariseOS', a ? [['About ' + a.name, () => toast(a.what)], null, ['Hide ' + a.name, () => minApp(id), '⌘H'], ['Quit ' + a.name, () => closeApp(id), '⌘Q']] : [['About This Server', () => openApp('about')]]], ['File', file], ['View', view], ['Window', win], ['Help', help]];
}
const FLAME_MENU = () => isMember() ? [['About This Server', () => openApp('about')], null, ['Change Password…', () => changePassword()], ['Two-step sign-in…', () => twofaModal()], ['Shared Links…', () => linksModal()], ['Launchpad', () => toggleLaunchpad(true)], null, ['Lock Screen', () => lockScreen(), '⌃⌘Q'], ['Sign Out ' + (S.user || ''), () => signOut()]]
  : [['About This Server', () => openApp('about')], null, ['System Settings…', () => openApp('settings')], ['Change Password…', () => changePassword()], ['Two-step sign-in…', () => twofaModal()], ['Security', () => openApp('security')], ['Launchpad', () => toggleLaunchpad(true)], null, ['Run backups now', () => runAllBackups()], ['Preview tonight\'s automator', () => api('/automator/preview', { method: 'POST' }).then(() => toast('Preview started: a dry run, nothing written'))], null, ['Lock Screen', () => lockScreen(), '⌃⌘Q'], ['Sign Out ' + (S.user || ''), () => signOut()], null, ['Restart…', () => powerAsk('reboot')], ['Shut Down…', () => powerAsk('poweroff')]];
function setAppMenus(id) {
  const m = $('#menus'); const list = menuItems(id);
  m.innerHTML = list.map((g, i) => `<button class="${i === 0 ? 'app' : ''}" data-m="${i}">${esc(g[0])}</button>`).join('');
  $$('button', m).forEach(b => { b.onclick = e => { e.stopPropagation(); openMenu(b, list[+b.dataset.m][1]); }; b.onmouseenter = () => { if (menuOpen && menuOpen !== b) openMenu(b, list[+b.dataset.m][1]); }; });
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
document.addEventListener('pointerdown', e => { if (menuOpen && !e.target.closest('#menuDrop') && !e.target.closest('#menus') && !e.target.closest('#barLogo')) closeMenu(); if (!$('#cc').hidden && !e.target.closest('#cc') && !e.target.closest('#ccBtn')) toggleCC(false); }, true);

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
const ACTIONS_ALL = [['Run backups now', () => runAllBackups(), 'backups'], ['Preview tonight\'s automator', () => api('/automator/preview', { method: 'POST' }).then(() => toast('Preview started')), 'automator'], ['Lock screen', () => lockScreen(), 'about'], ['Restart the server', () => powerAsk('reboot'), 'settings'], ['Shut down the server', () => powerAsk('poweroff'), 'settings'], ['Mission Control', () => missionControl(true), 'overview'], ['About This Server', () => openApp('about'), 'about']];
const actions = () => isMember() ? [['Change password…', () => changePassword(), 'about'], ['Shared links…', () => linksModal(), 'files']] : ACTIONS_ALL;
function spotResults(q, remote) {
  q = q.trim(); const ql = q.toLowerCase(); let out = ''; const row = (icon, label, small, data) => `<button data-s='${esc(JSON.stringify(data))}'><span class="dock__icon">${icon}</span>${esc(label)}${small ? `<small>${esc(small)}</small>` : ''}</button>`;
  const bible = q.match(/^([1-3]?\s?[a-z]{2,20})\s?(\d{1,3})(?::(\d{1,3})(?:-(\d{1,3}))?)?$/i);
  if (bible) out += `<div class="h">Bible</div>` + row(I.bible, `Read ${q}`, 'Bible', { bible: q });
  const apps = visibleApps().filter(a => !a.hidden && (!ql || a.name.toLowerCase().includes(ql) || a.what.toLowerCase().includes(ql)));
  if (apps.length) out += `<div class="h">Apps</div>` + apps.slice(0, ql ? 6 : 8).map(a => row(I[a.id], a.name, a.what, { app: a.id })).join('');
  const acts = actions().filter(a => ql && a[0].toLowerCase().includes(ql)); if (acts.length) out += `<div class="h">Actions</div>` + acts.map((a, i) => row(I[a[2]], a[0], 'Action', { act: actions().indexOf(a) })).join('');
  if (remote) {
    if (remote.users?.length) out += `<div class="h">People</div>` + remote.users.map(u => row(I.directory, u.display || u.name, u.name, { app: 'directory' })).join('');
    if (remote.computers?.length) out += `<div class="h">Computers</div>` + remote.computers.map(c => row(I.sites, c.name, c.os || c.kind, { app: 'sites' })).join('');
    if (remote.transcripts?.length) out += `<div class="h">Sermons · transcripts</div>` + remote.transcripts.map(t => row(I.sermons, t.title, t.snippet, { app: 'sermons' })).join('');
    if (remote.hits?.length) out += `<div class="h">Files</div>` + remote.hits.slice(0, 10).map(h => row(I.files, h.name, h.path, { file: h })).join('');
  }
  if (!out) out = `<div class="h">Nothing for “${esc(q)}”</div>`;
  return out;
}
function spotGo(data) {
  toggleSpot(false);
  if (data.app) openApp(data.app);
  else if (data.bible) { S.bible = { ref: data.bible, tr: S.bible?.tr || 'web' }; openApp('bible'); }
  else if (data.act != null) actions()[data.act][1]();
  else if (data.file) { const f = data.file; const dir = f.dir ? f.path : f.path.replace(/\/[^/]*$/, '') || '/'; S.fs = Object.assign(S.fs || { view: 'icon', hist: [], fwd: [], q: '' }, { root: f.root, path: dir, sel: f.dir ? null : f.name, q: '' }); openApp('files'); }
}

/* Notification Center widgets */
function fmtSvc(t) { const [h, m] = String(t).split(':').map(Number); const d = new Date(); d.setHours(h, m || 0); return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); }
function weekWidget() {
  const c = S.church; const n = c?.next;
  const rows = (c?.services || [{ name: 'Sunday Service', site: 'Pineville', day: 'Sunday', time: '10:30' }, { name: 'Sunday Service', site: 'Alexandria', day: 'Sunday', time: '10:00' }, { name: 'Glory Night', site: 'Pineville', day: 'Monday', time: '19:00' }]);
  return `<div class="widget"><div class="widget__kicker">This week${n ? ` · next in ${esc(n.in_words)}` : ''}</div><div class="widget__rows">${rows.map(x => `<div class="widget__row"><span>${esc(x.name === 'Sunday Service' ? 'Sunday · ' + x.site : x.name + ' · ' + x.day)}</span><b>${esc(fmtSvc(x.time))}</b></div>`).join('')}</div></div>`;
}
function verseWidget() { const v = S.church?.verse; if (!v || !v.text) return ''; return `<div class="widget widget--verse"><div class="widget__kicker">Verse of the day</div><blockquote>${esc(v.text)}<cite>${esc(v.ref)}</cite></blockquote></div>`; }
async function loadChurch() { try { S.church = await api('/church'); } catch { S.church = S.church || null; } }
async function buildMemberWidgets() {
  const w = $('#widgets'); const roots = S.me?.roots || []; let links = [];
  try { links = (await api('/links')).links || []; } catch {}
  const live = links.filter(l => !l.expired);
  w.innerHTML = `<div class="widget widget--clear"><div class="widget__kicker">Signed in</div><div class="widget__title" style="font-size:18px">${esc(S.user)}</div><div class="widget__sub">${(S.me?.groups || []).join(' · ') || 'member'}</div></div>
    <div class="widget"><div class="widget__kicker">Your places</div><div class="widget__rows">${roots.map(r => `<button class="widget__row" data-root="${esc(r.id)}"><span>${esc(r.name)}</span><b>${r.home ? 'your home folder' : r.writable === false ? 'read only' : 'share'}</b></button>`).join('')}</div></div>
    <div class="widget"><div class="widget__kicker">Shared links</div><div class="widget__rows"><div class="widget__row"><span>Live</span><b>${live.length}</b></div><div class="widget__row"><span>Downloads</span><b>${links.reduce((a, l) => a + (l.downloads || 0), 0)}</b></div></div><button class="btn btn--ghost btn--xs" data-act="links" style="margin-top:8px">Manage</button></div>
    ${weekWidget()}${verseWidget()}`;
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
const CC_FEEL = { theme: toggleTheme, sounds: () => { PREF.set('sounds', PREF.get('sounds', '1') === '1' ? '0' : '1'); tone('click'); buildCC(); }, push: () => { toggleCC(false); enablePush(); }, walk: () => { toggleCC(false); walkthrough(true); } };
function ccFeel() {
  const bone = PREF.get('theme', 'dark') === 'bone', snd = PREF.get('sounds', '1') === '1', pushOn = PREF.get('push', '') === '1';
  return `<button class="${bone ? 'ok' : ''}" data-act="theme" ${S.kiosk ? 'disabled title="the monitor stays dark"' : ''}><b>${bone ? 'Bone' : 'House Lights Down'}</b><span>${S.kiosk ? 'the monitor stays dark' : bone ? 'light paper · tap for dark' : 'dark stage · tap for light'}</span></button>
    <button class="${snd ? 'ok' : ''}" data-act="sounds"><b>Sounds ${snd ? 'on' : 'off'}</b><span>quiet clicks and chimes</span></button>
    ${S.me && S.me.user && !S.kiosk ? `<button class="${pushOn ? 'ok' : ''}" data-act="push"><b>Push ${pushOn ? 'on' : 'off'}</b><span>${pushOn ? 'this device gets alerts' : 'alerts to this phone'}</span></button>` : ''}
    <button data-act="walk"><b>Show me around</b><span>the five-step tour</span></button>`;
}
async function runAllBackups() { const jobs = (await api('/backups/jobs')).jobs || []; for (const j of jobs) await api(`/backups/run/${encodeURIComponent(j.id)}`, { method: 'POST' }); toast(`Started ${jobs.length} backup jobs; rows appear in Backups as they finish`); }
function powerAsk(action) { confirmType(action === 'reboot' ? 'Restart the server' : 'Shut the server down', action, action === 'reboot' ? 'Everything stops for about a minute. Logged-in Macs keep working on cached accounts. The desktop comes back by itself.' : '<b>Someone has to walk to the closet to turn it back on.</b> No domain logins, no 02:05 automator, no backups until then.', async () => { const r = await withReauth(() => api('/system/power', { method: 'POST', body: { action, confirm: action } })); if (r.ok === false) throw new Error(r.err); toast(action === 'reboot' ? 'Restarting…' : 'Shutting down.', 'warn', 8000); }); }

/* ---------------- dock + launchpad + desktop icons ---------------- */
function buildDock() {
  const d = $('#dock');
  d.innerHTML = visibleApps().filter(a => a.dock).map(a => `<button class="dock__i" data-app="${a.id}" aria-label="${esc(a.name)}">${iconHtml(a)}<span class="lbl">${a.n} · ${esc(a.name)}</span></button>`).join('') +
    `<span class="dock__sep"></span><button class="dock__i" id="dockLp" aria-label="Launchpad"><span class="dock__icon">${I.apps}</span><span class="lbl">Launchpad</span></button>`;
  $$('[data-app]', d).forEach(b => b.onclick = () => { tone('click'); const id = b.dataset.app; const w = S.wins[id]; if (w && !w.min && w.el.classList.contains('focus') && !isPhone()) minApp(id); else openApp(id, true); });
  $('#dockLp').onclick = () => toggleLaunchpad();
  // magnification
  const items = $$('.dock__i', d);
  d.addEventListener('mousemove', e => { if (isPhone() || matchMedia('(prefers-reduced-motion: reduce)').matches) return; items.forEach(it => { const r = it.getBoundingClientRect(); const dist = Math.abs(e.clientX - (r.left + r.width / 2)); const s = Math.max(1, 1.55 - dist / 120); it.style.transform = `scale(${s.toFixed(3)}) translateY(${(-(s - 1) * 10).toFixed(1)}px)`; }); });
  d.addEventListener('mouseleave', () => items.forEach(it => it.style.transform = ''));
  const lp = $('#lpGrid'); lp.innerHTML = visibleApps().filter(a => !a.hidden).map(a => `<button class="lp" data-lp="${a.id}">${iconHtml(a)}<b>${esc(a.name)}</b><i>${a.n}</i><span>${esc(isMember() && a.whatMember ? a.whatMember : a.what)}</span></button>`).join('');
  $$('[data-lp]', lp).forEach(b => b.onclick = () => { toggleLaunchpad(false); openApp(b.dataset.lp); });
  $('#lpQ').oninput = e => { const q = e.target.value.toLowerCase(); $$('.lp', lp).forEach(b => b.hidden = q && !b.textContent.toLowerCase().includes(q)); };
  $('#launchpad').onclick = e => { if (e.target.id === 'launchpad') toggleLaunchpad(false); };
}
function updateDock() { $$('#dock [data-app]').forEach(b => { const w = S.wins[b.dataset.app]; b.classList.toggle('run', !!w); b.classList.toggle('active', !!w && w.el.classList.contains('focus') && !w.min); }); }
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
  let o; try { o = await api('/overview'); } catch (e) { if (e.status === 401) return showLogin(e); o = null; }
  S.overview = o;
  const w = $('#widgets'); if (!o) { w.innerHTML = ''; return; }
  if (o.demo) { S.demo = true; $('#demoBadge').hidden = false; if (!S.demoOnly) $('#demoBadge').textContent = 'Sample data'; }
  const att = o.attention || [], bad = att.some(x => x.level === 'bad');
  const badKey = att.filter(x => x.level === 'bad').map(x => x.text).join('|'); if (bad && S.badKey !== undefined && S.badKey !== badKey) tone('bad'); S.badKey = badKey;
  $('#barAtt').hidden = !att.length; $('#barAttN').textContent = att.length;
  const a = o.automator || {}, b = o.backup || {}, n = o.nas || {};
  const bk = $('#stBk'); bk.className = 'bar__item ' + (b.failed_recent ? 'bad' : b.last ? 'ok' : ''); $('b', bk).textContent = b.last ? (b.last.ok ? 'ok' : 'failed') : '—';
  try { const r = await api('/remote'); S.remoteCache = r; const on = r.tailscale?.up || r.wireguard?.up; const v = $('#stVpn'); v.className = 'bar__item ' + (on ? 'ok' : 'warn'); $('b', v).textContent = on ? (r.tailscale?.up ? `${(r.tailscale.peers || []).filter(p => p.online).length} online` : 'up') : 'off'; } catch {}
  const nowH = new Date().getHours();
  const next = nowH < 2 ? '02:05 automator' : nowH < 3 ? '03:00 backups' : nowH < 4 ? '04:00 GitHub mirror' : nowH < 7 ? '07:00 daily note' : '02:05 automator (tonight)';
  w.innerHTML = `
    <div class="widget ${att.length ? (bad ? 'widget--bad' : 'widget--warn') : 'widget--clear'}"><div class="widget__kicker">${att.length ? 'Needs you' : 'All clear'}</div>
      ${att.length ? `<div class="att">${att.slice(0, 4).map(x => `<div class="att__i ${x.level}">${esc(x.text)}</div>`).join('')}${att.length > 4 ? `<button class="btn btn--ghost btn--xs" data-open="overview">${att.length - 4} more</button>` : ''}</div>` : '<div class="widget__sub">Services up, last automator run clean, backups ok, Synology mounted.</div>'}</div>
    <div class="widget"><div class="widget__kicker">Live</div><div class="row row--between"><span class="widget__big" id="wgCpu">–</span><span class="widget__sub" style="text-align:right">CPU<br><span id="wgNet" class="mono" style="font-size:11px">–</span></span></div><div class="meter"><i id="wgCpuM"></i></div><svg class="spark" id="wgSpark" style="height:34px"></svg><div class="row row--between" style="margin-top:6px"><span class="widget__sub">Memory <b id="wgRam" style="color:#fff">–</b></span></div><div class="meter meter--warn"><i id="wgRamM"></i></div></div>
    <div class="widget"><div class="widget__kicker">The box</div>
      <div class="widget__row"><span>Directory</span><b>${o.directory_ok ? 'online' : '<span style="color:var(--redL)">down</span>'} · ${o.counts?.users} users</b></div>
      <div class="widget__row"><span>Automator</span><b>${a.last_run ? ago(a.last_run) : 'never'} · ${a.last_ok === false ? '<span style="color:var(--redL)">failures</span>' : a.last_ok ? 'clean' : '—'}</b></div>
      <div class="widget__row"><span>Quota</span><b>${fmtN(a.quota_today)} / ${fmtN(a.quota_daily)}</b></div>
      <div class="widget__row"><span>Backups</span><b>${b.last ? (b.last.ok ? 'ok' : '<span style="color:var(--redL)">failed</span>') + ' · ' + ago(b.last.started) : 'none'}</b></div>
      <div class="widget__row"><span>Synology</span><b>${n.mounted ? fmtB(n.free) + ' free' : '<span style="color:var(--warn)">not mounted</span>'}</b></div>
      <div class="widget__row"><span>Next</span><b>${esc(next)}</b></div></div>
    ${weekWidget()}${verseWidget()}`;
  $$('[data-open]', w).forEach(x => x.onclick = () => openApp(x.dataset.open));
  if (S.stats) paintWidgetLive(S.stats);
}

/* ---------------- lock, login, sign out ---------------- */
function lockScreen(idle) {
  saver(false);
  const l = $('#lock'); l.hidden = false; l.classList.toggle('idle', !!idle); $('#lockName').textContent = S.user || 'bradly'; closeOverlays(); tickLock();
  if (idle) { const wake = () => { l.classList.remove('idle'); $('#lockPw').focus(); document.removeEventListener('keydown', wake); l.removeEventListener('pointerdown', wake); }; document.addEventListener('keydown', wake); l.addEventListener('pointerdown', wake); } else $('#lockPw').focus();
}
function tickLock() { const d = new Date(); $('#lockTime').textContent = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); $('#lockDate').textContent = d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }); }
$('#lockForm').onsubmit = async e => { e.preventDefault(); const pw = $('#lockPw').value; $('#lockPw').value = '';
  if (S.demoOnly || S.demo) { $('#lock').hidden = true; return; }
  try { await api('/auth/login', { method: 'POST', body: { user: S.user, password: pw } }); $('#lock').hidden = true; } catch (er) { toast(er.message, 'bad'); } };
async function signOut() { await api('/auth/logout', { method: 'POST' }).catch(() => {}); location.reload(); }
function showLogin(err) {
  const remembered = (() => { try { return localStorage.getItem('arise.user') || ''; } catch { return ''; } })();
  const codeStep = !!(err && err.code);
  document.body.innerHTML = `<div class="login"><div class="login__box">
    <div class="lock__avatar">${I.about.replace('<svg', '<svg width="44" height="44"').replace('#D6222D', '#fff')}</div><h1>ariseOS</h1>
    ${err?.setup ? `<p>No admin password has been set yet. On the server run:</p><pre class="log pre">sudo arisectl admin set-password</pre><p style="margin-top:12px">then reload this page.</p>`
    : codeStep ? `<p>Two-step sign-in is on for <b>${esc(err.user || remembered)}</b>. Open <b>Microsoft Authenticator</b> and type the six digits it shows for ariseOS.</p>
    <form id="lf" class="lock__form"><input id="lc" inputmode="numeric" pattern="[0-9 ]*" placeholder="6 digits" autocomplete="one-time-code" maxlength="7" style="width:160px;text-align:center;letter-spacing:.3em"><button type="submit" aria-label="Continue">→</button></form><button class="btn btn--ghost btn--xs" id="lback" style="margin-top:10px">Start over</button>`
    : `<p>${esc(err?.message && err.message !== 'Sign in' ? err.message : 'Arise Church · Pineville, LA')}</p>
    <form id="lf" class="lock__form"><input id="lu" value="${esc(remembered)}" placeholder="Name" autocomplete="username" style="width:110px"><input id="lp" type="password" placeholder="Password" autocomplete="current-password"><button type="submit" aria-label="Sign in">→</button></form>`}
    <div class="lock__hint">arise-server · AD.ARISECENLA.CHURCH</div></div></div>`;
  const f = $('#lf'); if (!f) return;
  const fail = msg => { let t = $('.login .toast'); if (!t) { t = document.createElement('div'); t.className = 'toast bad'; t.style.marginTop = '12px'; $('.login__box').appendChild(t); } t.textContent = msg; };
  if (codeStep) {
    $('#lc').focus(); $('#lback').onclick = () => showLogin(null);
    f.onsubmit = async e => { e.preventDefault(); const b = $('button', f); b.classList.add('busy');
      try { await api('/auth/login/code', { method: 'POST', body: { pending: err.pending, code: $('#lc').value } }); location.reload(); }
      catch (er) { if (/Sign in again|more than five|Three wrong/.test(er.message)) { showLogin({ message: er.message }); return; } fail(er.message); $('#lc').value = ''; $('#lc').focus(); }
      finally { b.classList.remove('busy'); } };
    return;
  }
  $('#lp').focus();
  f.onsubmit = async e => { e.preventDefault(); const b = $('button', f); b.classList.add('busy');
    try { const user = $('#lu').value; try { localStorage.setItem('arise.user', user); } catch {}
      const r = await api('/auth/login', { method: 'POST', body: { user, password: $('#lp').value } });
      if (r && r.need_code) { showLogin({ code: true, pending: r.pending, user: r.user || user }); return; }
      location.reload(); }
    catch (er) { fail(er.message); }
    finally { b.classList.remove('busy'); } };
}
function clock() { const d = new Date(); $('#barClock').textContent = d.toLocaleString('en-US', { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); if (!$('#lock').hidden) tickLock(); }

/* ---------------- keyboard + kiosk + boot ---------------- */
document.addEventListener('keydown', e => {
  const cmd = e.metaKey || e.ctrlKey; const inField = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName) || e.target.closest('.xterm');
  if (e.key === 'Escape') { if (!$('#spot').hidden) { toggleSpot(false); return; } if (!$('#ql').hidden) { $('#ql').hidden = true; return; } if ($('#stage').classList.contains('mc')) { missionControl(false); return; } closeOverlays(); toggleNC(false); $('#switcher').hidden = true; return; }
  if (cmd && e.code === 'Space') { e.preventDefault(); toggleSpot(); return; }
  if (e.key === 'F3') { e.preventDefault(); missionControl(); return; }
  if (cmd && e.key === 'Tab') { e.preventDefault(); switcher(e.shiftKey ? -1 : 1); return; }
  if (inField) return;
  if (e.key === 'F4') { e.preventDefault(); toggleLaunchpad(); return; }
  const id = focusedApp();
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
  paint(); S.saverT = setInterval(paint, 30000);
  // a slow slideshow of the channel's thumbnails behind the clock
  api('/sermons?limit=12').then(r => { const th = (r.videos || []).map(v => v.thumbnail).filter(Boolean); if (!th.length) return; let i = 0; const art = $('#saverArt'); const step = () => { if (sv.hidden) return; art.style.backgroundImage = `url(${th[i % th.length]})`; i++; }; step(); S.saverA = setInterval(step, 20000); }).catch(() => {});
}
function kioskSetup() {
  const q = new URLSearchParams(location.search);
  if (q.has('signage')) { document.body.classList.add('kiosk', 'signage'); S.kiosk = true; S.signage = true; loadChurch().then(() => saver(true)); setInterval(() => loadChurch(), 10 * 60000); return; }
  if (!q.has('kiosk')) return;
  document.body.classList.add('kiosk'); S.kiosk = true;
  let idle = 0; const reset = () => { idle = 0; document.body.classList.remove('idle'); if (!$('#saver').hidden) saver(false); };
  ['pointermove', 'keydown', 'pointerdown', 'wheel'].forEach(ev => document.addEventListener(ev, reset, { passive: true }));
  // 5 minutes idle: the screensaver (clock, next service, the verse, the channel's art); 10: the lock on top of it.
  setInterval(() => { idle += 5; if (idle >= 5) document.body.classList.add('idle'); if (idle >= 300 && $('#lock').hidden) saver(true); if (idle >= 600 && $('#lock').hidden) lockScreen(true); }, 5000);
}
async function boot() {
  if (window.ARISE_FORCE_DEMO) setDemoOnly();
  clock(); setInterval(clock, 15000);
  buildDock(); setAppMenus(null); kioskSetup(); applyTheme();
  try {
    const me = await api('/auth/me');
    if (me.error) { if (me.error.setup) return showLogin({ setup: true }); return showLogin(me.error); }
    S.authed = true; S.user = me.user || 'bradly'; S.role = me.role || 'admin'; S.me = me;
    applyTheme();
    if ('serviceWorker' in navigator && location.protocol !== 'file:' && !S.demoOnly) navigator.serviceWorker.register('/sw.js').catch(() => {});
    if (!S.kiosk && !me.demo) setTimeout(() => walkthrough(false), 1200);
    try { if (!me.demo) localStorage.setItem('arise.user', S.user); } catch {}
    if (isMember()) { document.body.classList.add('member'); buildDock(); setAppMenus(null); }
    if (me.demo) { S.demo = true; $('#demoBadge').hidden = false; }
  } catch (e) { if (!S.demoOnly) return showLogin(e); S.user = 'bradly'; }
  if (!isMember()) startStats();
  await loadChurch();
  await Promise.all([buildWidgets(), isMember() ? Promise.resolve() : buildIcons()]);
  setInterval(loadChurch, 15 * 60000);
  setInterval(buildWidgets, 60000);
  const first = (location.hash || '').replace('#', '').split('/')[0];
  if (first && appOf(first)) openApp(first); else if (!isPhone()) openApp('files');
  window.addEventListener('hashchange', () => { const id = (location.hash || '').replace('#', ''); if (appOf(id) && !S.wins[id]) openApp(id); });
}
boot();
// A small console handle: `arise.openApp('files')` from the browser devtools, Playwright, or the kiosk.
window.arise = { openApp, closeApp, minApp, focusWin, rerender, toggleLaunchpad, toggleNC, toggleCC, toggleSpot, missionControl, switcher, lockScreen, showLogin, signOut, saver, toast, tone, walkthrough, toggleTheme, twofaModal, reauth, withReauth, S, APPS };
})();
