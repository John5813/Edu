"""Sport: rasmiy o'lchamdagi maydonlar (futbol 105×68 m — FIFA tavsiyasi, basketbol 28×15 m — FIBA, voleybol 18×9 m — FIVB)
belgilari bilan, futbol to'pi (kesik ikosaedr: 12 beshburchak, 20 oltiburchak), shtanga."""
import numpy as np

from .asos import (TUBE, ball, cuboid, cylinder, disc, flat, prim, shade, solid, tube, tube_path, wire, edges_of)

FAN = "sport"
LINE = (0.96, 0.96, 0.90, 1)               # maydon chiziqlari (yashil/yog'och ustida ko'rinadi)


def poly(pts, z=0.012, r=0.012):
    return tube_path([[x, y, z] for x, y in pts], r, 6)


def circle(cx, cy, rad, a0=0.0, a1=2 * np.pi, n=64, z=0.012, r=0.012):
    return tube_path([[cx + rad * np.cos(a), cy + rad * np.sin(a), z] for a in np.linspace(a0, a1, n)], r, 6)


def rect(x0, y0, x1, y1, **kw):
    return poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], **kw)


def football_pitch():
    s = 3.4 / 105                                            # 105 m → 3.4 birlik
    L, W = 105 * s, 68 * s
    stripes = []
    for k in range(10):
        x0 = -L / 2 + k * L / 10
        stripes.append(((x0, x0 + L / 10), (0.27, 0.62, 0.30, 1) if k % 2 else (0.32, 0.70, 0.34, 1)))
    out = []
    for k, ((x0, x1), col) in enumerate(stripes):
        out.append(prim([cuboid(x1 - x0, W, 0.02, centre=((x0 + x1) / 2, 0, 0.0))], col, f"maysa_{k}", 0.8))
    lines = [rect(-L / 2, -W / 2, L / 2, W / 2), poly([(0, -W / 2), (0, W / 2)]), circle(0, 0, 9.15 * s)]
    for sgn in (-1, 1):
        x = sgn * L / 2
        lines += [rect(x, -40.32 * s / 2, x - sgn * 16.5 * s, 40.32 * s / 2), rect(x, -18.32 * s / 2, x - sgn * 5.5 * s, 18.32 * s / 2)]
        a = np.arccos(5.5 / 9.15)
        cx = x - sgn * 11 * s
        lines.append(circle(cx, 0, 9.15 * s, (np.pi - a) if sgn > 0 else -a, (np.pi + a) if sgn > 0 else a, 24))
    out.append(prim(lines, LINE, "chiziqlar", 0.5))
    goals = []
    for sgn in (-1, 1):
        x = sgn * L / 2
        gw, gh = 7.32 * s, 2.44 * s * 1.6
        goals += [tube([x, -gw / 2, 0], [x, -gw / 2, gh], 0.02, 8), tube([x, gw / 2, 0], [x, gw / 2, gh], 0.02, 8),
                  tube([x, -gw / 2, gh], [x, gw / 2, gh], 0.02, 8)]
    out.append(prim(goals, (0.92, 0.92, 0.88, 1), "darvozalar", 0.4))
    return out


def basketball_court():
    s = 3.4 / 28
    L, W = 28 * s, 15 * s
    out = [prim([cuboid(L + 0.2, W + 0.2, 0.03, centre=(0, 0, -0.005))], (0.80, 0.58, 0.34, 1), "parket", 0.6)]
    lines = [rect(-L / 2, -W / 2, L / 2, W / 2), poly([(0, -W / 2), (0, W / 2)]), circle(0, 0, 1.8 * s)]
    for sgn in (-1, 1):
        x = sgn * L / 2
        lines += [rect(x, -4.9 * s / 2, x - sgn * 5.8 * s, 4.9 * s / 2), circle(x - sgn * 5.8 * s, 0, 1.8 * s)]
        hx = x - sgn * 1.575 * s
        lines.append(circle(hx, 0, 6.75 * s, (np.pi / 2 if sgn > 0 else -np.pi / 2) + 0.15, (3 * np.pi / 2 if sgn > 0 else np.pi / 2) - 0.15, 48))
    out.append(prim(lines, (0.95, 0.95, 0.92, 1), "chiziqlar", 0.5))
    hoops = []
    for sgn in (-1, 1):
        x = sgn * L / 2
        hoops += [tube([x + sgn * 0.12, 0, 0], [x + sgn * 0.12, 0, 0.55], 0.03, 8), tube([x + sgn * 0.12, 0, 0.55], [x - sgn * 0.05, 0, 0.55], 0.025, 8)]
    out.append(prim(hoops, (0.35, 0.38, 0.45, 1), "ustunlar", 0.4))
    boards = [cuboid(0.02, 1.8 * s, 1.05 * s, centre=(sgn * (L / 2 - 0.05), 0, 0.6)) for sgn in (-1, 1)]
    out.append(prim(boards, (0.85, 0.90, 0.96, 1), "shitlar", 0.3))
    rings = [circle(sgn * (L / 2 - 0.05 - 0.23 * s * 1.2), 0, 0.23 * s * 1.2, n=32, z=0.5, r=0.012) for sgn in (-1, 1)]
    out.append(prim(rings, (0.95, 0.45, 0.15, 1), "halqalar", 0.4))
    return out


