"""Kimyo: molekulalar (RDKit — haqiqiy bog' uzunligi va burchaklari), kristall panjaralar, atom tuzilishi (Bor modeli),
orbitallar (formuladan), molekula shakllari (VSEPR), laboratoriya idishlari.

Atom ranglari — xalqaro CPK an'anasi, lekin har qanday fonda ko'rinadigan qilib moslangan: vodorod sof oq emas
(kumushrang), uglerod sof qora emas (to'q kulrang).
"""
import numpy as np

from .asos import (C, RADIUS, TUBE, WIRE, ball, body, cylinder, dashed, disc, lathe, lathe_smooth, merge, moved, prim,
                   ring, rot_x, shade, sphere, tube, tube_path)

FAN = "kimyo"
ATOM = {"H": ((0.80, 0.83, 0.88, 1), 0.25), "C": ((0.36, 0.38, 0.43, 1), 0.36), "O": ((0.90, 0.20, 0.18, 1), 0.34),
        "N": ((0.22, 0.42, 0.95, 1), 0.35), "Cl": ((0.25, 0.78, 0.25, 1), 0.42), "S": ((0.95, 0.80, 0.15, 1), 0.42),
        "Na": ((0.62, 0.36, 0.86, 1), 0.45), "P": ((0.98, 0.55, 0.10, 1), 0.42), "F": ((0.55, 0.88, 0.30, 1), 0.30)}
VDW = {"H": 1.10, "C": 1.70, "O": 1.52, "N": 1.55, "Cl": 1.75, "S": 1.80, "Na": 2.27, "P": 1.80, "F": 1.47}
BOND = (0.62, 0.65, 0.72, 1)                 # bog' tayoqchasi — o'rta kulrang (har qanday fonda ko'rinadi)


def _embed(smiles, seed=7):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    AllChem.EmbedMolecule(mol, params)
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
    except Exception:
        pass
    pos = mol.GetConformer().GetPositions()
    pos = pos - pos.mean(0)
    # eng uzun o'q gorizontal, molekula yerdan ko'tarilgan (z ≥ 0)
    u, s, vt = np.linalg.svd(pos - pos.mean(0))
    pos = pos @ vt.T
    pos = pos[:, [0, 2, 1]]
    pos[:, 2] -= pos[:, 2].min() - 0.4
    return mol, pos


def molecule(name, smiles, kekule=False):
    from rdkit import Chem

    mol, pos = _embed(smiles)
    if kekule:
        Chem.Kekulize(mol, clearAromaticFlags=True)
    out, bonds = [], []
    by_el = {}
    for atom in mol.GetAtoms():
        el = atom.GetSymbol()
        by_el.setdefault(el, []).append(ball(pos[atom.GetIdx()], ATOM.get(el, ATOM["C"])[1], 28))
    for el, parts in by_el.items():
        out.append(prim(parts, ATOM.get(el, ATOM["C"])[0], f"{name}_{el}", 0.35))
    for b in mol.GetBonds():
        i, j = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        a, c = pos[i], pos[j]
        order = 2 if b.GetBondType() == Chem.BondType.DOUBLE else 3 if b.GetBondType() == Chem.BondType.TRIPLE else 1
        if b.GetIsAromatic():
            order = 1
        if order == 1:
            bonds.append(tube(a, c, 0.09, 16))
            continue
        d = (c - a) / np.linalg.norm(c - a)
        # qo'sh bog' tekisligi: qo'shni atom bo'yicha
        nb = [n.GetIdx() for n in mol.GetAtomWithIdx(i).GetNeighbors() if n.GetIdx() != j]
        ref = (pos[nb[0]] - a) if nb else np.array([0, 0, 1.0])
        off = ref - np.dot(ref, d) * d
        off = off / (np.linalg.norm(off) or 1) if np.linalg.norm(off) > 1e-6 else np.cross(d, [0, 0, 1])
        gap = 0.12
        shifts = [-gap, gap] if order == 2 else [-1.6 * gap, 0, 1.6 * gap]
        for s in shifts:
            bonds.append(tube(a + off * s, c + off * s, 0.06, 12))
    if bonds:
        out.append(prim(bonds, BOND, name + "_boglar", 0.4))
    return out


