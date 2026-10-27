/* ===========================================================================
   ARISE SERVER — dashboard
   Plain JS, no build step. Hash router, one fetch wrapper, one SSE stream.
   When the API is unreachable (the published preview page, a dev laptop) it
   falls back to window.ARISE_DEMO_DATA, which is generated from the server's
   own demo responses by scripts/gen-demo-data.py, so the preview is the
   real UI over the real sample shapes.
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
const ago = iso => { if (!iso) return 'never'; const d = new Date(iso); if (isNaN(d)) return esc(iso); const s = (Date.now() - d) / 1000; if (s < 60) return 'just now'; if (s < 3600) return `${Math.floor(s/60)} min ago`; if (s < 86400) return `${Math.floor(s/3600)} h ago`; return `${Math.floor(s/86400)} d ago`; };
const pct = (a, b) => b ? Math.round(a / b * 100) : 0;

/* ---------------- state ---------------- */
const S = { demo: false, authed: false, user: null, view: 'overview', stats: null, hist: [], sse: null, demoTimer: null, machine: null };

/* ---------------- API ---------------- */
const DEMO = window.ARISE_DEMO_DATA || null;
function demoLookup(method, path) {
  if (!DEMO) return null;
  const key = method + ' ' + path.split('?')[0];
  if (key in DEMO) return DEMO[key];
  // any POST/DELETE in demo succeeds
  if (method !== 'GET') return { ok: true, demo: true, out: '(preview) nothing was changed' };
  return null;
}
async function api(path, opts = {}) {
  const method = opts.method || 'GET';
  if (S.demoOnly) { const d = demoLookup(method, path); if (d) return structuredClone(d); return { demo: true, error: { message: 'not in the preview' } }; }
  let r;
  try {
    r = await fetch('/api' + path, { method, headers: opts.body ? { 'Content-Type': 'application/json' } : {}, body: opts.body ? JSON.stringify(opts.body) : undefined, credentials: 'same-origin' });
  } catch (e) {
    const d = demoLookup(method, path);
    if (d) { setDemoOnly(); return structuredClone(d); }
    throw new Error('Could not reach the server');
  }
  const ct = r.headers.get('content-type') || '';
  if (!ct.includes('json')) {
    // not our API answering (a static host, the preview page): use the sample data
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
  es.onopen = () => { live.className = 'live on'; $('#sideLiveText').textContent = 'live'; };
  es.onerror = () => { live.className = 'live off'; $('#sideLiveText').textContent = 'reconnecting'; };
  es.onmessage = e => { try { onStat(JSON.parse(e.data)); } catch {} };
}
function startDemoStats() {
  if (S.demoTimer) return;
  const live = $('#sideLive'); live.className = 'live on'; $('#sideLiveText').textContent = 'preview';
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
  if (S.view === 'overview') paintLive(s);
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
  set('lvCpu', s.cpu.toFixed(0)); set('lvRam', fmtB(s.ram.used)); set('lvRamPct', s.ram.pct.toFixed(0) + '%'); set('lvRx', fmtRate(s.net?.rx)); set('lvTx', fmtRate(s.net?.tx));
  set('lvLoad', (s.load || []).map(x => x.toFixed(2)).join(' · ')); set('lvTemp', s.temp ? s.temp.toFixed(0) + '°C' : '—'); set('lvUp', fmtUp(s.uptime));
  set('lvRd', fmtRate(s.disk_io?.read)); set('lvWr', fmtRate(s.disk_io?.write));
  const m = $('#lvCpuMeter i'); if (m) m.style.width = s.cpu + '%';
  const r = $('#lvRamMeter i'); if (r) r.style.width = s.ram.pct + '%';
  const cores = $('#lvCores'); if (cores && s.cores) { if (cores.children.length !== s.cores.length) cores.innerHTML = s.cores.map(() => '<i></i>').join(''); s.cores.forEach((c, i) => cores.children[i].style.height = Math.max(2, c) + '%'); }
  spark('spCpu', S.hist.map(x => x.cpu), '#D6222D'); spark('spRam', S.hist.map(x => x.ram), '#E0A32E'); spark('spNet', S.hist.map(x => (x.net?.rx || 0) + (x.net?.tx || 0)), '#5CA8E0');
  const dk = $('#lvDisks'); if (dk && s.disks && !dk.dataset.t || (dk && s.disks && Date.now() - +dk.dataset.t > 10000)) { dk.dataset.t = Date.now(); dk.innerHTML = s.disks.map(d => `<div class="stat" style="margin-bottom:12px"><div class="row row--between"><span class="mono" style="font-size:13px">${esc(d.mount)} <span class="dim" style="color:var(--muted)">${esc(d.fs)}</span></span><span style="font-size:12.5px;color:var(--text2)">${fmtB(d.used)} of ${fmtB(d.total)}</span></div><div class="meter ${d.pct > 90 ? '' : d.pct > 75 ? 'meter--warn' : 'meter--ok'}"><i style="width:${d.pct}%"></i></div></div>`).join(''); }
}

/* ---------------- views ---------------- */
const TITLES = { overview: 'Overview', directory: 'Directory', files: 'Files', backups: 'Backups', automator: 'Automator', apps: 'Apps', nas: 'Synology', services: 'Services', logs: 'Logs', settings: 'Settings' };
const V = {};

V.overview = async () => {
  const o = await api('/overview');
  if (o.demo) { S.demo = true; $('#demoBadge').hidden = false; if (!S.demoOnly) $('#demoBadge').textContent = 'Sample data'; }
  $('#sideMeta').textContent = `${o.hostname} · v${o.version} “${o.codename}”`;
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
      <div class="row" style="margin-top:14px"><a class="btn btn--sm" href="#directory">Manage</a></div></div>
    <div class="c4 panel"><div class="panel__hd"><h3>Automator</h3><span class="pill ${a.last_ok === false ? 'bad' : a.last_ok ? 'ok' : ''}">${a.last_ok === false ? 'failures' : a.last_ok ? 'clean' : 'no run yet'}</span></div>
      <div class="kv"><dt>Last run</dt><dd>${fmtT(a.last_run)} <span style="color:var(--muted)">(${ago(a.last_run)})</span></dd><dt>Next</dt><dd>${fmtT(a.next_run)}</dd><dt>Quota</dt><dd>${fmtN(a.quota_today)} of ${fmtN(a.quota_daily)} units</dd><dt>Token</dt><dd>${a.token_ok ? `ok${a.token_days_left != null ? ` · ~${a.token_days_left} d left` : ''}` : '<span style="color:var(--redL)">missing</span>'}</dd><dt>Holds</dt><dd>${a.holds ?? '—'} videos</dd></div>
      <div class="meter ${pct(a.quota_today, a.quota_daily) > 75 ? 'meter--warn' : 'meter--ok'}"><i style="width:${pct(a.quota_today, a.quota_daily)}%"></i></div>
      <div class="row" style="margin-top:14px"><a class="btn btn--sm" href="#automator">Open</a></div></div>
    <div class="c4 panel"><div class="panel__hd"><h3>Backups</h3><span class="pill ${b.failed_recent ? 'bad' : b.last ? 'ok' : ''}">${b.failed_recent ? `${b.failed_recent} failed` : b.last ? 'healthy' : 'none yet'}</span></div>
      <div class="kv"><dt>Last</dt><dd>${b.last ? `${esc(b.last.name)} · ${fmtT(b.last.started)} · ${b.last.ok ? 'ok' : 'failed'}` : '—'}</dd><dt>Jobs</dt><dd>${c.backups}</dd><dt>Running</dt><dd>${(b.running || []).length ? b.running.map(r => esc(r.job)).join(', ') : 'none'}</dd><dt>Synology</dt><dd>${n.mounted ? `mounted · ${fmtB(n.free)} free` : '<span style="color:var(--warn)">not mounted</span>'}</dd><dt>Apps</dt><dd>${c.apps_running} of ${c.apps} running</dd></div>
      <div class="row" style="margin-top:14px"><a class="btn btn--sm" href="#backups">History</a></div></div>

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
    $('#nuGo', m).onclick = async e => { const r = await act(e.target, () => api('/directory/users', { method: 'POST', body: { name: $('#nuName', m).value.trim(), display: $('#nuDisp', m).value.trim(), password: $('#nuPw', m).value, groups: $('#nuGroups', m).value.split(',').map(s => s.trim()).filter(Boolean) } }), 'User created'); if (r && r.ok !== false) { m.close(); render(); } };
  });
  $$('[data-pw]').forEach(b => b.onclick = () => modal(`<h2>Reset password</h2><p class="note" style="margin-bottom:14px">For <b>${esc(b.dataset.pw)}</b>. Their Mac asks for the new one at next login; the cached mobile account updates then.</p><div class="field"><label>New password</label><input id="rpPw" type="password"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="rpGo">Set</button></div>`, m => { $('#rpGo', m).onclick = async e => { const r = await act(e.target, () => api(`/directory/users/${encodeURIComponent(b.dataset.pw)}/reset-password`, { method: 'POST', body: { password: $('#rpPw', m).value } }), 'Password set'); if (r && r.ok !== false) m.close(); }; }));
  $$('[data-tog]').forEach(b => b.onclick = async () => { const r = await act(b, () => api(`/directory/users/${encodeURIComponent(b.dataset.tog)}/${b.dataset.en === '1' ? 'enable' : 'disable'}`, { method: 'POST' }), b.dataset.en === '1' ? 'Enabled' : 'Disabled'); if (r && r.ok !== false) render(); });
  $$('[data-del]').forEach(b => b.onclick = () => confirmType('Delete user', b.dataset.del, `This removes the account from the domain. <b>The home folder stays on disk</b> - nothing in it is deleted. Deleting is your click, not the server's.`, async () => { const r = await api(`/directory/users/${encodeURIComponent(b.dataset.del)}`, { method: 'DELETE', body: { confirm: b.dataset.del } }); if (r.ok === false) throw new Error(r.err); toast('User deleted'); render(); }));
  $('#addGroup').onclick = () => modal(`<h2>New group</h2><div class="field"><label>Name</label><input id="ngName" placeholder="Praise-Team"></div><div class="field"><label>Description</label><input id="ngDesc"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="ngGo">Create</button></div>`, m => { $('#ngGo', m).onclick = async e => { const r = await act(e.target, () => api('/directory/groups', { method: 'POST', body: { name: $('#ngName', m).value.trim(), description: $('#ngDesc', m).value.trim() } }), 'Group created'); if (r && r.ok !== false) { m.close(); render(); } }; });
  $$('[data-addm]').forEach(b => b.onclick = () => modal(`<h2>Add to ${esc(b.dataset.addm)}</h2><div class="field"><label>User name</label><input id="amUser"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="amGo">Add</button></div>`, m => { $('#amGo', m).onclick = async e => { const r = await act(e.target, () => api(`/directory/groups/${encodeURIComponent(b.dataset.addm)}/members`, { method: 'POST', body: { user: $('#amUser', m).value.trim() } }), 'Added'); if (r && r.ok !== false) { m.close(); render(); } }; }));
};

