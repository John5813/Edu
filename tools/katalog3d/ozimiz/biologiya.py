"""Biologiya (hujayra va molekulalar darajasi):
- DNK — haqiqiy atomlar (PDB 1BNA, rentgen tuzilmasi) va B-DNK qo'sh spirali (aniq parametrlar: 10 juft/o'ram,
  3,38 Å ko'tarilish, katta va kichik egatlar);
- gemoglobin — PDB 2HHB: 4 zanjir (Cα umurtqasi bo'ylab silliq naycha) va 4 ta gem (temir atomi bilan);
- virus (ikosaedrik kapsid), koronavirus, bakteriofag;
- hayvon va o'simlik hujayrasi (kesib ochilgan), mitoxondriya (kesim), xromosoma, mitoz bosqichlari,
  hujayra membranasi (fosfolipid qo'sh qavati va oqsillar).
"""
import os

import numpy as np

from .asos import (C, RADIUS, TUBE, WIRE, ball, cuboid, cylinder, dashed, disc, flat, lathe, lathe_smooth, moved,
                   plate_poly, prim, ring, rot_x, rot_y, rot_z, shade, sphere, tube, tube_path)

FAN = "biologiya"
PDB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                   "data", "katalog3d", "pdb")
BASE = {"A": (0.92, 0.30, 0.28, 1), "T": (0.98, 0.78, 0.20, 1), "G": (0.25, 0.72, 0.35, 1), "C": (0.22, 0.48, 0.95, 1)}
ATOMC = {"C": (0.42, 0.44, 0.50, 1), "O": (0.90, 0.22, 0.20, 1), "N": (0.25, 0.45, 0.95, 1), "P": (0.98, 0.55, 0.10, 1)}


def _centre(xyz, height=2.6):
    """Koordinatalarni markazlash, eng uzun o'qni tik qo'yish va o'lchamni moslash."""
    xyz = xyz - xyz.mean(0)
    _, _, vt = np.linalg.svd(xyz, full_matrices=False)
    xyz = xyz @ vt.T                                    # 0-o'q — eng uzun
    xyz = xyz[:, [1, 2, 0]]                             # eng uzun → z
    k = height / np.ptp(xyz[:, 2])
    xyz = xyz * k
    xyz[:, 2] -= xyz[:, 2].min() - 0.1
    return xyz, k


# ───────── DNK
def dna_real():
    d = np.load(os.path.join(PDB, "1bna.npz"))
    xyz, k = _centre(d["xyz"].astype(float), 2.8)
    el = d["el"]
    out, by = [], {}
    for p, e in zip(xyz, el):
        by.setdefault(e, []).append(ball(p, 0.85 * k * (1.0 if e != "P" else 1.2), 12))
    for e, parts in by.items():
        out.append(prim(parts, ATOMC.get(e, ATOMC["C"]), f"dnk_{e}", 0.35))
    bonds = []
    for i in range(len(xyz)):
        dd = np.linalg.norm(xyz[i + 1:] - xyz[i], axis=1) / k
        for j in np.where((dd > 0.5) & (dd < 1.75))[0]:
            bonds.append(tube(xyz[i], xyz[i + 1 + j], 0.25 * k, 6))
    out.append(prim(bonds, (0.62, 0.65, 0.72, 1), "dnk_boglar", 0.4))
    return out


