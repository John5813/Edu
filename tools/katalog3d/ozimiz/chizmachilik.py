"""Chizmachilik: detal, uch proyeksiya tekisligi (frontal V, gorizontal H, profil W) va proyeksiyalari, kesim
(shtrixlangan), izometrik aksonometriya o'qlari."""
import numpy as np

from .asos import (HEIGHT, RADIUS, TUBE, WIRE, arrow, box, cylinder, dashed, disc, flat, lathe, plate_poly, prim,
                   shade, solid, tube, tube_path, edges_of, wire)

FAN = "chizmachilik"
PART = (0.60, 0.68, 0.80, 1)
HATCH = (0.85, 0.30, 0.25, 1)


def part_geometry(ox=0.0, oy=0.0, oz=0.0, s=1.0):
    """L-simon detal: asos 2.0×1.2×0.4 va tik devor 0.4×1.2×1.2 (o'lchamlar shartli birlikda)."""
    base = box(2.0 * s, 1.2 * s, 0.4 * s, centre=(ox + 1.0 * s, oy + 0.6 * s, oz))
    wall = box(0.4 * s, 1.2 * s, 1.2 * s, centre=(ox + 0.2 * s, oy + 0.6 * s, oz + 0.4 * s))
    return base, wall


def part(ox=0.0, oy=0.0, oz=0.0, s=1.0, name="detal"):
    base, wall = part_geometry(ox, oy, oz, s)
    out = solid(name + "_asos", PART, *base) + solid(name + "_devor", PART, *wall)
    hole_c = np.array([ox + 1.35 * s, oy + 0.6 * s, oz + 0.4 * s + 0.003])          # teshik (asosda)
    out.append(prim([disc(0.22 * s, hole_c[2], True, 48, centre=(hole_c[0], hole_c[1])),
                     ], (0.18, 0.22, 0.30, 1), name + "_teshik", 0.6))
    return out


def projections():
    """Detal uch proyeksiya tekisligining burchagida (V — orqa devor, H — pol, W — chap devor); har tekislikda
    uning proyeksiyasi (konturi) va proyeksiya nurlari. Kamera old tomondan qaraydi, shuning uchun V orqada."""
    L, D = 3.0, 2.4
    x0, z0 = 0.35, 0.35
    y1 = D - 0.35                      # detalning orqa yuzasi
    y0 = y1 - 1.2                      # old yuzasi
    out = part(x0, y0, z0, s=1.0)
    V = [[0, D, 0], [L, D, 0], [L, D, D], [0, D, D]]
    H = [[0, 0, 0], [L, 0, 0], [L, D, 0], [0, D, 0]]
    W = [[0, 0, 0], [0, D, 0], [0, D, D], [0, 0, D]]
    pl = (0.80, 0.87, 0.96, 1)
    out.append(prim([plate_poly(V, 0.01), plate_poly(H, 0.01), plate_poly(W, 0.01)], pl, "proyeksiya_tekisliklari", 0.7))
    frame = [tube_path(p + [p[0]], TUBE * 0.5, 6) for p in (V, H, W)]
    out.append(prim(frame, WIRE, "tekislik_chegaralari", 0.4))
    yv = D - 0.012
    front = [[x0, yv, z0], [x0 + 2, yv, z0], [x0 + 2, yv, z0 + 0.4], [x0 + 0.4, yv, z0 + 0.4], [x0 + 0.4, yv, z0 + 1.6], [x0, yv, z0 + 1.6], [x0, yv, z0]]
    top = [[x0, y0, 0.012], [x0 + 2, y0, 0.012], [x0 + 2, y1, 0.012], [x0, y1, 0.012], [x0, y0, 0.012]]
    top_inner = [[x0 + 0.4, y0, 0.012], [x0 + 0.4, y1, 0.012]]
    side = [[0.012, y0, z0], [0.012, y1, z0], [0.012, y1, z0 + 1.6], [0.012, y0, z0 + 1.6], [0.012, y0, z0]]
    side_inner = [[0.012, y0, z0 + 0.4], [0.012, y1, z0 + 0.4]]
    hole = [[x0 + 1.35 + 0.22 * np.cos(a), (y0 + y1) / 2 + 0.22 * np.sin(a), 0.014] for a in np.linspace(0, 2 * np.pi, 49)]
    lines = [tube_path(front, TUBE * 0.7, 6), tube_path(top, TUBE * 0.7, 6), tube_path(top_inner, TUBE * 0.7, 6),
             tube_path(side, TUBE * 0.7, 6), tube_path(side_inner, TUBE * 0.7, 6), tube_path(hole, TUBE * 0.5, 6)]
    out.append(prim(lines, (0.15, 0.30, 0.75, 1), "proyeksiyalar", 0.4))
    rays = []
    for p in ([x0 + 2, y0, z0 + 0.4], [x0 + 0.4, y0, z0 + 1.6]):
        rays += dashed(p, [p[0], yv, p[2]], TUBE * 0.4) + dashed(p, [p[0], p[1], 0.012], TUBE * 0.4) + dashed(p, [0.012, p[1], p[2]], TUBE * 0.4)
    out.append(prim(rays, HATCH, "proyeksiya_nurlari", 0.4))
    return out