def spacefill(name, smiles):
    mol, pos = _embed(smiles)
    out, by_el = [], {}
    for atom in mol.GetAtoms():
        el = atom.GetSymbol()
        by_el.setdefault(el, []).append(sphere(VDW.get(el, 1.6) * 0.55, 40, 20, centre=pos[atom.GetIdx()]))
    for el, parts in by_el.items():
        out.append(prim(parts, ATOM.get(el, ATOM["C"])[0], f"{name}_{el}", 0.35))
    return out


# ───────── kristall panjaralar
def lattice_cell(name, points, kinds, a=2.0, bonds=(), cell=True, sizes=None):
    """points — birlik katakdagi koordinatalar (0..1), kinds — atom turi (rang/o'lcham)."""
    out, by = [], {}
    for p, k in zip(points, kinds):
        col, r = kinds_style(k, sizes)
        by.setdefault(k, (col, []))[1].append(ball(np.asarray(p) * a, r, 24))
    for k, (col, parts) in by.items():
        out.append(prim(parts, col, f"{name}_{k}", 0.35))
    lines = []
    if cell:
        v = [[x * a, y * a, z * a] for z in (0, 1) for y in (0, 1) for x in (0, 1)]
        for e in [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]:
            lines += dashed(v[e[0]], v[e[1]], TUBE * 0.5, 0.1, 0.07)
    if bonds:
        out.append(prim([tube(np.asarray(p) * a, np.asarray(q) * a, 0.05, 10) for p, q in bonds], BOND, name + "_boglar", 0.4))
    if lines:
        out.append(prim(lines, WIRE, name + "_katak", 0.4))
    return out


def kinds_style(k, sizes=None):
    table = {"Na": ((0.62, 0.36, 0.86, 1), 0.22), "Cl": ((0.25, 0.78, 0.25, 1), 0.34), "C": ((0.36, 0.38, 0.43, 1), 0.16),
             "M": ((0.80, 0.62, 0.30, 1), 0.28), "M2": ((0.85, 0.45, 0.25, 1), 0.28), "Cs": ((0.55, 0.30, 0.75, 1), 0.30)}
    col, r = table[k]
    return col, (sizes or {}).get(k, r)


def nacl():
    pts, kinds = [], []
    for i in range(3):
        for j in range(3):
            for k in range(3):
                pts.append((i / 2, j / 2, k / 2))
                kinds.append("Na" if (i + j + k) % 2 == 0 else "Cl")
    bonds = [(p, q) for p in pts for q in pts if abs(np.linalg.norm(np.subtract(p, q)) - 0.5) < 1e-6 and p < q]
    return lattice_cell("nacl", pts, kinds, 2.4, bonds)


def cubic(kind):
    corners = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
    extra = {"oddiy": [], "hajm": [(0.5, 0.5, 0.5)],
             "yoq": [(0.5, 0.5, 0), (0.5, 0.5, 1), (0.5, 0, 0.5), (0.5, 1, 0.5), (0, 0.5, 0.5), (1, 0.5, 0.5)]}[kind]
    kinds = ["M"] * len(corners) + ["M2"] * len(extra)
    return lattice_cell("metall_" + kind, corners + extra, kinds, 2.2)


def diamond():
    fcc = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)] + \
          [(0.5, 0.5, 0), (0.5, 0.5, 1), (0.5, 0, 0.5), (0.5, 1, 0.5), (0, 0.5, 0.5), (1, 0.5, 0.5)]
    inner = [(0.25, 0.25, 0.25), (0.75, 0.75, 0.25), (0.75, 0.25, 0.75), (0.25, 0.75, 0.75)]
    pts = fcc + inner
    bonds = [(p, q) for p in inner for q in fcc if abs(np.linalg.norm(np.subtract(p, q)) - np.sqrt(3) / 4) < 1e-6]
    return lattice_cell("olmos", pts, ["C"] * len(pts), 2.4, bonds, sizes={"C": 0.17})