def dna_helix(bp=30):
    rise, twist, rP, minor = 0.338, 36.0, 0.89, 150.0       # nm; minor egat burchagi
    seq = ("ATGCGTACGTTAGCATGCAATCGGCTAGCT" * 2)[:bp]
    comp = {"A": "T", "T": "A", "G": "C", "C": "G"}
    s1, s2, rods = [], [], {b: [] for b in "ATGC"}
    for i, b in enumerate(seq):
        a1 = np.radians(twist * i)
        a2 = a1 + np.radians(minor)
        z = 0.2 + i * rise * 0.9
        p1 = np.array([rP * np.cos(a1), rP * np.sin(a1), z])
        p2 = np.array([rP * np.cos(a2), rP * np.sin(a2), z])
        s1.append(p1); s2.append(p2)
        mid = (p1 + p2) / 2
        rods[b].append(tube(p1 * [0.92, 0.92, 1], mid, 0.07, 10))
        rods[comp[b]].append(tube(mid, p2 * [0.92, 0.92, 1], 0.07, 10))
    def smooth(pts):
        pts = np.array(pts)
        t = np.linspace(0, len(pts) - 1, len(pts) * 6)
        return np.stack([np.interp(t, np.arange(len(pts)), pts[:, k]) for k in range(3)], 1) if False else \
            np.array([[rP * np.cos(np.arctan2(*_yx(pts, u))) for _ in [0]][0] for u in t]) if False else _arc(pts)
    out = [prim([tube_path(_arc(s1), 0.11, 12)] + [ball(p, 0.16, 14) for p in s1], (0.96, 0.58, 0.18, 1), "zanjir_1", 0.35),
           prim([tube_path(_arc(s2), 0.11, 12)] + [ball(p, 0.16, 14) for p in s2], (0.30, 0.55, 0.92, 1), "zanjir_2", 0.35)]
    for b, parts in rods.items():
        out.append(prim(parts, BASE[b], f"asos_{b}", 0.4))
    return out


def _yx(pts, u):
    return 0, 0


def _arc(pts):
    """Spiral nuqtalari orasini silindrik koordinatada silliq to'ldirish (naycha spiral bo'ylab egilsin)."""
    pts = np.array(pts)
    ang = np.unwrap(np.arctan2(pts[:, 1], pts[:, 0]))
    r = np.hypot(pts[:, 0], pts[:, 1])
    t = np.linspace(0, len(pts) - 1, (len(pts) - 1) * 8 + 1)
    a = np.interp(t, np.arange(len(pts)), ang)
    rr = np.interp(t, np.arange(len(pts)), r)
    z = np.interp(t, np.arange(len(pts)), pts[:, 2])
    return np.stack([rr * np.cos(a), rr * np.sin(a), z], 1)


# ───────── gemoglobin (PDB 2HHB)
def catmull(pts, n=6):
    pts = np.asarray(pts, float)
    p = np.vstack([pts[:1], pts, pts[-1:]])
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pts[-1])
    return np.array(out)


def hemoglobin():
    d = np.load(os.path.join(PDB, "2hhb.npz"))
    allxyz = np.vstack([d["ca"], d["hem"]]).astype(float)
    centre = allxyz.mean(0)
    k = 3.0 / np.ptp(allxyz - centre, axis=0).max()
    def tr(x):
        x = (np.asarray(x, float) - centre) * k
        return x[:, [0, 2, 1]] + [0, 0, 1.7]
    cols = {"A": (0.25, 0.55, 0.95, 1), "B": (0.95, 0.55, 0.20, 1), "C": (0.30, 0.75, 0.45, 1), "D": (0.85, 0.35, 0.55, 1)}
    out = []
    for ch, col in cols.items():
        ca = tr(d["ca"][d["ca_chain"] == ch])
        out.append(prim([tube_path(catmull(ca, 5), 0.075, 10)], col, f"zanjir_{ch}", 0.4))
    hem = tr(d["hem"])
    fe = [ball(p, 0.11, 16) for p, e in zip(hem, d["hem_el"]) if e == "FE"]
    ring_atoms = [ball(p, 0.045, 8) for p, e in zip(hem, d["hem_el"]) if e in ("C", "N")]
    out += [prim(ring_atoms, (0.80, 0.15, 0.15, 1), "gem", 0.4), prim(fe, (0.70, 0.45, 0.30, 1), "temir_Fe", 0.3)]
    return out


# ───────── viruslar
def icosa_vertices(r):
    p = (1 + 5 ** 0.5) / 2
    v = np.array([[-1, p, 0], [1, p, 0], [-1, -p, 0], [1, -p, 0], [0, -1, p], [0, 1, p], [0, -1, -p], [0, 1, -p],
                  [p, 0, -1], [p, 0, 1], [-p, 0, -1], [-p, 0, 1]], float)
    return v / np.linalg.norm(v[0]) * r


