// Serves web/ the way the published artifact does: index.html without its document
// skeleton, relative paths, window.ARISE_FORCE_DEMO set, wrapped again in a plain
// document (which is what the artifact host does). No Arise API behind it, so every
// call lands in web/demo-mock.js, exactly as in the artifact.
//
//   node tests/ui/serve-preview.js [port]          then open http://127.0.0.1:<port>/
//   DEMO_DATA=/path/to/demo-data.js node ...       to try a freshly generated sample set
const http = require('http');
const fs = require('fs');
const path = require('path');

const WEB = path.resolve(__dirname, '..', '..', 'web');
const TYPES = { '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.html': 'text/html', '.json': 'application/json', '.webmanifest': 'application/manifest+json' };

function page() {
  let html = fs.readFileSync(path.join(WEB, 'index.html'), 'utf8');
  html = html.replace(/<!doctype html>\s*/i, '').replace(/<\/?html[^>]*>|<\/?head>|<\/?body[^>]*>/gi, '');
  html = html.split('"/assets/').join('"./').split("'/assets/").join("'./").replace('href="/favicon.svg"', 'href="./favicon.svg"');
  html = html.replace('<script src="./vendor/xterm.js">', '<script>window.ARISE_FORCE_DEMO = true;</script>\n<script src="./vendor/xterm.js">');
  if (!html.includes('ARISE_FORCE_DEMO')) throw new Error('index.html changed shape: no xterm script to hang the preview flag on');
  return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' + html + '</body></html>';
}

// The phone checklist page (round 7, 89), the same way: relative paths, the preview flag set.
function checklistPage() {
  let html = fs.readFileSync(path.join(WEB, 'checklist.html'), 'utf8');
  html = html.split('"/assets/').join('"./').replace('href="/favicon.svg"', 'href="./favicon.svg"').replace('href="/manifest.webmanifest"', 'href="./manifest.webmanifest"');
  html = html.replace('<script src="./demo-data.js">', '<script>window.ARISE_FORCE_DEMO = true;</script>\n<script src="./demo-data.js">');
  if (!html.includes('ARISE_FORCE_DEMO = true')) throw new Error('checklist.html changed shape: no demo-data script to hang the preview flag on');
  return html;
}

function serve(port = 0) {
  const srv = http.createServer((req, res) => {
    const u = decodeURIComponent(req.url.split('?')[0]);
    if (u === '/' || u === '/index.html') { res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }); return res.end(page()); }
    if (u === '/checklist' || u === '/checklist.html') { res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }); return res.end(checklistPage()); }
    let f = path.join(WEB, path.normalize(u).replace(/^(\.\.[/\\])+/, ''));
    if (u === '/demo-data.js' && process.env.DEMO_DATA) f = process.env.DEMO_DATA;
    if (!f.startsWith(WEB) && f !== process.env.DEMO_DATA) { res.writeHead(403); return res.end(); }
    fs.readFile(f, (err, buf) => {
      if (err) { res.writeHead(404, { 'content-type': 'text/plain' }); return res.end('not found'); }
      res.writeHead(200, { 'content-type': (TYPES[path.extname(f)] || 'application/octet-stream') + '; charset=utf-8' }); res.end(buf);
    });
  });
  return new Promise(r => srv.listen(port, '127.0.0.1', () => r(srv)));
}

module.exports = { serve, page, checklistPage };
if (require.main === module) serve(+process.argv[2] || 8098).then(s => console.log(`preview on http://127.0.0.1:${s.address().port}/`));
