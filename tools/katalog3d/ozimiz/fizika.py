"""Fizika: mexanika (richag, blok, qiya tekislik, mayatnik, prujina, kuchlar), elektr va magnetizm (maydon chiziqlari —
dipol formulasi bo'yicha sonli integratsiya, to'g'ri tok, solenoid, elektr zanjiri), to'lqinlar (to'lqin sirti,
interferensiya), optika (linzalar, prizma va dispersiya, yorug'lik sinishi), atom yadrosi.

Kuch vektorlari darslikdagi kabi: og'irlik — qizil, tayanch reaksiyasi — yashil, ishqalanish — to'q sariq,
qo'yilgan kuch — ko'k.
"""
import numpy as np

from .asos import (C, GREEN, HEIGHT, RADIUS, SLANT, TUBE, WIRE, arrow, ball, box, cuboid, cylinder, dashed, disc, flat,
                   lathe, lathe_smooth, merge, moved, prim, prism_like, rot_y, rot_z, shade, solid, sphere, tube,
                   tube_path)

FAN = "fizika"
WOOD = (0.78, 0.56, 0.32, 1)
METAL = (0.60, 0.64, 0.70, 1)
COPPER = (0.86, 0.50, 0.24, 1)
LIGHT = (0.98, 0.88, 0.45, 1)               # «oq yorug'lik» — sof oq emas (oq fonda ko'rinsin)
RAINBOW = [(0.90, 0.15, 0.15, 1), (0.98, 0.50, 0.10, 1), (0.97, 0.85, 0.10, 1), (0.25, 0.75, 0.25, 1),
           (0.15, 0.70, 0.90, 1), (0.20, 0.30, 0.90, 1), (0.55, 0.25, 0.85, 1)]


def vec(a, b, color, name, r=TUBE * 1.3):
    return prim(arrow(a, b, r, head=0.3), color, name, 0.35)


# ───────── mexanika
def lever():
    beam = cuboid(4.2, 0.35, 0.14, centre=(0, 0, 1.05))
    fulcrum = prism_like([[-0.4, -0.3, 0], [0.4, -0.3, 0], [0, -0.3, 0.98]], [[-0.4, 0.3, 0], [0.4, 0.3, 0], [0, 0.3, 0.98]])
    w1 = cuboid(0.55, 0.4, 0.55, centre=(-1.6, 0, 1.4))
    w2 = cuboid(0.4, 0.3, 0.32, centre=(1.75, 0, 1.28))
    return (solid("tayanch", C["kulrang"], *fulcrum) +
            [prim([beam], WOOD, "richag", 0.6), prim([w1], C["ko'k"], "yuk_katta", 0.5), prim([w2], C["sariq_q"], "yuk_kichik", 0.5),
             vec([-1.6, 0, 1.1], [-1.6, 0, 0.1], HEIGHT, "kuch_1"), vec([1.75, 0, 1.1], [1.75, 0, 0.55], HEIGHT, "kuch_2"),
             prim(dashed([-1.6, -0.25, 1.15], [0, -0.25, 1.15], TUBE * 0.5) + dashed([0, -0.25, 1.15], [1.75, -0.25, 1.15], TUBE * 0.5),
                  WIRE, "elkalar", 0.4)])


