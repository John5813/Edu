"""O'zimiz yasaydigan 3D modellar uchun umumiy kutubxona: to'r (mesh) yordamchilari, uslub va katalogga yozish.

HAR QANDAY FONDA KO'RINISH (3D taqdimot uslublari oq ham, to'q ko'k/qora ham):
- yaxlit jismning qirralari — jism rangining to'q tusi (`shade`): yuzasi o'rtacha yorqin bo'lgani uchun jism oq fonda
  ham, to'q fonda ham ajralib turadi, qirra esa yuzada aniq ko'rinadi;
- yolg'iz chiziqlar (karkas, o'qlar, orbitalar, maydon chiziqlari, strelkalar) — o'rta yorqinlikdagi to'yingan rang
  (nisbiy yorqinlik ~0.18-0.25): oq fonga ham, to'q fonga ham kontrast ~4:1;
- sof oq va sof qora rang ishlatilmaydi (oq yoki qora fonda yo'qolib qoladi).
Har model katalog preview'i bilan birga oq va to'q fonda tekshiriladi (`tekshir.py`).
"""
import json
import os
import sys
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
os.environ.setdefault("BOT_TOKEN", "1:x")

from services import katalog3d  # noqa: E402
from services.med3d.glb import Primitive, write_glb  # noqa: E402

Color = Tuple[float, float, float, float]

# ───────────────────────────────────────────── uslub
# Yolg'iz chiziqlar uchun (har qanday fonda ko'rinadi): o'rta yorqinlik, to'yingan.
WIRE: Color = (0.30, 0.45, 0.80, 1.0)        # karkas, yordamchi chiziqlar
HEIGHT: Color = (0.92, 0.26, 0.24, 1.0)      # balandlik — qizil
SLANT: Color = (0.96, 0.58, 0.12, 1.0)       # apofema, yasovchi, diagonal — to'q sariq
RADIUS: Color = (0.20, 0.52, 0.95, 1.0)      # radius — ko'k
POINT: Color = (0.92, 0.26, 0.24, 1.0)
GREEN: Color = (0.20, 0.70, 0.35, 1.0)
TUBE = 0.035                                  # qirra naychasi radiusi (model ~2 birlik)
C = {"ko'k": (0.20, 0.47, 0.93, 1), "sariq_q": (0.96, 0.55, 0.16, 1), "pushti": (0.89, 0.33, 0.55, 1),
     "feruza": (0.12, 0.68, 0.62, 1), "yashil": (0.27, 0.70, 0.36, 1), "binafsha": (0.55, 0.36, 0.86, 1),
     "sariq": (0.98, 0.78, 0.18, 1), "qizil": (0.92, 0.33, 0.27, 1), "moviy": (0.25, 0.70, 0.90, 1),
     "kesim": (0.55, 0.80, 1.00, 1), "kesim2": (1.00, 0.84, 0.45, 1), "ichki": (0.99, 0.90, 0.62, 1),
     "kumush": (0.74, 0.77, 0.82, 1), "jigar": (0.62, 0.42, 0.26, 1), "kulrang": (0.56, 0.60, 0.66, 1),
     "shisha": (0.70, 0.86, 0.95, 1), "mis": (0.85, 0.52, 0.30, 1), "to'q_qizil": (0.70, 0.16, 0.18, 1)}


def shade(color: Sequence[float], k: float = 0.42) -> Color:
    """Rangning to'q tusi — yaxlit jism qirralari uchun."""
    return (color[0] * k, color[1] * k, color[2] * k, 1.0)


def tint(color: Sequence[float], k: float = 0.5) -> Color:
    """Rangning och tusi (oqqa aralash, lekin sof oq emas)."""
    return tuple(min(1.0, c + (0.92 - c) * k) for c in color[:3]) + (1.0,)


# ───────────────────────────────────────────── to'r yordamchilari
Mesh = Tuple[np.ndarray, np.ndarray, np.ndarray]


