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
  if (!r.ok) throw new Error(j.error?.message || j.err || `HTTP ${r.status}`);
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
  $('#miniCpu').textContent = s.cpu != null ? s.cpu.toFixed(0) + '%' : '–';
  $('#miniRam').textContent = s.ram ? s.ram.pct.toFixed(0) + '%' : '–';
  $('#miniUp').textContent = fmtUp(s.uptime);
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
  const [st, us, gs, cs] = await Promise.all([api('/directory/status'), api('/directory/users'), api('/directory/groups'), api('/directory/computers')]);
  const users = us.users || [], groups = gs.groups || [], comps = cs.computers || [];
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
      ${users.map(u => `<tr data-q="${esc((u.name + ' ' + u.display).toLowerCase())}"><td><b>${esc(u.name)}</b> ${u.enabled ? '' : '<span class="pill warn">disabled</span>'}</td><td>${esc(u.display)}</td><td>${(u.groups || []).map(g => `<span class="tag">${esc(g)}</span>`).join('')}</td><td class="dim">${u.last_logon ? fmtT(u.last_logon) : 'never'}</td><td class="mono dim" style="font-size:12px">${esc(u.home || '')}</td>
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
  $$('[data-del]').forEach(b => b.onclick = () => confirmType('Delete user', b.dataset.del, `This removes the account from the domain. <b>The home folder stays on disk</b> - nothing in it is deleted. Deleting is your click, not the server's.`, async () => { const r = await api(`/directory/users/${encodeURIComponent(b.dataset.del)}`, { method: 'DELETE', body: { confirm: b.dataset.del } }); if (r.ok === false) throw new Error(r.err); toast('User deleted'); rerender('directory'); }));
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
  S.fs = S.fs || { root: 'data', path: '/' };
  const [roots, list] = await Promise.all([api('/files/roots'), api(`/files/list?root=${encodeURIComponent(S.fs.root)}&path=${encodeURIComponent(S.fs.path)}`)]);
  const parts = S.fs.path.split('/').filter(Boolean);
  const crumbs = [`<button data-cd="/">${esc((roots.roots || []).find(r => r.id === S.fs.root)?.name || S.fs.root)}</button>`].concat(parts.map((p, i) => `<span>/</span><button data-cd="/${parts.slice(0, i + 1).join('/')}">${esc(p)}</button>`)).join('');
  const rows = (list.entries || []).map(e => `<tr><td class="fname"><i class="fico ${e.dir ? '' : 'f'}" style="--i:${e.dir ? FICO.d : FICO.f}"></i>${e.dir ? `<button data-cd="${esc((S.fs.path === '/' ? '' : S.fs.path) + '/' + e.name)}">${esc(e.name)}</button>` : `<span>${esc(e.name)}</span>`}</td><td class="num dim">${e.dir ? '' : fmtB(e.size)}</td><td class="dim">${fmtT(e.mtime)}</td><td class="acts">${e.dir ? '' : `<a class="btn btn--ghost btn--xs" href="/api/files/download?root=${encodeURIComponent(S.fs.root)}&path=${encodeURIComponent((S.fs.path === '/' ? '' : S.fs.path) + '/' + e.name)}" ${S.demoOnly ? 'onclick="return false"' : 'download'}>Download</a>`}</td></tr>`).join('');
  return `<div class="fade">
    <div class="tabs" id="fsTabs"><button class="active" data-t="browse">Browse</button><button data-t="shares">Shares</button></div>
    <div data-tab="browse">
      <div class="toolbar"><select class="search" id="fsRoot">${(roots.roots || []).map(r => `<option value="${esc(r.id)}" ${r.id === S.fs.root ? 'selected' : ''}>${esc(r.name)} · ${esc(r.path)}</option>`).join('')}</select><div class="crumbs">${crumbs}</div><span class="spacer"></span><label class="btn btn--ghost btn--sm" for="fsUp">Upload here</label><input id="fsUp" type="file" hidden></div>
      ${list.error ? `<div class="empty">${esc(list.error)}</div>` : `<div class="panel panel--flat tbl-wrap" style="padding:0"><table class="tbl ftable"><thead><tr><th>Name</th><th class="num">Size</th><th>Modified</th><th></th></tr></thead><tbody>${rows || '<tr><td colspan="4" class="empty">Empty folder</td></tr>'}</tbody></table></div>`}
      <p class="note" style="margin-top:12px">Browse and download only. Moving and deleting happen in Finder on a Mac over <b>smb://arise-server</b>, where the person doing it can see what they are doing.</p>
    </div>
    <div data-tab="shares" hidden id="fsShares"></div>
  </div>`;
};
V.files.after = async root => {
  tabs('#fsTabs');
  $$('[data-cd]').forEach(b => b.onclick = () => { S.fs.path = b.dataset.cd.replace(/\/+/g, '/') || '/'; rerender('files'); });
  $('#fsRoot').onchange = e => { S.fs = { root: e.target.value, path: '/' }; rerender('files'); };
  $('#fsUp').onchange = async e => { const f = e.target.files[0]; if (!f) return; const fd = new FormData(); fd.append('root', S.fs.root); fd.append('path', S.fs.path); fd.append('file', f); const btn = $('label[for=fsUp]'); const r = await act(btn, () => api('/files/upload', { method: 'POST', body: fd }), `Uploaded ${f.name}`); if (r) rerender('files'); };
  const sh = $('#fsShares'); sh.innerHTML = await V.shares(); V.shares.after();
};

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
    'arisectl info': 'Arise Server v0.2.0 “Pineville”\r\n  host      arise-server  (Ubuntu 24.04, 4 cores, 16 GB RAM)\r\n  realm     AD.ARISECENLA.CHURCH / ARISE   directory on\r\n  web       http://arise-server:4147   password set\r\n  automator /srv/arise/automator/ARISE_YouTube_Updater  at 02:05\r\n  backups   /mnt/synology/arise-backups/restic  at 03:00',
    'arisectl doctor': '  \x1b[32m✓\x1b[0m config /etc/arise/arise.toml\r\n  \x1b[32m✓\x1b[0m Samba AD DC answers\r\n  \x1b[32m✓\x1b[0m DNS SRV for ad.arisecenla.church resolves\r\n  \x1b[32m✓\x1b[0m token.json present\r\n  \x1b[32m✓\x1b[0m restic installed\r\n  \x1b[32m✓\x1b[0m Synology /mnt/synology mounted\r\n  \x1b[33m!\x1b[0m 3 apt packages upgradable (1 security)\r\n  \x1b[32m✓\x1b[0m clock synchronised',
    'arisectl backup status': 'repository /mnt/synology/arise-backups/restic\r\n  \x1b[32m✓\x1b[0m 53 snapshots, 296.2 GB stored\r\n  JOB        LAST              RESULT  ADDED\r\n  automator  2026-10-27T03:00  ok      797.1 MB\r\n  homes      2026-10-27T03:04  ok      451.3 MB\r\n  config     2026-10-27T03:16  ok      739.5 MB',
    'arisectl user list': '  USER          NAME             ENABLED  GROUPS\r\n  bradly        Bradly Dyer      yes      Domain Admins, Media, Staff\r\n  media-mac     Media Booth Mac  yes      Media\r\n  office        Church Office    yes      Staff',
    uptime: ' 09:41:12 up 14 days,  3:07,  1 user,  load average: 0.42, 0.58, 0.61', 'df -h': 'Filesystem      Size  Used Avail Use% Mounted on\r\n/dev/sda2       224G   66G  147G  31% /\r\n/dev/sdb1       894G  242G  607G  29% /srv/arise\r\n//synology/arise  15T  4.5T   10T  31% /mnt/synology', whoami: 'root', hostname: 'arise-server' };
  term.write('\x1b[31m   ▲\x1b[0m  Arise Server \x1b[2mv0.2.0 “Pineville”\x1b[0m  ·  preview terminal\r\n   A sample shell. On the real server this is a root shell on the box. Type help.\r\n\r\n' + P);
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
  settings: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 6h12v2H3zm14 0h4v2h-4zM3 11h4v2H3zm6 0h12v2H9zM3 16h10v2H3zm12 0h6v2h-6z"/></svg>',
};
const APPS = [
  { id: 'overview', n: '01', name: 'Overview', what: 'Needs you, live stats, tonight', tone: 'red', dock: true },
  { id: 'directory', n: '02', name: 'Directory', what: 'Users, groups, joined computers', dock: true },
  { id: 'files', n: '03', name: 'Files', what: 'Browse the server and the NAS; shares', dock: true },
  { id: 'backups', n: '04', name: 'Backups', what: 'restic jobs, history, snapshots', dock: true },
  { id: 'automator', n: '05', name: 'Automator', what: 'The 02:05 YouTube job', dock: true },
  { id: 'sermons', n: '06', name: 'Sermons', what: 'The channel, no quota spent', tone: 'bone', dock: true },
  { id: 'bible', n: '07', name: 'Bible', what: 'Read a passage', tone: 'bone', dock: true },
  { id: 'apps', n: '08', name: 'Apps', what: 'Docker templates the church uses', dock: true },
  { id: 'remote', n: '09', name: 'Remote', what: 'VPN, SSH, remote desktop', dock: true },
  { id: 'sites', n: '10', name: 'Campuses', what: 'Pineville, Alexandria, the Hub' },
  { id: 'terminal', n: '11', name: 'Terminal', what: 'A shell on the box', dock: true, flush: true },
  { id: 'nas', n: '12', name: 'Synology', what: 'Mount, space, DSM health' },
  { id: 'services', n: '13', name: 'Services', what: 'The systemd units' },
  { id: 'logs', n: '14', name: 'Logs', what: 'journalctl, last 300 lines' },
  { id: 'settings', n: '15', name: 'Settings', what: 'arise.toml, updates, power' },
];
const appOf = id => APPS.find(a => a.id === id);
const iconHtml = a => `<span class="dock__icon ${a.tone || ''}">${I[a.id]}</span>`;