def volleyball_court():
    s = 3.0 / 18
    L, W = 18 * s, 9 * s
    out = [prim([cuboid(L + 0.5, W + 0.5, 0.03, centre=(0, 0, -0.005))], (0.30, 0.55, 0.85, 1), "atrof", 0.6),
           prim([cuboid(L, W, 0.031, centre=(0, 0, -0.004))], (0.95, 0.60, 0.30, 1), "maydon", 0.6)]
    lines = [rect(-L / 2, -W / 2, L / 2, W / 2), poly([(-3 * s, -W / 2), (-3 * s, W / 2)]), poly([(3 * s, -W / 2), (3 * s, W / 2)])]
    out.append(prim(lines, LINE, "chiziqlar", 0.5))
    h = 2.43 * s * 1.3
    net = [tube([0, -W / 2 - 0.1, 0], [0, -W / 2 - 0.1, h], 0.025, 8), tube([0, W / 2 + 0.1, 0], [0, W / 2 + 0.1, h], 0.025, 8)]
    mesh = [tube([0, y, h - 0.25], [0, y, h], 0.004, 4) for y in np.linspace(-W / 2, W / 2, 30)]
    mesh += [tube([0, -W / 2, z], [0, W / 2, z], 0.004, 4) for z in np.linspace(h - 0.25, h, 6)]
    out += [prim(net, (0.35, 0.38, 0.45, 1), "ustunlar", 0.4), prim(mesh, (0.15, 0.18, 0.25, 1), "to'r", 0.5),
            prim([tube([0, -W / 2, h], [0, W / 2, h], 0.012, 6)], LINE, "to'r_tasmasi", 0.5)]
    return out