def pulley():
    r = 0.55
    top = cuboid(2.0, 0.4, 0.15, centre=(0, 0, 3.0))
    hang = tube([0, 0, 2.93], [0, 0, 2.2], 0.05)
    wheel = cylinder(r, [0, -0.08, 2.0], [0, 0.08, 2.0], 64)
    rim = [tube_path([[r * np.cos(a), -0.09, 2.0 + r * np.sin(a)] for a in np.linspace(0, 2 * np.pi, 97)], TUBE * 0.7, 8)]
    rope = [tube_path([[r * np.cos(a), 0, 2.0 + r * np.sin(a)] for a in np.linspace(0, np.pi, 49)], 0.03, 8),
            tube([r, 0, 2.0], [r, 0, 0.75], 0.03, 8), tube([-r, 0, 2.0], [-r, 0, 1.0], 0.03, 8)]
    load = cuboid(0.55, 0.45, 0.5, centre=(r, 0, 0.5))
    return [prim([top], C["kulrang"], "tayanch", 0.6), prim([hang], METAL, "ilgak", 0.4),
            prim(wheel, C["ko'k"], "blok_g'ildirak", 0.45), prim(rim + [ball([0, -0.1, 2.0], 0.07)], shade(C["ko'k"]), "o'q", 0.4),
            prim(rope, WOOD, "arqon", 0.7), prim([load], C["sariq_q"], "yuk", 0.5),
            vec([-r, 0, 1.0], [-r, 0, 0.2], RADIUS, "tortish_kuchi"), vec([r, 0, 0.25], [r, 0, -0.35], HEIGHT, "og'irlik")]


def incline():
    a = np.radians(30)
    L = 3.6
    hgt = L * np.tan(a)
    wedge = prism_like([[-L / 2, -0.6, 0], [L / 2, -0.6, 0], [L / 2, -0.6, hgt]],
                       [[-L / 2, 0.6, 0], [L / 2, 0.6, 0], [L / 2, 0.6, hgt]])
    s = 0.5                                                 # jism qiya tekislik o'rtasida
    t = np.array([np.cos(a), 0, np.sin(a)])
    n = np.array([-np.sin(a), 0, np.cos(a)])
    base = np.array([-L / 2, 0, 0]) + t * (L * 0.55)
    centre = base + n * (s / 2)
    blk = cuboid(s, 0.5, s, centre=(0, 0, 0))
    rot = rot_y(-np.degrees(a))
    blk = moved([blk], centre, rot)
    return (solid("qiya_tekislik", WOOD, *wedge) +
            [prim(blk, C["ko'k"], "jism", 0.5),
             vec(centre, centre + [0, 0, -1.1], HEIGHT, "og'irlik_kuchi"),
             vec(centre, centre + n * 1.0, GREEN, "tayanch_reaksiyasi"),
             vec(centre, centre - t * 0.9, SLANT, "ishqalanish_kuchi"),
             prim(dashed([-L / 2 + 0.05, -0.62, 0.02], [-L / 2 + 1.0, -0.62, 0.02], TUBE * 0.5), WIRE, "burchak", 0.4)])


def pendulum():
    base = cuboid(1.8, 0.8, 0.12, centre=(0, 0, 0.06))
    pole = cylinder(0.06, [-0.7, 0, 0.1], [-0.7, 0, 3.0])
    arm = cylinder(0.05, [-0.75, 0, 3.0], [0.2, 0, 3.0])
    pivot = np.array([0.15, 0, 3.0])
    L = 2.1
    out = [prim([base], WOOD, "asos", 0.6), prim(pole + arm, METAL, "shtativ", 0.4)]
    pos = [pivot + L * np.array([np.sin(t), 0, -np.cos(t)]) for t in np.radians([0, 28, -28])]
    out.append(prim([tube(pivot, pos[0], 0.02, 8)], shade(METAL, 0.6), "ip", 0.5))
    out.append(prim([ball(pos[0], 0.22, 28)], C["qizil"], "yuk", 0.35))
    ghost = [tube(pivot, p, 0.012, 6) for p in pos[1:]] + [ball(p, 0.22, 20) for p in pos[1:]]
    out.append(prim(ghost, (0.96, 0.66, 0.62, 1), "chetki_holatlar", 0.5))
    arc = [pivot + L * np.array([np.sin(t), 0, -np.cos(t)]) for t in np.linspace(np.radians(-30), np.radians(30), 40)]
    out.append(prim([tube_path(arc, TUBE * 0.45, 6)], WIRE, "trayektoriya", 0.4))
    return out


