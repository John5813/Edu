"""Geometriya uchun 3D modellar — katalogga o'zimiz yasaymiz (dasturda, aniq o'lchamlar bilan).

Katalogda (Objaverse/Smithsonian skanlari) toza geometrik jismlar yo'q edi: «Fazoviy jismlarning hajmi» kabi
maktab mavzulariga AI basketbol to'pi, gaz rezervuarlari va Rim arkasini qo'yardi. Bu yerda 5-11-sinf geometriya
va stereometriyasi uchun to'plam yasaladi:

- «Geometrik jismlar»: kub, parallelepiped (to'g'ri va og'ma), prizmalar, piramidalar (kesik ham), muntazam
  ko'pyoqlar (Platon jismlari), silindr, konus (kesik ham), shar va uning qismlari, birlik kubchalar;
- «Geometriya: kesimlar va elementlar»: karkas uslubida — diagonal, balandlik, apofema, o'q kesimi, ichi ochilgan
  shar, ichki chizilgan jismlar, Arximed jismlari, fazoviy koordinatalar sistemasi;
- «Geometriya: yoyilmalar»: kub, parallelepiped, prizma, piramida, silindr, konus yoyilmalari;
- «Geometriya: tekis shakllar»: uchburchaklar, to'rtburchaklar, doira, muntazam oltiburchak (yupqa plastinka).

Uslub: yoqlar rangli, qirralar to'q naycha, uchlar sharcha; ichki elementlar rangli chiziq yoki plastinka
(balandlik — qizil, apofema/yasovchi/diagonal — to'q sariq, radius — to'q ko'k). Shaffoflik ishlatilmaydi
(PowerPoint 3D da ishonchsiz): ichki qismlar karkas yoki kesib ochilgan jism bilan ko'rsatiladi.
Har model 20-250 KB, litsenziya CC0 (o'zimizniki).

    python tools/katalog3d/geometriya.py            # hammasi
    python tools/katalog3d/geometriya.py geo_kub    # faqat shu modellarning rasmi qayta chiziladi

Natija: `data/katalog3d/geometriya.json` (katalog yozuvlari), `data/katalog3d/preview/<id>.jpg` va
`mask/<id>.png` (zaxira rasm uchun), modellar — `KATALOG3D_DIR/geometriya/<id>/model.glb`.
"""
import json
import os
import sys
from typing import List, Sequence

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("BOT_TOKEN", "1:x")

from services import katalog3d  # noqa: E402
from services.med3d.glb import Primitive, write_glb  # noqa: E402

# ───────────────────────────────────────────── uslub
EDGE = (0.30, 0.45, 0.80, 1.0)          # karkas chiziqlari — o'rta yorqinlik: oq va to'q fonda ham ko'rinadi


def shade(color, k=0.42):
    """Yoq rangining to'q tusi — yaxlit jism qirralari uchun (har qanday fonda yoq ustida ko'rinadi)."""
    return (color[0] * k, color[1] * k, color[2] * k, 1.0)
HEIGHT = (0.90, 0.20, 0.20, 1.0)        # balandlik — qizil
SLANT = (0.96, 0.55, 0.10, 1.0)         # apofema, yasovchi, diagonal — to'q sariq
RADIUS = (0.12, 0.30, 0.70, 1.0)        # radius — to'q ko'k
POINT = (0.90, 0.20, 0.20, 1.0)
TUBE = 0.035                            # qirra naychasi radiusi (jism ~2 birlik)
C = {"ko'k": (0.20, 0.47, 0.93, 1), "sariq_q": (0.96, 0.55, 0.16, 1), "pushti": (0.89, 0.33, 0.55, 1),
     "feruza": (0.12, 0.68, 0.62, 1), "yashil": (0.27, 0.70, 0.36, 1), "binafsha": (0.55, 0.36, 0.86, 1),
     "sariq": (0.98, 0.78, 0.18, 1), "qizil": (0.92, 0.33, 0.27, 1), "moviy": (0.25, 0.70, 0.90, 1),
     "kesim": (0.55, 0.80, 1.00, 1), "kesim2": (1.00, 0.84, 0.45, 1), "ichki": (0.99, 0.90, 0.62, 1)}


# ───────────────────────────────────────────── to'r yordamchilari
def flat(vertices, faces, centre=None):
    """Ko'pyoq: har yoq alohida (tekis yorug'lik), qavariq ko'pburchak yoqlar uchburchaklarga bo'linadi."""
    v = np.asarray(vertices, float)
    centre = v.mean(0) if centre is None else np.asarray(centre, float)
    pos, nor, idx = [], [], []
    for face in faces:
        pts = v[list(face)]
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        n /= np.linalg.norm(n)
        if np.dot(n, pts.mean(0) - centre) < 0:          # normal tashqariga qarasin
            n, pts = -n, pts[::-1]
        base = len(pos)
        pos += list(pts)
        nor += [n] * len(pts)
        for k in range(1, len(pts) - 1):
            idx += [base, base + k, base + k + 1]
    return np.array(pos), np.array(nor), np.array(idx)


