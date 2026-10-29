// GLB ni PowerPoint'ga mos holatga keltiradi: Draco/meshopt yechiladi, WebP/KTX2 → JPEG/PNG,
// teksturalar ≤ MAX px, juda og'ir to'rlar soddalashtiriladi, keraksiz ma'lumot tozalanadi.
//
// stdin: har qatorda {"in": "...", "out": "...", "max_texture": 2048, "max_tris": 600000}
// stdout: har qatorga {"ok": true, "tris": .., "size": .., "bbox": [...], "textures": ..} yoki {"ok": false, "error": ".."}
//
// Ishga tushirish: NODE_PATH=<gltf-transform o'rnatilgan node_modules> node glb_tayyorla.mjs
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';

console.log = console.info = console.warn = console.error;   // gltf-transform loglari stdout'ni buzmasin
const require = createRequire(path.resolve(process.env.NODE_PATH || process.cwd(), 'x.js'));
const { NodeIO } = require('@gltf-transform/core');
const { ALL_EXTENSIONS } = require('@gltf-transform/extensions');
const { dedup, prune, weld, simplify, getBounds, unpartition, flatten, clearNodeTransform, metalRough, join } = require('@gltf-transform/functions');
const draco3d = require('draco3dgltf');
const { MeshoptDecoder, MeshoptSimplifier } = require('meshoptimizer');
const sharp = require('sharp');

const DROP = ['KHR_draco_mesh_compression', 'EXT_meshopt_compression', 'EXT_texture_webp',
  'KHR_texture_basisu', 'EXT_mesh_gpu_instancing', 'KHR_mesh_quantization', 'EXT_texture_avif'];

await MeshoptDecoder.ready;
await MeshoptSimplifier.ready;
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
  'draco3d.decoder': await draco3d.createDecoderModule(),
  'meshopt.decoder': MeshoptDecoder,
});

function triangles(doc) {
  let n = 0;
  for (const mesh of doc.getRoot().listMeshes()) {
    for (const p of mesh.listPrimitives()) {
      if (p.getMode() !== 4) continue;
      const idx = p.getIndices();
      const pos = p.getAttribute('POSITION');
      n += (idx ? idx.getCount() : pos ? pos.getCount() : 0) / 3;
    }
  }
  return Math.round(n);
}

async function textures(doc, max) {
  const root = doc.getRoot();
  const alpha = new Set();
  for (const m of root.listMaterials()) {
    const t = m.getBaseColorTexture();
    if (t && m.getAlphaMode() !== 'OPAQUE') alpha.add(t);
  }
  for (const tex of root.listTextures()) {
    const img = tex.getImage();
    if (!img) { tex.dispose(); continue; }
    const s = sharp(Buffer.from(img), { limitInputPixels: false });
    const meta = await s.metadata();
    let pipe = s;
    if (Math.max(meta.width || 0, meta.height || 0) > max) {
      pipe = pipe.resize({ width: max, height: max, fit: 'inside', withoutEnlargement: true });
    }
    const keepAlpha = alpha.has(tex) && meta.hasAlpha;
    const out = keepAlpha ? await pipe.png({ compressionLevel: 9 }).toBuffer()
      : await pipe.flatten({ background: '#ffffff' }).jpeg({ quality: 85, mozjpeg: true }).toBuffer();
    tex.setImage(new Uint8Array(out)).setMimeType(keepAlpha ? 'image/png' : 'image/jpeg');
    const uri = tex.getURI();
    if (uri) tex.setURI(uri.replace(/\.[a-z0-9]+$/i, keepAlpha ? '.png' : '.jpg'));
  }
  return root.listTextures().length;
}

// Node transformlarini geometriyaga o'tkazadi: shunda accessor min/max = haqiqiy chegara qutisi
// (services/med3d/glb.bounds va pptx3d kamerasi shunga tayanadi). Skelet/animatsiyali modelga tegilmaydi.
async function bake(doc) {
  const root = doc.getRoot();
  if (root.listSkins().length || root.listAnimations().length) return false;
  await doc.transform(flatten());
  for (const node of root.listNodes()) {
    if (node.getMesh()) clearNodeTransform(node);
  }
  return true;
}