def section():
    """Detal o'rtasidan (y = 0.6) kesilgan: kesim yuzasi shtrixlangan (45°)."""
    base = box(2.0, 0.6, 0.4, centre=(1.0, 0.9, 0.0))
    wall = box(0.4, 0.6, 1.2, centre=(0.2, 0.9, 0.4))
    out = solid("asos_yarmi", PART, *base) + solid("devor_yarmi", PART, *wall)
    face = [[0, 0.6, 0], [2.0, 0.6, 0], [2.0, 0.6, 0.4], [0.4, 0.6, 0.4], [0.4, 0.6, 1.6], [0, 0.6, 1.6]]
    hatch = []
    for k in np.arange(-1.6, 2.2, 0.16):                     # 45° shtrix chiziqlari, faqat kesim ichida
        pts = []
        for t in np.linspace(0, 2.2, 120):
            x, z = k + t, t
            inside = (0 <= x <= 2.0 and 0 <= z <= 0.4) or (0 <= x <= 0.4 and 0 <= z <= 1.6)
            pts.append(([x, 0.595, z], inside))
        seg = []
        for p, inside in pts:
            if inside:
                seg.append(p)
            elif len(seg) > 1:
                hatch.append(tube_path(seg, TUBE * 0.35, 6)); seg = []
            else:
                seg = []
        if len(seg) > 1:
            hatch.append(tube_path(seg, TUBE * 0.35, 6))
    out.append(prim(hatch, HATCH, "shtrix", 0.4))
    out.append(prim([tube_path(face + [face[0]], TUBE * 0.6, 6)], shade(PART, 0.35), "kesim_konturi", 0.4))
    return out


def isometric():
    """Kub koordinata boshida, o'qlar uning qirralari bo'ylab davom etadi (izometriyada o'qlar orasi 120°)."""
    v, f = box(0.9, 0.9, 0.9, centre=(0.45, 0.45, 0))
    out = solid("kub", PART, v, f)
    L = 2.6
    o = np.zeros(3)
    out += [prim(arrow(o, o + [L, 0, 0], TUBE, head=0.2), (0.90, 0.22, 0.20, 1), "o'q_x", 0.4),
            prim(arrow(o, o + [0, L, 0], TUBE, head=0.2), (0.20, 0.65, 0.30, 1), "o'q_y", 0.4),
            prim(arrow(o, o + [0, 0, L], TUBE, head=0.2), (0.15, 0.40, 0.90, 1), "o'q_z", 0.4)]
    return out


def entries():
    K = "Chizmachilik"
    pre = (22, -35, 0)
    return [
        ("cz_detal", "Detal (L-simon, teshikli)", "Machine part", FAN, K, ["detal", "деталь", "chizma", "chizmachilik"],
         lambda: part(), pre),
        ("cz_proyeksiyalar", "Uch proyeksiya tekisligi va detal proyeksiyalari", "Three projection planes", FAN, K,
         ["proyeksiya", "ortogonal proyeksiya", "frontal", "gorizontal", "profil", "проекции", "chizmachilik"], projections, (24, -40, 0)),
        ("cz_kesim", "Kesim (shtrixlangan)", "Section with hatching", FAN, K, ["kesim", "qirqim", "shtrix", "разрез", "сечение"], section, (18, -25, 0)),
        ("cz_izometriya", "Izometrik aksonometriya o'qlari", "Isometric axes", FAN, K,
         ["izometriya", "aksonometriya", "аксонометрия", "o'qlar"], isometric, (35.26, -45, 0)),
    ]
