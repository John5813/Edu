// Har model uchun preview rasm (JPEG, odatda 512×512) — Chromium + <model-viewer>.
//
//   node tools/katalog3d/rasm.mjs <katalog_papka> <model-viewer.min.js yo'li> [--qayta] [--ulush 0/4] [--hajm 384]
//
// <katalog_papka>/<fan>/<id>/model.glb yonida preview.jpg paydo bo'ladi; borlari o'tkazib yuboriladi.
// --ulush i/n — ro'yxatning i-bo'lagi (bir nechta jarayonda parallel chizish uchun).
// --maska — fonsiz va soyasiz (shaffof) chizadi va <id>/mask.png ga yozadi: xuddi shu burchak va kadr,
//           preview.jpg ning shaffoflik niqobi (3D ko'rinmaydigan dasturlar uchun model rasmi).
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const [root, mvPath] = process.argv.slice(2);
const qayta = process.argv.includes('--qayta');
const opt = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const [ulush, ulushlar] = opt('--ulush', '0/1').split('/').map(Number);
const SIZE = Number(opt('--hajm', '512'));
const MASK = process.argv.includes('--maska');
const OUT_NAME = MASK ? 'mask.png' : 'preview.jpg';
let models = [];
for (const fan of fs.readdirSync(root)) {
  const d = path.join(root, fan);
  if (fan.startsWith('_') || !fs.statSync(d).isDirectory()) continue;
  for (const id of fs.readdirSync(d)) {
    const glb = path.join(d, id, 'model.glb');
    const jpg = path.join(d, id, OUT_NAME);
    if (fs.existsSync(glb) && (qayta || !fs.existsSync(jpg))) models.push([`${fan}/${id}/model.glb`, jpg]);
  }
}
models = models.filter((_, i) => i % ulushlar === ulush);
console.error(`${models.length} ta rasm chiziladi`);

const BG = MASK ? 'transparent' : '#f2f2f0';
const page_html = `<!doctype html><html><body style="margin:0;background:${BG}">
<style>model-viewer::part(default-progress-bar){display:none}</style>
<script type="module" src="/__mv.js"></script>
<model-viewer id="m" style="width:${SIZE}px;height:${SIZE}px;background:${BG}" camera-orbit="35deg 70deg auto"
  shadow-intensity="${MASK ? 0 : 0.6}" exposure="1" environment-image="neutral" interaction-prompt="none"></model-viewer>
<script>
window.show = (src) => new Promise((ok) => {
  const m = document.getElementById('m');
  const done = (e) => { m.removeEventListener('load', done); m.removeEventListener('error', done); ok(e.type); };
  m.addEventListener('load', done); m.addEventListener('error', done);
  m.src = src;
});
</script></body></html>`;

const server = http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  if (url === '/') { res.writeHead(200, { 'Content-Type': 'text/html' }); return res.end(page_html); }
  const file = url === '/__mv.js' ? mvPath : path.join(root, url);
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': file.endsWith('.js') ? 'text/javascript' : 'model/gltf-binary' });
    res.end(data);
  });
});
await new Promise((ok) => server.listen(0, '127.0.0.1', ok));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: SIZE, height: SIZE } });
await page.goto(base + '/');
await page.waitForFunction(() => customElements.get('model-viewer'));
let n = 0, xato = 0;
for (const [src, jpg] of models) {
  try {
    const r = await Promise.race([page.evaluate((s) => window.show('/' + s + '?' + Date.now()), src),
      new Promise((ok) => setTimeout(() => ok('timeout'), 90000))]);
    if (r !== 'load') throw new Error(r);
    await page.waitForTimeout(400);
    await page.locator('#m').screenshot(MASK ? { path: jpg, type: 'png', omitBackground: true }
      : { path: jpg, type: 'jpeg', quality: 82 });
  } catch (e) {
    xato++;
    console.error('xato', src, String(e).slice(0, 120));
    if (String(e).includes('timeout')) { await page.goto(base + '/'); await page.waitForFunction(() => customElements.get('model-viewer')); }
  }
  if (++n % 50 === 0) console.error(`${n}/${models.length} (xato ${xato})`);
}
await browser.close();
server.close();
console.error(`tugadi: ${n - xato} ok, ${xato} xato`);