def spring():
    wall = cuboid(0.15, 1.0, 1.2, centre=(-1.8, 0, 0.6))
    floor = cuboid(4.0, 1.0, 0.08, centre=(0.2, 0, -0.04))
    turns, x0, x1, r = 9, -1.72, 0.55, 0.2
    pts = [[x0 + (x1 - x0) * u, r * np.sin(2 * np.pi * turns * u), 0.5 + r * np.cos(2 * np.pi * turns * u)]
           for u in np.linspace(0, 1, 400)]
    blk = cuboid(0.7, 0.7, 0.7, centre=(0.9, 0, 0.35))
    return [prim([wall, floor], C["kulrang"], "devor", 0.6), prim([tube_path(pts, 0.035, 8)], METAL, "prujina", 0.3),
            prim([blk], C["ko'k"], "jism", 0.5), vec([1.25, 0, 0.5], [2.1, 0, 0.5], RADIUS, "kuch")]


def forces():
    blk = cuboid(1.0, 1.0, 1.0, centre=(0, 0, 0.5))
    floor = cuboid(3.6, 1.6, 0.08, centre=(0, 0, -0.04))
    c = np.array([0, 0, 0.5])
    return [prim([floor], C["kulrang"], "sirt", 0.6), prim([blk], C["ko'k"], "jism", 0.5),
            vec(c, c + [0, 0, -1.3], HEIGHT, "og'irlik"), vec(c + [0, 0, 0.5], c + [0, 0, 1.6], GREEN, "tayanch"),
            vec(c + [0.5, 0, 0], c + [1.6, 0, 0], RADIUS, "tortish"), vec(c - [0.5, 0, 0.3], c - [1.3, 0, 0.3], SLANT, "ishqalanish")]


# ───────── elektr va magnetizm
def field_lines(charges, starts, bounds=3.2, step=0.03, max_steps=600, stop_r=0.22):
    """2D (x–z) maydon chiziqlari: E = Σ q (r − rᵢ)/|r − rᵢ|³, RK2."""
    lines = []
    for p0, sign in starts:
        p = np.array(p0, float)
        pts = [p.copy()]
        for _ in range(max_steps):
            def field(q):
                e = np.zeros(2)
                for (cx, cz), qq in charges:
                    d = q - [cx, cz]
                    e += qq * d / (np.linalg.norm(d) ** 3 + 1e-9)
                n = np.linalg.norm(e)
                return e / n if n else e
            k1 = field(p)
            k2 = field(p + sign * k1 * step / 2)
            p = p + sign * k2 * step
            pts.append(p.copy())
            if np.abs(p).max() > bounds or any(np.linalg.norm(p - [cx, cz]) < stop_r for (cx, cz), q in charges
                                                if np.sign(q) != np.sign(sign)):
                break
        if len(pts) > 5:
            lines.append(np.array(pts))
    return lines