def graphite():
    out_pts, bonds = [], []
    a = 0.55
    for layer in range(3):
        z = layer * 0.9
        shift = (a * np.sqrt(3) / 2 if layer % 2 else 0.0)
        pts = []
        for i in range(-2, 3):
            for j in range(-2, 3):
                for s in (0, 1):
                    x = (i + j / 2) * a * np.sqrt(3) + shift
                    y = j * a * 1.5 + (a if s else 0)
                    if abs(x) <= 1.7 and abs(y) <= 1.6:
                        pts.append((x, y, z))
        out_pts += pts
        for p in pts:
            for q in pts:
                if p < q and abs(np.linalg.norm(np.subtract(p, q)) - a) < 1e-3:
                    bonds.append((p, q))
    parts = [ball(p, 0.13, 18) for p in out_pts]
    out = [prim(parts, ATOM["C"][0], "grafit_C", 0.35),
           prim([tube(p, q, 0.045, 8) for p, q in bonds], BOND, "grafit_boglar", 0.4)]
    inter = []
    for p in out_pts:
        if p[2] < 1.7 and abs(p[0]) < 0.6 and abs(p[1]) < 0.6:
            inter += dashed(p, (p[0], p[1], p[2] + 0.9), TUBE * 0.4, 0.08, 0.06)
    if inter:
        out.append(prim(inter, WIRE, "grafit_qatlamlar_orasi", 0.4))
    return out


# ───────── atom tuzilishi (Bor modeli)
def bohr(name, protons, neutrons, shells):
    """Bor modeli: yadro (proton — qizil, neytron — kumushrang) va elektron qobiqlari. Qobiqlar kameraga qaragan
    tekislikda (biroz turli burchaklarda) — taqdimotda aylana bo'lib ko'rinadi, chiziqqa aylanib qolmaydi."""
    rng = np.random.default_rng(protons)
    total = protons + neutrons
    rn = 0.16 * total ** (1 / 3) + 0.06
    centre = np.array([0, 0, 0.75 + 0.5 * len(shells)])
    pts = []
    while len(pts) < total:                                 # nuklonlar zich, ustma-ust tushmasdan
        v = rng.normal(size=3)
        v = v / np.linalg.norm(v) * rn * rng.random() ** (1 / 3)
        if all(np.linalg.norm(v - q) > 0.2 for q in pts) or len(pts) > total * 4:
            pts.append(v)
    out = [prim([ball(centre + p, 0.13, 16) for p in pts[:protons]], C["qizil"], name + "_proton", 0.35)]
    if neutrons:
        out.append(prim([ball(centre + p, 0.13, 16) for p in pts[protons:]], C["kumush"], name + "_neytron", 0.35))
    orbits, electrons = [], []
    for s, count in enumerate(shells):
        r = 0.75 + 0.5 * s
        a, b = np.radians([0, 14, -14, 8][s % 4]), np.radians([0, 10, -8, 14][s % 4])
        turn = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        tilt = turn @ rot_x(90 - np.degrees(b))            # qobiq kameraga qaragan, biroz og'ma
        circle = np.array([[r * np.cos(t), r * np.sin(t), 0] for t in np.linspace(0, 2 * np.pi, 121)]) @ tilt.T + centre
        orbits.append(tube_path(circle, TUBE * 0.55, 8))
        for e in range(count):
            t = 2 * np.pi * e / count + s * 0.4
            electrons.append(ball(np.array([r * np.cos(t), r * np.sin(t), 0]) @ tilt.T + centre, 0.1, 14))
    out += [prim(orbits, WIRE, name + "_qobiqlar", 0.4), prim(electrons, RADIUS, name + "_elektronlar", 0.3)]
    return out


# ───────── orbitallar: r(θ, φ) = |Y(θ, φ)| sirti, ikki faza ikki rangda
PHASE = ((0.95, 0.45, 0.20, 1), (0.25, 0.55, 0.95, 1))


def lobe_surface(f, n=96, scale=1.4):
    th = np.linspace(0, np.pi, n + 1)
    ph = np.linspace(0, 2 * np.pi, 2 * n + 1)
    t, p = np.meshgrid(th, ph, indexing="ij")
    d = np.stack([np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)], -1)
    val = f(d[..., 0], d[..., 1], d[..., 2])
    r = np.abs(val) * scale
    pos = (d * r[..., None]).reshape(-1, 3)
    sign = (val >= 0).reshape(-1)
    idx_pos, idx_neg = [], []
    w = 2 * n + 1
    for i in range(n):
        for j in range(2 * n):
            a, b = i * w + j, i * w + j + 1
            quad = [a, a + w, b, b, a + w, b + w]
            (idx_pos if sign[a] else idx_neg).extend(quad)
    gpos = pos.reshape(n + 1, w, 3)
    du = np.gradient(gpos, axis=0)
    dv = np.gradient(gpos, axis=1)
    nor = np.cross(du, dv).reshape(-1, 3)
    nor /= np.linalg.norm(nor, axis=1, keepdims=True) + 1e-9
    out_dir = np.sign(np.sum(nor * pos, 1, keepdims=True))
    nor = nor * np.where(out_dir == 0, 1, out_dir)
    lift = np.array([0, 0, scale * 1.05])
    return (pos + lift, nor, np.array(idx_pos)), (pos + lift, nor, np.array(idx_neg))


