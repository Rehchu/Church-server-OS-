/* Arise Server — landing page script: mobile menu, tabs, terminal typewriter, reveal, back-to-top */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const y = $('#year'); if (y) y.textContent = new Date().getFullYear();

  const btn = $('#menuBtn'), mob = $('#mobile');
  const toggle = f => { const o = f !== undefined ? f : !mob.classList.contains('open'); mob.classList.toggle('open', o); btn.setAttribute('aria-expanded', o); mob.setAttribute('aria-hidden', !o); document.body.style.overflow = o ? 'hidden' : ''; };
  btn.addEventListener('click', () => toggle());
  $$('a', mob).forEach(a => a.addEventListener('click', () => toggle(false)));
  window.addEventListener('resize', () => { if (innerWidth > 1000) toggle(false); });

  $$('[data-tabs]').forEach(root => {
    const tabs = $$('[role=tab]', root), panels = $$('[role=tabpanel]', root);
    tabs.forEach(t => t.addEventListener('click', () => {
      tabs.forEach(x => { x.classList.toggle('active', x === t); x.setAttribute('aria-selected', x === t); });
      panels.forEach(p => { const on = p.id === t.getAttribute('aria-controls'); p.classList.toggle('active', on); p.hidden = !on; });
    }));
  });

  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const els = $$('.reveal');
  if ('IntersectionObserver' in window && !reduce) {
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: .12, rootMargin: '0px 0px -8% 0px' });
    els.forEach(el => io.observe(el));
  } else els.forEach(el => el.classList.add('in'));

  const top = $('#toTop');
  const onScroll = () => top.classList.toggle('on', scrollY > 600);
  addEventListener('scroll', onScroll, { passive: true }); onScroll();

  /* terminal */
  const term = $('#term');
  const script = [
    ['p', '$ arisectl info'],
    ['', 'Arise Server v0.1.0 “Pineville”'],
    ['', '  host      arise-server  (Ubuntu 24.04, 4 cores, 16 GB RAM)'],
    ['', '  realm     AD.ARISECENLA.COM / ARISE   directory on'],
    ['', '  web       http://arise-server:4147   password set'],
    ['', '  automator /srv/arise/automator/ARISE_YouTube_Updater  at 02:05'],
    ['', '  backups   /mnt/synology/arise-backups/restic  at 03:00'],
    ['p', '$ sudo arisectl doctor'],
    ['ok', '  ✓ Samba AD DC answers'],
    ['ok', '  ✓ DNS SRV for ad.arisecenla.com resolves'],
    ['ok', '  ✓ token.json present'],
    ['ok', '  ✓ repository /mnt/synology/arise-backups/restic'],
    ['warn', '  ! arise-automator.timer waiting · next 02:05 America/Chicago'],
    ['ok', '  ✓ clock synchronised'],
    ['p', '$ _'],
  ];
  if (term) {
    if (reduce) { term.innerHTML = script.map(([c, t]) => `<span class="${c}">${t}</span>`).join('\n'); }
    else {
      let i = 0, j = 0, out = '';
      const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
      const step = () => {
        if (i >= script.length) { term.innerHTML = out; return; }
        const [c, t] = script[i];
        if (c === 'p') { if (j <= t.length) { term.innerHTML = out + `<span class="p cur">${esc(t.slice(0, j))}</span>`; j++; setTimeout(step, 38); return; } out += `<span class="p">${esc(t)}</span>\n`; i++; j = 0; setTimeout(step, 260); return; }
        out += `<span class="${c}">${esc(t)}</span>\n`; term.innerHTML = out + '<span class="cur"></span>'; i++; setTimeout(step, 90);
      };
      setTimeout(step, 500);
    }
  }
})();