def flat(vertices, faces, centre=None) -> Mesh:
    """Ko'pyoq: har yoq alohida (tekis yorug'lik), qavariq ko'pburchak yoqlar uchburchaklarga bo'linadi."""
    v = np.asarray(vertices, float)
    centre = v.mean(0) if centre is None else np.asarray(centre, float)
    pos, nor, idx = [], [], []
    for face in faces:
        pts = v[list(face)]
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        n /= np.linalg.norm(n)
        if np.dot(n, pts.mean(0) - centre) < 0:
            n, pts = -n, pts[::-1]
        base = len(pos)
        pos += list(pts)
        nor += [n] * len(pts)
        for k in range(1, len(pts) - 1):
            idx += [base, base + k, base + k + 1]
    return np.array(pos), np.array(nor), np.array(idx)


def _frame(z):
    z = np.asarray(z, float) / np.linalg.norm(z)
    x = np.cross(z, [0, 0, 1] if abs(z[2]) < 0.9 else [1, 0, 0])
    x /= np.linalg.norm(x)
    return x, np.cross(z, x), z


def tube(a, b, r=TUBE, seg=14) -> Mesh:
    a, b = np.asarray(a, float), np.asarray(b, float)
    x, y, _ = _frame(b - a)
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    ring_ = np.cos(ang)[:, None] * x + np.sin(ang)[:, None] * y
    idx = []
    for i in range(seg):
        j = (i + 1) % seg
        idx += [i, j, seg + i, j, seg + j, seg + i]
    return np.vstack([a + r * ring_, b + r * ring_]), np.vstack([ring_, ring_]), np.array(idx)