ICO_F = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]


def capsid_virus():
    """Ikosaedrik kapsid (adenovirus turi): kapsomerlar (bo'rtiqlar) va 12 uchidagi tolalar."""
    R, c = 1.0, np.array([0, 0, 1.6])
    v = icosa_vertices(R)
    out = [prim(flat(v + c, ICO_F, c), (0.55, 0.78, 0.45, 1), "kapsid", 0.5)]
    caps = []
    for f in ICO_F:                                          # har yoqda 6 ta kapsomer
        a, b, d = v[list(f)]
        for (u, w) in [(1 / 3, 1 / 3), (0.6, 0.2), (0.2, 0.6), (0.2, 0.2), (0.45, 0.45), (0.15, 0.7)]:
            p = a + (b - a) * u + (d - a) * w
            n = p / np.linalg.norm(p)
            caps.append(sphere(0.085, 10, 6, centre=c + p + n * 0.02, scale=(1, 1, 0.6)))
    out.append(prim(caps, (0.35, 0.62, 0.30, 1), "kapsomerlar", 0.5))
    fibers = []
    for p in v:
        n = p / np.linalg.norm(p)
        fibers += [tube(c + p, c + p + n * 0.55, 0.025, 8), ball(c + p + n * 0.58, 0.07, 12)]
    out.append(prim(fibers, (0.85, 0.45, 0.25, 1), "tolalar", 0.4))
    return out


def coronavirus():
    R, c = 1.0, np.array([0, 0, 1.6])
    rng = np.random.default_rng(5)
    out = [prim([sphere(R, 64, 32, centre=c)], (0.78, 0.80, 0.86, 1), "qobiq", 0.6)]
    n = 70
    gold = np.pi * (3 - 5 ** 0.5)
    spikes, m_prot = [], []
    for i in range(n):                                       # spiral bo'yicha tekis taqsimot
        z = 1 - 2 * (i + 0.5) / n
        r = np.sqrt(1 - z * z)
        d = np.array([r * np.cos(gold * i), r * np.sin(gold * i), z])
        base = c + d * R
        spikes += [tube(base, base + d * 0.32, 0.03, 8), sphere(0.11, 14, 8, centre=base + d * 0.38, scale=(1, 1, 1))]
    for i in range(40):
        d = rng.normal(size=3); d /= np.linalg.norm(d)
        m_prot.append(ball(c + d * R * 1.005, 0.06, 10))
    return out + [prim(spikes, (0.88, 0.25, 0.22, 1), "S_oqsil_tikanlari", 0.4), prim(m_prot, (0.98, 0.70, 0.20, 1), "membrana_oqsillari", 0.4)]


def phage():
    head_c = np.array([0, 0, 2.55])
    v = icosa_vertices(0.5) * [1, 1, 1.35]
    out = [prim(flat(v + head_c, ICO_F, head_c), (0.55, 0.62, 0.92, 1), "bosh", 0.45),
           prim([lathe([(0.16, 1.88), (0.2, 1.92), (0.2, 1.98), (0.12, 2.0)])], (0.40, 0.45, 0.70, 1), "bo'yin", 0.5)]
    tail = cylinder(0.11, [0, 0, 0.75], [0, 0, 1.9], 32)
    rings = [m for z in np.linspace(0.8, 1.85, 12) for m in cylinder(0.135, [0, 0, z], [0, 0, z + 0.04], 32)]
    plate = cylinder(0.32, [0, 0, 0.66], [0, 0, 0.76], 6)
    out += [prim(tail, (0.62, 0.66, 0.78, 1), "dum", 0.5), prim(rings, (0.45, 0.50, 0.65, 1), "dum_halqalari", 0.5),
            prim(plate, (0.40, 0.45, 0.70, 1), "tayanch_plastinka", 0.5)]
    legs = []
    for k in range(6):
        a = np.radians(60 * k)
        p0 = np.array([0.3 * np.cos(a), 0.3 * np.sin(a), 0.7])
        p1 = np.array([0.85 * np.cos(a), 0.85 * np.sin(a), 0.55])
        p2 = np.array([1.05 * np.cos(a), 1.05 * np.sin(a), 0.0])
        legs += [tube(p0, p1, 0.03, 8), tube(p1, p2, 0.03, 8), ball(p1, 0.045, 8)]
    return out + [prim(legs, (0.85, 0.50, 0.25, 1), "dum_tolalari", 0.4)]