def soccer_ball():
    p = (1 + 5 ** 0.5) / 2
    ico = np.array([[-1, p, 0], [1, p, 0], [-1, -p, 0], [1, -p, 0], [0, -1, p], [0, 1, p], [0, -1, -p], [0, 1, -p],
                    [p, 0, -1], [p, 0, 1], [-p, 0, -1], [-p, 0, 1]], float)
    F = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    R, c = 1.1, np.array([0, 0, 1.15])
    def tp(a, b):
        return ico[a] + (ico[b] - ico[a]) / 3
    pents, hexes = [], []
    for v in range(12):                                     # har ikosaedr uchi — beshburchak
        nb = [b for f in F if v in f for b in f if b != v]
        nb = list(dict.fromkeys(nb))
        pts = np.array([tp(v, b) for b in nb])
        cen = pts.mean(0)
        n = cen / np.linalg.norm(cen)
        x = pts[0] - cen; x /= np.linalg.norm(x); y = np.cross(n, x)
        pts = pts[np.argsort([np.arctan2(np.dot(q - cen, y), np.dot(q - cen, x)) for q in pts])]
        pents.append(pts)
    for f in F:                                             # har ikosaedr yog'i — oltiburchak
        a, b, d = f
        hexes.append(np.array([tp(a, b), tp(b, a), tp(b, d), tp(d, b), tp(d, a), tp(a, d)]))
    def puff(poly_pts, sub=3):
        """Yoqni sharga bo'rttirish (yoq markazidan yelpig'ich, nuqtalar shar sirtiga)."""
        cen = poly_pts.mean(0)
        pos, idx = [cen / np.linalg.norm(cen) * R], []
        for k in range(len(poly_pts)):
            a, b = poly_pts[k], poly_pts[(k + 1) % len(poly_pts)]
            base = len(pos)
            ring_ = []
            for i in range(sub + 1):
                for j in range(sub + 1 - i):
                    q = cen + (a - cen) * (i / sub) + (b - cen) * (j / sub)
                    ring_.append((i, j, len(pos)))
                    pos.append(q / np.linalg.norm(q) * R)
            lut = {(i, j): ix for i, j, ix in ring_}
            for i in range(sub):
                for j in range(sub - i):
                    idx += [lut[(i, j)], lut[(i + 1, j)], lut[(i, j + 1)]]
                    if i + j + 1 < sub:
                        idx += [lut[(i + 1, j)], lut[(i + 1, j + 1)], lut[(i, j + 1)]]
        pos = np.array(pos) + c
        nor = (pos - c) / R
        return pos, nor, np.array(idx)
    seams = []
    for poly_pts in pents + hexes:
        loop = []
        for k in range(len(poly_pts)):
            a, b = poly_pts[k], poly_pts[(k + 1) % len(poly_pts)]
            for t in np.linspace(0, 1, 6):
                q = a + (b - a) * t
                loop.append(q / np.linalg.norm(q) * R * 1.004 + c)
        seams.append(tube_path(loop, 0.012, 5))
    return [prim([puff(pp) for pp in hexes], (0.93, 0.93, 0.90, 1), "oltiburchaklar", 0.45),
            prim([puff(pp) for pp in pents], (0.14, 0.16, 0.22, 1), "beshburchaklar", 0.45),
            prim(seams, (0.45, 0.47, 0.52, 1), "choklar", 0.5)]


def barbell():
    bar = cylinder(0.04, [-1.7, 0, 0.55], [1.7, 0, 0.55], 24)
    out = [prim(bar, (0.72, 0.74, 0.78, 1), "grif", 0.3)]
    plates = []
    cols = [(0.85, 0.20, 0.20, 1), (0.20, 0.45, 0.90, 1), (0.98, 0.78, 0.18, 1)]
    for sgn in (-1, 1):
        for k, (r, w) in enumerate([(0.55, 0.09), (0.45, 0.07), (0.35, 0.05)]):
            x = sgn * (0.95 + sum([0.09, 0.07, 0.05][:k]) + w / 2)
            out.append(prim(cylinder(r, [x - w / 2, 0, 0.55], [x + w / 2, 0, 0.55], 48), cols[k], f"disk_{sgn}_{k}", 0.4))
    out.append(prim([m for sgn in (-1, 1) for m in cylinder(0.07, [sgn * 0.88, 0, 0.55], [sgn * 0.93, 0, 0.55], 24)],
                    (0.50, 0.52, 0.58, 1), "qulf", 0.3))
    return out


def entries():
    M, A = "Sport: maydonlar", "Sport: anjomlar"
    return [
        ("sp_futbol_maydoni", "Futbol maydoni (105×68 m)", "Football pitch", FAN, M,
         ["futbol maydoni", "футбольное поле", "futbol", "darvoza", "jarima maydoni"], football_pitch, (38, -20, 0)),
        ("sp_basketbol_maydoni", "Basketbol maydoni (28×15 m)", "Basketball court", FAN, M,
         ["basketbol", "баскетбол", "maydon", "halqa", "uch ochkolik chiziq"], basketball_court, (38, -20, 0)),
        ("sp_voleybol_maydoni", "Voleybol maydoni (18×9 m)", "Volleyball court", FAN, M, ["voleybol", "волейбол", "to'r", "maydon"],
         volleyball_court, (30, -25, 0)),
        ("sp_futbol_topi", "Futbol to'pi (kesik ikosaedr)", "Football", FAN, A, ["futbol to'pi", "мяч", "kesik ikosaedr", "futbol"],
         soccer_ball, (18, -25, 0)),
        ("sp_shtanga", "Shtanga", "Barbell", FAN, A, ["shtanga", "штанга", "og'ir atletika", "disk"], barbell, (20, -20, 0)),
    ]