def orbital(name, f, axes=True):
    plus, minus = lobe_surface(f)
    out = []
    if len(plus[2]):
        out.append(prim(plus, PHASE[0], name + "_musbat", 0.35))
    if len(minus[2]):
        out.append(prim(minus, PHASE[1], name + "_manfiy", 0.35))
    if axes:
        c = np.array([0, 0, 1.47])
        L = 1.9
        out.append(prim([tube(c - [L, 0, 0], c + [L, 0, 0], TUBE * 0.45, 8), tube(c - [0, L, 0], c + [0, L, 0], TUBE * 0.45, 8),
                         tube(c - [0, 0, L * 0.75], c + [0, 0, L * 0.75], TUBE * 0.45, 8)], WIRE, name + "_oqlar", 0.4))
    return out


def p_set():
    out = []
    for k, (f, col) in enumerate([(lambda x, y, z: x, (0.95, 0.45, 0.20, 1)), (lambda x, y, z: y, (0.25, 0.70, 0.35, 1)),
                                  (lambda x, y, z: z, (0.25, 0.55, 0.95, 1))]):
        plus, minus = lobe_surface(f, 64)
        out += [prim(plus, col, f"p{k}_a", 0.35), prim(minus, tuple(min(1, v * 0.75 + 0.18) for v in col[:3]) + (1,), f"p{k}_b", 0.35)]
    return out


def sp3():
    dirs = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float) / np.sqrt(3)
    out = []
    for k, d in enumerate(dirs):
        f = lambda x, y, z, d=d: np.clip(x * d[0] + y * d[1] + z * d[2] + 0.35, 0, None) ** 2
        plus, _ = lobe_surface(f, 56, 1.1)
        out.append(prim(plus, PHASE[0] if k % 2 == 0 else (0.98, 0.65, 0.25, 1), f"sp3_{k}", 0.35))
    out.append(prim([ball([0, 0, 1.15], 0.18)], ATOM["C"][0], "sp3_C", 0.35))
    return out


# ───────── molekula shakllari (VSEPR)
def vsepr(name, ligands, lone=(), angle_lines=True):
    centre = np.array([0, 0, 1.4])
    out = [prim([ball(centre, 0.32, 28)], ATOM["C"][0] if not lone else ATOM["N"][0], name + "_markaz", 0.35)]
    lig, bonds, lp = [], [], []
    for d in ligands:
        p = centre + np.asarray(d, float) * 1.25
        lig.append(ball(p, 0.22, 24))
        bonds.append(tube(centre, p, 0.07, 14))
    for d in lone:                                          # bo'linmagan elektron jufti — qanot shakli
        dd = np.asarray(d, float)
        f = lambda x, y, z, dd=dd: np.clip(x * dd[0] + y * dd[1] + z * dd[2], 0, None) ** 3
        plus, _ = lobe_surface(f, 40, 0.75)
        pts = plus[0] - [0, 0, 0.75 * 1.05] + centre
        lp.append((pts, plus[1], plus[2]))
    out += [prim(lig, ATOM["H"][0] if name != "oktaedr_sf6" else ATOM["F"][0], name + "_atomlar", 0.35),
            prim(bonds, BOND, name + "_boglar", 0.4)]
    if lp:
        out.append(prim(lp, (0.55, 0.75, 1.0, 1), name + "_juft", 0.4))
    if angle_lines and len(ligands) >= 3:
        pts = [centre + np.asarray(d, float) * 1.25 for d in ligands]
        lines = []
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                if abs(np.linalg.norm(pts[i] - pts[j]) - min(np.linalg.norm(pts[a] - pts[b]) for a in range(len(pts))
                                                             for b in range(a + 1, len(pts)))) < 0.05:
                    lines += dashed(pts[i], pts[j], TUBE * 0.4, 0.09, 0.06)
        if lines:
            out.append(prim(lines, WIRE, name + "_shakl", 0.4))
    return out


