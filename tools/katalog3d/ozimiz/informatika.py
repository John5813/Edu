"""Informatika: ma'lumot tuzilmalari (massiv, stek, navbat, ikkilik daraxt, graf), tarmoq topologiyalari (yulduz, halqa,
shina), ikkilik son (bitlar)."""
import numpy as np

from .asos import (C, HEIGHT, RADIUS, TUBE, WIRE, arrow, ball, cuboid, cylinder, prim, shade, tube, tube_path)

FAN = "informatika"
A, B = (0.25, 0.55, 0.95, 1), (0.40, 0.75, 0.98, 1)


def array_():
    cells = [cuboid(0.42, 0.42, 0.42, centre=((k - 3.5) * 0.48, 0, 0.6)) for k in range(8)]
    ticks = [cylinder(0.03, [(k - 3.5) * 0.48, -0.25, 0.25], [(k - 3.5) * 0.48, -0.25, 0.35], 12) for k in range(8)]
    return [prim(cells[::2], A, "elementlar_a", 0.45), prim(cells[1::2], B, "elementlar_b", 0.45),
            prim([m for t in ticks for m in t], WIRE, "indekslar", 0.4),
            prim(arrow([(2 - 3.5) * 0.48, 0, 1.6], [(2 - 3.5) * 0.48, 0, 0.9], TUBE * 1.2, head=0.18), HEIGHT, "murojaat", 0.35)]


def stack():
    slabs = [cuboid(1.2, 0.8, 0.22, centre=(0, 0, 0.15 + k * 0.27)) for k in range(5)]
    return [prim(slabs[::2], A, "stek_a", 0.45), prim(slabs[1::2], B, "stek_b", 0.45),
            prim(arrow([0.4, 0, 2.6], [0.4, 0, 1.6], TUBE * 1.3, head=0.2), C["yashil"], "push", 0.35),
            prim(arrow([-0.4, 0, 1.6], [-0.4, 0, 2.6], TUBE * 1.3, head=0.2), HEIGHT, "pop", 0.35)]


def queue():
    slabs = [cuboid(0.4, 0.8, 0.8, centre=((k - 2) * 0.5, 0, 0.45)) for k in range(5)]
    return [prim(slabs[::2], A, "navbat_a", 0.45), prim(slabs[1::2], B, "navbat_b", 0.45),
            prim(arrow([2.4, 0, 0.45], [1.4, 0, 0.45], TUBE * 1.3, head=0.2), C["yashil"], "kirish", 0.35),
            prim(arrow([-1.4, 0, 0.45], [-2.4, 0, 0.45], TUBE * 1.3, head=0.2), HEIGHT, "chiqish", 0.35)]


def tree():
    nodes, edges = [], []
    levels = 4
    for lv in range(levels):
        n = 2 ** lv
        for i in range(n):
            x = (i + 0.5) / n * 3.2 - 1.6
            z = 2.6 - lv * 0.75
            nodes.append(((lv, i), np.array([x, 0, z])))
    pos = dict(nodes)
    for (lv, i), p in nodes:
        if lv + 1 < levels:
            for ch in (2 * i, 2 * i + 1):
                edges.append(tube(p, pos[(lv + 1, ch)], 0.03, 8))
    cols = [C["qizil"], C["sariq_q"], C["yashil"], C["ko'k"]]
    out = [prim(edges, WIRE, "qirralar", 0.4)]
    for lv in range(levels):
        out.append(prim([ball(p, 0.16, 20) for (l, i), p in nodes if l == lv], cols[lv], f"daraja_{lv}", 0.35))
    return out


def graph():
    pts = np.array([[0, 0, 1.6], [1.2, 0.3, 2.2], [1.4, -0.4, 0.9], [-1.1, 0.4, 2.3], [-1.3, -0.3, 1.0], [0.2, 0.6, 0.5], [0.1, -0.6, 2.6]])
    E = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (3, 4), (4, 5), (2, 5), (1, 6), (3, 6), (0, 5)]
    return [prim([tube(pts[a], pts[b], 0.035, 8) for a, b in E], WIRE, "qirralar", 0.4),
            prim([ball(p, 0.17, 20) for p in pts], C["binafsha"], "uchlar", 0.35)]