def tube(a, b, r=TUBE, seg=14):
    a, b = np.asarray(a, float), np.asarray(b, float)
    z = (b - a) / np.linalg.norm(b - a)
    x = np.cross(z, [0, 0, 1] if abs(z[2]) < 0.9 else [1, 0, 0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    ring_ = np.cos(ang)[:, None] * x + np.sin(ang)[:, None] * y
    idx = []
    for i in range(seg):
        j = (i + 1) % seg
        idx += [i, j, seg + i, j, seg + j, seg + i]
    return np.vstack([a + r * ring_, b + r * ring_]), np.vstack([ring_, ring_]), np.array(idx)


def dashed(a, b, r=TUBE * 0.7, dash=0.12, gap=0.08):
    a, b = np.asarray(a, float), np.asarray(b, float)
    length = np.linalg.norm(b - a)
    d = (b - a) / length
    parts, t = [], 0.0
    while t < length:
        e = min(t + dash, length)
        if e - t > 0.02:
            parts.append(tube(a + d * t, a + d * e, r, 8))
        t = e + gap
    return parts


def sphere(r, seg=64, rings=32, centre=(0, 0, 0), skip=None):
    """UV shar. skip(theta, phi) — True bo'lsa, o'sha to'rtburchak tashlanadi (kesib ochish uchun)."""
    th = np.linspace(0, np.pi, rings + 1)
    ph = np.linspace(0, 2 * np.pi, seg + 1)
    t, p = np.meshgrid(th, ph, indexing="ij")
    n = np.stack([np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)], -1).reshape(-1, 3)
    idx = []
    w = seg + 1
    for i in range(rings):
        for j in range(seg):
            if skip and skip((th[i] + th[i + 1]) / 2, (ph[j] + ph[j + 1]) / 2):
                continue
            a, b = i * w + j, i * w + j + 1
            idx += [a, a + w, b, b, a + w, b + w]
    return np.asarray(centre, float) + r * n, n, np.array(idx)


def ball(c, r):
    return sphere(r, 16, 8, centre=c)


def lathe(profile, seg=72, smooth_sphere=None):
    """Aylanish jismi sirti: profile — [(radius, z)]. smooth_sphere=z markaz — shar bo'lagi uchun aniq normal."""
    ang = np.linspace(0, 2 * np.pi, seg + 1)
    prof = np.asarray(profile, float)
    pos, nor, idx = [], [], []
    for k in range(len(prof) - 1):
        (r0, z0), (r1, z1) = prof[k], prof[k + 1]
        nr, nz = z1 - z0, -(r1 - r0)
        ln = np.hypot(nr, nz) or 1
        nr, nz = nr / ln, nz / ln
        base = len(pos)
        for a in ang:
            c, s = np.cos(a), np.sin(a)
            pos += [[r0 * c, r0 * s, z0], [r1 * c, r1 * s, z1]]
            if smooth_sphere is not None:
                for rr, zz in ((r0, z0), (r1, z1)):
                    v = np.array([rr * c, rr * s, zz - smooth_sphere])
                    nor.append(v / (np.linalg.norm(v) or 1))
            else:
                nor += [[nr * c, nr * s, nz]] * 2
        for i in range(seg):
            a, b = base + 2 * i, base + 2 * i + 2
            idx += [a, b, a + 1, b, b + 1, a + 1]
    return np.array(pos), np.array(nor), np.array(idx)


def disc(r, z, up, seg=72):
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    pos = np.vstack([[0, 0, z], np.stack([r * np.cos(ang), r * np.sin(ang), np.full(seg, z)], 1)])
    nor = np.tile([0, 0, 1 if up else -1], (seg + 1, 1))
    idx = []
    for i in range(seg):
        a, b = 1 + i, 1 + (i + 1) % seg
        idx += [0, a, b] if up else [0, b, a]
    return pos, nor, np.array(idx)


def ring(r, z, seg=48, rad=TUBE * 0.9, centre=(0, 0, 0), plane="xy"):
    ang = np.linspace(0, 2 * np.pi, seg + 1)
    cx, cy, cz = centre
    if plane == "xy":
        pts = np.stack([cx + r * np.cos(ang), cy + r * np.sin(ang), np.full(seg + 1, cz + z)], 1)
    else:                                                   # xz — vertikal aylana (meridian)
        pts = np.stack([cx + r * np.cos(ang), np.full(seg + 1, cy), cz + z + r * np.sin(ang)], 1)
    return [tube(pts[i], pts[i + 1], rad, 8) for i in range(seg)]


def merge(parts):
    pos, nor, idx, off = [], [], [], 0
    for p, n, i in parts:
        pos.append(p); nor.append(n); idx.append(np.asarray(i) + off)
        off += len(p)
    return np.vstack(pos), np.vstack(nor), np.concatenate(idx)


def edges_of(faces):
    out = set()
    for f in faces:
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            out.add((min(a, b), max(a, b)))
    return sorted(out)


def wire(vertices, edges, r=TUBE, balls=True):
    v = np.asarray(vertices, float)
    parts = [tube(v[a], v[b], r) for a, b in edges]
    if balls:
        parts += [ball(p, r * 1.35) for p in v]
    return parts


def prim(parts, color, name, rough=0.5):
    return Primitive(*(merge(parts) if isinstance(parts, list) else parts), color, rough, name)


def plate_poly(pts, t=0.02):
    """Fazodagi tekis qavariq ko'pburchak (ikki tomonlama, yupqa) — kesim, uchburchak va h.k."""
    p = np.asarray(pts, float)
    n = np.cross(p[1] - p[0], p[2] - p[0])
    n /= np.linalg.norm(n)
    k = len(p)
    pos = np.vstack([p + n * t / 2, p - n * t / 2])
    nor = np.vstack([np.tile(n, (k, 1)), np.tile(-n, (k, 1))])
    idx = []
    for i in range(1, k - 1):
        idx += [0, i, i + 1, k, k + i + 1, k + i]
    return pos, nor, np.array(idx)


# ───────────────────────────────────────────── ko'pyoqlar (uchlar va yoqlar)
def box(a, b, c, shift=(0, 0)):
    """To'g'ri (shift=0) yoki og'ma parallelepiped: yuqori asos `shift` ga surilgan."""
    sx, sy = shift
    v = [[x + (sx if z else 0), y + (sy if z else 0), z] for z in (0, c) for y in (-b / 2, b / 2) for x in (-a / 2, a / 2)]
    return v, [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]


def ngon(n, r, z=0.0, start=90):
    return [[r * np.cos(np.radians(start + 360 * k / n)), r * np.sin(np.radians(start + 360 * k / n)), z] for k in range(n)]


def prism(n, r, h, start=90):
    v = ngon(n, r, 0, start) + ngon(n, r, h, start)
    faces = [tuple(range(n)), tuple(range(n, 2 * n))] + [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    return v, faces


def pyramid_n(n, r, h, start=45, top_r=0.0):
    """n-burchakli piramida; top_r > 0 — kesik piramida."""
    if top_r:
        return prism_like(ngon(n, r, 0, start), ngon(n, top_r, h, start))
    v = ngon(n, r, 0, start) + [[0, 0, h]]
    return v, [tuple(range(n))] + [(k, (k + 1) % n, n) for k in range(n)]


def prism_like(bottom, top):
    n = len(bottom)
    faces = [tuple(range(n)), tuple(range(n, 2 * n))] + [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    return bottom + top, faces


def tetrahedron(a):
    return pyramid_n(3, a / np.sqrt(3), a * np.sqrt(2 / 3), start=90)


def octahedron(a):
    s = a / np.sqrt(2)
    v = [[s, 0, s], [-s, 0, s], [0, s, s], [0, -s, s], [0, 0, 0], [0, 0, 2 * s]]
    return v, [(0, 2, 5), (2, 1, 5), (1, 3, 5), (3, 0, 5), (2, 0, 4), (1, 2, 4), (3, 1, 4), (0, 3, 4)]


def icosahedron(scale):
    p = (1 + 5 ** 0.5) / 2
    v = np.array([[-1, p, 0], [1, p, 0], [-1, -p, 0], [1, -p, 0], [0, -1, p], [0, 1, p], [0, -1, -p], [0, 1, -p],
                  [p, 0, -1], [p, 0, 1], [-p, 0, -1], [-p, 0, 1]], float)
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
             (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
             (8, 6, 7), (9, 8, 1)]
    v = v * scale / 2
    v[:, 2] -= v[:, 2].min()
    return v.tolist(), faces


def dodecahedron(scale):
    p = (1 + 5 ** 0.5) / 2
    v = [[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    v += [[0, s / p, t * p] for s in (-1, 1) for t in (-1, 1)]
    v += [[s / p, t * p, 0] for s in (-1, 1) for t in (-1, 1)]
    v += [[s * p, 0, t / p] for s in (-1, 1) for t in (-1, 1)]
    v = np.array(v, float)
    edge = 2 / p                                          # yoqlar: qirra bilan bog'langan 5 uchli tekis halqalar
    adj = {i: [j for j in range(20) if j != i and abs(np.linalg.norm(v[i] - v[j]) - edge) < 1e-6] for i in range(20)}
    faces = set()
    for a in range(20):
        for b in adj[a]:
            for c in adj[b]:
                if c == a:
                    continue
                for d in adj[c]:
                    if d in (a, b):
                        continue
                    for e in adj[d]:
                        if e in (a, b, c) or a not in adj[e]:
                            continue
                        pts = v[[a, b, c, d, e]]
                        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
                        if all(abs(np.dot(n, x - pts[0])) < 1e-6 for x in pts):
                            faces.add(tuple(sorted((a, b, c, d, e))))
    ordered = []
    for f in faces:                                       # uchlarni aylana bo'yicha tartiblash
        pts = v[list(f)]
        c = pts.mean(0)
        n = c / np.linalg.norm(c)
        x = (pts[0] - c) / np.linalg.norm(pts[0] - c)
        y = np.cross(n, x)
        ang = [np.arctan2(np.dot(q - c, y), np.dot(q - c, x)) for q in pts]
        ordered.append(tuple(int(i) for i in np.array(f)[np.argsort(ang)]))
    v = v * scale / 2
    v[:, 2] -= v[:, 2].min()
    return v.tolist(), ordered


def polyhedron(name, color, v, faces):
    return [prim(flat(v, faces), color, name, 0.55), prim(wire(v, edges_of(faces)), shade(color), name + "_qirralar", 0.4)]


# ───────────────────────────────────────────── aylanish jismlari
def revolution(name, color, profile, caps, rings_at, extra=(), smooth_sphere=None):
    body = merge([lathe(profile, smooth_sphere=smooth_sphere)] + [disc(r, z, up) for r, z, up in caps])
    lines = [e for r, z in rings_at for e in ring(r, z)] + list(extra)
    out = [Primitive(*body, color, 0.5, name)]
    if lines:
        out.append(prim(lines, EDGE, name + "_chiziqlar", 0.4))
    return out


def radius_line(r, z):
    return [tube([0, 0, z + 0.006], [r, 0, z + 0.006], TUBE * 0.9), ball([0, 0, z + 0.006], TUBE * 1.6)]


def arc(r, z0, z1, n=28):
    """Shar yoyi profili: z0 dan z1 gacha (markaz 0)."""
    return [(float(np.sqrt(max(r * r - z * z, 0))), float(z)) for z in np.linspace(z0, z1, n)]


def shifted(profile, dz):
    return [(r, z + dz) for r, z in profile]


# ───────────────────────────────────────────── tekis shakllar (vertikal plastinka, x–z tekisligi)
PLATE = 0.06
FRONT = -PLATE / 2 - 0.02          # plastinka oldi (kamera tomoni) — chiziqlar shu yerda


def plate(points2d, t=PLATE):
    """Qavariq ko'pburchak plastinka (u, v) → (u, 0, v); qalinligi y bo'yicha. Qirra — o'rtadagi naycha."""
    p2 = np.asarray(points2d, float)
    n = len(p2)
    v = [[u, -t / 2, w] for u, w in p2] + [[u, t / 2, w] for u, w in p2]
    faces = [tuple(range(n)), tuple(range(n, 2 * n))] + [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    mid = [[u, 0, w] for u, w in p2]
    return flat(v, faces), [tube(mid[k], mid[(k + 1) % n], TUBE * 0.8, 10) for k in range(n)]


def circle2d(r, n=64, c=(0, 0)):
    return [(c[0] + r * np.cos(a), c[1] + r * np.sin(a)) for a in np.linspace(0, 2 * np.pi, n, endpoint=False)]


def sector2d(r, deg, n=48):
    return [(0.0, 0.0)] + [(r * np.cos(a), r * np.sin(a))
                           for a in np.linspace(np.radians(90 - deg / 2), np.radians(90 + deg / 2), n)]


def flat_model(name, pieces, extra_lines=()):
    """pieces — [(points2d, color)]: bir nechta plastinkadan tekis shakl yoki yoyilma (har bo'lak — alohida yoq)."""
    out, lines, by_color = [], list(extra_lines), {}
    for pts, color in pieces:
        body, ln = plate(pts)
        by_color.setdefault(color, []).append(body)
        lines += ln
    for k, (color, parts) in enumerate(by_color.items()):
        out.append(prim(parts, color, f"{name}_{k}", 0.55))
    out.append(prim(lines, EDGE, name + "_qirralar", 0.4))
    return out


def sq(a, cx=0.0, cz=0.0):
    return [(cx - a / 2, cz - a / 2), (cx + a / 2, cz - a / 2), (cx + a / 2, cz + a / 2), (cx - a / 2, cz + a / 2)]


def rect(w, h, cx=0.0, cz=0.0):
    return [(cx - w / 2, cz - h / 2), (cx + w / 2, cz - h / 2), (cx + w / 2, cz + h / 2), (cx - w / 2, cz + h / 2)]


def xz(u, w, y=FRONT):
    return [u, y, w]


def mark_right(p, d1, d2, s=0.3):
    """To'g'ri burchak belgisi (plastinka oldida)."""
    p, d1, d2 = (np.asarray(x, float) for x in (p, d1, d2))
    a, b, c = p + d1 * s, p + d1 * s + d2 * s, p + d2 * s
    return [tube(a, b, TUBE * 0.9, 8), tube(b, c, TUBE * 0.9, 8)]


# ───────────────────────────────────────────── modellar
def m_unit_cubes():
    s, g = 0.5, 0.04
    parts_a, parts_b, lines = [], [], []
    for i in range(4):
        for j in range(3):
            for k in range(2):
                x0, y0, z0 = (i - 2) * (s + g), (j - 1.5) * (s + g), k * (s + g)
                v = [[x0 + dx, y0 + dy, z0 + dz] for dz in (0, s) for dy in (0, s) for dx in (0, s)]
                faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
                (parts_a if (i + j + k) % 2 == 0 else parts_b).append(flat(v, faces))
                lines += wire(v, edges_of(faces), TUBE * 0.45, balls=False)
    return [prim(parts_a, C["ko'k"], "kubcha_a", 0.55), prim(parts_b, C["moviy"], "kubcha_b", 0.55),
            prim(lines, EDGE, "kubcha_qirralar", 0.4)]


def m_sphere():
    r = 1.2
    lines = ring(r * 1.004, 0, 96, centre=(0, 0, r)) + ring(r * 1.004, 0, 96, centre=(0, 0, r), plane="xz")
    return [Primitive(*sphere(r, centre=(0, 0, r)), C["sariq"], 0.45, "shar"), prim(lines, EDGE, "shar_aylanalar", 0.4)]


def m_hemisphere():
    r = 1.2
    return revolution("yarim_shar", C["sariq"], arc(r, 0, r), [(r, 0, False)], [(r, 0)], smooth_sphere=0.0)


def m_segment():
    r, z0 = 1.4, 0.55
    prof = shifted(arc(r, z0, r), -z0)
    rb = prof[0][0]
    out = revolution("shar_segmenti", C["sariq"], prof, [(rb, 0, False)], [(rb, 0)], smooth_sphere=-z0)
    out.append(prim([tube([0, 0, 0], [0, 0, r - z0], TUBE * 0.9), ball([0, 0, 0], TUBE * 1.6)], HEIGHT, "segment_balandligi"))
    return out


def m_layer():
    r, z0, z1 = 1.3, -0.55, 0.75
    prof = shifted(arc(r, z0, z1), -z0)
    rb, rt, h = prof[0][0], prof[-1][0], z1 - z0
    out = revolution("shar_qatlami", C["sariq"], prof, [(rb, 0, False), (rt, h, True)], [(rb, 0), (rt, h)],
                     extra=radius_line(rt, h), smooth_sphere=-z0)
    out.append(prim([tube([0.25, 0, 0], [0.25, 0, h], TUBE * 0.8)], HEIGHT, "qatlam_balandligi"))
    return out


def m_sector():
    r, z0 = 1.5, 0.95
    cap = arc(r, z0, r)
    rb = cap[0][0]
    lines = ring(rb, z0) + [tube([0, 0, 0], [rb, 0, z0], TUBE * 0.9), tube([0, 0, 0], [-rb, 0, z0], TUBE * 0.9)]
    return [Primitive(*lathe([(0.0, 0.0), (rb, z0)]), C["sariq_q"], 0.5, "sektor_konus"),
            Primitive(*lathe(cap, smooth_sphere=0.0), C["sariq"], 0.5, "sektor_qopqoq"),
            prim(lines, EDGE, "sektor_chiziqlar", 0.4), prim([ball([0, 0, 0], TUBE * 1.8)], POINT, "sektor_markaz")]


def m_cut_sphere():
    """Shar — kameraga qaragan yuqori choragi (oktant: x > 0, y < 0, z > 0) kesib olingan: markaz va uchta radius
    ko'rinadi. (glTF da kamera −y tomonda: y_up dan keyin y → −Z.)"""
    r, q = 1.2, np.pi / 2
    body = sphere(r, 64, 32, centre=(0, 0, r), skip=lambda t, p: t < q and p > 3 * q)
    cut = []
    ang = np.linspace(0, q, 24)
    o = np.array([0, 0, r])
    for pts, nrm in (([o + [r * np.cos(a), -r * np.sin(a), 0] for a in ang], [0, 0, 1]),
                     ([o + [r * np.cos(a), 0, r * np.sin(a)] for a in ang], [0, -1, 0]),
                     ([o + [0, -r * np.cos(a), r * np.sin(a)] for a in ang], [1, 0, 0])):
        pts = np.vstack([o, pts])
        tris = []
        for k in range(1, len(pts) - 1):
            tri = [0, k, k + 1]
            if np.dot(np.cross(pts[k] - pts[0], pts[k + 1] - pts[0]), nrm) < 0:
                tri = [0, k + 1, k]
            tris += tri
        cut.append((pts, np.tile(nrm, (len(pts), 1)).astype(float), np.array(tris)))
    radii = [tube(o, o + [r, 0, 0]), tube(o, o + [0, -r, 0]), tube(o, o + [0, 0, r])]
    return [Primitive(*body, C["sariq"], 0.45, "shar"), prim(cut, C["ichki"], "shar_kesimi", 0.6),
            prim(radii, RADIUS, "shar_radiuslari", 0.4), prim([ball(o, TUBE * 2)], POINT, "shar_markazi")]


def m_cube_diagonal():
    v, faces = box(2, 2, 2)
    return [prim(wire(v, edges_of(faces)), EDGE, "kub_karkasi", 0.4),
            prim([plate_poly([v[0], v[3], v[7], v[4]])], C["kesim"], "diagonal_kesim", 0.6),
            prim([tube(v[0], v[7], TUBE * 1.1)], HEIGHT, "kub_diagonali", 0.4),
            prim([tube(v[0], v[3], TUBE * 1.05)], SLANT, "yoq_diagonali", 0.4)]


def m_box_diagonal():
    v, faces = box(3, 2, 1.5)
    return [prim(wire(v, edges_of(faces)), EDGE, "karkas", 0.4),
            prim([plate_poly([v[0], v[3], v[7], v[4]])], C["kesim"], "diagonal_kesim", 0.6),
            prim([tube(v[0], v[7], TUBE * 1.1)], HEIGHT, "fazoviy_diagonal", 0.4),
            prim([tube(v[0], v[3], TUBE * 1.05)], SLANT, "asos_diagonali", 0.4)]


def m_pyramid_elements():
    a, h = 2.4, 2.2
    v, faces = pyramid_n(4, a / np.sqrt(2), h, start=45)
    apex, o = np.array(v[4]), np.zeros(3)
    mid = (np.array(v[0]) + np.array(v[1])) / 2              # asos qirrasi o'rtasi
    return [prim(wire(v, edges_of(faces)), EDGE, "piramida_karkasi", 0.4),
            prim([plate_poly([o, mid, apex])], C["kesim2"], "uchburchak_h_apofema", 0.6),
            prim([tube(o, apex, TUBE * 1.1), ball(o, TUBE * 1.7)], HEIGHT, "balandlik", 0.4),
            prim([tube(mid, apex, TUBE * 1.05), ball(mid, TUBE * 1.5)], SLANT, "apofema", 0.4),
            prim(dashed(o, mid), EDGE, "asos_kesmasi", 0.4)]


def m_cone_section():
    r, h = 1.1, 2.4
    apex = [0, 0, h]
    lines = ring(r, 0) + [tube([0, r, 0], apex), tube([0, -r, 0], apex), tube([-r, 0, 0], apex)]
    return [prim(lines + [ball(apex, TUBE * 1.4)], EDGE, "konus_karkasi", 0.4),
            prim([plate_poly([[-r, 0, 0], [r, 0, 0], apex])], C["kesim"], "o'q_kesimi", 0.6),
            prim([tube([0, 0, 0], apex, TUBE * 1.1)], HEIGHT, "balandlik", 0.4),
            prim([tube([0, 0, 0.01], [0, -r, 0.01], TUBE), ball([0, 0, 0], TUBE * 1.6)], RADIUS, "radius", 0.4),
            prim([tube([r, 0, 0], apex, TUBE * 1.12)], SLANT, "yasovchi", 0.4)]


def m_cylinder_section():
    r, h = 1.0, 2.4
    lines = ring(r, 0) + ring(r, h) + [tube([0, r, 0], [0, r, h]), tube([0, -r, 0], [0, -r, h])]
    return [prim(lines, EDGE, "silindr_karkasi", 0.4),
            prim([plate_poly([[-r, 0, 0], [r, 0, 0], [r, 0, h], [-r, 0, h]])], C["kesim"], "o'q_kesimi", 0.6),
            prim([tube([0, 0, 0], [0, 0, h], TUBE * 1.1)], HEIGHT, "balandlik", 0.4),
            prim([tube([0, 0, h + 0.01], [0, -r, h + 0.01], TUBE), ball([0, 0, h], TUBE * 1.6)], RADIUS, "radius", 0.4),
            prim([tube([r, 0, 0], [r, 0, h], TUBE * 1.12), tube([-r, 0, 0], [-r, 0, h], TUBE * 1.12)], SLANT, "yasovchilar", 0.4)]


def wire_sphere(r, centre, n_merid=6, parallels=(-0.5, 0, 0.5)):
    cx, cy, cz = centre
    lines = []
    for k in range(n_merid):
        a = np.pi * k / n_merid
        pts = [[cx + r * np.cos(t) * np.cos(a), cy + r * np.cos(t) * np.sin(a), cz + r * np.sin(t)]
               for t in np.linspace(0, 2 * np.pi, 73)]
        lines += [tube(pts[i], pts[i + 1], TUBE * 0.6, 8) for i in range(72)]
    for f in parallels:
        rr = r * np.sqrt(1 - f * f)
        pts = [[cx + rr * np.cos(t), cy + rr * np.sin(t), cz + r * f] for t in np.linspace(0, 2 * np.pi, 73)]
        lines += [tube(pts[i], pts[i + 1], TUBE * 0.6, 8) for i in range(72)]
    return lines


def m_cube_in_sphere():
    r = 1.3
    a = 2 * r / np.sqrt(3)                                   # kub diagonali = shar diametri
    v, faces = box(a, a, a)
    v = [[x, y, z + r - a / 2] for x, y, z in v]
    return [prim(wire_sphere(r, (0, 0, r)), EDGE, "shar_karkasi", 0.4)] + polyhedron("ichki_kub", C["ko'k"], v, faces)


def m_cone_in_cylinder():
    r, h = 1.0, 2.4
    gens = [tube([r * np.cos(a), r * np.sin(a), 0], [r * np.cos(a), r * np.sin(a), h], TUBE * 0.8)
            for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)]
    cone = revolution("ichki_konus", C["binafsha"], [(r * 0.985, 0.005), (0, h)], [(r * 0.985, 0.005, False)], [])
    return [prim(ring(r, 0) + ring(r, h) + gens, EDGE, "silindr_karkasi", 0.4)] + cone


def m_archimedes():
    """Bir xil radius va balandlik (h = 2r): konus, shar, silindr — hajmlar nisbati 1 : 2 : 3."""
    r, out = 0.8, []
    shapes = [("konus", C["binafsha"], [lathe([(r, 0), (0, 2 * r)]), disc(r, 0, False)], ring(r, 0)),
              ("shar", C["sariq"], [sphere(r, 48, 24, centre=(0, 0, r))], ring(r * 1.004, r)),
              ("silindr", C["yashil"], [lathe([(r, 0), (r, 2 * r)]), disc(r, 2 * r, True), disc(r, 0, False)],
               ring(r, 0) + ring(r, 2 * r))]
    for k, (nm, col, parts, lines) in enumerate(shapes):
        d = np.array([(k - 1) * 2.2, 0, 0])
        out.append(prim([(p + d, n, i) for p, n, i in parts], col, "arximed_" + nm, 0.5))
        out.append(prim([(p + d, n, i) for p, n, i in lines], EDGE, "arximed_" + nm + "_chiziq", 0.4))
    return out


def arrow(a, b, color, name):
    a, b = np.asarray(a, float), np.asarray(b, float)
    z = (b - a) / np.linalg.norm(b - a)
    tip = b - z * 0.28
    x = np.cross(z, [0, 0, 1] if abs(z[2]) < 0.9 else [1, 0, 0])
    x /= np.linalg.norm(x)
    rot = np.stack([x, np.cross(z, x), z], 1)
    cp, cn, ci = lathe([(0.1, 0), (0, 0.28)], seg=24)
    return prim([tube(a, tip, TUBE * 1.1), (cp @ rot.T + tip, cn @ rot.T, ci)], color, name, 0.4)


def m_coordinates():
    L, P = 2.4, np.array([1.4, 1.1, 1.6])
    x, y, z = [P[0], 0, 0], [0, P[1], 0], [0, 0, P[2]]
    pxy, pxz, pyz = [P[0], P[1], 0], [P[0], 0, P[2]], [0, P[1], P[2]]
    dash = []
    for a, b in [(P, pxy), (pxy, x), (pxy, y), (P, pxz), (P, pyz), (pxz, x), (pxz, z), (pyz, y), (pyz, z)]:
        dash += dashed(a, b, TUBE * 0.55)
    return [arrow([-0.4, 0, 0], [L, 0, 0], (0.90, 0.22, 0.20, 1), "o'q_x"),
            arrow([0, -0.4, 0], [0, L, 0], (0.20, 0.65, 0.30, 1), "o'q_y"),
            arrow([0, 0, -0.4], [0, 0, L], (0.15, 0.40, 0.90, 1), "o'q_z"),
            prim([ball([0, 0, 0], TUBE * 2)], EDGE, "koordinata_boshi", 0.4),
            prim(dash, EDGE, "proyeksiyalar", 0.4),
            prim([ball(P, TUBE * 2.6)], SLANT, "nuqta_P", 0.4)]


# ───────── yoyilmalar (vertikal plastinkalar)
def m_net_cube():
    a = 0.9
    cells = [(0, 1), (-1, 1), (1, 1), (2, 1), (0, 0), (0, 2)]
    return flat_model("kub_yoyilmasi", [(sq(a, x * a, z * a), C["ko'k"] if k % 2 else C["moviy"])
                                        for k, (x, z) in enumerate(cells)])


def m_net_box():
    a, b, c = 1.2, 0.8, 0.6                                # uzunlik, en, balandlik
    return flat_model("parallelepiped_yoyilmasi", [
        (rect(a, b, 0, 0), C["sariq_q"]), (rect(a, c, 0, b / 2 + c / 2), C["kesim2"]),
        (rect(a, c, 0, -b / 2 - c / 2), C["kesim2"]), (rect(a, b, 0, b + c), C["sariq_q"]),
        (rect(c, b, -a / 2 - c / 2, 0), C["kesim2"]), (rect(c, b, a / 2 + c / 2, 0), C["kesim2"])])


def m_net_prism():
    a, h = 0.9, 1.4
    th = a * np.sqrt(3) / 2
    pieces = [(rect(a, h, (k - 1) * a, 0), C["kesim2"] if k == 1 else C["pushti"]) for k in range(3)]
    pieces += [([(-a / 2, h / 2), (a / 2, h / 2), (0, h / 2 + th)], C["ichki"]),
               ([(-a / 2, -h / 2), (0, -h / 2 - th), (a / 2, -h / 2)], C["ichki"])]
    return flat_model("prizma_yoyilmasi", pieces)


def m_net_pyramid():
    a, l = 1.0, 1.1                                         # asos tomoni, yon yoq balandligi (apofema)
    return flat_model("piramida_yoyilmasi", [
        (sq(a), C["kesim2"]),
        ([(-a / 2, a / 2), (a / 2, a / 2), (0, a / 2 + l)], C["feruza"]),
        ([(-a / 2, -a / 2), (0, -a / 2 - l), (a / 2, -a / 2)], C["feruza"]),
        ([(a / 2, -a / 2), (a / 2 + l, 0), (a / 2, a / 2)], C["feruza"]),
        ([(-a / 2, -a / 2), (-a / 2, a / 2), (-a / 2 - l, 0)], C["feruza"])])


def m_net_cylinder():
    r, h = 0.42, 1.2
    return flat_model("silindr_yoyilmasi", [(rect(2 * np.pi * r, h), C["yashil"]),
                                             (circle2d(r, 48, (0, h / 2 + r)), C["kesim2"]),
                                             (circle2d(r, 48, (0, -h / 2 - r)), C["kesim2"])])


def m_net_cone():
    r, l = 0.5, 1.4                                         # asos radiusi, yasovchi: sektor burchagi 360·r/l
    sector = [(x, z - l / 2) for x, z in sector2d(l, 360 * r / l)]
    return flat_model("konus_yoyilmasi", [(sector, C["binafsha"]), (circle2d(r, 48, (0, -l / 2 - r)), C["kesim2"])])


# ───────── tekis shakllar
def m_right_triangle():
    return flat_model("togri_burchakli_uchburchak", [([(-1.0, -0.7), (1.0, -0.7), (-1.0, 0.8)], C["qizil"])],
                      mark_right(xz(-1.0, -0.7), [1, 0, 0], [0, 0, 1]))


def m_rhombus():
    return flat_model("romb", [([(0, -1.1), (0.75, 0), (0, 1.1), (-0.75, 0)], C["feruza"])],
                      dashed(xz(0, -1.1), xz(0, 1.1), TUBE * 0.55) + dashed(xz(-0.75, 0), xz(0.75, 0), TUBE * 0.55))


def m_trapezoid():
    return flat_model("trapetsiya", [([(-1.2, -0.6), (1.2, -0.6), (0.6, 0.6), (-0.6, 0.6)], C["sariq_q"])],
                      dashed(xz(-0.6, 0.6), xz(-0.6, -0.6), TUBE * 0.55))


def m_parallelogram():
    return flat_model("parallelogramm", [([(-1.2, -0.6), (0.6, -0.6), (1.2, 0.6), (-0.6, 0.6)], C["pushti"])],
                      dashed(xz(-0.6, 0.6), xz(-0.6, -0.6), TUBE * 0.55))


def m_circle():
    return flat_model("doira", [(circle2d(1.0, 72), C["sariq"])],
                      [tube(xz(0, 0), xz(1.0, 0), TUBE * 0.8), ball(xz(0, 0), TUBE * 1.6)])


def entries():
    """(id, nom_uz, nom, kategoriya, kalit, yasovchi, preview burchagi)"""
    J, K, Y, T = "Geometrik jismlar", "Geometriya: kesimlar va elementlar", "Geometriya: yoyilmalar", "Geometriya: tekis shakllar"
    pre, flatv = (22, 35, 0), (8, 0, 0)
    poly = polyhedron
    return [
        ("geo_kub", "Kub", "Cube", J, ["kub", "cube", "куб", "hajm", "ko'pyoq", "qirra", "yoq"],
         lambda: poly("kub", C["ko'k"], *box(2, 2, 2)), pre),
        ("geo_parallelepiped", "To'g'ri burchakli parallelepiped", "Rectangular cuboid", J,
         ["parallelepiped", "cuboid", "параллелепипед", "hajm", "ko'pyoq", "prizma"],
         lambda: poly("parallelepiped", C["sariq_q"], *box(3, 2, 1.5)), pre),
        ("geo_ogma_parallelepiped", "Og'ma parallelepiped", "Oblique parallelepiped", J,
         ["og'ma", "parallelepiped", "oblique", "наклонный параллелепипед", "prizma", "hajm"],
         lambda: poly("ogma_parallelepiped", C["sariq_q"], *box(2.2, 1.6, 1.8, shift=(0.8, 0))), pre),
        ("geo_prizma", "Uchburchakli prizma", "Triangular prism", J, ["prizma", "prism", "призма", "uchburchakli", "hajm"],
         lambda: poly("prizma", C["pushti"], *prism(3, 2.2 / np.sqrt(3), 2.4)), pre),
        ("geo_prizma6", "Muntazam oltiburchakli prizma", "Hexagonal prism", J,
         ["prizma", "oltiburchakli", "hexagonal prism", "шестиугольная призма", "muntazam", "hajm"],
         lambda: poly("prizma6", C["pushti"], *prism(6, 1.1, 2.2, start=0)), pre),
        ("geo_piramida", "To'rtburchakli piramida", "Square pyramid", J, ["piramida", "pyramid", "пирамида", "hajm"],
         lambda: poly("piramida", C["feruza"], *pyramid_n(4, 2.2 / np.sqrt(2), 2.2)), pre),
        ("geo_tetraedr", "Uchburchakli piramida (tetraedr)", "Tetrahedron", J,
         ["tetraedr", "uchburchakli piramida", "tetrahedron", "тетраэдр", "muntazam ko'pyoq", "platon"],
         lambda: poly("tetraedr", C["feruza"], *tetrahedron(2.4)), pre),
        ("geo_piramida6", "Muntazam oltiburchakli piramida", "Hexagonal pyramid", J,
         ["piramida", "oltiburchakli", "hexagonal pyramid", "шестиугольная пирамида", "muntazam"],
         lambda: poly("piramida6", C["feruza"], *pyramid_n(6, 1.2, 2.2, start=0)), pre),
        ("geo_kesik_piramida", "Kesik piramida", "Frustum of a pyramid", J,
         ["kesik piramida", "frustum", "усечённая пирамида", "hajm", "piramida"],
         lambda: poly("kesik_piramida", C["feruza"], *pyramid_n(4, 2.4 / np.sqrt(2), 1.8, top_r=1.2 / np.sqrt(2))), pre),
        ("geo_oktaedr", "Oktaedr", "Octahedron", J, ["oktaedr", "octahedron", "октаэдр", "muntazam ko'pyoq", "platon"],
         lambda: poly("oktaedr", C["binafsha"], *octahedron(2.0)), pre),
        ("geo_dodekaedr", "Dodekaedr", "Dodecahedron", J, ["dodekaedr", "dodecahedron", "додекаэдр", "muntazam ko'pyoq", "platon"],
         lambda: poly("dodekaedr", C["qizil"], *dodecahedron(1.4)), pre),
        ("geo_ikosaedr", "Ikosaedr", "Icosahedron", J, ["ikosaedr", "icosahedron", "икосаэдр", "muntazam ko'pyoq", "platon"],
         lambda: poly("ikosaedr", C["moviy"], *icosahedron(1.4)), pre),
        ("geo_kubchalar", "Birlik kubchalardan parallelepiped", "Unit cubes (4×3×2)", J,
         ["kubcha", "birlik kub", "unit cube", "единичный куб", "hajm", "sm³"], m_unit_cubes, pre),
        ("geo_silindr", "Silindr", "Cylinder", J, ["silindr", "cylinder", "цилиндр", "hajm", "aylanish jismi"],
         lambda: revolution("silindr", C["yashil"], [(1, 0), (1, 2.4)], [(1, 2.4, True), (1, 0, False)],
                            [(1, 0), (1, 2.4)], extra=radius_line(1, 2.4)), pre),
        ("geo_konus", "Konus", "Cone", J, ["konus", "cone", "конус", "hajm", "aylanish jismi"],
         lambda: revolution("konus", C["binafsha"], [(1.1, 0), (0, 2.4)], [(1.1, 0, False)], [(1.1, 0)]), pre),
        ("geo_kesik_konus", "Kesik konus", "Frustum of a cone", J, ["kesik konus", "frustum", "усечённый конус", "hajm"],
         lambda: revolution("kesik_konus", C["binafsha"], [(1.2, 0), (0.6, 2.0)], [(0.6, 2.0, True), (1.2, 0, False)],
                            [(1.2, 0), (0.6, 2.0)], extra=radius_line(0.6, 2.0)), pre),
        ("geo_shar", "Shar", "Sphere", J, ["shar", "sphere", "шар", "hajm", "aylanish jismi"], m_sphere, pre),
        ("geo_yarim_shar", "Yarim shar", "Hemisphere", J, ["yarim shar", "hemisphere", "полушар", "shar"], m_hemisphere, pre),
        ("geo_shar_segmenti", "Shar segmenti", "Spherical cap", J, ["shar segmenti", "spherical cap", "шаровой сегмент", "shar"],
         m_segment, pre),
        ("geo_shar_qatlami", "Shar qatlami", "Spherical zone", J, ["shar qatlami", "spherical zone", "шаровой слой", "shar"],
         m_layer, pre),
        ("geo_shar_sektori", "Shar sektori", "Spherical sector", J, ["shar sektori", "spherical sector", "шаровой сектор", "shar"],
         m_sector, pre),
        ("geo_kub_diagonal", "Kub: diagonali va diagonal kesimi", "Cube diagonal and diagonal section", K,
         ["kub diagonali", "diagonal kesim", "диагональ куба", "диагональное сечение", "kesim", "stereometriya"],
         m_cube_diagonal, pre),
        ("geo_parallelepiped_diagonal", "Parallelepiped diagonali", "Cuboid space diagonal", K,
         ["parallelepiped diagonali", "diagonal", "диагональ параллелепипеда", "kesim", "stereometriya"], m_box_diagonal, pre),
        ("geo_piramida_elementlar", "Piramida: balandlik va apofema", "Pyramid height and apothem", K,
         ["balandlik", "apofema", "piramida", "высота пирамиды", "апофема", "stereometriya"], m_pyramid_elements, pre),
        ("geo_konus_kesim", "Konus: o'q kesimi, yasovchi, radius", "Cone axial section", K,
         ["o'q kesimi", "yasovchi", "konus", "осевое сечение конуса", "образующая", "radius"], m_cone_section, pre),
        ("geo_silindr_kesim", "Silindr: o'q kesimi", "Cylinder axial section", K,
         ["o'q kesimi", "silindr", "осевое сечение цилиндра", "yasovchi", "radius"], m_cylinder_section, pre),
        ("geo_shar_ichi", "Shar: markazi va radiuslari (kesib ochilgan)", "Sphere cut-away", K,
         ["shar markazi", "radius", "shar", "центр шара", "радиус", "kesim"], m_cut_sphere, (24, 30, 0)),
        ("geo_sharga_ichki_kub", "Sharga ichki chizilgan kub", "Cube inscribed in a sphere", K,
         ["ichki chizilgan", "shar", "kub", "вписанный куб", "kombinatsiya"], m_cube_in_sphere, pre),
        ("geo_silindrga_ichki_konus", "Silindrga ichki chizilgan konus", "Cone inscribed in a cylinder", K,
         ["ichki chizilgan", "silindr", "konus", "вписанный конус", "kombinatsiya", "hajm nisbati"], m_cone_in_cylinder, pre),
        ("geo_arximed", "Arximed jismlari: konus, shar, silindr", "Archimedes: cone, sphere, cylinder", K,
         ["arximed", "konus shar silindr", "archimedes", "архимед", "hajm nisbati"], m_archimedes, (16, 10, 0)),
        ("geo_koordinatalar", "Fazoviy koordinatalar sistemasi", "3D coordinate system", K,
         ["koordinata", "koordinatalar sistemasi", "x y z", "система координат", "vektor", "nuqta"], m_coordinates, (20, 40, 0)),
        ("geo_kub_yoyilma", "Kub yoyilmasi", "Net of a cube", Y, ["yoyilma", "kub yoyilmasi", "развёртка куба", "sirt yuzi"],
         m_net_cube, flatv),
        ("geo_parallelepiped_yoyilma", "Parallelepiped yoyilmasi", "Net of a cuboid", Y,
         ["yoyilma", "parallelepiped yoyilmasi", "развёртка параллелепипеда", "sirt yuzi"], m_net_box, flatv),
        ("geo_prizma_yoyilma", "Uchburchakli prizma yoyilmasi", "Net of a triangular prism", Y,
         ["yoyilma", "prizma yoyilmasi", "развёртка призмы", "sirt yuzi"], m_net_prism, flatv),
        ("geo_piramida_yoyilma", "Piramida yoyilmasi", "Net of a square pyramid", Y,
         ["yoyilma", "piramida yoyilmasi", "развёртка пирамиды", "sirt yuzi"], m_net_pyramid, flatv),
        ("geo_silindr_yoyilma", "Silindr yoyilmasi", "Net of a cylinder", Y,
         ["yoyilma", "silindr yoyilmasi", "развёртка цилиндра", "yon sirt", "sirt yuzi"], m_net_cylinder, flatv),
        ("geo_konus_yoyilma", "Konus yoyilmasi", "Net of a cone", Y,
         ["yoyilma", "konus yoyilmasi", "развёртка конуса", "yon sirt", "sektor"], m_net_cone, flatv),
        ("geo_uchburchak", "Teng tomonli uchburchak", "Equilateral triangle", T,
         ["uchburchak", "teng tomonli", "triangle", "треугольник", "yuza"],
         lambda: flat_model("uchburchak", [([(-1.1, -0.65), (1.1, -0.65), (0, 1.255)], C["qizil"])]), flatv),
        ("geo_togri_uchburchak", "To'g'ri burchakli uchburchak", "Right triangle", T,
         ["to'g'ri burchakli uchburchak", "pifagor", "right triangle", "прямоугольный треугольник", "katet", "gipotenuza"],
         m_right_triangle, flatv),
        ("geo_kvadrat", "Kvadrat", "Square", T, ["kvadrat", "square", "квадрат", "yuza", "perimetr"],
         lambda: flat_model("kvadrat", [(sq(1.8), C["ko'k"])]), flatv),
        ("geo_togri_tortburchak", "To'g'ri to'rtburchak", "Rectangle", T,
         ["to'g'ri to'rtburchak", "rectangle", "прямоугольник", "yuza", "perimetr"],
         lambda: flat_model("togri_tortburchak", [(rect(2.4, 1.4), C["sariq_q"])]), flatv),
        ("geo_parallelogramm", "Parallelogramm", "Parallelogram", T, ["parallelogramm", "parallelogram", "параллелограмм", "yuza"],
         m_parallelogram, flatv),
        ("geo_romb", "Romb", "Rhombus", T, ["romb", "rhombus", "ромб", "diagonal", "yuza"], m_rhombus, flatv),
        ("geo_trapetsiya", "Trapetsiya", "Trapezoid", T, ["trapetsiya", "trapezoid", "трапеция", "yuza"], m_trapezoid, flatv),
        ("geo_doira", "Doira va aylana", "Circle", T, ["doira", "aylana", "circle", "круг", "окружность", "radius"], m_circle, flatv),
        ("geo_oltiburchak", "Muntazam oltiburchak", "Regular hexagon", T,
         ["oltiburchak", "muntazam ko'pburchak", "hexagon", "шестиугольник"],
         lambda: flat_model("oltiburchak", [([(np.cos(a), np.sin(a)) for a in np.linspace(0, 2 * np.pi, 6, endpoint=False)],
                                             C["feruza"])]), flatv),
    ]


# Jismlar Z yuqoriga qarab yasaladi; glTF da esa «yuqori» — Y o'qi: (x, y, z) → (x, z, −y) (to'g'ri burilish).
_Z_TO_Y = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)


def y_up(prims: List[Primitive]) -> List[Primitive]:
    return [Primitive(p.positions @ _Z_TO_Y.T, p.normals @ _Z_TO_Y.T, p.indices, p.color, p.roughness, p.name)
            for p in prims]


def build_all(only: Sequence[str] = ()) -> list:
    from PIL import Image

    from services.med3d import preview

    out = []
    os.makedirs(katalog3d.PREVIEW_DIR, exist_ok=True)
    os.makedirs(katalog3d.MASK_DIR, exist_ok=True)
    for mid, nom_uz, nom, kat, kalit, make, rot in entries():
        prims = y_up(make())
        allpos = np.vstack([p.positions for p in prims])
        lo, hi = allpos.min(0), allpos.max(0)
        data = write_glb(prims, name=nom)
        rel = f"geometriya/{mid}/model.glb"
        path = os.path.join(katalog3d.MODELS_DIR, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        if not only or mid in only:
            img = preview.render(data, rot, 600).convert("RGBA")
            bg = Image.new("RGBA", img.size, (242, 242, 240, 255))
            Image.alpha_composite(bg, img).convert("RGB").save(os.path.join(katalog3d.PREVIEW_DIR, mid + ".jpg"), quality=90)
            img.getchannel("A").save(os.path.join(katalog3d.MASK_DIR, mid + ".png"))
        tris = int(sum(len(p.indices) for p in prims) // 3)
        out.append({"id": mid, "nom_uz": nom_uz, "nom": nom, "fan": "matematika", "kalit": kalit,
                    "manba": "edufayl", "litsenziya": "CC0", "muallif": "Edufayl", "muallif_url": "",
                    "sahifa": "", "attribution": "3D: Edufayl · CC0",
                    "attribution_full": f"\"{nom}\" — Edufayl (dasturda yasalgan geometrik model), CC0",
                    "fayl": rel, "uchburchak": tris, "hajm": len(data),
                    "bbox": [lo.round(4).tolist(), hi.round(4).tolist()], "animatsiya": 0, "pishirilgan": True,
                    "sifat": 4, "kategoriya": kat, "tur": "real"})
        print(f"{mid:30} {len(data) / 1024:7.0f} KB  {tris:6} uchburchak  {kat}")
    with open(os.path.join(katalog3d.KATALOG_DIR, "geometriya.json"), "w", encoding="utf-8") as fh:
        json.dump({"modellar": out}, fh, ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    build_all(sys.argv[1:])
