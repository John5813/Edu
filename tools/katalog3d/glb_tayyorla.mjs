// GLB ni PowerPoint'ga mos holatga keltiradi: Draco/meshopt yechiladi, WebP/KTX2 → JPEG/PNG,
// teksturalar ≤ MAX px, juda og'ir to'rlar soddalashtiriladi, keraksiz ma'lumot tozalanadi.
//
// stdin: har qatorda {"in": "...", "out": "...", "max_texture": 2048, "max_tris": 600000}
// stdout: har qatorga {"ok": true, "tris": .., "size": .., "bbox": [...], "textures": ..} yoki {"ok": false, "error": ".."}
//
// Ishga tushirish: NODE_PATH=<gltf-transform o'rnatilgan node_modules> node glb_tayyorla.mjs
import { createRequire } from 'node:module';
import path from 'node:path';
import readline from 'node:readline';

console.log = console.info = console.warn = console.error;   // gltf-transform loglari stdout'ni buzmasin
const require = createRequire(path.join(process.env.NODE_PATH || process.cwd(), 'x.js'));
const { NodeIO } = require('@gltf-transform/core');
const { ALL_EXTENSIONS } = require('@gltf-transform/extensions');
const { dedup, prune, weld, simplify, getBounds, unpartition, flatten, clearNodeTransform } = require('@gltf-transform/functions');
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

async function handle(job) {
  const doc = await io.read(job.in);
  for (const ext of doc.getRoot().listExtensionsUsed()) {
    if (DROP.includes(ext.extensionName)) ext.dispose();
  }
  const maxTris = job.max_tris || 600000;
  const before = triangles(doc);
  if (before > maxTris && !job.bake_only) {
    await doc.transform(weld(), simplify({ simplifier: MeshoptSimplifier, ratio: maxTris / before, error: 0.001 }));
  }
  const ntex = job.bake_only ? doc.getRoot().listTextures().length : await textures(doc, job.max_texture || 2048);
  const baked = await bake(doc);
  await doc.transform(dedup(), prune(), unpartition());
  const tris = triangles(doc);
  if (tris < 500) throw new Error(`juda oz uchburchak: ${tris}`);
  const scene = doc.getRoot().getDefaultScene() || doc.getRoot().listScenes()[0];
  const b = getBounds(scene);
  await io.write(job.out, doc);
  const { size } = await import('node:fs').then((fs) => fs.promises.stat(job.out));
  return { ok: true, tris, tris_before: before, size, textures: ntex, baked,
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