def tube_path(points, r=TUBE, seg=10, closed=False) -> Mesh:
    """Uzluksiz naycha ko'p nuqtali chiziq bo'ylab (orbita, maydon chizig'i, spiral) — parallel ko'chirish ramkasi."""
    p = np.asarray(points, float)
    if closed:
        p = np.vstack([p, p[:1]])
    n = len(p)
    t = np.gradient(p, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    x, _, _ = _frame(t[0])
    frames = []
    for i in range(n):
        x = x - np.dot(x, t[i]) * t[i]
        x /= np.linalg.norm(x) + 1e-12
        frames.append((x, np.cross(t[i], x)))
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    pos, nor = [], []
    for i in range(n):
        fx, fy = frames[i]
        ring_ = np.cos(ang)[:, None] * fx + np.sin(ang)[:, None] * fy
        pos.append(p[i] + r * ring_)
        nor.append(ring_)
    idx = []
    for i in range(n - 1):
        for k in range(seg):
            a, b = i * seg + k, i * seg + (k + 1) % seg
            idx += [a, b, a + seg, b, b + seg, a + seg]
    return np.vstack(pos), np.vstack(nor), np.array(idx)


def dashed(a, b, r=TUBE * 0.7, dash=0.12, gap=0.08) -> List[Mesh]:
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


def sphere(r, seg=64, rings=32, centre=(0, 0, 0), skip=None, scale=(1, 1, 1)) -> Mesh:
    """UV shar (scale — ellipsoid). skip(theta, phi) — True bo'lsa, o'sha to'rtburchak tashlanadi (kesib ochish)."""
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
    s = np.asarray(scale, float)
    nn = n / s
    nn /= np.linalg.norm(nn, axis=1, keepdims=True)
    return np.asarray(centre, float) + r * n * s, nn, np.array(idx)


def ball(c, r, seg=16) -> Mesh:
    return sphere(r, seg, max(6, seg // 2), centre=c)


def lathe(profile, seg=72, smooth_sphere=None, centre=(0, 0, 0)) -> Mesh:
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
    return np.array(pos) + np.asarray(centre, float), np.array(nor), np.array(idx)


def lathe_smooth(profile, seg=72, centre=(0, 0, 0)) -> Mesh:
    """Silliq aylanish sirti (idishlar, kolba): normal qo'shni segmentlar o'rtachasi."""
    prof = np.asarray(profile, float)
    m = len(prof)
    tang = np.gradient(prof, axis=0)
    nr, nz = tang[:, 1], -tang[:, 0]
    ln = np.hypot(nr, nz) + 1e-12
    nr, nz = nr / ln, nz / ln
    ang = np.linspace(0, 2 * np.pi, seg + 1)
    c, s = np.cos(ang), np.sin(ang)
    pos = np.stack([prof[:, 0, None] * c, prof[:, 0, None] * s, np.repeat(prof[:, 1, None], seg + 1, 1)], -1).reshape(-1, 3)
    nor = np.stack([nr[:, None] * c, nr[:, None] * s, np.repeat(nz[:, None], seg + 1, 1)], -1).reshape(-1, 3)
    idx = []
    w = seg + 1
    for i in range(m - 1):
        for j in range(seg):
            a, b = i * w + j, i * w + j + 1
            idx += [a, b, a + w, b, b + w, a + w]
    return pos + np.asarray(centre, float), nor, np.array(idx)


def disc(r, z, up, seg=72, centre=(0, 0)) -> Mesh:
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    cx, cy = centre
    pos = np.vstack([[cx, cy, z], np.stack([cx + r * np.cos(ang), cy + r * np.sin(ang), np.full(seg, z)], 1)])
    nor = np.tile([0, 0, 1 if up else -1], (seg + 1, 1))
    idx = []
    for i in range(seg):
        a, b = 1 + i, 1 + (i + 1) % seg
        idx += [0, a, b] if up else [0, b, a]
    return pos, nor, np.array(idx)


def circle_pts(r, centre=(0, 0, 0), normal=(0, 0, 1), n=96, start=0.0, end=2 * np.pi):
    x, y, _ = _frame(normal)
    ang = np.linspace(start, end, n)
    return np.asarray(centre, float) + r * (np.cos(ang)[:, None] * x + np.sin(ang)[:, None] * y)


def ring(r, z, seg=96, rad=TUBE * 0.9, centre=(0, 0, 0), plane="xy") -> List[Mesh]:
    cx, cy, cz = centre
    normal = {"xy": (0, 0, 1), "xz": (0, 1, 0), "yz": (1, 0, 0)}[plane]
    return [tube_path(circle_pts(r, (cx, cy, cz + z), normal, seg + 1), rad, 10)]


def merge(parts) -> Mesh:
    pos, nor, idx, off = [], [], [], 0
    for p, n, i in parts:
        pos.append(p); nor.append(n); idx.append(np.asarray(i) + off)
        off += len(p)
    return np.vstack(pos), np.vstack(nor), np.concatenate(idx)


def moved(parts, d, rot: Optional[np.ndarray] = None) -> List[Mesh]:
    d = np.asarray(d, float)
    if rot is None:
        return [(p + d, n, i) for p, n, i in parts]
    return [(p @ rot.T + d, n @ rot.T, i) for p, n, i in parts]


def rot_z(deg):
    a = np.radians(deg)
    return np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])


def rot_x(deg):
    a = np.radians(deg)
    return np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])


def rot_y(deg):
    a = np.radians(deg)
    return np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])


def edges_of(faces):
    out = set()
    for f in faces:
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            out.add((min(a, b), max(a, b)))
    return sorted(out)


def wire(vertices, edges, r=TUBE, balls=True) -> List[Mesh]:
    v = np.asarray(vertices, float)
    parts = [tube(v[a], v[b], r) for a, b in edges]
    if balls:
        parts += [ball(p, r * 1.35) for p in v]
    return parts


def orient(mesh: Mesh) -> Mesh:
    """Har uchburchakning aylanish yo'nalishi (winding) uning nuqta normallariga mos bo'lsin — aks holda renderer
    (va PowerPoint) uni orqa yuza deb tashlab yuboradi va sirt ko'rinmay qoladi."""
    pos, nor, idx = mesh
    tri = np.asarray(idx).reshape(-1, 3).copy()
    if not len(tri):
        return mesh
    fn = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
    vn = nor[tri[:, 0]] + nor[tri[:, 1]] + nor[tri[:, 2]]
    flip = np.einsum("ij,ij->i", fn, vn) < 0
    tri[flip] = tri[flip][:, [0, 2, 1]]
    return pos, nor, tri.reshape(-1)