# ───────── hujayralar (kesib ochilgan)
def cut_skip(t, p):
    return p > 3 * np.pi / 2 and t < np.pi * 0.62                  # oldingi o'ng-yuqori bo'lak ochiq


def animal_cell():
    R, c = 1.4, np.array([0, 0, 1.45])
    out = [prim([sphere(R, 72, 36, centre=c, skip=cut_skip)], (0.98, 0.72, 0.72, 1), "hujayra_membranasi", 0.5),
           prim([sphere(R * 0.985, 72, 36, centre=c, skip=cut_skip)], (0.99, 0.88, 0.80, 1), "sitoplazma", 0.7)]
    out[-1] = prim([_flip(sphere(R * 0.985, 72, 36, centre=c, skip=cut_skip))], (0.99, 0.88, 0.80, 1), "sitoplazma", 0.7)
    nuc_c = c + [0.25, -0.2, 0.1]
    out += [prim([sphere(0.48, 48, 24, centre=nuc_c, skip=lambda t, p: p > 3 * np.pi / 2 and t < np.pi * 0.55)],
                 (0.55, 0.35, 0.80, 1), "yadro", 0.45),
            prim([sphere(0.2, 24, 12, centre=nuc_c + [0.08, -0.08, 0.05])], (0.35, 0.18, 0.55, 1), "yadrocha", 0.45)]
    mito = [sphere(0.11, 20, 10, centre=c + p, scale=(2.2, 1, 1)) for p in [[-0.6, -0.4, -0.3], [-0.2, 0.6, -0.5], [0.7, 0.4, -0.4], [-0.7, 0.2, 0.4]]]
    out.append(prim(mito, (0.95, 0.55, 0.25, 1), "mitoxondriyalar", 0.4))
    golgi = [m for k in range(4) for m in [sphere(0.28 - 0.03 * k, 24, 6, centre=c + [-0.55, -0.35, 0.05 + 0.07 * k], scale=(1, 0.45, 0.12))]]
    out.append(prim(golgi, (0.98, 0.80, 0.25, 1), "golji_apparati", 0.45))
    er = [tube_path([nuc_c + (0.62 + 0.05 * np.sin(6 * a)) * np.array([np.cos(a), np.sin(a), 0.15 * k]) for a in np.linspace(0.3, 3.6, 60)], 0.035, 8)
          for k in (-1, 0, 1)]
    out.append(prim(er, (0.35, 0.60, 0.95, 1), "endoplazmatik_tur", 0.45))
    rng = np.random.default_rng(2)
    pts = rng.normal(size=(400, 3)) * 0.55
    pts = pts[np.linalg.norm(pts, axis=1) < R * 0.85][:120]          # faqat hujayra ichida
    rib = [ball(c + p, 0.025, 6) for p in pts]
    out.append(prim(rib, (0.45, 0.25, 0.55, 1), "ribosomalar", 0.5))
    lyso = [ball(c + p, 0.08, 12) for p in [[0.5, 0.7, 0.3], [-0.3, -0.7, 0.5], [0.2, 0.7, -0.6]]]
    out.append(prim(lyso, (0.30, 0.72, 0.45, 1), "lizosomalar", 0.45))
    return out


def _flip(mesh):
    p, n, i = mesh
    return p, -n, np.asarray(i).reshape(-1, 3)[:, ::-1].reshape(-1)