/* ---------------- window manager ---------------- */
function tabs(sel) {
  const root = $(sel); if (!root) return; const panels = $$('[data-tab]', root.parentElement);
  $$('button', root).forEach(b => b.onclick = () => { $$('button', root).forEach(x => x.classList.toggle('active', x === b)); panels.forEach(p => p.hidden = p.dataset.tab !== b.dataset.t); });
}
let cascade = 0;
function openApp(id, focusOnly) {
  const a = appOf(id); if (!a) return;
  let w = S.wins[id];
  if (w) { w.min = false; w.el.classList.remove('min'); focusWin(id); if (!focusOnly) rerender(id); return; }
  const el = document.createElement('section'); el.className = 'win' + (a.flush ? ' win--term' : ''); el.dataset.app = id;
  el.innerHTML = `<div class="win__bar"><div class="win__dots"><button class="x" title="Close" aria-label="Close"></button><button class="m" title="Minimise" aria-label="Minimise"></button><button class="z" title="Zoom" aria-label="Zoom"></button></div><span class="win__folio">${a.n}</span><span class="win__title">${esc(a.name)}</span><span class="win__sub" id="ws-${id}">${esc(a.what)}</span></div><div class="win__body${a.flush ? ' win__body--flush' : ''}" id="wb-${id}"></div>`;
  const stage = $('#stage');
  if (!isPhone()) { const n = cascade++ % 6; el.style.left = (40 + n * 28 + Math.min(stage.clientWidth - 1000, 320)) + 'px'; el.style.top = (24 + n * 24) + 'px'; }
  stage.appendChild(el);
  w = S.wins[id] = { el, min: false, max: false };
  $('.x', el).onclick = () => closeApp(id); $('.m', el).onclick = () => minApp(id); $('.z', el).onclick = () => { w.max = !w.max; el.classList.toggle('max', w.max); };
  $('.win__bar', el).ondblclick = () => $('.z', el).click();
  el.addEventListener('pointerdown', () => focusWin(id), true);
  drag(el, $('.win__bar', el));
  focusWin(id); rerender(id); location.hash = '#' + id; $('#barApp').textContent = a.name;
  updateDock(); $('#widgets').classList.toggle('dim', !isPhone() && Object.keys(S.wins).length > 0);
}
function closeApp(id) {
  const w = S.wins[id]; if (!w) return;
  if (id === 'terminal' && S.termDispose) { S.termDispose(); S.termDispose = null; }
  w.el.remove(); delete S.wins[id]; updateDock();
  const rest = Object.keys(S.wins); if (rest.length) focusWin(rest[rest.length - 1]); else { $('#barApp').textContent = 'Arise Server'; history.replaceState(null, '', location.pathname); }
  $('#widgets').classList.toggle('dim', Object.keys(S.wins).length > 0 && !isPhone());
}
function minApp(id) { const w = S.wins[id]; if (!w) return; w.min = true; w.el.classList.add('min'); updateDock(); const rest = Object.keys(S.wins).filter(k => !S.wins[k].min); if (rest.length) focusWin(rest[rest.length - 1]); else $('#barApp').textContent = 'Arise Server'; }
function focusWin(id) { const w = S.wins[id]; if (!w) return; $$('.win').forEach(e => e.classList.remove('focus')); w.el.classList.add('focus'); w.el.style.zIndex = ++S.z; $('#barApp').textContent = appOf(id).name; updateDock(); }
function drag(el, handle) {
  let sx, sy, ox, oy, on = false;
  handle.addEventListener('pointerdown', e => { if (isPhone() || e.target.closest('button') || el.classList.contains('max')) return; on = true; sx = e.clientX; sy = e.clientY; ox = el.offsetLeft; oy = el.offsetTop; handle.setPointerCapture(e.pointerId); });
  handle.addEventListener('pointermove', e => { if (!on) return; const st = $('#stage'); el.style.left = Math.max(-el.offsetWidth + 80, Math.min(st.clientWidth - 80, ox + e.clientX - sx)) + 'px'; el.style.top = Math.max(0, Math.min(st.clientHeight - 40, oy + e.clientY - sy)) + 'px'; });
  handle.addEventListener('pointerup', () => on = false); handle.addEventListener('pointercancel', () => on = false);
}
const seqs = {};
async function rerender(id) {
  const w = S.wins[id]; const fn = V[id]; if (!w || !fn) return;
  S.lastView = id;
  const body = $('#wb-' + id); const seq = seqs[id] = (seqs[id] || 0) + 1;
  if (id === 'terminal' && S.termDispose) return; // never re-create a live shell
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

/* ---------------- dock + launchpad ---------------- */
function buildDock() {
  const d = $('#dock');
  d.innerHTML = APPS.filter(a => a.dock).map(a => `<button class="dock__i" data-app="${a.id}" aria-label="${esc(a.name)}">${iconHtml(a)}<span class="lbl">${a.n} · ${esc(a.name)}</span></button>`).join('') +
    `<span class="dock__sep"></span><button class="dock__i" id="dockLp" aria-label="Launchpad"><span class="dock__icon">${I.apps}</span><span class="lbl">Launchpad</span></button>`;
  $$('[data-app]', d).forEach(b => b.onclick = () => { const id = b.dataset.app; const w = S.wins[id]; if (w && !w.min && w.el.classList.contains('focus') && !isPhone()) minApp(id); else openApp(id, true); });
  $('#dockLp').onclick = toggleLaunchpad;
  const lp = $('#lpGrid'); lp.innerHTML = APPS.map(a => `<button class="lp" data-lp="${a.id}">${iconHtml(a)}<b>${esc(a.name)}</b><i>${a.n}</i><span>${esc(a.what)}</span></button>`).join('');
  $$('[data-lp]', lp).forEach(b => b.onclick = () => { toggleLaunchpad(false); openApp(b.dataset.lp); });
  $('#lpQ').oninput = e => { const q = e.target.value.toLowerCase(); $$('.lp', lp).forEach(b => b.hidden = q && !b.textContent.toLowerCase().includes(q)); };
  $('#barLogo').onclick = () => toggleLaunchpad();
  $('#launchpad').onclick = e => { if (e.target.id === 'launchpad') toggleLaunchpad(false); };
  document.addEventListener('keydown', e => { if (e.key === 'Escape') toggleLaunchpad(false); });
}
function toggleLaunchpad(force) { const lp = $('#launchpad'); const open = force !== undefined ? force : lp.hidden; lp.hidden = !open; if (open) { $('#lpQ').value = ''; $$('.lp').forEach(b => b.hidden = false); $('#lpQ').focus(); } }
function updateDock() { $$('#dock [data-app]').forEach(b => { const w = S.wins[b.dataset.app]; b.classList.toggle('run', !!w); b.classList.toggle('active', !!w && w.el.classList.contains('focus') && !w.min); }); }

/* ---------------- desktop widgets ---------------- */
async function buildWidgets() {
  let o; try { o = await api('/overview'); } catch (e) { if (e.status === 401) return showLogin(e); o = null; }
  S.overview = o;
  const w = $('#widgets'); if (!o) { w.innerHTML = ''; return; }
  if (o.demo) { S.demo = true; $('#demoBadge').hidden = false; if (!S.demoOnly) $('#demoBadge').textContent = 'Sample data'; }
  $('#barHost').textContent = `${o.hostname} · v${o.version} “${o.codename}”`;
  const att = o.attention || [], bad = att.some(x => x.level === 'bad');
  $('#barAtt').hidden = !att.length; $('#barAttN').textContent = att.length;
  const a = o.automator || {}, b = o.backup || {}, n = o.nas || {};
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
    <div class="widget"><div class="widget__kicker">This week</div>
      <div class="widget__row"><span>Sunday · Pineville</span><b>10:30 AM</b></div><div class="widget__row"><span>Sunday · Alexandria</span><b>10:00 AM</b></div><div class="widget__row"><span>Glory Night · Monday</span><b>7:00 PM</b></div></div>`;
  $$('[data-open]', w).forEach(x => x.onclick = () => openApp(x.dataset.open));
  if (S.stats) paintWidgetLive(S.stats);
}

/* ---------------- login + boot ---------------- */
function showLogin(err) {
  document.body.innerHTML = `<div class="login"><div class="login__box">
    <div class="mark"><span class="kicker">Arise Church · Pineville</span></div><h1>Arise Server</h1>
    ${err?.setup ? `<p>No admin password has been set yet. On the server run:</p><pre class="log">sudo arisectl admin set-password</pre><p style="margin-top:12px">then reload this page.</p>` : `<p>${esc(err?.message && err.message !== 'Sign in' ? err.message : 'Sign in with the admin account from arise.toml.')}</p>
    <form id="lf"><div class="field"><label>User</label><input id="lu" value="bradly" autocomplete="username"></div><div class="field"><label>Password</label><input id="lp" type="password" autocomplete="current-password"></div><button class="btn" style="width:100%;justify-content:center" type="submit">Sign in</button></form>`}
  </div></div>`;
  const f = $('#lf'); if (f) f.onsubmit = async e => { e.preventDefault(); const b = $('button', f); b.classList.add('busy'); try { await api('/auth/login', { method: 'POST', body: { user: $('#lu').value, password: $('#lp').value } }); location.reload(); } catch (er) { let t = $('.login .toast'); if (!t) { t = document.createElement('div'); t.className = 'toast bad'; t.style.marginTop = '12px'; $('.login__box').appendChild(t); } t.textContent = er.message; } finally { b.classList.remove('busy'); } };
}
function clock() { const d = new Date(); $('#barClock').textContent = d.toLocaleString('en-US', { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); }
async function boot() {
  if (window.ARISE_FORCE_DEMO) setDemoOnly();
  clock(); setInterval(clock, 15000);
  buildDock();
  try {
    const me = await api('/auth/me');
    if (me.error) { if (me.error.setup) return showLogin({ setup: true }); return showLogin(me.error); }
    S.authed = true; S.user = me.user; $('#userBtn').textContent = me.user || 'admin';
    if (me.demo) { S.demo = true; $('#demoBadge').hidden = false; }
  } catch (e) { if (!S.demoOnly) return showLogin(e); }
  $('#userBtn').onclick = () => modal(`<h2>${esc(S.user || 'admin')}</h2><p class="note" style="margin-bottom:14px">Signed in to the Arise Server dashboard${S.demoOnly ? ' (preview)' : ''}.</p><div class="acts"><button class="btn btn--ghost" data-close>Close</button><button class="btn" id="lo">Sign out</button></div>`, m => { $('#lo', m).onclick = async () => { await api('/auth/logout', { method: 'POST' }).catch(() => {}); location.reload(); }; });
  $('#barAtt').onclick = () => openApp('overview');
  startStats();
  await buildWidgets();
  setInterval(buildWidgets, 60000);
  const first = (location.hash || '').replace('#', '').split('/')[0];
  if (first && appOf(first)) openApp(first); else if (!isPhone()) openApp('overview');
  window.addEventListener('hashchange', () => { const id = (location.hash || '').replace('#', ''); if (appOf(id) && !S.wins[id]) openApp(id); });
}
boot();
})();
