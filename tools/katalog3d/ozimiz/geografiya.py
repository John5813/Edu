"""Geografiya: Yer ichki tuzilishi (haqiqiy radiuslar nisbatida), globus va koordinata to'ri, Yer o'qi va fasllar,
vulqon kesimi, tog' jinslari qatlamlari va uzilma, burmalar, hamda HAQIQIY relyef (O'zbekiston, Samarqand viloyati,
Farg'ona vodiysi).

Relyef manbasi: AWS Open Data «Terrain Tiles» (Terrarium kodlash; asosan NASA SRTM). Yuklangan balandlik to'ri
`data/katalog3d/dem/<nom>.npz` da saqlanadi (git'da) — server modelni internetsiz qayta yasaydi.
"""
import io
import os

import numpy as np

from .asos import (C, HEIGHT, SLANT, TUBE, WIRE, ball, circle_pts, cuboid, cylinder, dashed, disc, flat, lathe, merge,
                   moved, prim, rot_x, rot_y, shade, sphere, tube, tube_path)

FAN = "geografiya"
SOURCE = "Yer tasviri: NASA Blue Marble (jamoat mulki); relyef: AWS Terrain Tiles / NASA SRTM"
DEM_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                       "data", "katalog3d", "dem")
OCEAN = (0.18, 0.48, 0.85, 1)
LAYERS = [("ichki_yadro", 1221, (0.99, 0.85, 0.25, 1)), ("tashqi_yadro", 3480, (0.98, 0.55, 0.15, 1)),
          ("mantiya", 6271, (0.80, 0.30, 0.18, 1)), ("yer_qobig'i", 6371, (0.55, 0.40, 0.28, 1))]   # qobiq qalinligi bo'rttirilgan


# ───────── haqiqiy Yer (NASA Blue Marble): tuzilishi, globus, fasllar
TEX_DIR = os.path.join(os.path.dirname(DEM_DIR), "tekstura")
_TEX = {}
# Taqdimotda (kat3d: BASE_ROT y = −30°) O'rta Osiyo kameraga qarasin: tekstura uzoqligi siljishi.
LON_SHIFT = 160.0


def texture(name="yer_2048.jpg"):
    """Blue Marble'da okeanlar juda to'q (deyarli qora-ko'k): to'q fonli slaydda Yer fonga qo'shilib ketardi.
    Faqat okean piksellari yorqinroq moviyga ko'tariladi (quruqlik va muzlar o'zgarmaydi)."""
    if name not in _TEX:
        from PIL import Image
        t = np.asarray(Image.open(os.path.join(TEX_DIR, name)).convert("RGB")).astype(float)
        r, g, b = t[..., 0], t[..., 1], t[..., 2]
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        ocean = np.clip((b - np.maximum(r, g) - 4) / 20, 0, 1) * np.clip((110 - lum) / 60, 0, 1)
        target = np.array([38, 92, 176], float) + (t - t.mean((0, 1))) * 0.35      # okean tafsiloti saqlanadi
        t = t * (1 - ocean[..., None]) + target * ocean[..., None]
        _TEX[name] = np.clip(t * 1.06, 0, 255)
    return _TEX[name]


def sample(tex, lon_deg, lat_deg):
    """Bilinear namuna: tekstura ekvidistant (x — uzoqlik −180…180, y — kenglik 90…−90)."""
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