TET = [[0, 0, 1], [0.943, 0, -0.333], [-0.471, 0.816, -0.333], [-0.471, -0.816, -0.333]]


# ───────── laboratoriya idishlari: shisha (och moviy) + suyuqlik (rangli) + bo'linmalar
GLASS = (0.72, 0.85, 0.94, 1)


def vessel(name, profile, level, liquid, marks=(), rim=True):
    prof = np.asarray(profile, float)
    lower = [p for p in prof if p[1] <= level]
    upper = [p for p in prof if p[1] >= level]
    r_level = float(np.interp(level, prof[:, 1], prof[:, 0]))
    lower = lower + [(r_level, level)]
    upper = [(r_level, level)] + upper
    out = [prim([lathe_smooth(upper)], GLASS, name + "_shisha", 0.15),
           prim([lathe_smooth(lower), disc(r_level * 0.98, level + 0.002, True)], liquid, name + "_suyuqlik", 0.3)]
    lines = []
    if rim:
        lines += ring(prof[-1][0], prof[-1][1], rad=TUBE * 0.7)
    for z in marks:
        r = float(np.interp(z, prof[:, 1], prof[:, 0]))
        lines.append(tube_path([[r * np.cos(a) * 1.004, r * np.sin(a) * 1.004, z]
                                for a in np.linspace(-0.5, 0.5, 12) - np.pi / 2], TUBE * 0.35, 6))
    if lines:
        out.append(prim(lines, shade(GLASS, 0.45), name + "_belgilar", 0.4))
    return out


def flask_round():
    prof = [(0.0, 0.0)] + [(1.0 * np.sin(t), 1.0 - 1.0 * np.cos(t)) for t in np.linspace(0.05, np.pi * 0.86, 40)]
    prof += [(0.28, 1.9), (0.28, 3.0), (0.33, 3.05)]
    return vessel("kolba", prof, 0.9, (0.25, 0.55, 0.95, 1))


def erlenmeyer():
    prof = [(0.0, 0.0), (1.0, 0.0), (1.05, 0.08), (0.32, 2.0), (0.32, 2.7), (0.38, 2.75)]
    return vessel("konus_kolba", prof, 0.8, (0.92, 0.35, 0.55, 1), marks=(0.4, 0.8, 1.2))


def test_tube():
    prof = [(0.0, 0.0)] + [(0.28 * np.sin(t), 0.28 - 0.28 * np.cos(t)) for t in np.linspace(0.1, np.pi / 2, 12)] + [(0.28, 2.8), (0.33, 2.85)]
    return vessel("probirka", prof, 1.2, (0.30, 0.78, 0.35, 1))


def beaker():
    prof = [(0.0, 0.0), (0.9, 0.0), (0.92, 0.04), (0.92, 1.9), (0.97, 1.95)]
    return vessel("stakan", prof, 1.1, (0.98, 0.70, 0.20, 1), marks=(0.4, 0.7, 1.0, 1.3, 1.6))


def cylinder_measure():
    base = [(0.0, 0.0), (0.7, 0.0), (0.7, 0.12), (0.28, 0.14)]
    prof = base + [(0.28, 3.0), (0.33, 3.05)]
    return vessel("menzurka", prof, 2.0, (0.35, 0.65, 0.98, 1), marks=tuple(np.arange(0.4, 2.9, 0.25)))


def funnel():
    prof = [(0.07, 0.0), (0.07, 1.0), (0.9, 2.0), (0.95, 2.05)]
    return [prim([lathe_smooth(prof)], GLASS, "voronka", 0.15), prim(ring(0.95, 2.05), shade(GLASS, 0.45), "voronka_chet", 0.4)]