def plant_cell():
    W, D, H = 2.6, 1.6, 1.6
    c = np.array([0, 0, H / 2])
    wall = cuboid(W, D, H, centre=c)
    # yuqori old chorak ochiq: devor yoqlarini qirqish o'rniga — ochiq qutini 5 ta plastinkadan
    t = 0.08
    plates = [cuboid(W, D, t, centre=(0, 0, t / 2)), cuboid(W, t, H, centre=(0, D / 2 - t / 2, H / 2)),
              cuboid(t, D, H, centre=(-W / 2 + t / 2, 0, H / 2)), cuboid(t, D, H, centre=(W / 2 - t / 2, 0, H / 2)),
              cuboid(W, D / 2, t, centre=(0, D / 4, H - t / 2)), cuboid(W / 2, t, H / 2, centre=(-W / 4, -D / 2 + t / 2, H / 4)),
              cuboid(W, t, H / 2, centre=(0, -D / 2 + t / 2, H / 4))]
    out = [prim(plates, (0.35, 0.68, 0.30, 1), "hujayra_devori", 0.6)]
    vac = sphere(0.55, 48, 24, centre=(0.1, 0.1, 0.8), scale=(1.6, 0.9, 1.0))
    out.append(prim([vac], (0.62, 0.82, 0.98, 1), "vakuola", 0.3))
    out.append(prim([sphere(0.26, 32, 16, centre=(-0.85, 0.2, 0.6))], (0.55, 0.35, 0.80, 1), "yadro", 0.45))
    chl = [sphere(0.12, 20, 10, centre=p, scale=(1.8, 1, 0.8)) for p in [[0.9, -0.3, 0.3], [-0.4, -0.45, 0.35], [0.95, 0.4, 1.2],
                                                                           [-0.9, -0.3, 1.25], [0.3, -0.5, 1.3], [1.0, -0.4, 0.95]]]
    out.append(prim(chl, (0.20, 0.62, 0.22, 1), "xloroplastlar", 0.45))
    return out


def mitochondrion():
    L, R = 1.6, 0.6
    prof = [(R * np.sin(t), -L / 2 * np.cos(t)) for t in np.linspace(0, np.pi / 2, 16)] + \
           [(R, z) for z in np.linspace(-L / 2 + 0.01, L / 2 - 0.01, 6)] + [(R * np.sin(t), L / 2 * np.cos(np.pi / 2 - t) + 0) for t in []]
    out = []
    ang_skip = lambda t, p: p > np.pi
    shell = sphere(R, 64, 32, centre=(0, 0, 1.0), skip=lambda t, p: p > np.pi, scale=(2.2, 1, 1))
    inner = sphere(R * 0.88, 64, 32, centre=(0, 0, 1.0), skip=lambda t, p: p > np.pi, scale=(2.2, 1, 1))
    out += [prim([shell, _flip(shell)], (0.95, 0.55, 0.25, 1), "tashqi_membrana", 0.45),        # ikki tomonlama
            prim([_flip(inner)], (0.99, 0.80, 0.55, 1), "matriks", 0.6)]
    cristae = []
    for k, x in enumerate(np.linspace(-0.95, 0.95, 8)):     # ichki membrana burmalari: devordan ichkariga
        zb = 0.5 * np.sqrt(max(0.0, 1 - (x / 1.3) ** 2))      # ichki membrana chegarasi (kesim tekisligida)
        side = 1 if k % 2 == 0 else -1
        pts = [[x + 0.05 * np.sin(u * 14), -0.01, 1.0 + side * (zb - u)] for u in np.linspace(0, zb * 1.25, 24)]
        cristae.append(tube_path(pts, 0.045, 8))
    out.append(prim(cristae, (0.90, 0.40, 0.20, 1), "kristalar", 0.45))
    return out