// Asosiy massadan uzoqda yotgan mayda bo'laklarni (chiroq, yordamchi nuqta, adashgan uchburchak) olib tashlaydi —
// ular chegara qutisini kattalashtirib, model ramkada nuqtadek kichrayib qolardi. Faqat pishirilgan modelda
// (u yerda node transformi yo'q, accessor koordinatasi = dunyo koordinatasi).
function chetlarni_olib_tashla(doc) {
  const nodes = doc.getRoot().listNodes().filter((n) => n.getMesh());
  const info = [];
  const sample = [];
  let total = 0;
  for (const node of nodes) {
    const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    let tris = 0;
    for (const prim of node.getMesh().listPrimitives()) {
      const pos = prim.getAttribute('POSITION');
      if (!pos) continue;
      const n = pos.getCount();
      tris += (prim.getIndices() ? prim.getIndices().getCount() : n) / 3;
      const step = Math.max(1, Math.floor(n / 2000));
      const v = [0, 0, 0];
      for (let i = 0; i < n; i++) {
        pos.getElement(i, v);
        for (let k = 0; k < 3; k++) { if (v[k] < lo[k]) lo[k] = v[k]; if (v[k] > hi[k]) hi[k] = v[k]; }
        if (i % step === 0) sample.push([v[0], v[1], v[2]]);
      }
    }
    total += tris;
    info.push({ node, lo, hi, tris });
  }
  if (info.length < 2 || sample.length < 50) return 0;
  const core_lo = [], core_hi = [];
  for (let k = 0; k < 3; k++) {
    const a = sample.map((p) => p[k]).sort((x, y) => x - y);
    core_lo.push(a[Math.floor(a.length * 0.01)]);
    core_hi.push(a[Math.ceil(a.length * 0.99) - 1]);
  }
  const ext = Math.max(...core_hi.map((h, k) => h - core_lo[k])) || 1;
  let removed = 0;
  for (const { node, lo, hi, tris } of info) {
    const outside = [0, 1, 2].some((k) => lo[k] > core_hi[k] + 0.5 * ext || hi[k] < core_lo[k] - 0.5 * ext);
    if (outside && tris < 0.02 * total) { node.dispose(); removed++; }
  }
  return removed;
}

async function handle(job) {
  const doc = await io.read(job.in);
  for (const ext of doc.getRoot().listExtensionsUsed()) {
    if (DROP.includes(ext.extensionName)) ext.dispose();
  }
  // PowerPoint (va ko'p ko'ruvchilar) eski spec/gloss materialni o'qimaydi — model oq chiqadi.
  if (doc.getRoot().listExtensionsUsed().some((e) => e.extensionName === 'KHR_materials_pbrSpecularGlossiness')) {
    await doc.transform(metalRough());
  }
  const maxTris = job.max_tris || 600000;
  const before = triangles(doc);
  // Tartib: transformni pishirish → chetdagi bo'laklarni olib tashlash → bir xil materialli bo'laklarni
  // birlashtirish (mayda bo'laklarga bo'lingan to'r aks holda soddalashmaydi) → soddalashtirish → teksturalar.
  const baked = await bake(doc);
  const chetlar = baked ? chetlarni_olib_tashla(doc) : 0;
  if (baked) await doc.transform(join({ keepNamed: false }));
  if (before > maxTris && !job.bake_only) {
    // Avval sifatni saqlab (xato ≤ 0.1%), yetmasa — kattaroq xatoga ruxsat bilan qayta.
    for (const error of [0.001, 0.01, 0.05, 0.2]) {
      const now = triangles(doc);
      if (now <= maxTris * 1.2) break;
      await doc.transform(weld(), simplify({ simplifier: MeshoptSimplifier, ratio: maxTris / now, error }));
    }
  }
  const ntex = job.bake_only ? doc.getRoot().listTextures().length : await textures(doc, job.max_texture || 2048);
  await doc.transform(dedup(), prune(), unpartition());
  const tris = triangles(doc);
  if (tris < 500) throw new Error(`juda oz uchburchak: ${tris}`);
  if (!job.bake_only && tris > maxTris * 3) throw new Error(`soddalashmadi: ${tris} uchburchak`);
  const scene = doc.getRoot().getDefaultScene() || doc.getRoot().listScenes()[0];
  const b = getBounds(scene);
  if (![...b.min, ...b.max].every(Number.isFinite)) throw new Error('chegara qutisi noto\'g\'ri (NaN/Infinity koordinata)');
  // Kengaytmaga qaramay doim binar GLB (io.write ".tmp" ni JSON-glTF + alohida fayllar qilib yozadi).
  const bin = await io.writeBinary(doc);
  await fs.promises.writeFile(job.out, bin);
  const size = bin.byteLength;
  return { ok: true, tris, tris_before: before, size, textures: ntex, baked, chetlar,
    bbox: [b.min, b.max], animations: doc.getRoot().listAnimations().length };
}

const rl = readline.createInterface({ input: process.stdin });
for await (const line of rl) {
  if (!line.trim()) continue;
  let res;
  try {
    res = await handle(JSON.parse(line));
  } catch (e) {
    res = { ok: false, error: String(e && e.message || e).slice(0, 300) };
  }
  process.stdout.write(JSON.stringify(res) + '\n');
}