def burner():
    glass = [(0.0, 0.0), (0.8, 0.0), (0.85, 0.3), (0.8, 0.8), (0.35, 1.1), (0.2, 1.3)]
    cap = [(0.2, 1.3), (0.22, 1.5), (0.0, 1.55)]
    flame = [(0.0, 1.55), (0.18, 1.8), (0.14, 2.2), (0.0, 2.7)]
    return [prim([lathe_smooth(glass)], GLASS, "spirt_lampa", 0.15),
            prim([lathe_smooth(cap)], C["kulrang"], "lampa_qopqoq", 0.5),
            prim([lathe_smooth(flame)], (0.98, 0.62, 0.15, 1), "alanga", 0.2),
            prim([lathe_smooth([(0.0, 1.6), (0.09, 1.8), (0.06, 2.05), (0.0, 2.3)])], (0.30, 0.55, 0.98, 1), "alanga_ich", 0.2)]


MOLS = [
    ("kim_suv", "Suv molekulasi (H₂O)", "Water H2O", "O", ["suv", "h2o", "вода", "water", "molekula", "kislorod", "vodorod"]),
    ("kim_co2", "Karbonat angidrid (CO₂)", "Carbon dioxide CO2", "O=C=O", ["karbonat angidrid", "co2", "углекислый газ", "molekula"]),
    ("kim_metan", "Metan (CH₄)", "Methane CH4", "C", ["metan", "ch4", "метан", "uglevodorod", "alkan"]),
    ("kim_ammiak", "Ammiak (NH₃)", "Ammonia NH3", "N", ["ammiak", "nh3", "аммиак", "azot"]),
    ("kim_kislorod", "Kislorod molekulasi (O₂)", "Oxygen O2", "O=O", ["kislorod", "o2", "кислород", "oddiy modda"]),
    ("kim_azot", "Azot molekulasi (N₂)", "Nitrogen N2", "N#N", ["azot", "n2", "азот", "uch bog'"]),
    ("kim_vodorod", "Vodorod molekulasi (H₂)", "Hydrogen H2", "[H][H]", ["vodorod", "h2", "водород"]),
    ("kim_hcl", "Vodorod xlorid (HCl)", "Hydrogen chloride HCl", "Cl", ["vodorod xlorid", "hcl", "хлороводород", "kislota"]),
    ("kim_etan", "Etan (C₂H₆)", "Ethane C2H6", "CC", ["etan", "c2h6", "этан", "alkan"]),
    ("kim_eten", "Eten (etilen, C₂H₄)", "Ethene C2H4", "C=C", ["eten", "etilen", "этилен", "alken", "qo'sh bog'"]),
    ("kim_etin", "Etin (atsetilen, C₂H₂)", "Ethyne C2H2", "C#C", ["etin", "atsetilen", "ацетилен", "alkin", "uch bog'"]),
    ("kim_propan", "Propan (C₃H₈)", "Propane C3H8", "CCC", ["propan", "c3h8", "пропан", "alkan"]),
    ("kim_butan", "Butan (C₄H₁₀)", "Butane C4H10", "CCCC", ["butan", "бутан", "alkan"]),
    ("kim_metanol", "Metanol (CH₃OH)", "Methanol", "CO", ["metanol", "spirt", "метанол"]),
    ("kim_etanol", "Etanol (C₂H₅OH)", "Ethanol", "CCO", ["etanol", "etil spirti", "этанол", "spirt"]),
    ("kim_sirka", "Sirka kislota (CH₃COOH)", "Acetic acid", "CC(=O)O", ["sirka kislota", "уксусная кислота", "karbon kislota"]),
    ("kim_benzol", "Benzol (C₆H₆)", "Benzene", "c1ccccc1", ["benzol", "бензол", "aromatik", "arenlar"]),
    ("kim_glyukoza", "Glyukoza (C₆H₁₂O₆)", "Glucose", "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O", ["glyukoza", "глюкоза", "uglevod", "shakar"]),
    ("kim_siklogeksan", "Siklogeksan (C₆H₁₂)", "Cyclohexane", "C1CCCCC1", ["siklogeksan", "циклогексан", "sikloalkan"]),
    ("kim_sulfat", "Sulfat kislota (H₂SO₄)", "Sulfuric acid", "OS(=O)(=O)O", ["sulfat kislota", "h2so4", "серная кислота"]),
    ("kim_glitsin", "Glitsin (aminokislota)", "Glycine", "NCC(=O)O", ["glitsin", "aminokislota", "глицин", "oqsil"]),
    ("kim_karbamid", "Karbamid (mochevina)", "Urea", "NC(=O)N", ["karbamid", "mochevina", "мочевина", "o'g'it"]),
]