V.files = async () => {
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
V.files.after = () => {
  $('#addShare').onclick = () => modal(`<h2>New share</h2><div class="field"><label>Name</label><input id="nsName" placeholder="graphics"></div><div class="field"><label>Folder on the server</label><input id="nsPath" placeholder="/srv/arise/shares/graphics"></div><div class="field"><label>Who can use it</label><input id="nsGroup" value="Domain Users"><span class="hint">A group name. "Domain Users" is everyone.</span></div><div class="field"><label>Description</label><input id="nsComment"></div><div class="acts"><button class="btn btn--ghost" data-close>Cancel</button><button class="btn" id="nsGo">Create</button></div>`, m => { $('#nsGo', m).onclick = async e => { const r = await act(e.target, () => api('/shares', { method: 'POST', body: { name: $('#nsName', m).value.trim(), path: $('#nsPath', m).value.trim(), group: $('#nsGroup', m).value.trim(), comment: $('#nsComment', m).value.trim(), mac: true } }), 'Share created'); if (r && r.ok !== false) { m.close(); render(); } }; });
  $$('[data-rm]').forEach(b => b.onclick = () => confirmType('Remove share', b.dataset.rm, 'The share stops being visible on the network. <b>The folder and its files stay on disk.</b>', async () => { const r = await api(`/shares/${encodeURIComponent(b.dataset.rm)}`, { method: 'DELETE', body: { confirm: b.dataset.rm } }); if (r.ok === false) throw new Error(r.err); toast('Share removed'); render(); }));
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
  $$('[data-rmapp]').forEach(b => b.onclick = () => confirmType('Remove app', b.dataset.rmapp, 'Stops and removes the containers. <b>Its data folder is kept</b> under /srv/arise/apps.', async () => { const r = await api(`/apps/${encodeURIComponent(b.dataset.rmapp)}/remove`, { method: 'POST', body: { confirm: b.dataset.rmapp } }); if (r.ok === false) throw new Error(r.err); toast('Removed'); render(); }));
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
      <td class="acts"><button class="btn btn--ghost btn--xs" data-svc="${esc(s.unit)}" data-do="restart">Restart</button>${s.active === 'active' ? `<button class="btn btn--ghost btn--xs" data-svc="${esc(s.unit)}" data-do="stop">Stop</button>` : `<button class="btn btn--xs" data-svc="${esc(s.unit)}" data-do="start">Start</button>`}<a class="btn btn--ghost btn--xs" href="#logs/${encodeURIComponent(s.unit)}">Logs</a></td></tr>`).join('')}
  </tbody></table></div>`;
};
V.services.after = () => { $$('[data-svc]').forEach(b => b.onclick = async () => { if (b.dataset.svc === 'arise-web.service' && b.dataset.do !== 'restart') { toast('Stopping the dashboard from the dashboard is a bad idea', 'warn'); return; } const r = await act(b, () => api(`/services/${encodeURIComponent(b.dataset.svc)}/${b.dataset.do}`, { method: 'POST' }), `${b.dataset.do} ${b.dataset.svc}`); if (r) setTimeout(render, 1200); }); };

V.logs = async (arg) => {
  const units = ['arise-web.service', 'arise-automator.service', 'arise-backup.service', 'arise-mirror.service', 'samba-ad-dc.service', 'docker.service', 'arise-nas-mount.service'];
  const unit = decodeURIComponent(arg || units[0]);
  const r = await api(`/logs/${encodeURIComponent(unit)}?lines=300`);
  return `<div class="fade"><div class="toolbar"><select class="search" id="logUnit">${units.map(u => `<option ${u === unit ? 'selected' : ''}>${esc(u)}</option>`).join('')}</select><button class="btn btn--ghost btn--sm" id="logRefresh">Refresh</button><span class="spacer"></span><span class="sub" style="font-size:12px;color:var(--muted)">last 300 lines · journalctl -u ${esc(unit)}</span></div><pre class="log" style="max-height:72vh">${esc(r.text || '(empty)')}</pre></div>`;
};
V.logs.after = () => { $('#logUnit').onchange = e => location.hash = '#logs/' + encodeURIComponent(e.target.value); $('#logRefresh').onclick = render; };

V.settings = async () => {
  const s = await api('/settings');
  const sec = (name, d) => `<div class="c6 panel panel--flat"><div class="panel__hd"><h3>${esc(name)}</h3></div><div class="kv">${Object.entries(d).map(([k, v]) => `<dt>${esc(k)}</dt><dd class="mono" style="font-size:12.5px">${esc(Array.isArray(v) ? v.join(', ') : typeof v === 'boolean' ? (v ? 'yes' : 'no') : (v === '' ? '—' : v))}</dd>`).join('')}</div></div>`;
  return `<div class="fade"><p class="note" style="margin-bottom:14px">Read from <code>${esc(s._meta?.path)}</code>${s._meta?.found ? '' : ' <b>(not found: these are the defaults)</b>'}. The dashboard never writes this file; change it with <code>sudo nano ${esc(s._meta?.path)}</code> and <code>sudo systemctl restart arise-web</code>, or with <code>arisectl</code>. Secrets are never shown here.</p>
    <div class="grid">${['system', 'web', 'directory', 'automator', 'backups', 'nas', 'apps', 'github', 'paths'].filter(k => s[k]).map(k => sec(k, s[k])).join('')}</div></div>`;
};

/* ---------------- router + shell ---------------- */
function tabs(sel) {
  const root = $(sel); if (!root) return; const panels = $$('[data-tab]', root.parentElement);
  $$('button', root).forEach(b => b.onclick = () => { $$('button', root).forEach(x => x.classList.toggle('active', x === b)); panels.forEach(p => p.hidden = p.dataset.tab !== b.dataset.t); });
}
let renderSeq = 0;
async function render() {
  const [view, arg] = (location.hash.replace('#', '') || 'overview').split('/');
  const fn = V[view] || V.overview; S.view = V[view] ? view : 'overview';
  $$('#nav a').forEach(a => a.classList.toggle('active', a.dataset.view === S.view));
  $('#topTitle').textContent = TITLES[S.view]; $('#topKicker').textContent = 'Arise Server';
  closeSide();
  const seq = ++renderSeq; const el = $('#view');
  el.innerHTML = '<div class="grid"><div class="c12 panel panel--flat"><div class="skeleton" style="width:40%"></div><div class="skeleton" style="width:70%;margin-top:10px"></div><div class="skeleton" style="width:55%;margin-top:10px"></div></div></div>';
  try {
    const html = await fn(arg);
    if (seq !== renderSeq) return;
    el.innerHTML = html; fn.after && fn.after();
    if (S.view === 'overview' && S.stats) paintLive(S.stats);
  } catch (e) {
    if (e.status === 401) return showLogin(e);
    el.innerHTML = `<div class="panel panel--bad"><div class="panel__hd"><h3>Could not load</h3></div><p>${esc(e.message)}</p><div class="row" style="margin-top:12px"><button class="btn btn--sm" onclick="location.reload()">Reload</button></div></div>`;
  }
}
function closeSide() { $('#side').classList.remove('open'); $('#scrim').classList.remove('open'); $('#burger').setAttribute('aria-expanded', 'false'); }
$('#burger').onclick = () => { const o = !$('#side').classList.contains('open'); $('#side').classList.toggle('open', o); $('#scrim').classList.toggle('open', o); $('#burger').setAttribute('aria-expanded', o); };
$('#scrim').onclick = closeSide;
window.addEventListener('hashchange', render);
$('#logoutBtn').onclick = async () => { await api('/auth/logout', { method: 'POST' }).catch(() => {}); location.reload(); };

function showLogin(err) {
  document.body.innerHTML = `<div class="login"><div class="login__box">
    <div class="mark"><span class="kicker">Arise Church · Pineville</span></div><h1>Arise Server</h1>
    ${err?.setup ? `<p>No admin password has been set yet. On the server run:</p><pre class="log">sudo arisectl admin set-password</pre><p style="margin-top:12px">then reload this page.</p>` : `<p>${esc(err?.message && err.message !== 'Sign in' ? err.message : 'Sign in with the admin account from arise.toml.')}</p>
    <form id="lf"><div class="field"><label>User</label><input id="lu" value="bradly" autocomplete="username"></div><div class="field"><label>Password</label><input id="lp" type="password" autocomplete="current-password"></div><button class="btn" style="width:100%;justify-content:center" type="submit">Sign in</button></form>`}
  </div></div>`;
  const f = $('#lf'); if (f) f.onsubmit = async e => { e.preventDefault(); const b = $('button', f); b.classList.add('busy'); try { await api('/auth/login', { method: 'POST', body: { user: $('#lu').value, password: $('#lp').value } }); location.reload(); } catch (er) { toastLogin(er.message); } finally { b.classList.remove('busy'); } };
  function toastLogin(m) { let t = $('.login .toast'); if (!t) { t = document.createElement('div'); t.className = 'toast bad'; t.style.marginTop = '12px'; $('.login__box').appendChild(t); } t.textContent = m; }
}

async function boot() {
  if (window.ARISE_FORCE_DEMO) setDemoOnly();
  try {
    const me = await api('/auth/me');
    if (me.error) { if (me.error.setup) return showLogin({ setup: true }); return showLogin(me.error); }
    S.authed = true; S.user = me.user; if (me.demo) { S.demo = true; $('#demoBadge').hidden = false; } else $('#logoutBtn').hidden = false;
  } catch (e) { if (!S.demoOnly) return showLogin(e); }
  startStats();
  render();
}
boot();
})();