def earth_sphere(R, centre, seg=256, rings=128, skip=None, sun=None, tilt=None, lon_shift=None):
    """Haqiqiy Yer (NASA Blue Marble) — tekstura zich sfera nuqtalariga «pishirilgan» (nuqta ranglari: PowerPoint ham,
    zaxira rasm chizgichi ham ko'rsatadi). sun — Quyosh yo'nalishi (kun/tun), tilt — Yer o'qi og'ishi (matritsa)."""
    pos, nor, idx = sphere(R, seg, rings, centre=(0, 0, 0), skip=skip)
    lat = np.degrees(np.arcsin(np.clip(nor[:, 2], -1, 1)))
    lon = np.degrees(np.arctan2(nor[:, 1], nor[:, 0])) + (LON_SHIFT if lon_shift is None else lon_shift)
    col = sample(texture(), lon, lat)
    if tilt is not None:
        pos, nor = pos @ tilt.T, nor @ tilt.T
    if sun is not None:
        d = np.asarray(sun, float) / np.linalg.norm(sun)
        col = col * np.clip(nor @ d * 3 + 0.6, 0.32, 1.0)[:, None]          # tun tomoni ham ko'rinsin
    cols = np.column_stack([np.clip(col, 0, 255).astype(np.uint8), np.full(len(col), 255, np.uint8)])
    return (pos + np.asarray(centre, float), nor, idx), cols


# Qatlam ranglari chuqurlik bo'yicha (nisbiy radius): ichki yadro qizigan oq-sariq → tashqi yadro to'q sariq →
# mantiya pastdan yuqoriga to'qlashadi → yer qobig'i jigarrang-kulrang.
LAYER_GRAD = [(0.00, (255, 246, 200)), (0.19, (255, 214, 80)), (0.192, (250, 160, 40)), (0.546, (230, 110, 30)),
              (0.548, (205, 85, 35)), (0.75, (170, 60, 35)), (0.94, (120, 45, 35)), (0.942, (130, 105, 80)), (1.0, (100, 85, 70))]
BOUNDS = [0.19, 0.546, 0.94]   # ichki/tashqi yadro (1221/6371, 3480/6371), mantiya/qobiq (qobiq qalinlashtirilgan)


def grad_color(t):
    ts = np.array([a for a, _ in LAYER_GRAD])
    cs = np.array([c for _, c in LAYER_GRAD], float)
    return np.stack([np.interp(t, ts, cs[:, k]) for k in range(3)], -1)


def half_disc(R, plane, n_ang=72, n_rad=60):
    """Tik kesim yuzasi (yarim doira, z bo'yicha −90°…90°), chuqurlik bo'yicha gradient rang."""
    ang = np.linspace(-np.pi / 2, np.pi / 2, n_ang)
    pos, cols = [], []
    for r in np.linspace(0, R, n_rad):
        for a in ang:
            pos.append([r * np.cos(a), 0, r * np.sin(a)] if plane == "y" else [0, -r * np.cos(a), r * np.sin(a)])
            cols.append(grad_color(r / R))
    idx = []
    for i in range(n_rad - 1):
        for j in range(n_ang - 1):
            a = i * n_ang + j
            idx += [a, a + 1, a + n_ang, a + 1, a + n_ang + 1, a + n_ang]
    nrm = [0, -1.0, 0] if plane == "y" else [1.0, 0, 0]
    cols = np.column_stack([np.array(cols).astype(np.uint8), np.full(len(cols), 255, np.uint8)])
    return (np.array(pos), np.tile(nrm, (len(pos), 1)), np.array(idx)), cols


def earth_layers():
    """Haqiqiy Yer shari, 90° li tik bo'lagi kesib olingan: kesimda ichki yadro, tashqi yadro, mantiya, yer qobig'i
    (radiuslar nisbati haqiqiy: 1221 / 3480 / 6371 km; qobiq ko'rinishi uchun qalinlashtirilgan)."""
    R = 1.3
    c = np.array([0, 0, R])
    q = np.pi / 2
    surf, cols = earth_sphere(R, c, skip=lambda t, p: p > 3 * q)
    out = [prim(surf, (1, 1, 1, 1), "yer_yuzasi", 0.55, colors=cols)]
    for plane in ("y", "x"):
        mesh, gcols = half_disc(R * 0.998, plane)
        out.append(prim((mesh[0] + c, mesh[1], mesh[2]), (1, 1, 1, 1), f"kesim_{plane}", 0.6, colors=gcols))
    lines = []
    for b in BOUNDS:
        for plane in ("y", "x"):
            arc = [c + ([b * R * np.cos(a), -0.012, b * R * np.sin(a)] if plane == "y" else [0.012, -b * R * np.cos(a), b * R * np.sin(a)])
                   for a in np.linspace(-np.pi / 2, np.pi / 2, 60)]
            lines.append(tube_path(arc, TUBE * 0.35, 6))
    out.append(prim(lines, (0.30, 0.18, 0.12, 1), "qatlam_chegaralari", 0.5))
    return out


