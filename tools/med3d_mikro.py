"""Mikro dunyo modellari: hujayra, qon tanachalari, bakteriya, virus, DNK, xromosoma, jinsiy hujayralar, neyron.

Human Atlas'da bunday tuzilmalar yo'q va tayyor ochiq modellar topilmadi, shuning uchun modellar shu faylda
parametrik formulalar bilan yasaladi (tashqi fayl va litsenziya kerak emas). Natija atlas formatidagi qo'shimcha
katalog: `assets/med3d/mikro/` (`atlas-mikro.json` + `mikro.bin`); `Atlas` uni ikkala tanaga ham qo'shadi.
O'lchamlar ko'rinishi uchun kattalashtirilgan (hammasi ~0.2-0.6 m). Keyin: `python tools/med3d_lugat.py`.

    python tools/med3d_mikro.py
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from services.med3d import MICRO_DIR            # noqa: E402
from services.med3d.simplify import vertex_normals   # noqa: E402

TAU = 2 * np.pi


# ───────────────────────────────────────────── to'r (mesh) yordamchilari: mesh = (nuqtalar N×3, uchburchaklar M×3)

def _grid(P, wrap=True):
    nu, nv = P.shape[:2]
    i, j = np.meshgrid(np.arange(nu - 1), np.arange(nv if wrap else nv - 1), indexing="ij")
    j2 = (j + 1) % nv
    a, b, c, d = i * nv + j, i * nv + j2, (i + 1) * nv + j2, (i + 1) * nv + j
    tri = np.concatenate([np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)])
    return P.reshape(-1, 3), tri


def _weld(pos, tri):
    _, first, inv = np.unique(np.round(pos, 6), axis=0, return_index=True, return_inverse=True)
    tri = inv.reshape(-1)[tri]
    ok = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
    return pos[first], tri[ok]


def _volume(pos, tri):
    p = pos[tri]
    return float(np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum() / 6)


def closed(pos, tri):
    """Yopiq jism: nuqtalar yopishtiriladi, yuzalar tashqariga qaratiladi."""
    pos, tri = _weld(pos, tri)
    return (pos, tri[:, ::-1]) if _volume(pos, tri) < 0 else (pos, tri)


def join(*meshes):
    pos, tri, base = [], [], 0
    for p, t in meshes:
        pos.append(p)
        tri.append(t + base)
        base += len(p)
    return np.vstack(pos), np.vstack(tri)


def _compact(pos, tri):
    used = np.unique(tri)
    remap = np.full(len(pos), -1)
    remap[used] = np.arange(len(used))
    return pos[used], remap[tri]


def _rotation(rng):
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    return q * np.sign(np.linalg.det(q))


def _sphere_grid(radii, center, nu, nv, phi0, bump, seed, rot):
    th = np.linspace(0, np.pi, nu)[:, None]
    ph = (np.linspace(0, TAU, nv, endpoint=False) if phi0 is None else np.linspace(phi0, TAU, nv))[None, :]
    d = np.stack([np.sin(th) * np.cos(ph), np.cos(th) * np.ones_like(ph), np.sin(th) * np.sin(ph)], -1)
    if bump:
        wave = np.sin(4 * d[..., 0] + seed) + np.sin(5 * d[..., 1] + 2 * seed + 1) + np.sin(6 * d[..., 2] + 3 * seed + 2)
        d = d * (1 + bump * wave / 3)[..., None]
    P = d * np.asarray(radii, float)
    if rot is not None:
        P = P @ rot.T
    return P + np.asarray(center, float)


def sphere(radii, center=(0, 0, 0), nu=30, nv=48, bump=0.0, seed=0, rot=None):
    return closed(*_grid(_sphere_grid(radii, center, nu, nv, None, bump, seed, rot)))


def shell(radius, thick, center=(0, 0, 0), nu=36, nv=64, bump=0.0, seed=0):
    """Kesilgan kosa (to'rtdan bir bo'lagi — x>0, z>0 — olib tashlangan): tashqi yuza, ichki yuza, kesim chetlari.
    Ichkarisi ko'rinadi, ichidagi organellalar kesim orqali ko'zga tashlanadi."""
    c = np.asarray(center, float)
    phi0 = np.pi / 2
    outer = _sphere_grid((radius,) * 3, c, nu, nv, phi0, bump, seed, None)
    inner = c + (outer - c) * ((radius - thick) / radius)
    out_mesh = _weld(*_grid(outer, wrap=False))
    in_p, in_t = _weld(*_grid(inner, wrap=False))
    rims = []
    for j, side, phi in ((0, -1.0, phi0), (nv - 1, 1.0, TAU)):
        sp, st = _grid(np.stack([outer[:, j], inner[:, j]], axis=1), wrap=False)
        n = np.cross(sp[st[:, 1]] - sp[st[:, 0]], sp[st[:, 2]] - sp[st[:, 0]])
        want = side * np.array([-np.sin(phi), 0.0, np.cos(phi)])
        st = np.where((n @ want < 0)[:, None], st[:, ::-1], st)
        rims.append(_weld(sp, st))
    return out_mesh, (in_p, in_t[:, ::-1]), join(*rims)


def catmull(points, k=60):
    p = np.asarray(points, float)
    p = np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]])
    per = max(2, k // (len(p) - 3))
    t = np.linspace(0, 1, per, endpoint=False)[:, None]
    out = []
    for i in range(1, len(p) - 2):
        a, b, c, d = p[i - 1], p[i], p[i + 1], p[i + 2]
        out.append(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t ** 2 + (-a + 3 * b - 3 * c + d) * t ** 3))
    out.append(p[-2][None])
    return np.vstack(out)


def tube(path, radius, nv=14):
    path = np.asarray(path, float)
    radius = np.broadcast_to(np.asarray(radius, float), (len(path),))
    T = np.gradient(path, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-12
    ref = np.array([0.0, 1.0, 0.0]) if abs(T[0, 1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    n = np.cross(T[0], ref)
    n /= np.linalg.norm(n)
    ang = np.linspace(0, TAU, nv, endpoint=False)
    ca, sa = np.cos(ang)[:, None], np.sin(ang)[:, None]
    rings = []
    for k in range(len(path)):
        if k:
            n = n - T[k] * (n @ T[k])
            n /= np.linalg.norm(n) + 1e-12
        rings.append(path[k] + radius[k] * (ca * n + sa * np.cross(T[k], n)))
    pos, tri = _grid(np.array(rings))
    j, last = np.arange(nv), (len(path) - 1) * nv
    c0, c1 = len(pos), len(pos) + 1
    caps = [np.stack([np.full(nv, c0), (j + 1) % nv, j], -1), np.stack([np.full(nv, c1), last + j, last + (j + 1) % nv], -1)]
    return closed(np.vstack([pos, path[0], path[-1]]), np.vstack([tri, *caps]))


def capsule_radius(s, R, power=8):
    """Uchlari yumaloq tayoqcha profili: s ∈ [0, 1]."""
    return R * np.sqrt(np.clip(1 - np.abs(2 * s - 1) ** power, 0, 1))


# ───────────────────────────────────────────── modellar: {qism nomi: mesh}

def erythrocyte():
    R, n = 0.12, 40
    rho = np.sin(np.linspace(0, np.pi / 2, n))
    h = R * np.sqrt(np.clip(1 - rho ** 2, 0, 1)) * (0.2072 + 0.5006 * rho ** 2 - 0.0702 * rho ** 4)   # ikki botiq disk
    rr, yy = np.concatenate([rho, rho[::-1]]), np.concatenate([h, -h[::-1]])
    ph = np.linspace(0, TAU, 72, endpoint=False)
    P = np.stack([R * rr[:, None] * np.cos(ph), yy[:, None] * np.ones_like(ph), R * rr[:, None] * np.sin(ph)], -1)
    return {"Erythrocyte": closed(*_grid(P))}


def leukocyte():
    rng = np.random.default_rng(11)
    outer, inner, rim = shell(0.13, 0.012, bump=0.05, seed=1)
    lobes = [np.array(c) for c in ((0.02, 0.045, 0.0), (0.065, 0.0, 0.025), (0.04, -0.05, -0.01), (0.0, -0.02, -0.045))]
    nucleus = [sphere((0.04,) * 3, c, nu=22, nv=32, bump=0.05, seed=k) for k, c in enumerate(lobes)]
    nucleus += [tube(catmull([a, b], 8), 0.012, nv=10) for a, b in zip(lobes, lobes[1:])]
    pts = []
    while len(pts) < 18:
        p = rng.uniform(-0.1, 0.1, 3)
        if np.linalg.norm(p) < 0.095 and min(np.linalg.norm(p - c) for c in lobes) > 0.052:
            pts.append(p)
    return {"Leukocyte membrane": join(outer, rim), "Leukocyte cytoplasm": inner,
            "Leukocyte nucleus": join(*nucleus),
            "Leukocyte granules": join(*[sphere((0.009,) * 3, p, nu=10, nv=14) for p in pts])}


def platelet():
    return {"Platelet": sphere((0.075, 0.028, 0.06), nu=26, nv=40, bump=0.09, seed=2)}


def spermatozoon():
    pos, tri = sphere((0.075, 0.034, 0.045), nu=32, nv=48)
    front = pos[tri].mean(1)[:, 0] > 0.028
    s = np.linspace(0, 1, 30)
    mid = tube(np.stack([-0.068 - 0.075 * s, 0 * s, 0 * s], 1), 0.016 + 0.002 * np.sin(TAU * 9 * s), nv=14)
    u = np.linspace(0, 1, 110)
    wave = 0.05 * np.sin(TAU * 2.0 * u) * u ** 0.5
    tail = tube(np.stack([-0.143 - 0.28 * u, wave, 0.012 * np.sin(TAU * 2.0 * u + 1.2) * u], 1), 0.012 * (1 - 0.75 * u) + 0.002, nv=10)
    return {"Sperm head": (pos, tri[~front]), "Sperm acrosome": (pos, tri[front]),
            "Sperm midpiece": mid, "Sperm tail": tail}


def bacterium_rod():
    rng = np.random.default_rng(5)
    L, R = 0.34, 0.06
    x = L / 2 * np.sin(np.linspace(-np.pi / 2, np.pi / 2, 90))
    cyl = L / 2 - R
    r = np.where(np.abs(x) <= cyl, R, np.sqrt(np.clip(R ** 2 - (np.abs(x) - cyl) ** 2, 0, None)))
    body = tube(np.stack([x, 0 * x, 0 * x], 1), r, nv=24)
    s = np.linspace(0, 1, 80)[:, None]
    flagella = []
    for k in range(8):
        a, xk = TAU * k / 8 + rng.uniform(-0.2, 0.2), rng.uniform(-0.1, 0.1)
        u, e1 = np.array([0, np.cos(a), np.sin(a)]), np.array([0, -np.sin(a), np.cos(a)])
        start = np.array([xk, 0.0, 0.0]) + 0.97 * R * u
        wob = 0.016 * s * (np.sin(TAU * 5 * s) * e1 + (np.cos(TAU * 5 * s) - 1) * u)
        path = start + u * 0.11 * np.sqrt(s) - np.array([1.0, 0, 0]) * 0.42 * s + wob
        flagella.append(tube(path, 0.0045 * (1 - 0.4 * s[:, 0]), nv=8))
    return {"Bacterium rod": body, "Bacterium flagella": join(*flagella)}


def coccus_cluster():
    rng = np.random.default_rng(9)
    cells = []
    g = np.arange(-2, 3) * 0.1
    for p in ((x, y, z) for x in g for y in g for z in g):
        p = np.array(p) + rng.uniform(-0.012, 0.012, 3)
        if np.linalg.norm(p) < 0.19:
            cells.append(sphere((0.052,) * 3, p, nu=22, nv=32))
    return {"Coccus": join(*cells)}


def chromosome():
    left = [(-0.052, 0.24, 0), (-0.03, 0.12, 0), (-0.012, 0.0, 0), (-0.032, -0.14, 0), (-0.055, -0.30, 0)]
    s = np.linspace(0, 1, 110)
    r = 0.032 * np.sqrt(np.clip(1 - np.abs(2 * s - 1) ** 8, 0, 1)) * (1 - 0.35 * np.exp(-((s - 0.45) / 0.06) ** 2)) \
        * (1 + 0.06 * np.sin(TAU * 8 * s))
    arms, bands = [], []
    for sign in (-1, 1):
        path = catmull([(sign * x, y, z) for x, y, z in left], 110)[:110]
        path = np.array([np.interp(np.linspace(0, 1, 110), np.linspace(0, 1, len(path)), path[:, k]) for k in range(3)]).T
        arms.append(tube(path, r, nv=18))
        keep = slice(40, 52)
        bands.append(tube(path[keep], r[keep] + 0.006, nv=18))
    return {"Chromosome chromatid": join(*arms), "Chromosome centromere": join(*bands)}


def dna():
    R, pitch = 0.06, 0.14
    t = np.linspace(0, 3 * TAU, 220)
    y = t * pitch / TAU - 1.5 * pitch

    def strand(shift):
        return np.stack([R * np.cos(t + shift), y, R * np.sin(t + shift)], 1)
    rng = np.random.default_rng(3)
    pairs = {"A": ("A", "T"), "T": ("T", "A"), "G": ("G", "C"), "C": ("C", "G")}
    bases = {k: [] for k in "ATGC"}
    for a in np.arange(0.3, 3 * TAU - 0.2, 0.62):
        yk = a * pitch / TAU - 1.5 * pitch
        p1 = np.array([R * np.cos(a), yk, R * np.sin(a)])
        p2 = np.array([R * np.cos(a + np.pi), yk, R * np.sin(a + np.pi)])
        mid = np.array([0.0, yk, 0.0])
        b1, b2 = pairs[rng.choice(list("ATGC"))]
        bases[b1].append(tube(np.stack([p1 * 0.96, mid]), 0.0085, nv=8))
        bases[b2].append(tube(np.stack([mid, p2 * 0.96]), 0.0085, nv=8))
    out = {"DNA backbone 1": tube(strand(0.0), 0.014, nv=12), "DNA backbone 2": tube(strand(np.pi), 0.014, nv=12)}
    out.update({f"DNA base {k}": join(*v) for k, v in bases.items() if v})
    return out


def virus():
    R, n = 0.1, 54
    k = np.arange(n) + 0.5
    y, phi = 1 - 2 * k / n, np.pi * (1 + 5 ** 0.5) * k
    d = np.stack([np.sqrt(1 - y * y) * np.cos(phi), y, np.sqrt(1 - y * y) * np.sin(phi)], -1)
    stalks = [tube(np.linspace(u * R * 0.96, u * (R + 0.055), 3), [0.006, 0.0055, 0.007], nv=8) for u in d]
    heads = [sphere((0.017,) * 3, u * (R + 0.067), nu=10, nv=14) for u in d]
    return {"Virus envelope": sphere((R,) * 3, nu=32, nv=52), "Virus spike": join(*stalks, *heads)}


def neuron():
    rng = np.random.default_rng(7)
    soma = sphere((0.07, 0.06, 0.07), nu=30, nv=44, bump=0.07, seed=3)
    dend = []

    def branch(p, d, r, length, depth):
        end = p + d * length
        path = catmull([p, (p + end) / 2 + rng.normal(0, 0.02, 3), end], 16)
        dend.append(tube(path, np.linspace(r, r * 0.6, len(path)), nv=8))
        if depth < 2:
            for _ in range(2):
                nd = d + rng.normal(0, 0.7, 3)
                branch(path[-1], nd / np.linalg.norm(nd), r * 0.65, length * 0.68, depth + 1)
    for _ in range(7):
        d = rng.normal(size=3)
        d[1] = abs(d[1]) * 0.6 - 0.1
        d /= np.linalg.norm(d)
        branch(d * 0.055, d, 0.015, 0.17, 0)
    axon_path = catmull([(0, -0.05, 0), (0.03, -0.3, 0.02), (-0.02, -0.55, -0.01), (0, -0.75, 0)], 90)
    axon = [tube(axon_path, 0.011, nv=10)]
    myelin = []
    for a in np.linspace(14, 70, 6).astype(int):
        seg = axon_path[a - 5:a + 5]
        myelin.append(tube(seg, 0.03 * np.sqrt(np.clip(np.sin(np.linspace(0.05, np.pi - 0.05, len(seg))), 0, 1)), nv=14))
    end = axon_path[-1]
    for k in range(4):
        a = TAU * k / 4 + 0.4
        tip = end + np.array([0.08 * np.cos(a), -0.07, 0.08 * np.sin(a)])
        axon.append(tube(catmull([end, (end + tip) / 2 + [0.01, 0, 0], tip], 10), 0.007, nv=8))
        axon.append(sphere((0.018,) * 3, tip, nu=12, nv=16))
    return {"Neuron soma": soma, "Neuron dendrites": join(*dend), "Neuron axon": join(*axon),
            "Neuron myelin": join(*myelin)}


def animal_cell():
    rng = np.random.default_rng(4)
    outer, inner, rim = shell(0.2, 0.012, bump=0.02, seed=4, nu=40, nv=72)
    nuc = np.array([0.05, 0.0, 0.05])
    n_out, n_in, n_rim = shell(0.075, 0.008, nuc, nu=30, nv=48)
    spots = []
    while len(spots) < 7:
        p = rng.uniform(-0.15, 0.15, 3)
        if np.linalg.norm(p) < 0.16 and np.linalg.norm(p - nuc) > 0.12 and p[0] > -0.02 and p[2] > -0.02:
            spots.append(p)
    mito = [sphere((0.04, 0.017, 0.017), p, nu=14, nv=22, rot=_rotation(rng)) for p in spots]
    golgi = [sphere((0.052 - 0.005 * k, 0.005, 0.034), (0.07, -0.1 + 0.014 * k, 0.04), nu=14, nv=24) for k in range(5)]
    lyso = []
    while len(lyso) < 6:
        p = rng.uniform(-0.15, 0.15, 3)
        if np.linalg.norm(p) < 0.16 and np.linalg.norm(p - nuc) > 0.1 and p[0] > -0.03 and p[2] > -0.03 \
                and min(np.linalg.norm(p - q) for q in spots) > 0.05:
            lyso.append(p)
    return {"Cell membrane": join(outer, rim), "Cell cytoplasm": inner,
            "Cell nucleus envelope": join(n_out, n_rim), "Cell nucleoplasm": n_in,
            "Cell nucleolus": sphere((0.022,) * 3, nuc + [0.0, 0.005, 0.0], nu=14, nv=22),
            "Cell mitochondria": join(*mito), "Cell Golgi": join(*golgi),
            "Cell lysosomes": join(*[sphere((0.014,) * 3, p, nu=10, nv=16) for p in lyso])}


def oocyte():
    rng = np.random.default_rng(6)
    z_out, z_in, z_rim = shell(0.2, 0.035, nu=40, nv=72)
    c_out, c_in, c_rim = shell(0.163, 0.004, nu=36, nv=64)
    nuc = np.array([0.04, 0.0, 0.04])
    n_out, n_in, n_rim = shell(0.05, 0.006, nuc, nu=24, nv=40)
    cells = []
    while len(cells) < 40:
        d = rng.normal(size=3)
        d /= np.linalg.norm(d)
        if d[0] > -0.1 and d[2] > -0.1:        # kesim ochiq qolsin
            continue
        cells.append(sphere((0.02,) * 3, d * 0.215, nu=10, nv=16))
    return {"Oocyte zona pellucida": join(z_out, z_rim), "Oocyte zona inner": z_in,
            "Oocyte cytoplasm": join(c_out, c_rim), "Oocyte cytoplasm inner": c_in,
            "Oocyte nucleus": join(n_out, n_rim), "Oocyte nucleus inner": n_in,
            "Oocyte nucleolus": sphere((0.015,) * 3, nuc + [0.0, 0.004, 0.0], nu=12, nv=18),
            "Oocyte corona cells": join(*cells)}


# (model, joyi, burilish X va Y gradus): kesilgan hujayralarning "derazasi" (x>0, z>0 chorak) kameraga qaraydi,
# yassi disklar (qon tanachalari) old ko'rinishda qirrasi bilan emas, yuzi bilan ko'rinadi.
MODELS = [
    (erythrocyte, (-0.3, 0, 0), (50, 0)), (leukocyte, (0.0, 0, 0), (0, -45)), (platelet, (0.27, 0, 0), (50, 0)),
    (spermatozoon, (-0.36, 0, 0), (0, 0)), (oocyte, (0.0, 0, 0), (0, -45)),
    (animal_cell, (0, 0, 0), (0, -45)), (neuron, (0, 0, 0), (0, 0)), (chromosome, (0, 0, 0), (0, 0)),
    (dna, (0, 0, 0), (0, 0)), (bacterium_rod, (0, 0, 0), (0, 0)), (coccus_cluster, (0, 0, 0), (0, 0)),
    (virus, (0, 0, 0), (0, 0)),
]


def _turn(rx: float, ry: float) -> np.ndarray:
    ax, ay = np.radians(rx), np.radians(ry)
    mx = np.array([[1, 0, 0], [0, np.cos(ax), -np.sin(ax)], [0, np.sin(ax), np.cos(ax)]])
    my = np.array([[np.cos(ay), 0, np.sin(ay)], [0, 1, 0], [-np.sin(ay), 0, np.cos(ay)]])
    return my @ mx


def main() -> int:
    os.makedirs(MICRO_DIR, exist_ok=True)
    parts, blob = [], bytearray()
    for build, offset, (rx, ry) in MODELS:
        for name, (pos, tri) in build().items():
            pos, tri = _compact(pos @ _turn(rx, ry).T + np.asarray(offset, float), tri)
            pos32, idx = pos.astype("<f4"), tri.reshape(-1).astype("<u4")
            nrm = np.round(vertex_normals(pos32, idx) * 32767).astype("<i2")
            rec = {"id": "MK-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"), "name": name, "system": "micro",
                   "chunk": 0, "vertexCount": len(pos32), "indexCount": len(idx),
                   "bounds": [pos32.min(0).round(5).tolist(), pos32.max(0).round(5).tolist()]}
            for key, arr in (("positions", pos32), ("normals", nrm), ("indices", idx)):
                blob += b"\0" * (-len(blob) % 4)
                rec[key] = len(blob)
                blob += arr.tobytes()
            parts.append(rec)
            print(f"{name:28s} {len(pos32):7d} nuqta {len(idx) // 3:7d} ▲")
    with open(os.path.join(MICRO_DIR, "mikro.bin"), "wb") as fh:
        fh.write(bytes(blob))
    doc = {"version": "Edufayl mikro modellari (original)", "chunks": [{"url": "mikro.bin"}], "parts": parts}
    with open(os.path.join(MICRO_DIR, "atlas-mikro.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=0)
    print(f"{len(parts)} qism, {len(blob) / 1e6:.1f} MB →", MICRO_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