def computer(c):
    c = np.asarray(c, float)
    return ([cuboid(0.5, 0.06, 0.34, centre=c + [0, 0, 0.32]), cuboid(0.08, 0.06, 0.15, centre=c + [0, 0, 0.08]),
             cuboid(0.3, 0.2, 0.03, centre=c + [0, 0, 0.015])],
            [cuboid(0.44, 0.01, 0.28, centre=c + [0, -0.035, 0.32])])


def network(kind):
    out_body, screens, cables = [], [], []
    n = 6
    if kind == "yulduz":
        hub = np.array([0, 0, 0.0])
        out_body.append(cuboid(0.6, 0.4, 0.18, centre=(0, 0, 0.09)))
        pts = [np.array([1.7 * np.cos(a), 1.7 * np.sin(a), 0]) for a in np.linspace(0, 2 * np.pi, n, endpoint=False)]
        cables = [tube(hub + [0, 0, 0.05], p + [0, 0, 0.05], 0.025, 8) for p in pts]
    elif kind == "halqa":
        pts = [np.array([1.6 * np.cos(a), 1.6 * np.sin(a), 0]) for a in np.linspace(0, 2 * np.pi, n, endpoint=False)]
        cables = [tube(pts[k] + [0, 0, 0.05], pts[(k + 1) % n] + [0, 0, 0.05], 0.025, 8) for k in range(n)]
    else:
        pts = [np.array([(k - 2) * 0.8, 0.5 * (1 if k % 2 else -1), 0]) for k in range(5)]
        bus = [tube([-2.1, 0, 0.05], [2.1, 0, 0.05], 0.04, 10)]
        cables = bus + [tube(p + [0, 0, 0.05], [p[0], 0, 0.05], 0.025, 8) for p in pts]
    for p in pts:
        b, s = computer(p)
        out_body += b
        screens += s
    return [prim(out_body, (0.62, 0.66, 0.74, 1), "kompyuterlar", 0.45), prim(screens, (0.22, 0.45, 0.90, 1), "ekranlar", 0.3),
            prim(cables, C["sariq_q"], "kabellar", 0.45)]


def binary(bits="10110010"):
    ones, zeros = [], []
    for k, b in enumerate(bits):
        x = (k - 3.5) * 0.45
        (ones if b == "1" else zeros).append(cuboid(0.38, 0.38, 0.9 if b == "1" else 0.25, centre=(x, 0, (0.9 if b == "1" else 0.25) / 2)))
    return [prim(ones, (0.20, 0.75, 0.45, 1), "bit_1", 0.4), prim(zeros, (0.55, 0.60, 0.70, 1), "bit_0", 0.5)]


def entries():
    T, N = "Informatika: ma'lumot tuzilmalari", "Informatika: tarmoqlar"
    pre = (22, -30, 0)
    return [
        ("inf_massiv", "Massiv (indeksli elementlar)", "Array", FAN, T, ["massiv", "массив", "array", "indeks"], array_, pre),
        ("inf_stek", "Stek (LIFO)", "Stack", FAN, T, ["stek", "стек", "lifo", "push", "pop"], stack, pre),
        ("inf_navbat", "Navbat (FIFO)", "Queue", FAN, T, ["navbat", "очередь", "fifo", "queue"], queue, pre),
        ("inf_daraxt", "Ikkilik daraxt", "Binary tree", FAN, T, ["daraxt", "ikkilik daraxt", "дерево", "binary tree"], tree, (10, 0, 0)),
        ("inf_graf", "Graf (uchlar va qirralar)", "Graph", FAN, T, ["graf", "граф", "uchlar", "qirralar"], graph, pre),
        ("inf_ikkilik", "Ikkilik son (bitlar: 10110010)", "Binary number", FAN, T, ["ikkilik", "bit", "bayt", "двоичная", "sanoq sistemasi"],
         binary, pre),
        ("inf_tarmoq_yulduz", "«Yulduz» tarmoq topologiyasi", "Star topology", FAN, N, ["tarmoq", "topologiya", "yulduz", "сеть", "kommutator"],
         lambda: network("yulduz"), (35, -20, 0)),
        ("inf_tarmoq_halqa", "«Halqa» tarmoq topologiyasi", "Ring topology", FAN, N, ["tarmoq", "topologiya", "halqa", "сеть"],
         lambda: network("halqa"), (35, -20, 0)),
        ("inf_tarmoq_shina", "«Shina» tarmoq topologiyasi", "Bus topology", FAN, N, ["tarmoq", "topologiya", "shina", "сеть"],
         lambda: network("shina"), (35, -20, 0)),
    ]