def entries():
    M, K, A, O, S, L = ("Kimyo: molekulalar", "Kimyo: kristall panjaralar", "Kimyo: atom tuzilishi", "Kimyo: orbitallar",
                        "Kimyo: molekula shakllari", "Kimyo: laboratoriya idishlari")
    pre = (22, 35, 0)
    out = [(mid, nom_uz, nom, FAN, M, kalit, (lambda n=mid, s=smi: molecule(n, s, kekule=(n == "kim_benzol"))), pre)
           for mid, nom_uz, nom, smi, kalit in MOLS]
    out += [
        ("kim_suv_tola", "Suv molekulasi (to'ldirilgan model)", "Water space-filling", FAN, M, ["suv", "h2o", "molekula", "hajmiy model"],
         lambda: spacefill("suv_tola", "O"), pre),
        ("kim_metan_tola", "Metan (to'ldirilgan model)", "Methane space-filling", FAN, M, ["metan", "molekula", "hajmiy model"],
         lambda: spacefill("metan_tola", "C"), pre),
        ("kim_etanol_tola", "Etanol (to'ldirilgan model)", "Ethanol space-filling", FAN, M, ["etanol", "spirt", "hajmiy model"],
         lambda: spacefill("etanol_tola", "CCO"), pre),
        ("kim_nacl", "Osh tuzi (NaCl) kristall panjarasi", "Sodium chloride lattice", FAN, K,
         ["osh tuzi", "nacl", "kristall panjara", "ion", "хлорид натрия", "кристаллическая решётка"], nacl, pre),
        ("kim_olmos", "Olmos kristall panjarasi", "Diamond lattice", FAN, K, ["olmos", "алмаз", "uglerod", "atom panjara"], diamond, pre),
        ("kim_grafit", "Grafit qatlamli tuzilishi", "Graphite layers", FAN, K, ["grafit", "графит", "uglerod", "allotropiya"], graphite, pre),
        ("kim_metall_oddiy", "Oddiy kub panjara", "Simple cubic lattice", FAN, K, ["kub panjara", "metall", "кубическая решётка"],
         lambda: cubic("oddiy"), pre),
        ("kim_metall_hajm", "Hajmi markazlashgan kub panjara", "Body-centred cubic", FAN, K, ["hajmi markazlashgan", "metall", "оцк", "bcc"],
         lambda: cubic("hajm"), pre),
        ("kim_metall_yoq", "Yoqlari markazlashgan kub panjara", "Face-centred cubic", FAN, K, ["yoqlari markazlashgan", "metall", "гцк", "fcc"],
         lambda: cubic("yoq"), pre),
        ("kim_atom_h", "Vodorod atomi (Bor modeli)", "Hydrogen atom (Bohr)", FAN, A, ["atom tuzilishi", "vodorod", "bor modeli", "elektron"],
         lambda: bohr("atom_h", 1, 0, [1]), pre),
        ("kim_atom_c", "Uglerod atomi (Bor modeli)", "Carbon atom (Bohr)", FAN, A, ["atom tuzilishi", "uglerod", "elektron qobiq", "строение атома"],
         lambda: bohr("atom_c", 6, 6, [2, 4]), pre),
        ("kim_atom_o", "Kislorod atomi (Bor modeli)", "Oxygen atom (Bohr)", FAN, A, ["atom tuzilishi", "kislorod", "elektron"],
         lambda: bohr("atom_o", 8, 8, [2, 6]), pre),
        ("kim_atom_na", "Natriy atomi (Bor modeli)", "Sodium atom (Bohr)", FAN, A, ["atom tuzilishi", "natriy", "elektron qobiq"],
         lambda: bohr("atom_na", 11, 12, [2, 8, 1]), pre),
        ("kim_orbital_s", "s-orbital", "s orbital", FAN, O, ["s orbital", "orbital", "орбиталь", "elektron bulut"],
         lambda: orbital("s", lambda x, y, z: np.ones_like(x) * 0.8), pre),
        ("kim_orbital_p", "p-orbitallar (pₓ, p_y, p_z)", "p orbitals", FAN, O, ["p orbital", "orbital", "p-орбитали"], p_set, pre),
        ("kim_orbital_pz", "pz-orbital (ikki faza)", "pz orbital", FAN, O, ["p orbital", "orbital", "faza"],
         lambda: orbital("pz", lambda x, y, z: z * 1.1), pre),
        ("kim_orbital_dz2", "d_z²-orbital", "dz2 orbital", FAN, O, ["d orbital", "orbital", "d-орбиталь"],
         lambda: orbital("dz2", lambda x, y, z: (3 * z * z - 1) * 0.6), pre),
        ("kim_orbital_dxy", "d_xy-orbital", "dxy orbital", FAN, O, ["d orbital", "orbital"],
         lambda: orbital("dxy", lambda x, y, z: 2.2 * x * y), pre),
        ("kim_sp3", "sp³-gibridlanish", "sp3 hybridization", FAN, O, ["gibridlanish", "sp3", "гибридизация", "uglerod"], sp3, pre),
        ("kim_vsepr_chiziqli", "Chiziqli molekula (180°)", "Linear (VSEPR)", FAN, S, ["molekula shakli", "chiziqli", "vsepr", "линейная"],
         lambda: vsepr("chiziqli", [[1, 0, 0], [-1, 0, 0]]), pre),
        ("kim_vsepr_uchburchak", "Yassi uchburchak (120°)", "Trigonal planar", FAN, S, ["molekula shakli", "uchburchak", "vsepr"],
         lambda: vsepr("uchburchak", [[np.cos(a), np.sin(a), 0] for a in np.radians([90, 210, 330])]), pre),
        ("kim_vsepr_tetraedr", "Tetraedrik molekula (109,5°)", "Tetrahedral", FAN, S, ["molekula shakli", "tetraedr", "vsepr", "тетраэдр"],
         lambda: vsepr("tetraedr", TET), pre),
        ("kim_vsepr_piramida", "Piramidal molekula (NH₃, 107°)", "Trigonal pyramidal", FAN, S, ["molekula shakli", "piramida", "ammiak"],
         lambda: vsepr("piramidal", TET[1:], lone=[TET[0]]), pre),
        ("kim_vsepr_burchakli", "Burchakli molekula (H₂O, 104,5°)", "Bent", FAN, S, ["molekula shakli", "burchakli", "suv"],
         lambda: vsepr("burchakli", TET[2:], lone=TET[:2]), pre),
        ("kim_vsepr_bipiramida", "Trigonal bipiramida (PCl₅)", "Trigonal bipyramidal", FAN, S, ["molekula shakli", "bipiramida", "vsepr"],
         lambda: vsepr("bipiramida", [[0, 0, 1], [0, 0, -1]] + [[np.cos(a), np.sin(a), 0] for a in np.radians([0, 120, 240])]), pre),
        ("kim_vsepr_oktaedr", "Oktaedrik molekula (SF₆)", "Octahedral", FAN, S, ["molekula shakli", "oktaedr", "sf6", "vsepr"],
         lambda: vsepr("oktaedr_sf6", [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]), pre),
        ("kim_kolba", "Yumaloq tubli kolba", "Round-bottom flask", FAN, L, ["kolba", "laboratoriya", "колба", "idish"], flask_round, pre),
        ("kim_konus_kolba", "Konussimon kolba", "Erlenmeyer flask", FAN, L, ["kolba", "konussimon", "коническая колба", "laboratoriya"], erlenmeyer, pre),
        ("kim_probirka", "Probirka", "Test tube", FAN, L, ["probirka", "пробирка", "laboratoriya"], test_tube, pre),
        ("kim_stakan", "Kimyoviy stakan", "Beaker", FAN, L, ["kimyoviy stakan", "стакан", "laboratoriya"], beaker, pre),
        ("kim_menzurka", "Menzurka (o'lchov silindri)", "Graduated cylinder", FAN, L, ["menzurka", "мензурка", "hajm o'lchash"],
         cylinder_measure, pre),
        ("kim_voronka", "Voronka", "Funnel", FAN, L, ["voronka", "воронка", "filtrlash"], funnel, pre),
        ("kim_spirt_lampa", "Spirt lampasi", "Spirit lamp", FAN, L, ["spirt lampasi", "спиртовка", "qizdirish"], burner, pre),
    ]
    return out
