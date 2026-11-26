"""Geometrik jismlar (kub, parallelepiped, prizma, piramida, silindr, konus, shar) — 3D katalogga o'zimiz yasaymiz.

Katalogda (Objaverse/Smithsonian skanlari) toza geometrik jismlar yo'q edi: «Fazoviy jismlarning hajmi» kabi
maktab mavzulariga AI basketbol to'pi, gaz rezervuarlari va Rim arkasini qo'yardi. Bu jismlar dasturda aniq
yasaladi: yoqlari rangli, qirralari to'q naycha (shakl aniq o'qiladi), aylanish jismlarida asos aylanalari va
radius (r) chizig'i. Hajmi bir necha yuz KB, litsenziya — CC0 (o'zimizniki).

    python tools/katalog3d/geometriya.py

Natija: `data/katalog3d/geometriya.json` (katalog yozuvlari), `data/katalog3d/preview/<id>.jpg` va
`mask/<id>.png` (zaxira rasm uchun), modellar — `KATALOG3D_DIR/geometriya/<id>/model.glb`.
"""
import io
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("BOT_TOKEN", "1:x")

from services import katalog3d  # noqa: E402
from services.med3d.glb import Primitive, write_glb  # noqa: E402

EDGE = (0.10, 0.13, 0.22, 1.0)          # qirralar — to'q ko'k-kulrang
TUBE = 0.035                            # qirra naychasi radiusi (jism ~2 birlik)


