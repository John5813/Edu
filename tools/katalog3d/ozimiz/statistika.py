"""Statistika: 3D ustunli, doiraviy va chiziqli diagrammalar (namuna qiymatlar bilan; taqdimotda raqamlar matnda)."""
import numpy as np

from .asos import (C, TUBE, WIRE, ball, cuboid, disc, lathe, moved, plate_poly, prim, tube, tube_path)

FAN = "statistika"
PAL = [C["ko'k"], C["sariq_q"], C["yashil"], C["pushti"], C["binafsha"], C["feruza"]]


def axes_grid(w=3.2, d=1.2, h=2.0, n=5):
    base = cuboid(w, d, 0.05, centre=(0, 0, 0.025))
    lines = [tube([-w / 2, d / 2, 0.05 + h * k / n], [w / 2, d / 2, 0.05 + h * k / n], TUBE * 0.35, 6) for k in range(n + 1)]
    lines.append(tube([-w / 2, d / 2, 0.05], [-w / 2, d / 2, 0.05 + h], TUBE * 0.5, 6))
    return [prim([base], (0.80, 0.83, 0.88, 1), "asos", 0.6), prim(lines, WIRE, "to'r", 0.4)]


def bars(values=(0.55, 0.85, 0.65, 1.0, 0.75)):
    out = axes_grid()
    for k, v in enumerate(values):
        x = (k - (len(values) - 1) / 2) * 0.6
        out.append(prim([cuboid(0.42, 0.42, 1.9 * v, centre=(x, 0, 0.05 + 0.95 * v))], PAL[k % len(PAL)], f"ustun_{k}", 0.45))
    return out


def pie(values=(0.38, 0.27, 0.2, 0.15)):
    out, start = [], 0.0
    for k, v in enumerate(values):
        a0, a1 = start * 2 * np.pi, (start + v) * 2 * np.pi
        mid = (a0 + a1) / 2
        off = np.array([np.cos(mid), np.sin(mid), 0]) * (0.18 if k == 0 else 0.0)
        ang = np.linspace(a0, a1, max(4, int(64 * v)))
        r, h = 1.3, 0.35
        top = [[0, 0, h]] + [[r * np.cos(a), r * np.sin(a), h] for a in ang]
        bot = [[0, 0, 0]] + [[r * np.cos(a), r * np.sin(a), 0] for a in ang]
        parts = [plate_poly([top[0], top[i], top[i + 1]], 0.001) for i in range(1, len(top) - 1)]
        side = []
        for i in range(len(ang) - 1):
            side.append(plate_poly([bot[i + 1], bot[i + 2], top[i + 2], top[i + 1]], 0.001))
        side += [plate_poly([bot[0], bot[1], top[1], top[0]], 0.001), plate_poly([bot[0], top[0], top[-1], bot[-1]], 0.001)]
        out.append(prim(moved(parts + side, off + [0, 0, 0.3]), PAL[k], f"bo'lak_{k}", 0.45))
        start += v
    return out


def line_chart(values=(0.3, 0.55, 0.45, 0.8, 0.7, 1.0)):
    out = axes_grid(3.4, 0.6, 2.0, 5)
    pts = [np.array([(k - (len(values) - 1) / 2) * 0.62, 0, 0.05 + 1.9 * v]) for k, v in enumerate(values)]
    ribbon = []
    for a, b in zip(pts, pts[1:]):
        ribbon.append(plate_poly([a + [0, -0.12, 0], b + [0, -0.12, 0], b + [0, 0.12, 0], a + [0, 0.12, 0]], 0.04))
    out += [prim(ribbon, C["ko'k"], "chiziq", 0.4), prim([ball(p, 0.1, 18) for p in pts], C["sariq_q"], "nuqtalar", 0.35)]
    return out


def entries():
    D = "Statistika: diagrammalar"
    pre = (22, -25, 0)
    return [
        ("st_ustunli", "3D ustunli diagramma", "3D bar chart", FAN, D, ["diagramma", "ustunli", "statistika", "диаграмма", "grafik"], bars, pre),
        ("st_doiraviy", "3D doiraviy diagramma (ulushlar)", "3D pie chart", FAN, D, ["doiraviy diagramma", "ulush", "foiz", "круговая диаграмма"],
         pie, (35, -20, 0)),
        ("st_chiziqli", "3D chiziqli grafik (o'sish)", "3D line chart", FAN, D, ["grafik", "dinamika", "o'sish", "линейный график"], line_chart, pre),
    ]
