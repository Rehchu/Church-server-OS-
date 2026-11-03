/* ariseOS service worker: makes the dashboard installable and shows push
   notifications. It caches nothing (the dashboard is live data); offline it
   shows a short page. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  if (e.request.mode !== 'navigate') return;
  e.respondWith(fetch(e.request).catch(() => new Response('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><body style="margin:0;background:#0A0A0C;color:#F4F2F0;font-family:-apple-system,Helvetica,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center"><div><div style="font-size:42px;color:#D6222D">&#9650;</div><h1 style="font-weight:600;letter-spacing:.04em">ariseOS</h1><p>The server is out of reach. On the church network or Tailscale it comes back on its own.</p></div></body>', { headers: { 'Content-Type': 'text/html' } })));
});
self.addEventListener('push', e => {
  let d = {}; try { d = e.data ? e.data.json() : {}; } catch { d = { body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.title || 'ariseOS', { body: d.body || '', icon: '/assets/icons/icon-192.png', badge: '/assets/icons/icon-192.png', tag: d.tag || 'arise', data: { url: d.url || '/' } }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => { for (const c of cs) { if ('focus' in c) { c.navigate(url); return c.focus(); } } return self.clients.openWindow(url); }));
});