def prim(parts, color, name, rough=0.5, colors=None) -> Primitive:
    mesh = orient(merge(parts) if isinstance(parts, list) else parts)
    return Primitive(*mesh, color, rough, name, colors)


def plate_poly(pts, t=0.02) -> Mesh:
    """Fazodagi tekis qavariq ko'pburchak (ikki tomonlama, yupqa)."""
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


def arrow(a, b, r=TUBE * 1.1, head=0.28, head_r=None) -> List[Mesh]:
    """Strelka (vektor): naycha + konus uchi."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    x, y, z = _frame(b - a)
    head = min(head, np.linalg.norm(b - a) * 0.45)
    tip = b - z * head
    rot = np.stack([x, y, z], 1)
    cp, cn, ci = lathe([(head_r or r * 3.0, 0), (0, head)], seg=24)
    base = disc(head_r or r * 3.0, 0, False, 24)
    return [tube(a, tip, r), (cp @ rot.T + tip, cn @ rot.T, ci), (base[0] @ rot.T + tip, base[1] @ rot.T, base[2])]


# ───────────────────────────────────────────── ko'pyoqlar
def box(a, b, c, shift=(0, 0), centre=(0, 0, 0)):
    """To'g'ri (shift=0) yoki og'ma parallelepiped: yuqori asos `shift` ga surilgan. Asos z=0 da (markaz bo'yicha)."""
    sx, sy = shift
    cx, cy, cz = centre
    v = [[cx + x + (sx if z else 0), cy + y + (sy if z else 0), cz + z]
         for z in (0, c) for y in (-b / 2, b / 2) for x in (-a / 2, a / 2)]
    return v, [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]


def cuboid(a, b, c, centre=(0, 0, 0)) -> Mesh:
    """Markazi `centre` bo'lgan quti (tekis yoqli)."""
    cx, cy, cz = centre
    v, f = box(a, b, c, centre=(cx, cy, cz - c / 2))
    return flat(v, f)