def globe():
    """Maktab globusi: haqiqiy Yer, koordinata to'ri, ekvator, tropiklar, qutb doiralari, o'q, meridian halqa, tagkursi."""
    R = 1.2
    tilt = rot_y(23.4)
    c = np.array([0, 0, 1.6])
    surf, cols = earth_sphere(R, c, tilt=tilt)
    out = [prim(surf, (1, 1, 1, 1), "yer", 0.5, colors=cols)]
    grid, special, tropics = [], [], []
    rr = R * 1.006
    for lat in range(-60, 90, 30):
        r = rr * np.cos(np.radians(lat))
        pts = circle_pts(r, (0, 0, rr * np.sin(np.radians(lat))), (0, 0, 1), 129) @ tilt.T + c
        (special if lat == 0 else grid).append(tube_path(pts, TUBE * (0.6 if lat == 0 else 0.28), 6))
    for lon in range(0, 180, 30):
        a = np.radians(lon)
        grid.append(tube_path(circle_pts(rr, (0, 0, 0), (-np.sin(a), np.cos(a), 0), 129) @ tilt.T + c, TUBE * 0.28, 6))
    for lat in (23.44, -23.44, 66.56, -66.56):
        r = rr * np.cos(np.radians(lat))
        pts = circle_pts(r, (0, 0, rr * np.sin(np.radians(lat))), (0, 0, 1), 97) @ tilt.T + c
        tropics += [tube(pts[k], pts[k + 1], TUBE * 0.4, 6) for k in range(0, 96, 3)]
    ring_r = R * 1.12                                        # metall meridian halqa (yarim aylana)
    arc = [np.array([ring_r * np.sin(t), 0, ring_r * np.cos(t)]) @ tilt.T + c for t in np.linspace(-np.pi * 0.95, np.pi * 0.05, 90)]
    axis = [tube(np.array([0, 0, -ring_r]) @ tilt.T + c, np.array([0, 0, ring_r]) @ tilt.T + c, TUBE * 0.7)]
    stand = cylinder(0.6, [0, 0, 0], [0, 0, 0.1]) + cylinder(0.06, [0, 0, 0.1], np.array([0, 0, -ring_r]) @ tilt.T + c)
    return out + [prim(grid, (0.92, 0.92, 0.80, 1), "koordinata_to'ri", 0.4), prim(special, HEIGHT, "ekvator", 0.4),
                  prim(tropics, SLANT, "tropiklar_va_qutb_doiralari", 0.4),
                  prim([tube_path(arc, 0.05, 10)] + axis, (0.72, 0.62, 0.38, 1), "meridian_halqa", 0.3),
                  prim(stand, (0.45, 0.32, 0.22, 1), "tagkursi", 0.5)]