# ───────────────────────────────────────────── yordamchi to'rlar
def flat(vertices, faces):
    """Ko'pyoq: har yoq alohida (tekis yorug'lik), ko'pburchak yoqlar uchburchaklarga bo'linadi."""
    v = np.asarray(vertices, float)
    centre = v.mean(0)
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
    axis = b - a
    length = np.linalg.norm(axis)
    z = axis / length
    x = np.cross(z, [0, 0, 1] if abs(z[2]) < 0.9 else [1, 0, 0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    ring = np.cos(ang)[:, None] * x + np.sin(ang)[:, None] * y
    pos = np.vstack([a + r * ring, b + r * ring])
    nor = np.vstack([ring, ring])
    idx = []
    for i in range(seg):
        j = (i + 1) % seg
        idx += [i, j, seg + i, j, seg + j, seg + i]
    return pos, nor, np.array(idx)


def ball(c, r, seg=16):
    return sphere(r, seg, seg // 2, centre=c)


def sphere(r, seg=64, rings=32, centre=(0, 0, 0)):
    th = np.linspace(0, np.pi, rings + 1)
    ph = np.linspace(0, 2 * np.pi, seg + 1)
    t, p = np.meshgrid(th, ph, indexing="ij")
    n = np.stack([np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)], -1).reshape(-1, 3)
    pos = np.asarray(centre, float) + r * n
    idx = []
    w = seg + 1
    for i in range(rings):
        for j in range(seg):
            a, b = i * w + j, i * w + j + 1
            c, d = a + w, b + w
            idx += [a, c, b, b, c, d]
    return pos, n, np.array(idx)


def lathe(profile, seg=72):
    """Aylanish jismi yon sirti: profile — [(radius, z)], silliq normallar."""
    ang = np.linspace(0, 2 * np.pi, seg + 1)
    prof = np.asarray(profile, float)
    pos, nor, idx = [], [], []
    for k in range(len(prof) - 1):
        (r0, z0), (r1, z1) = prof[k], prof[k + 1]
        dr, dz = r1 - r0, z1 - z0
        nr, nz = dz, -dr                                   # profilga perpendikulyar (tashqariga)
        ln = np.hypot(nr, nz) or 1
        nr, nz = nr / ln, nz / ln
        base = len(pos)
        for a in ang:
            c, s = np.cos(a), np.sin(a)
            pos += [[r0 * c, r0 * s, z0], [r1 * c, r1 * s, z1]]
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


def circle_edges(r, z, seg=48):
    ang = np.linspace(0, 2 * np.pi, seg + 1)
    pts = np.stack([r * np.cos(ang), r * np.sin(ang), np.full(seg + 1, z)], 1)
    return [tube(pts[i], pts[i + 1], TUBE * 0.9, 8) for i in range(seg)]


def merge(parts):
    pos, nor, idx, off = [], [], [], 0
    for p, n, i in parts:
        pos.append(p); nor.append(n); idx.append(i + off)
        off += len(p)
    return np.vstack(pos), np.vstack(nor), np.concatenate(idx)


def poly_edges(vertices, edges):
    v = np.asarray(vertices, float)
    parts = [tube(v[a], v[b]) for a, b in edges]
    parts += [ball(p, TUBE * 1.35) for p in v]              # uchlar — kichik sharcha
    return parts


def edges_of(faces):
    out = set()
    for f in faces:
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            out.add((min(a, b), max(a, b)))
    return sorted(out)


# ───────────────────────────────────────────── jismlar
def box(a, b, c):
    v = [[x, y, z] for z in (0, c) for y in (-b / 2, b / 2) for x in (-a / 2, a / 2)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return v, faces


def pyramid(a, h):
    v = [[-a / 2, -a / 2, 0], [a / 2, -a / 2, 0], [a / 2, a / 2, 0], [-a / 2, a / 2, 0], [0, 0, h]]
    return v, [(0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]


def tri_prism(a, h):
    r = a / np.sqrt(3)
    base = [[r * np.cos(t), r * np.sin(t)] for t in np.radians([90, 210, 330])]
    v = [[x, y, 0] for x, y in base] + [[x, y, h] for x, y in base]
    return v, [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]


def polyhedron(name, color, v, faces):
    p, n, i = flat(v, faces)
    edge = merge(poly_edges(v, edges_of(faces)))
    return [Primitive(p, n, i, color, 0.55, name), Primitive(*edge, EDGE, 0.4, name + "_qirralar")]


def solid_of_revolution(name, color, profile, caps, rings, radius_at):
    parts = [lathe(profile)] + [disc(r, z, up) for r, z, up in caps]
    body = merge(parts)
    edge_parts = [e for r, z in rings for e in circle_edges(r, z)]
    if radius_at is not None:                               # radius chizig'i: markazdan aylanagacha
        r, z = radius_at
        edge_parts += [tube([0, 0, z + 0.004], [r, 0, z + 0.004], TUBE * 0.9), ball([0, 0, z + 0.004], TUBE * 1.6)]
    return [Primitive(*body, color, 0.5, name), Primitive(*merge(edge_parts), EDGE, 0.4, name + "_chiziqlar")]


def sphere_model(name, color, r):
    """Shar: ekvator va meridian aylanalari (shar ekani va markazi aniq o'qiladi)."""
    body = sphere(r, centre=(0, 0, r))
    rr = r * 1.004
    equator = [(np.array([0, 0, r]) + rr * np.array([np.cos(a), np.sin(a), 0])) for a in np.linspace(0, 2 * np.pi, 97)]
    meridian = [(np.array([0, 0, r]) + rr * np.array([np.cos(a), 0, np.sin(a)])) for a in np.linspace(0, 2 * np.pi, 97)]
    lines = [tube(p[i], p[i + 1], TUBE * 0.9, 8) for p in (equator, meridian) for i in range(96)]
    return [Primitive(*body, color, 0.45, name), Primitive(*merge(lines), EDGE, 0.4, name + "_aylanalar")]


# Jismlar Z yuqoriga qarab yasaladi; glTF da esa «yuqori» — Y o'qi: (x, y, z) → (x, z, −y) (to'g'ri burilish).
_Z_TO_Y = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)


def y_up(prims):
    return [Primitive(p.positions @ _Z_TO_Y.T, p.normals @ _Z_TO_Y.T, p.indices, p.color, p.roughness, p.name)
            for p in prims]


MODELS = [
    ("geo_kub", "Kub", "Cube", ["kub", "cube", "hajm", "volume", "geometriya", "ko'pyoq", "qirra"],
     lambda: polyhedron("kub", (0.20, 0.47, 0.93, 1), *box(2, 2, 2))),
    ("geo_parallelepiped", "To'g'ri burchakli parallelepiped", "Rectangular cuboid",
     ["parallelepiped", "cuboid", "box", "hajm", "volume", "geometriya", "ko'pyoq", "prizma"],
     lambda: polyhedron("parallelepiped", (0.96, 0.55, 0.16, 1), *box(3, 2, 1.5))),
    ("geo_prizma", "Uchburchakli prizma", "Triangular prism",
     ["prizma", "prism", "hajm", "volume", "geometriya", "ko'pyoq"],
     lambda: polyhedron("prizma", (0.89, 0.33, 0.55, 1), *tri_prism(2.2, 2.4))),
    ("geo_piramida", "To'rtburchakli piramida", "Square pyramid",
     ["piramida", "pyramid", "hajm", "volume", "geometriya", "ko'pyoq"],
     lambda: polyhedron("piramida", (0.12, 0.68, 0.62, 1), *pyramid(2.2, 2.2))),
    ("geo_silindr", "Silindr", "Cylinder", ["silindr", "cylinder", "hajm", "volume", "geometriya", "aylanish jismi"],
     lambda: solid_of_revolution("silindr", (0.27, 0.70, 0.36, 1), [(1, 0), (1, 2.4)],
                                 [(1, 2.4, True), (1, 0, False)], [(1, 0), (1, 2.4)], (1, 2.4))),
    ("geo_konus", "Konus", "Cone", ["konus", "cone", "hajm", "volume", "geometriya", "aylanish jismi"],
     lambda: solid_of_revolution("konus", (0.55, 0.36, 0.86, 1), [(1.1, 0), (0, 2.4)],
                                 [(1.1, 0, False)], [(1.1, 0)], None)),
    ("geo_shar", "Shar", "Sphere", ["shar", "sphere", "hajm", "volume", "geometriya", "aylanish jismi"],
     lambda: sphere_model("shar", (0.98, 0.78, 0.18, 1), 1.2)),
]


def build_all() -> list:
    from PIL import Image

    from services.med3d import preview

    out = []
    os.makedirs(katalog3d.PREVIEW_DIR, exist_ok=True)
    os.makedirs(katalog3d.MASK_DIR, exist_ok=True)
    for mid, nom_uz, nom, kalit, make in MODELS:
        prims = y_up(make())
        allpos = np.vstack([p.positions for p in prims])
        lo, hi = allpos.min(0), allpos.max(0)
        data = write_glb(prims, name=nom)
        rel = f"geometriya/{mid}/model.glb"
        path = os.path.join(katalog3d.MODELS_DIR, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        img = preview.render(data, (22, 35, 0), 600).convert("RGBA")
        bg = Image.new("RGBA", img.size, (242, 242, 240, 255))
        Image.alpha_composite(bg, img).convert("RGB").save(os.path.join(katalog3d.PREVIEW_DIR, mid + ".jpg"), quality=90)
        img.getchannel("A").save(os.path.join(katalog3d.MASK_DIR, mid + ".png"))
        tris = int(sum(len(p.indices) for p in prims) // 3)
        out.append({"id": mid, "nom_uz": nom_uz, "nom": nom, "fan": "matematika", "kalit": kalit,
                    "manba": "edufayl", "litsenziya": "CC0", "muallif": "Edufayl", "muallif_url": "",
                    "sahifa": "", "attribution": "3D: Edufayl · CC0",
                    "attribution_full": f"\"{nom}\" — Edufayl (dasturda yasalgan geometrik jism), CC0",
                    "fayl": rel, "uchburchak": tris, "hajm": len(data),
                    "bbox": [lo.round(4).tolist(), hi.round(4).tolist()], "animatsiya": 0, "pishirilgan": True,
                    "sifat": 4, "kategoriya": "Geometrik jismlar", "tur": "real"})
        print(f"{mid:22} {len(data) / 1024:7.0f} KB  {tris:6} uchburchak")
    with open(os.path.join(katalog3d.KATALOG_DIR, "geometriya.json"), "w", encoding="utf-8") as fh:
        json.dump({"modellar": out}, fh, ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    build_all()