def chromosome():
    out, bands = [], []
    for side in (-1, 1):
        for arm in (-1, 1):
            a = np.array([side * 0.12, 0, 1.35])
            b = np.array([side * (0.42 if arm > 0 else 0.5), 0, 1.35 + arm * (0.95 if arm > 0 else 1.15)])
            out.append(prim(cylinder(0.17, a, b, 32), (0.55, 0.35, 0.85, 1), f"xromatida_{side}_{arm}", 0.45))
            out.append(prim([ball(b, 0.17, 20)], (0.55, 0.35, 0.85, 1), f"uch_{side}_{arm}", 0.45))
            for t in (0.3, 0.55, 0.8):
                p = a + (b - a) * t
                bands += cylinder(0.175, p, p + (b - a) / np.linalg.norm(b - a) * 0.05, 24, caps=False)
    out.append(prim(bands, (0.35, 0.18, 0.55, 1), "polosalar", 0.5))
    out.append(prim([sphere(0.2, 24, 12, centre=(0, 0, 1.35), scale=(1.4, 0.8, 0.7))], (0.98, 0.70, 0.20, 1), "sentromera", 0.45))
    return out


def mitosis():
    out = []
    for k, phase in enumerate(["profaza", "metafaza", "anafaza", "telofaza"]):
        cx = (k - 1.5) * 1.55
        c = np.array([cx, 0, 0.75])
        cell = [sphere(0.62, 40, 20, centre=c, scale=(1, 0.35, 1))] if phase != "telofaza" else \
            [sphere(0.5, 40, 20, centre=c + [0, 0, 0.36], scale=(1.1, 0.35, 0.72)), sphere(0.5, 40, 20, centre=c - [0, 0, 0.36], scale=(1.1, 0.35, 0.72))]
        out.append(prim(cell, (0.98, 0.86, 0.78, 1), f"hujayra_{phase}", 0.6))
        chroms, spindle = [], []
        if phase == "profaza":
            for p in [[-0.2, 0.1], [0.15, -0.15], [0.05, 0.25], [-0.15, -0.25]]:
                chroms += [tube(c + [p[0], -0.23, p[1] - 0.08], c + [p[0] + 0.05, -0.23, p[1] + 0.1], 0.045, 8)]
        elif phase == "metafaza":
            for x in (-0.3, -0.1, 0.1, 0.3):
                chroms += [tube(c + [x, -0.23, -0.1], c + [x, -0.23, 0.1], 0.05, 8)]
                spindle += [tube(c + [0, -0.22, 0.55], c + [x, -0.22, 0.05], 0.012, 6), tube(c + [0, -0.22, -0.55], c + [x, -0.22, -0.05], 0.012, 6)]
        elif phase == "anafaza":
            for x in (-0.25, -0.08, 0.08, 0.25):
                chroms += [tube(c + [x, -0.23, 0.25], c + [x * 0.8, -0.23, 0.42], 0.045, 8), tube(c + [x, -0.23, -0.25], c + [x * 0.8, -0.23, -0.42], 0.045, 8)]
                spindle += [tube(c + [0, -0.22, 0.55], c + [x * 0.8, -0.22, 0.42], 0.012, 6), tube(c + [0, -0.22, -0.55], c + [x * 0.8, -0.22, -0.42], 0.012, 6)]
        else:
            for z in (0.36, -0.36):
                chroms += [sphere(0.18, 20, 10, centre=c + [0, -0.12, z], scale=(1, 0.5, 1))]
        if chroms:
            out.append(prim(chroms, (0.55, 0.30, 0.85, 1), f"xromosomalar_{phase}", 0.45))
        if spindle:
            out.append(prim(spindle, (0.35, 0.55, 0.85, 1), f"urchuq_{phase}", 0.5))
    return out


def membrane():
    out, heads, tails, prots = [], [], [], []
    n, s = 14, 0.22
    for i in range(n):
        for j in range(6):
            x, y = (i - n / 2) * s, (j - 3) * s
            for up in (1, -1):
                zc = 1.0 + up * 0.55
                heads.append(ball([x, y, zc], 0.1, 10))
                tails += [tube([x - 0.03, y, zc - up * 0.08], [x - 0.03, y, 1.0 + up * 0.05], 0.022, 6),
                          tube([x + 0.03, y, zc - up * 0.08], [x + 0.04, y, 1.0 + up * 0.08], 0.022, 6)]
    for x, h in ((-0.9, 1.5), (0.7, 1.7)):
        prots.append(sphere(0.32, 32, 16, centre=(x, 0.0, 1.0), scale=(1, 1, h)))
    channel = cylinder(0.24, [0.0, -0.2, 0.25], [0.0, -0.2, 1.75], 24)
    return [prim(heads, (0.25, 0.55, 0.92, 1), "fosfolipid_boshlari", 0.4), prim(tails, (0.98, 0.78, 0.30, 1), "yog'_dumlari", 0.5),
            prim(prots, (0.88, 0.35, 0.40, 1), "oqsillar", 0.45), prim(channel, (0.40, 0.72, 0.45, 1), "kanal_oqsil", 0.45)]