def seasons():
    sun = np.array([0, 0, 1.0])
    out = [prim([sphere(0.45, 48, 24, centre=sun)], (0.99, 0.78, 0.20, 1), "quyosh", 0.3)]
    orbit = np.array([[2.3 * np.cos(a), 1.7 * np.sin(a), 1.0] for a in np.linspace(0, 2 * np.pi, 145)])
    out.append(prim([tube_path(orbit, TUBE * 0.5, 8)], WIRE, "orbita", 0.4))
    tilt = rot_y(23.4)
    axes = []
    for k, a in enumerate(np.radians([0, 90, 180, 270])):
        c = np.array([2.3 * np.cos(a), 1.7 * np.sin(a), 1.0])
        mesh, cols = earth_sphere(0.26, c, seg=96, rings=48, sun=sun - c, tilt=tilt)
        out.append(prim(mesh, (1, 1, 1, 1), f"yer_{k}", 0.5, colors=cols))
        axes.append(tube(c - tilt @ [0, 0, 0.4], c + tilt @ [0, 0, 0.4], TUBE * 0.5, 8))
    out.append(prim(axes, (0.35, 0.38, 0.45, 1), "yer_o'qlari", 0.4))
    return out


# ───────── vulqon kesimi (yarmi kesib olingan)
def half_lathe(profile, seg=48):
    """Faqat orqa yarmi (y ≥ 0) — kesim tekisligi y = 0 kameraga qaraydi."""
    ang = np.linspace(0, np.pi, seg + 1)
    prof = np.asarray(profile, float)
    pos, nor, idx = [], [], []
    for k in range(len(prof) - 1):
        (r0, z0), (r1, z1) = prof[k], prof[k + 1]
        nr, nz = z1 - z0, -(r1 - r0)
        ln = np.hypot(nr, nz) or 1
        base = len(pos)
        for a in ang:
            c, s = np.cos(a), np.sin(a)
            pos += [[r0 * c, r0 * s, z0], [r1 * c, r1 * s, z1]]
            nor += [[nr / ln * c, nr / ln * s, nz / ln]] * 2
        for i in range(seg):
            a, b = base + 2 * i, base + 2 * i + 2
            idx += [a, b, a + 1, b, b + 1, a + 1]
    return np.array(pos), np.array(nor), np.array(idx)


def section_poly(profile):
    """Kesim yuzasi (y = 0 tekislik, normal −y): profil ikki tomonga ko'zgu."""
    pts = [(-r, z) for r, z in profile][::-1] + [(r, z) for r, z in profile]
    pos = np.array([[x, 0, z] for x, z in pts])
    n = len(pos)
    # markaz bo'yicha yelpig'ich (profil qavariq emas — markazdan pastgi nuqta)
    c = np.array([0, 0, min(z for _, z in pts) + 0.01])
    pos = np.vstack([c, pos])
    idx = []
    for k in range(1, n):
        idx += [0, k + 1, k]
    return pos, np.tile([0, -1.0, 0], (len(pos), 1)), np.array(idx)


def volcano():
    prof = [(1.9, 0.0), (1.4, 0.35), (0.9, 0.9), (0.45, 1.55), (0.28, 1.6), (0.18, 1.45), (0.0, 1.45)]
    rock = (0.50, 0.40, 0.33, 1)
    out = [prim([half_lathe(prof)], rock, "vulqon", 0.7),
           prim([section_poly(prof)], (0.66, 0.55, 0.45, 1), "kesim", 0.7)]
    from .asos import plate_poly
    chamber = plate_poly([[0.62 * np.cos(a), -0.015, 0.35 + 0.24 * np.sin(a)] for a in np.linspace(0, 2 * np.pi, 48, endpoint=False)], 0.01)
    vent = [tube([0, -0.03, 0.45], [0, -0.03, 1.5], 0.09, 12)]
    side = [tube([0.2, -0.03, 0.9], [0.65, -0.03, 1.08], 0.05, 10)]
    out.append(prim([chamber] + vent + side, (0.95, 0.30, 0.10, 1), "magma", 0.3))
    plume = [ball([0.05 * k, 0.0, 1.7 + 0.18 * k], 0.12 + 0.03 * k) for k in range(5)]
    out.append(prim(plume, (0.62, 0.64, 0.68, 1), "kul_buluti", 0.8))
    return out