def lines_3d(lines2d, angles=(0,), z0=1.6, r=TUBE * 0.6, arrows=True, color=WIRE, name="chiziqlar"):
    parts, heads = [], []
    for ang in angles:
        rot = np.array([[1, 0, 0], [0, np.cos(ang), -np.sin(ang)], [0, np.sin(ang), np.cos(ang)]])
        for ln in lines2d:
            pts = np.stack([ln[:, 0], np.zeros(len(ln)), ln[:, 1]], 1) @ rot.T + [0, 0, z0]
            parts.append(tube_path(pts, r, 8))
            if arrows and len(pts) > 20 and np.linalg.norm(pts[len(pts) // 2 + 3] - pts[len(pts) // 2 - 3]) > 1e-4:
                k = len(pts) // 2
                heads += arrow(pts[k - 3], pts[k + 3], r, head=0.16, head_r=r * 3.2)[1:]
    out = [prim(parts, color, name, 0.4)]
    if heads:
        out.append(prim(heads, shade(color, 0.7), name + "_yo'nalish", 0.4))
    return out


def bar_magnet():
    n_end, s_end = 0.9, -0.9
    mag_n = cuboid(0.9, 0.4, 0.4, centre=(0.45, 0, 1.6))
    mag_s = cuboid(0.9, 0.4, 0.4, centre=(-0.45, 0, 1.6))
    charges = [((n_end, 0.0), 1.0), ((s_end, 0.0), -1.0)]
    # N qutbdan o'qqa nisbatan qiya chiqqan chiziqlar S qutbga qaytadi (yopiq halqalar); o'q bo'yidagisi — to'g'ri chiziq
    starts = [((n_end + 0.12 * np.cos(a), 0.12 * np.sin(a)), 1) for a in np.radians([72, 92, 115, 140, 165, -72, -92, -115, -140, -165])]
    lines = field_lines(charges, starts, bounds=3.4, max_steps=1400, step=0.02)
    lines += [np.array([[x, 0.0] for x in np.linspace(0.95, 2.2, 20)]), np.array([[x, 0.0] for x in np.linspace(-2.2, -0.95, 20)])]
    return ([prim([mag_n], (0.90, 0.25, 0.22, 1), "N_qutb", 0.45), prim([mag_s], (0.22, 0.45, 0.92, 1), "S_qutb", 0.45)] +
            lines_3d(lines, angles=(0, np.pi / 3, -np.pi / 3), name="magnit_chiziqlari"))


def dipole(same=False):
    q2 = 1.0 if same else -1.0
    charges = [((-1.0, 0.0), 1.0), ((1.0, 0.0), q2)]
    starts = [((-1.0 + 0.24 * np.cos(a), 0.24 * np.sin(a)), 1) for a in np.linspace(0, 2 * np.pi, 13, endpoint=False)]
    if same:
        starts = [((x + 0.24 * np.cos(a), 0.24 * np.sin(a)), 1) for x in (-1.0, 1.0) for a in np.linspace(0, 2 * np.pi, 10, endpoint=False)]
    lines = field_lines(charges, starts, bounds=2.8)
    plus = (0.92, 0.28, 0.25, 1)
    minus = (0.22, 0.45, 0.95, 1)
    out = [prim([sphere(0.22, 32, 16, centre=(-1.0, 0, 1.6))], plus, "musbat_zaryad", 0.35),
           prim([sphere(0.22, 32, 16, centre=(1.0, 0, 1.6))], plus if same else minus, "ikkinchi_zaryad", 0.35)]
    signs = [tube([-1.12, -0.23, 1.6], [-0.88, -0.23, 1.6], 0.025, 8), tube([-1.0, -0.23, 1.48], [-1.0, -0.23, 1.72], 0.025, 8)]
    signs += [tube([0.88, -0.23, 1.6], [1.12, -0.23, 1.6], 0.025, 8)] + ([tube([1.0, -0.23, 1.48], [1.0, -0.23, 1.72], 0.025, 8)] if same else [])
    out.append(prim(signs, (0.96, 0.96, 0.92, 1), "belgilar", 0.4))
    return out + lines_3d(lines, name="kuch_chiziqlari")


def straight_current():
    plate = cuboid(2.8, 2.8, 0.06, centre=(0, 0, 1.0))
    wire_ = cylinder(0.07, [0, 0, 0], [0, 0, 2.6])
    out = [prim([plate], (0.86, 0.88, 0.92, 1), "karton", 0.7), prim(wire_, COPPER, "o'tkazgich", 0.35),
           vec([0.25, 0, 0.4], [0.25, 0, 1.2], HEIGHT, "tok_yo'nalishi")]
    circles, heads = [], []
    for r in (0.4, 0.7, 1.0, 1.3):
        pts = [[r * np.cos(a), r * np.sin(a), 1.06] for a in np.linspace(0, 2 * np.pi, 97)]
        circles.append(tube_path(pts, TUBE * 0.55, 8))
        k = 30
        heads += arrow(pts[k - 2], pts[k + 2], TUBE * 0.55, head=0.15, head_r=0.06)[1:]
    return out + [prim(circles, WIRE, "magnit_chiziqlari", 0.4), prim(heads, shade(WIRE, 0.7), "yo'nalish", 0.4)]


def solenoid():
    turns, r = 10, 0.45
    pts = [[-1.4 + 2.8 * u, r * np.sin(2 * np.pi * turns * u), 1.3 + r * np.cos(2 * np.pi * turns * u)] for u in np.linspace(0, 1, 600)]
    charges = [((1.4, 0.0), 1.0), ((-1.4, 0.0), -1.0)]
    starts = [((1.4 + 0.12 * np.cos(a), 0.12 * np.sin(a)), 1) for a in np.radians([80, 110, 140, -80, -110, -140])]
    lines = field_lines(charges, starts, bounds=3.4, max_steps=1400, step=0.02)
    inner = [np.array([[x, z * 0.5] for x in np.linspace(-1.35, 1.35, 30)]) for z in (-0.3, 0.0, 0.3)]
    return ([prim([tube_path(pts, 0.04, 8)], COPPER, "g'altak", 0.35)] +
            lines_3d(lines + inner, angles=(0, np.pi / 2), z0=1.3, name="magnit_chiziqlari"))


def circuit():
    board = cuboid(3.6, 2.4, 0.08, centre=(0, 0, 0.04))
    y = -0.6
    corners = [[-1.5, y, 0.25], [1.5, y, 0.25], [1.5, y, 1.9], [-1.5, y, 1.9]]
    wires = [tube(corners[0], [-0.5, y, 0.25], 0.035), tube([0.5, y, 0.25], corners[1], 0.035), tube(corners[1], [1.5, y, 0.75], 0.035),
             tube([1.5, y, 1.35], corners[2], 0.035), tube(corners[2], [0.45, y, 1.9], 0.035), tube([-0.45, y, 1.9], corners[3], 0.035),
             tube(corners[3], [-1.5, y, 1.35], 0.035), tube([-1.5, y, 0.85], corners[0], 0.035)]
    battery = cylinder(0.22, [-0.5, y, 0.25], [0.5, y, 0.25])
    plus_cap = cylinder(0.08, [0.5, y, 0.25], [0.6, y, 0.25])
    bulb = [sphere(0.28, 32, 16, centre=(1.5, y, 1.05))]
    base_b = cylinder(0.14, [1.5, y, 0.75], [1.5, y, 0.85])
    resistor = cylinder(0.12, [-0.45, y, 1.9], [0.45, y, 1.9])
    bands = [m for x in (-0.3, -0.12, 0.06, 0.24) for m in cylinder(0.125, [x, y, 1.9], [x + 0.06, y, 1.9], 24, caps=False)]
    sw_a, sw_b = np.array([-1.5, y, 0.85]), np.array([-1.5, y, 1.35])
    lever_ = tube(sw_a, sw_b + [0.25, 0, -0.08], 0.04)
    return [prim([board], (0.30, 0.55, 0.40, 1), "plata", 0.7), prim(wires, COPPER, "simlar", 0.35),
            prim(battery, (0.25, 0.30, 0.38, 1), "batareya", 0.4), prim(plus_cap, METAL, "batareya_musbat", 0.3),
            prim(bulb, (0.99, 0.86, 0.35, 1), "lampa", 0.2), prim(base_b, METAL, "lampa_asosi", 0.3),
            prim(resistor, (0.85, 0.75, 0.55, 1), "rezistor", 0.5), prim(bands, (0.55, 0.30, 0.15, 1), "rezistor_yo'llari", 0.5),
            prim([lever_, ball(sw_a, 0.07), ball(sw_b, 0.07)], METAL, "kalit", 0.35),
            vec([-1.2, y - 0.1, 0.55], [-0.75, y - 0.1, 0.55], HEIGHT, "tok_yo'nalishi")]


# ───────── to'lqinlar (balandlikka qarab rang — nuqta ranglari)
def wave_surface(name, f, n=110, size=3.2, amp=0.25):
    xs = np.linspace(-size / 2, size / 2, n)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    Z = f(X, Y) * amp
    pos = np.stack([X, Y, Z + 0.6], -1).reshape(-1, 3)
    dzx, dzy = np.gradient(Z, xs, xs)
    nor = np.stack([-dzx, -dzy, np.ones_like(Z)], -1).reshape(-1, 3)
    nor /= np.linalg.norm(nor, axis=1, keepdims=True)
    t = ((Z - Z.min()) / (np.ptp(Z) + 1e-9)).reshape(-1)
    low, high = np.array([20, 70, 170]), np.array([110, 215, 245])
    cols = np.column_stack([(low + (high - low) * t[:, None]).astype(np.uint8), np.full(len(t), 255, np.uint8)])
    idx = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            idx += [a, a + n, a + 1, a + 1, a + n, a + n + 1]
    return [prim((pos, nor, np.array(idx)), (1, 1, 1, 1), name, 0.25, colors=cols)]


def interference():
    s1, s2 = np.array([-0.5, -1.6]), np.array([0.5, -1.6])
    f = lambda X, Y: (np.sin(9 * np.hypot(X - s1[0], Y - s1[1])) + np.sin(9 * np.hypot(X - s2[0], Y - s2[1]))) / 2
    return wave_surface("interferensiya", f, 160, amp=0.18) + [
        prim([ball([s1[0], s1[1], 0.75], 0.08), ball([s2[0], s2[1], 0.75], 0.08)], HEIGHT, "manbalar", 0.35)]


# ───────── optika
def lens(convex=True):
    R, h = 1.2, 0.18
    if convex:
        prof = [(0.0, -h - 0.12)] + [(R * np.sin(t), -h * np.cos(t) - 0.12 * np.cos(t)) for t in np.linspace(0.05, np.pi / 2, 24)] + \
               [(R * np.sin(t), h * -np.cos(t) + 0.12 * np.cos(t) * -1 + 0.0) for t in []]
        prof = [(R * np.sin(t), -(h + 0.12) * np.cos(t)) for t in np.linspace(0, np.pi / 2, 24)] + \
               [(R * np.sin(t), (h + 0.12) * np.cos(t)) for t in np.linspace(np.pi / 2, 0, 24)]
    else:
        prof = [(0.0, -0.06)] + [(R * u, -0.06 - 0.22 * u * u) for u in np.linspace(0.05, 1, 20)] + \
               [(R * u, 0.06 + 0.22 * u * u) for u in np.linspace(1, 0.05, 20)] + [(0.0, 0.06)]
    g = lathe_smooth(prof, 72)
    rot = rot_y(90)                                         # linza o'qi — x
    glass = moved([g], [0, 0, 1.6], rot)
    out = [prim(glass, (0.62, 0.82, 0.95, 1), "linza", 0.1)]
    F = 1.8
    rays, axis = [], dashed([-3.0, 0, 1.6], [3.0, 0, 1.6], TUBE * 0.45)
    for hgt in (-0.7, 0.0, 0.7):
        a = np.array([-3.0, 0, 1.6 + hgt])
        b = np.array([0.0, 0, 1.6 + hgt])
        if convex:
            end = np.array([F, 0, 1.6]) + (np.array([F, 0, 1.6]) - b) * 0.55
        else:
            d = b - np.array([-F, 0, 1.6])
            end = b + d / np.linalg.norm(d) * 2.6
            if hgt:
                axis += dashed(b, np.array([-F, 0, 1.6]), TUBE * 0.4)
        rays += [tube(a, b, TUBE * 0.9)] + arrow(b, end, TUBE * 0.9, head=0.22)
    out += [prim(rays, SLANT, "nurlar", 0.35), prim(axis, WIRE, "bosh_optik_o'q", 0.4),
            prim([ball([F if convex else -F, 0, 1.6], 0.07)], HEIGHT, "fokus", 0.35)]
    return out


def prism_dispersion():
    tri = [[-0.8, -0.5, 0.4], [0.8, -0.5, 0.4], [0.0, -0.5, 1.8]]
    v, faces = prism_like(tri, [[x, 0.5, z] for x, _, z in tri])
    out = [prim(flat(v, faces), (0.66, 0.84, 0.95, 1), "prizma", 0.1),
           prim([tube(v[a], v[b], TUBE * 0.6) for a, b in [(0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (0, 3), (1, 4), (2, 5)]],
                shade((0.66, 0.84, 0.95, 1), 0.5), "prizma_qirralar", 0.4)]
    entry = np.array([-0.42, -0.5, 1.15])
    out.append(prim(arrow([-2.6, -0.5, 0.75], entry, TUBE * 1.4, head=0.01), LIGHT, "oq_yorug'lik", 0.3))
    exit_ = np.array([0.4, -0.5, 1.12])
    inside = [tube(entry, exit_, TUBE * 1.2)]
    out.append(prim(inside, (0.99, 0.95, 0.70, 1), "ichidagi_nur", 0.3))
    for k, col in enumerate(RAINBOW):
        ang = np.radians(-8 - 4.5 * k)
        end = exit_ + 2.4 * np.array([np.cos(ang), 0, np.sin(ang)])
        out.append(prim([tube(exit_, end, TUBE * 0.9)], col, f"rang_{k}", 0.3))
    return out


def refraction():
    water = cuboid(3.4, 1.4, 1.2, centre=(0, 0, 0.6))
    p = np.array([0, -0.72, 1.2])
    a_in = np.radians(45)
    a_out = np.arcsin(np.sin(a_in) / 1.33)
    start = p + 1.6 * np.array([-np.sin(a_in), 0, np.cos(a_in)])
    end = p + 1.25 * np.array([np.sin(a_out), 0, -np.cos(a_out)])
    return [prim([water], (0.45, 0.70, 0.95, 1), "suv", 0.2),
            prim(arrow(start, p, TUBE * 1.1, head=0.22), SLANT, "tushuvchi_nur", 0.35),
            prim(arrow(p, end, TUBE * 1.1, head=0.22), (0.95, 0.40, 0.15, 1), "singan_nur", 0.35),
            prim(dashed(p + [0, 0, 1.3], p - [0, 0, 1.1], TUBE * 0.5), WIRE, "normal", 0.4)]


def nucleus():
    rng = np.random.default_rng(3)
    pts = []
    while len(pts) < 40:
        v = rng.normal(size=3)
        v = v / np.linalg.norm(v) * 0.75 * rng.random() ** (1 / 3)
        if all(np.linalg.norm(v - q) > 0.24 for q in pts):
            pts.append(v)
    c = np.array([0, 0, 1.0])
    return [prim([ball(c + p, 0.15, 18) for p in pts[:18]], C["qizil"], "protonlar", 0.35),
            prim([ball(c + p, 0.15, 18) for p in pts[18:]], C["kumush"], "neytronlar", 0.35)]


def entries():
    M, E, T, O, A = ("Fizika: mexanika", "Fizika: elektr va magnetizm", "Fizika: to'lqinlar", "Fizika: optika", "Fizika: atom")
    pre, side = (22, 35, 0), (14, 8, 0)
    return [
        ("fiz_richag", "Richag (dastak) va muvozanat", "Lever", FAN, M, ["richag", "dastak", "рычаг", "muvozanat", "moment", "oddiy mexanizm"], lever, pre),
        ("fiz_blok", "Qo'zg'almas blok", "Fixed pulley", FAN, M, ["blok", "блок", "oddiy mexanizm", "arqon"], pulley, side),
        ("fiz_qiya_tekislik", "Qiya tekislik va kuchlar", "Inclined plane", FAN, M, ["qiya tekislik", "наклонная плоскость", "ishqalanish", "kuch"], incline, side),
        ("fiz_mayatnik", "Matematik mayatnik", "Pendulum", FAN, M, ["mayatnik", "маятник", "tebranish", "davr"], pendulum, side),
        ("fiz_prujina", "Prujina va elastiklik kuchi", "Spring", FAN, M, ["prujina", "пружина", "elastiklik", "guk qonuni"], spring, side),
        ("fiz_kuchlar", "Jismga ta'sir etuvchi kuchlar", "Forces on a body", FAN, M, ["kuch", "силы", "nyuton", "og'irlik", "ishqalanish"], forces, side),
        ("fiz_magnit", "Doimiy magnit va magnit maydon chiziqlari", "Bar magnet field", FAN, E,
         ["magnit", "magnit maydon", "магнитное поле", "qutb", "kuch chiziqlari"], bar_magnet, side),
        ("fiz_elektr_maydon", "Turli ishorali zaryadlar maydoni", "Electric dipole field", FAN, E,
         ["elektr maydon", "zaryad", "электрическое поле", "kuch chiziqlari"], lambda: dipole(False), side),
        ("fiz_bir_xil_zaryad", "Bir xil ishorali zaryadlar maydoni", "Like charges field", FAN, E,
         ["elektr maydon", "zaryad", "itarish", "kuch chiziqlari"], lambda: dipole(True), side),
        ("fiz_togri_tok", "To'g'ri tokning magnit maydoni", "Magnetic field of a wire", FAN, E,
         ["tok", "magnit maydon", "parma qoidasi", "ток", "o'tkazgich"], straight_current, pre),
        ("fiz_solenoid", "Solenoid (g'altak) magnit maydoni", "Solenoid", FAN, E, ["solenoid", "g'altak", "соленоид", "elektromagnit"], solenoid, side),
        ("fiz_zanjir", "Elektr zanjiri", "Electric circuit", FAN, E,
         ["elektr zanjiri", "электрическая цепь", "batareya", "lampa", "rezistor", "kalit", "tok"], circuit, (30, 10, 0)),
        ("fiz_tolqin", "Yassi to'lqin", "Plane wave", FAN, T, ["to'lqin", "волна", "to'lqin uzunligi", "amplituda"],
         lambda: wave_surface("tolqin", lambda X, Y: np.sin(4.2 * X)), (32, 30, 0)),
        ("fiz_doiraviy_tolqin", "Doiraviy to'lqin (suv yuzasida)", "Circular wave", FAN, T, ["to'lqin", "doiraviy", "suv yuzasi"],
         lambda: wave_surface("doiraviy_tolqin", lambda X, Y: np.sin(9 * np.hypot(X, Y)) / (1 + 1.2 * np.hypot(X, Y))), (32, 30, 0)),
        ("fiz_interferensiya", "To'lqinlar interferensiyasi", "Interference", FAN, T, ["interferensiya", "интерференция", "to'lqin", "kogerent"],
         interference, (36, 20, 0)),
        ("fiz_yiguvchi_linza", "Yig'uvchi linza va fokus", "Converging lens", FAN, O, ["linza", "yig'uvchi", "fokus", "линза", "nur"],
         lambda: lens(True), side),
        ("fiz_sochuvchi_linza", "Sochuvchi linza", "Diverging lens", FAN, O, ["linza", "sochuvchi", "mavhum fokus", "линза"], lambda: lens(False), side),
        ("fiz_prizma", "Prizmada yorug'lik dispersiyasi", "Prism dispersion", FAN, O, ["dispersiya", "prizma", "spektr", "дисперсия", "kamalak"],
         prism_dispersion, side),
        ("fiz_sinish", "Yorug'likning sinishi", "Refraction", FAN, O, ["sinish", "преломление", "nur", "sindirish ko'rsatkichi"], refraction, side),
        ("fiz_yadro", "Atom yadrosi (protonlar va neytronlar)", "Atomic nucleus", FAN, A, ["yadro", "ядро атома", "proton", "neytron"], nucleus, pre),
    ]