def entries():
    M, H = "Biologiya: molekulalar", "Biologiya: hujayra va mikroorganizmlar"
    pre = (16, -28, 0)
    return [
        ("bio_dnk_atomlar", "DNK — haqiqiy atomlar (PDB 1BNA)", "DNA, real atoms (PDB 1BNA)", FAN, M,
         ["dnk", "dna", "днк", "nukleotid", "genetika", "irsiyat"], dna_real, pre),
        ("bio_dnk_spiral", "DNK qo'sh spirali (A-T, G-C juftlari)", "DNA double helix", FAN, M,
         ["dnk", "qo'sh spiral", "двойная спираль", "komplementarlik", "azotli asoslar"], dna_helix, pre),
        ("bio_gemoglobin", "Gemoglobin (PDB 2HHB, 4 zanjir va gem)", "Hemoglobin (PDB 2HHB)", FAN, M,
         ["gemoglobin", "гемоглобин", "oqsil", "qon", "eritrotsit", "kislorod tashish"], hemoglobin, pre),
        ("bio_virus", "Virus (ikosaedrik kapsid)", "Icosahedral virus", FAN, H, ["virus", "вирус", "kapsid", "adenovirus"], capsid_virus, pre),
        ("bio_koronavirus", "Koronavirus", "Coronavirus", FAN, H, ["koronavirus", "коронавирус", "covid", "virus"], coronavirus, pre),
        ("bio_bakteriofag", "Bakteriofag", "Bacteriophage", FAN, H, ["bakteriofag", "бактериофаг", "virus", "bakteriya"], phage, pre),
        ("bio_hayvon_hujayrasi", "Hayvon hujayrasi (kesim)", "Animal cell", FAN, H,
         ["hujayra", "hayvon hujayrasi", "клетка", "organoidlar", "yadro", "mitoxondriya"], animal_cell, pre),
        ("bio_osimlik_hujayrasi", "O'simlik hujayrasi (kesim)", "Plant cell", FAN, H,
         ["o'simlik hujayrasi", "растительная клетка", "xloroplast", "vakuola", "hujayra devori"], plant_cell, pre),
        ("bio_mitoxondriya", "Mitoxondriya (kesim)", "Mitochondrion", FAN, H, ["mitoxondriya", "митохондрия", "kristalar", "energiya"], mitochondrion, pre),
        ("bio_xromosoma", "Xromosoma", "Chromosome", FAN, H, ["xromosoma", "хромосома", "xromatida", "sentromera"], chromosome, pre),
        ("bio_mitoz", "Mitoz bosqichlari", "Mitosis phases", FAN, H,
         ["mitoz", "митоз", "profaza", "metafaza", "anafaza", "telofaza", "hujayra bo'linishi"], mitosis, (10, 0, 0)),
        ("bio_membrana", "Hujayra membranasi (fosfolipid qo'sh qavati)", "Cell membrane", FAN, H,
         ["membrana", "мембрана", "fosfolipid", "qo'sh qavat", "kanal oqsil"], membrane, pre),
    ]


LICENSES = {"bio_dnk_atomlar": ("CC0", "ma'lumot: PDB 1BNA", "atom koordinatalari: Protein Data Bank 1BNA (wwPDB, CC0)"),
            "bio_gemoglobin": ("CC0", "ma'lumot: PDB 2HHB", "atom koordinatalari: Protein Data Bank 2HHB (wwPDB, CC0)")}