def strata(fault=False):
    cols = [(0.93, 0.82, 0.55, 1), (0.70, 0.52, 0.35, 1), (0.82, 0.78, 0.70, 1), (0.55, 0.45, 0.40, 1), (0.40, 0.55, 0.35, 1)]
    out, h, W, D = [], 0.32, 3.0, 1.6
    for k, col in enumerate(cols[::-1]):
        z = k * h
        if not fault:
            out.append(prim([cuboid(W, D, h, centre=(0, 0, z + h / 2))], col, f"qatlam_{k}", 0.75))
            continue
        left = cuboid(W / 2, D, h, centre=(-W / 4, 0, z + h / 2))
        right = cuboid(W / 2, D, h, centre=(W / 4 + 0.02, 0, z + h / 2 - 0.42))
        out.append(prim([left, right], col, f"qatlam_{k}", 0.75))
    if fault:
        out.append(prim(arrow_pair(), HEIGHT, "siljish", 0.35))
    return out


def arrow_pair():
    from .asos import arrow
    return arrow([0.35, -0.85, 1.5], [0.35, -0.85, 1.05], TUBE * 1.1, head=0.18) + arrow([-0.35, -0.85, 1.05], [-0.35, -0.85, 1.5], TUBE * 1.1, head=0.18)


def folds():
    """Burmalar: antiklinal va sinklinal — sinusoidal qatlamlar (yon kesimi ko'rinadi)."""
    cols = [(0.93, 0.82, 0.55), (0.70, 0.52, 0.35), (0.82, 0.78, 0.70), (0.55, 0.45, 0.40), (0.40, 0.55, 0.35)]
    nx, W, D, h = 80, 3.2, 1.4, 0.26
    xs = np.linspace(-W / 2, W / 2, nx)
    wave = 0.35 * np.sin(xs * 2.2)
    out = []
    for k, col in enumerate(cols[::-1]):
        z0, z1 = 0.4 + k * h + wave, 0.4 + (k + 1) * h + wave
        if k == 0:
            z0 = np.zeros(nx)
        pos, idx = [], []
        for i in range(nx):
            for y in (-D / 2, D / 2):
                pos += [[xs[i], y, z0[i]], [xs[i], y, z1[i]]]
        def v(i, side, top):
            return i * 4 + side * 2 + top
        for i in range(nx - 1):
            a, b = i, i + 1
            idx += [v(a, 0, 1), v(b, 0, 1), v(a, 1, 1), v(b, 0, 1), v(b, 1, 1), v(a, 1, 1)]    # ust
            idx += [v(a, 0, 0), v(a, 1, 0), v(b, 0, 0), v(b, 0, 0), v(a, 1, 0), v(b, 1, 0)]    # ost
            idx += [v(a, 0, 0), v(b, 0, 0), v(a, 0, 1), v(b, 0, 0), v(b, 0, 1), v(a, 0, 1)]    # old (kesim)
            idx += [v(a, 1, 0), v(a, 1, 1), v(b, 1, 0), v(b, 1, 0), v(a, 1, 1), v(b, 1, 1)]    # orqa
        pos = np.array(pos, float)
        nor = _normals(pos, np.array(idx))
        out.append(prim((pos, nor, np.array(idx)), tuple(col) + (1,), f"burma_{k}", 0.75))
    return out


def _median3(z):
    pad = np.pad(z, 1, mode="edge")
    stack = np.stack([pad[i:i + z.shape[0], j:j + z.shape[1]] for i in range(3) for j in range(3)])
    return np.median(stack, axis=0)


def _normals(pos, idx):
    nor = np.zeros_like(pos)
    tri = idx.reshape(-1, 3)
    fn = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
    for k in range(3):
        np.add.at(nor, tri[:, k], fn)
    return nor / (np.linalg.norm(nor, axis=1, keepdims=True) + 1e-12)