def cylinder(r, a, b, seg=48, caps=True) -> List[Mesh]:
    """Ixtiyoriy yo'nalishdagi silindr (a → b)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    x, y, z = _frame(b - a)
    h = np.linalg.norm(b - a)
    rot = np.stack([x, y, z], 1)
    parts = [lathe([(r, 0), (r, h)], seg)]
    if caps:
        parts += [disc(r, 0, False, seg), disc(r, h, True, seg)]
    return moved(parts, a, rot)


def ngon(n, r, z=0.0, start=90):
    return [[r * np.cos(np.radians(start + 360 * k / n)), r * np.sin(np.radians(start + 360 * k / n)), z] for k in range(n)]


def prism_like(bottom, top):
    n = len(bottom)
    faces = [tuple(range(n)), tuple(range(n, 2 * n))] + [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    return list(bottom) + list(top), faces


def solid(name, color, v, faces, edge_r=TUBE, rough=0.55) -> List[Primitive]:
    """Yaxlit ko'pyoq: yoqlar + to'q tusli qirralar (har qanday fonda ko'rinadi)."""
    return [prim(flat(v, faces), color, name, rough), prim(wire(v, edges_of(faces), edge_r), shade(color), name + "_qirralar", 0.4)]


def body(name, color, parts, edges=(), rough=0.5) -> List[Primitive]:
    """Yaxlit silliq jism + to'q tusli chiziqlar."""
    out = [prim(parts, color, name, rough)]
    if edges:
        out.append(prim(list(edges), shade(color), name + "_chiziqlar", 0.4))
    return out


# ───────────────────────────────────────────── tekis plastinkalar (vertikal, x–z tekisligi)
PLATE = 0.06
FRONT = -PLATE / 2 - 0.02          # plastinka oldi (kamera tomoni) — chiziqlar shu yerda


def plate(points2d, t=PLATE) -> Tuple[Mesh, List[Mesh]]:
    """Qavariq ko'pburchak plastinka (u, v) → (u, 0, v); qalinligi y bo'yicha. Qirra — o'rtadagi naycha."""
    p2 = np.asarray(points2d, float)
    n = len(p2)
    v = [[u, -t / 2, w] for u, w in p2] + [[u, t / 2, w] for u, w in p2]
    faces = [tuple(range(n)), tuple(range(n, 2 * n))] + [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    mid = [[u, 0, w] for u, w in p2]
    return flat(v, faces), [tube_path(mid + [mid[0]], TUBE * 0.8, 10)]


def flat_model(name, pieces, extra_lines=(), line_color=None) -> List[Primitive]:
    """pieces — [(points2d, color)]: bir nechta plastinkadan tekis shakl yoki yoyilma."""
    out, lines, by_color = [], list(extra_lines), {}
    for pts, color in pieces:
        b, ln = plate(pts)
        by_color.setdefault(color, []).append(b)
        lines += ln
    for k, (color, parts) in enumerate(by_color.items()):
        out.append(prim(parts, color, f"{name}_{k}", 0.55))
    out.append(prim(lines, line_color or shade(pieces[0][1], 0.38), name + "_qirralar", 0.4))
    return out


def circle2d(r, n=64, c=(0, 0)):
    return [(c[0] + r * np.cos(a), c[1] + r * np.sin(a)) for a in np.linspace(0, 2 * np.pi, n, endpoint=False)]


def sq(a, cx=0.0, cz=0.0):
    return [(cx - a / 2, cz - a / 2), (cx + a / 2, cz - a / 2), (cx + a / 2, cz + a / 2), (cx - a / 2, cz + a / 2)]


def rect(w, h, cx=0.0, cz=0.0):
    return [(cx - w / 2, cz - h / 2), (cx + w / 2, cz - h / 2), (cx + w / 2, cz + h / 2), (cx - w / 2, cz + h / 2)]


def xz(u, w, y=FRONT):
    return [u, y, w]


# ───────────────────────────────────────────── haqiqiy tasvirli sharlar (sayyoralar, Yer, Oy)
TEX_DIR = os.path.join(ROOT, "data", "katalog3d", "tekstura")
_TEX = {}


def texture(name, prepare=None):
    """Ekvidistant tekstura (`data/katalog3d/tekstura/`). prepare(array) — bir marta qo'llanadigan moslash."""
    if name not in _TEX:
        from PIL import Image
        t = np.asarray(Image.open(os.path.join(TEX_DIR, name)).convert("RGB")).astype(float)
        _TEX[name] = prepare(t) if prepare else t
    return _TEX[name]


def sample(tex, lon_deg, lat_deg):
    """Bilinear namuna: x — uzoqlik −180…180, y — kenglik 90…−90."""
    h, w, _ = tex.shape
    x = ((np.asarray(lon_deg) + 180.0) % 360.0) / 360.0 * w - 0.5
    y = (90.0 - np.asarray(lat_deg)) / 180.0 * h - 0.5
    x0 = np.floor(x).astype(int)
    y0 = np.clip(np.floor(y).astype(int), 0, h - 1)
    fx, fy = (x - x0)[..., None], np.clip(y - y0, 0, 1)[..., None]
    x0m, x1m = x0 % w, (x0 + 1) % w
    y1 = np.clip(y0 + 1, 0, h - 1)
    return (tex[y0, x0m] * (1 - fx) * (1 - fy) + tex[y0, x1m] * fx * (1 - fy) +
            tex[y1, x0m] * (1 - fx) * fy + tex[y1, x1m] * fx * fy)


def textured_sphere(tex, R, centre=(0, 0, 0), seg=192, rings=96, skip=None, sun=None, tilt=None, lon_shift=0.0,
                    night=0.28, gain=1.0):
    """Tekstura zich sfera nuqtalariga «pishiriladi» (nuqta ranglari — PowerPoint ham, zaxira rasm ham ko'rsatadi).
    sun — yorug'lik yo'nalishi (kun/tun), tilt — o'q og'ishi (matritsa)."""
    pos, nor, idx = sphere(R, seg, rings, centre=(0, 0, 0), skip=skip)
    lat = np.degrees(np.arcsin(np.clip(nor[:, 2], -1, 1)))
    lon = np.degrees(np.arctan2(nor[:, 1], nor[:, 0])) + lon_shift
    col = sample(tex, lon, lat) * gain
    if tilt is not None:
        pos, nor = pos @ tilt.T, nor @ tilt.T
    if sun is not None:
        d = np.asarray(sun, float) / np.linalg.norm(sun)
        col = col * np.clip(nor @ d * 3 + 0.6, night, 1.0)[:, None]
    cols = np.column_stack([np.clip(col, 0, 255).astype(np.uint8), np.full(len(col), 255, np.uint8)])
    return (pos + np.asarray(centre, float), nor, idx), cols


def tex_prim(tex, R, name, centre=(0, 0, 0), rough=0.6, **kw) -> Primitive:
    mesh, cols = textured_sphere(tex, R, centre, **kw)
    return prim(mesh, (1, 1, 1, 1), name, rough, colors=cols)


# ───────────────────────────────────────────── yozish
# Jismlar Z yuqoriga qarab yasaladi; glTF da esa «yuqori» — Y o'qi: (x, y, z) → (x, z, −y) (to'g'ri burilish).
_Z_TO_Y = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)


def y_up(prims: List[Primitive]) -> List[Primitive]:
    return [Primitive(p.positions @ _Z_TO_Y.T, p.normals @ _Z_TO_Y.T, p.indices, p.color, p.roughness, p.name, p.colors)
            for p in prims]


# entry: (id, nom_uz, nom, fan, kategoriya, kalit, yasovchi, preview burchagi)
Entry = Tuple[str, str, str, str, str, List[str], Callable[[], List[Primitive]], Tuple[float, float, float]]


def build(entries: Iterable[Entry], json_name: str, only: Sequence[str] = (), source: str = "", licenses=None) -> list:
    """licenses — {id: (litsenziya, qisqa muallif yozuvi, to'liq manba)}: begona teksturali modellar uchun (CC BY)."""
    """Modellarni yasaydi: GLB (KATALOG3D_DIR/ozimiz/<id>/model.glb), preview + niqob, katalog JSON."""
    from PIL import Image

    from services.med3d import preview

    out = []
    os.makedirs(katalog3d.PREVIEW_DIR, exist_ok=True)
    os.makedirs(katalog3d.MASK_DIR, exist_ok=True)
    folder = "geometriya" if json_name == "geometriya" else "ozimiz"
    for mid, nom_uz, nom, fan, kat, kalit, make, rot in entries:
        prims = y_up(make())
        allpos = np.vstack([p.positions for p in prims])
        lo, hi = allpos.min(0), allpos.max(0)
        data = write_glb(prims, name=nom)
        rel = f"{folder}/{mid}/model.glb"
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
        lic, attr, full = "CC0", "3D: Edufayl · CC0", f"\"{nom}\" — Edufayl (dasturda yasalgan o'quv modeli{', ' + source if source else ''}), CC0"
        if licenses and mid in licenses:
            lic, short, extra = licenses[mid]
            attr = f"3D: Edufayl · {short}"
            full = f"\"{nom}\" — Edufayl (dasturda yasalgan o'quv modeli; {extra}), {lic}"
        out.append({"id": mid, "nom_uz": nom_uz, "nom": nom, "fan": fan, "kalit": kalit,
                    "manba": "edufayl", "litsenziya": lic, "muallif": "Edufayl", "muallif_url": "",
                    "sahifa": "", "attribution": attr, "attribution_full": full,
                    "fayl": rel, "uchburchak": tris, "hajm": len(data),
                    "bbox": [lo.round(4).tolist(), hi.round(4).tolist()], "animatsiya": 0, "pishirilgan": True,
                    "sifat": 4, "kategoriya": kat, "tur": "real"})
        print(f"{mid:34} {len(data) / 1024:7.0f} KB  {tris:6} uchb.  {kat}")
    with open(os.path.join(katalog3d.KATALOG_DIR, json_name + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"modellar": out}, fh, ensure_ascii=False, indent=1)
    return out