# ───────── haqiqiy relyef (SRTM)
def fetch_dem(name, lon0, lon1, lat0, lat1, zoom, grid=(220, 160)):
    path = os.path.join(DEM_DIR, name + ".npz")
    if os.path.exists(path):
        d = np.load(path)
        return d["z"].astype(float), tuple(d["bbox"])
    import math
    import urllib.request

    from PIL import Image

    def tile_xy(lon, lat):
        n = 2 ** zoom
        x = (lon + 180) / 360 * n
        y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
        return x, y
    x0, y0 = tile_xy(lon0, lat1)
    x1, y1 = tile_xy(lon1, lat0)
    tiles = {}
    for tx in range(int(x0), int(x1) + 1):
        for ty in range(int(y0), int(y1) + 1):
            url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{tx}/{ty}.png"
            with urllib.request.urlopen(url, timeout=60) as r:
                im = np.asarray(Image.open(io.BytesIO(r.read())).convert("RGB")).astype(float)
            tiles[(tx, ty)] = im[..., 0] * 256 + im[..., 1] + im[..., 2] / 256 - 32768
    gw, gh = grid
    z = np.zeros((gh, gw))
    for j in range(gh):
        for i in range(gw):
            x = x0 + (x1 - x0) * i / (gw - 1)
            y = y0 + (y1 - y0) * j / (gh - 1)
            tx, ty = int(x), int(y)
            px, py = min(255, int((x - tx) * 256)), min(255, int((y - ty) * 256))
            z[j, i] = tiles[(tx, ty)][py, px]
    os.makedirs(DEM_DIR, exist_ok=True)
    np.savez_compressed(path, z=z.astype(np.int16), bbox=np.array([lon0, lon1, lat0, lat1]))
    return z, (lon0, lon1, lat0, lat1)


HYPSO = [(-100, (40, 110, 190)), (0, (70, 140, 80)), (300, (110, 165, 85)), (700, (190, 190, 110)),
         (1500, (175, 130, 80)), (2500, (140, 100, 80)), (3500, (175, 170, 170)), (4500, (225, 225, 232))]


def hypso(h):
    hs = np.array([a for a, _ in HYPSO], float)
    cs = np.array([c for _, c in HYPSO], float)
    return np.stack([np.interp(h, hs, cs[:, k]) for k in range(3)], -1)


def relief(name, bbox, zoom, height=0.75, grid=(220, 160)):
    z, (lon0, lon1, lat0, lat1) = fetch_dem(name, *bbox, zoom, grid)
    z = _median3(z)                                       # plitka chetidagi yakka noto'g'ri nuqtalar (igna) yo'qoladi
    gh, gw = z.shape
    W = 3.2
    kx = np.cos(np.radians((lat0 + lat1) / 2))
    Dp = W * (lat1 - lat0) / ((lon1 - lon0) * kx)
    xs = np.linspace(-W / 2, W / 2, gw)
    ys = np.linspace(Dp / 2, -Dp / 2, gh)            # shimol — orqada (+y), janub — kamera tomonda
    zs = np.clip(z, -50, None)
    scale = height / max(np.ptp(zs), 1)
    base = 0.18
    Z = base + (zs - zs.min()) * scale
    X, Y = np.meshgrid(xs, ys)
    pos = np.stack([X, Y, Z], -1).reshape(-1, 3)
    idx = []
    for j in range(gh - 1):
        for i in range(gw - 1):
            a = j * gw + i
            idx += [a, a + 1, a + gw, a + 1, a + gw + 1, a + gw]
    idx = np.array(idx)
    nor = _normals(pos, idx)
    nor = nor * np.sign(nor[:, 2:3] + 1e-9)
    cols = np.column_stack([hypso(zs.reshape(-1)).astype(np.uint8), np.full(len(pos), 255, np.uint8)])
    top = prim((pos, nor, idx), (1, 1, 1, 1), name + "_relyef", 0.8, colors=cols)
    # yon devorlar (tuproq kesimi)
    walls = []
    edges = [[(i, 0) for i in range(gw)], [(gw - 1, j) for j in range(gh)], [(i, gh - 1) for i in range(gw - 1, -1, -1)],
             [(0, j) for j in range(gh - 1, -1, -1)]]
    for edge in edges:
        p, k = [], []
        for (i, j) in edge:
            p += [[xs[i], ys[j], 0.0], [xs[i], ys[j], Z[j, i]]]
        p = np.array(p)
        for m in range(len(edge) - 1):
            a = 2 * m
            k += [a, a + 2, a + 1, a + 2, a + 3, a + 1]
        k = np.array(k)
        nn = _normals(p, k)
        walls += [(p, nn, k), (p, -nn, k.reshape(-1, 3)[:, ::-1].reshape(-1))]   # ikki tomonlama
    return [top, prim(walls, (0.55, 0.42, 0.30, 1), name + "_devor", 0.8)]


def entries():
    T, R = "Geografiya: Yer va jarayonlar", "Geografiya: relyef (haqiqiy)"
    pre = (22, 35, 0)
    return [
        ("gg_yer_tuzilishi", "Yerning ichki tuzilishi", "Earth's interior", FAN, T,
         ["yer tuzilishi", "yadro", "mantiya", "yer qobig'i", "строение земли", "litosfera"], earth_layers, (18, -32, 0)),
        ("gg_globus", "Globus: koordinata to'ri, ekvator, tropiklar", "Globe with graticule", FAN, T,
         ["globus", "kenglik", "uzoqlik", "ekvator", "tropik", "глобус", "koordinata"], globe, pre),
        ("gg_fasllar", "Yer o'qi og'ishi va fasllar", "Seasons", FAN, T,
         ["fasllar", "yer o'qi", "orbita", "времена года", "kun va tun", "quyosh"], seasons, (35, 10, 0)),
        ("gg_vulqon", "Vulqon tuzilishi (kesim)", "Volcano cross-section", FAN, T,
         ["vulqon", "magma", "вулкан", "krater", "lava", "otilish"], volcano, (14, 0, 0)),
        ("gg_qatlamlar", "Tog' jinslari qatlamlari", "Rock strata", FAN, T,
         ["qatlamlar", "cho'kindi jinslar", "геологические слои", "tog' jinslari"], lambda: strata(False), pre),
        ("gg_uzilma", "Uzilma (yer qobig'ining siljishi)", "Fault", FAN, T,
         ["uzilma", "siljish", "zilzila", "разлом", "tektonika"], lambda: strata(True), pre),
        ("gg_burmalar", "Burmalar (antiklinal va sinklinal)", "Folds", FAN, T,
         ["burma", "antiklinal", "sinklinal", "складки", "tog' hosil bo'lishi"], folds, (18, 15, 0)),
        ("gg_relyef_uzbekiston", "O'zbekiston va qo'shni hududlar relyefi", "Relief of Uzbekistan region", FAN, R,
         ["o'zbekiston relyefi", "relyef", "tog'lar", "tekislik", "рельеф узбекистана", "turon pasttekisligi"],
         lambda: relief("uzbekiston", (55.9, 73.2, 37.1, 45.6), 6, 0.55), (40, 0, 0)),
        ("gg_relyef_samarqand", "Samarqand viloyati relyefi", "Relief of Samarkand region", FAN, R,
         ["samarqand", "relyef", "zarafshon", "nurota", "рельеф самарканда"],
         lambda: relief("samarqand", (65.4, 68.3, 38.9, 40.3), 9, 0.55), (40, 0, 0)),
        ("gg_relyef_fargona", "Farg'ona vodiysi relyefi", "Relief of the Fergana Valley", FAN, R,
         ["farg'ona vodiysi", "relyef", "ферганская долина", "tog'lar bilan o'ralgan"],
         lambda: relief("fargona", (70.2, 73.6, 39.9, 41.6), 8, 0.6), (40, 0, 0)),
    ]
