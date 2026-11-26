"""Astronomiya: haqiqiy tasvirli Quyosh, Oy va sayyoralar (o'qining haqiqiy og'ishi bilan), Quyosh tizimi, Oy fazalari,
Quyosh va Oy tutilishlari, Keplerning 2-qonuni (teng vaqtda teng yuzalar — Kepler tenglamasidan), osmon sferasi.

Teksturalar: Solar System Scope (NASA ma'lumotlari asosida), CC BY 4.0 — muallif katalog yozuvida va slaydda;
Yer — NASA Blue Marble (jamoat mulki).
"""
import numpy as np

from .asos import (HEIGHT, SLANT, TUBE, WIRE, arrow, ball, circle_pts, dashed, lathe, moved, plate_poly, prim, rot_x,
                   rot_y, shade, sphere, tex_prim, texture, tube, tube_path)

FAN = "astronomiya"
SSS = ("CC BY 4.0", "teksturalar: Solar System Scope · CC BY 4.0",
       "sayyora teksturalari: Solar System Scope (solarsystemscope.com), NASA ma'lumotlari asosida")
TILT = {"merkuriy": 0.03, "venera": 2.6, "yer": 23.4, "mars": 25.2, "yupiter": 3.1, "saturn": 26.7, "uran": 97.8, "neptun": 28.3}


def tex(name):
    if name == "yer":
        from .geografiya import texture as earth_texture
        return earth_texture()
    return texture(f"{name}_1024.jpg")


def planet(name, R=1.2, centre=(0, 0, 1.25), sun=None, seg=192, rings=96, lon_shift=0.0):
    return tex_prim(tex(name), R, name, centre=centre, seg=seg, rings=rings, tilt=rot_y(TILT.get(name, 0)), sun=sun,
                    lon_shift=lon_shift, night=0.25)


def saturn_rings(R, centre, tilt, n_ang=144):
    """Saturn halqalari: halqa teksturasi radial profili (shaffof joylar — Kassini oralig'i — tashlab ketiladi)."""
    from PIL import Image

    from .asos import TEX_DIR
    import os
    ring = np.asarray(Image.open(os.path.join(TEX_DIR, "saturn_halqa.png")).convert("RGBA")).astype(float)
    prof = ring.mean(0)                                     # radial bo'yicha (512 ta)
    r0, r1 = R * 1.24, R * 2.27
    n_rad = 96
    rs = np.linspace(r0, r1, n_rad + 1)
    pos, nor, idx, cols = [], [], [], []
    ang = np.linspace(0, 2 * np.pi, n_ang + 1)
    for i, r in enumerate(rs):
        k = int((r - r0) / (r1 - r0) * (len(prof) - 1))
        c = prof[k]
        for a in ang:
            for up in (1, -1):
                pos.append([r * np.cos(a), r * np.sin(a), 0])
                nor.append([0, 0, up])
                cols.append([*np.clip(c[:3] * 1.05, 0, 255), 255])
    for i in range(n_rad):
        k = int(((rs[i] + rs[i + 1]) / 2 - r0) / (r1 - r0) * (len(prof) - 1))
        if prof[k][3] < 40:                                  # bo'shliq
            continue
        for j in range(n_ang):
            for up in (0, 1):
                a = ((i * (n_ang + 1)) + j) * 2 + up
                b = a + 2
                c_ = a + (n_ang + 1) * 2
                d = c_ + 2
                idx += [a, b, c_, b, d, c_]
    pos = np.array(pos) @ tilt.T + centre
    nor = np.array(nor, float) @ tilt.T
    return prim((pos, nor, np.array(idx)), (1, 1, 1, 1), "saturn_halqalari", 0.6, colors=np.array(cols, np.uint8))


def single(name, R=1.15):
    out = [planet(name, R)]
    if name == "saturn":
        out = [planet(name, 0.85, centre=(0, 0, 1.25)), saturn_rings(0.85, np.array([0, 0, 1.25]), rot_y(TILT["saturn"]))]
    return out


def sun_model():
    return [tex_prim(texture("quyosh_1024.jpg"), 1.25, "quyosh", centre=(0, 0, 1.3), gain=1.15)]


def solar_system():
    order = [("merkuriy", 0.10, 1.25), ("venera", 0.17, 1.75), ("yer", 0.18, 2.3), ("mars", 0.13, 2.85),
             ("yupiter", 0.42, 3.75), ("saturn", 0.34, 4.75), ("uran", 0.25, 5.6), ("neptun", 0.24, 6.3)]
    out = [tex_prim(texture("quyosh_1024.jpg"), 0.72, "quyosh", centre=(0, 0, 0.8), seg=96, rings=48, gain=1.15)]
    orbits = []
    for k, (name, r, d) in enumerate(order):
        a = np.radians(-60 + 28 * k)
        c = np.array([d * np.cos(a), d * np.sin(a), 0.8])
        sun_dir = np.array([0, 0, 0.8]) - c
        out.append(tex_prim(tex(name), r, name, centre=c, seg=72, rings=36, tilt=rot_y(TILT[name]), sun=sun_dir, night=0.35))
        if name == "saturn":
            out.append(saturn_rings(r, c, rot_y(TILT[name]), 72))
        orbits.append(tube_path(circle_pts(d, (0, 0, 0.8), (0, 0, 1), 181), TUBE * 0.45, 6))
    out.append(prim(orbits, WIRE, "orbitalar", 0.4))
    return out


def moon_phases():
    out = [tex_prim(tex("yer"), 0.42, "yer", centre=(0, 0, 1.0), seg=96, rings=48, tilt=rot_y(23.4))]
    sun = np.array([-1.0, 0, 0])
    for k in range(8):
        a = np.radians(45 * k)
        c = np.array([1.55 * np.cos(a), 1.55 * np.sin(a), 1.0])
        out.append(tex_prim(texture("oy_1024.jpg"), 0.17, f"oy_{k}", centre=c, seg=64, rings=32, sun=sun, night=0.10))
    orbit = tube_path(circle_pts(1.55, (0, 0, 1.0), (0, 0, 1), 145), TUBE * 0.4, 6)
    rays = [m for z in (0.6, 1.0, 1.4) for m in arrow([-3.0, 0, z], [-2.1, 0, z], TUBE * 0.9, head=0.18)]
    return out + [prim([orbit], WIRE, "oy_orbitasi", 0.4), prim(rays, (0.98, 0.78, 0.20, 1), "quyosh_nurlari", 0.3)]


def cone(apex, base_c, base_r, color, name, seg=48):
    apex, base_c = np.asarray(apex, float), np.asarray(base_c, float)
    from .asos import _frame
    x, y, z = _frame(base_c - apex)
    h = np.linalg.norm(base_c - apex)
    rot = np.stack([x, y, z], 1)
    return prim(moved([lathe([(0.001, 0), (base_r, h)], seg)], apex, rot), color, name, 0.7)


def eclipse(solar=True):
    y = 1.0
    sun_c, R_sun = np.array([-3.2, 0, y]), 1.0
    out = [tex_prim(texture("quyosh_1024.jpg"), R_sun, "quyosh", centre=sun_c, seg=96, rings=48, gain=1.15)]
    if solar:
        moon_c, earth_c = np.array([0.6, 0, y]), np.array([2.6, 0, y])
        out += [tex_prim(texture("oy_1024.jpg"), 0.16, "oy", centre=moon_c, seg=64, rings=32, sun=sun_c - moon_c, night=0.12),
                tex_prim(tex("yer"), 0.5, "yer", centre=earth_c, seg=128, rings=64, tilt=rot_y(23.4), sun=sun_c - earth_c, night=0.3)]
        tip = earth_c + np.array([-0.38, 0, 0])
        out.append(cone(tip, moon_c, 0.16, (0.22, 0.22, 0.26, 1), "to'liq_soya"))
        lines = [tube(sun_c + [0, 0, s * R_sun], earth_c + [-0.45, 0, -s * 0.45], TUBE * 0.4, 6) for s in (1, -1)]
        lines += [tube(sun_c + [0, 0, s * R_sun], earth_c + [-0.45, 0, s * 0.05], TUBE * 0.4, 6) for s in (1, -1)]
    else:
        earth_c, moon_c = np.array([0.4, 0, y]), np.array([2.7, 0, y])
        out += [tex_prim(tex("yer"), 0.5, "yer", centre=earth_c, seg=128, rings=64, tilt=rot_y(23.4), sun=sun_c - earth_c, night=0.3),
                tex_prim(texture("oy_1024.jpg"), 0.17, "oy_qizargan", centre=moon_c, seg=64, rings=32, gain=0.55)]
        out[-1].colors = (out[-1].colors.astype(float) * [1.25, 0.55, 0.40, 1]).clip(0, 255).astype(np.uint8)
        # Yer soyasi (to'liq soya konusi) — chegara chiziqlari bilan: ichidagi qizargan Oy ko'rinib tursin
        tip = earth_c + np.array([3.4, 0, 0])
        shadow = []
        for a in np.linspace(0, 2 * np.pi, 8, endpoint=False):
            shadow += dashed(earth_c + 0.5 * np.array([0, np.cos(a), np.sin(a)]), tip, TUBE * 0.45, 0.1, 0.07)
        out.append(prim(shadow, (0.42, 0.44, 0.52, 1), "yer_soyasi_chegarasi", 0.5))
        lines = [tube(sun_c + [0, 0, s * R_sun], earth_c + [0, 0, s * 0.5], TUBE * 0.4, 6) for s in (1, -1)]
    return out + [prim(lines, (0.98, 0.78, 0.20, 1), "nurlar", 0.3)]


def kepler():
    a, e = 2.3, 0.55
    b = a * np.sqrt(1 - e * e)
    c = a * e
    z = 1.0

    def pos(M):                                             # Kepler tenglamasi: M = E − e·sinE
        E = M
        for _ in range(50):
            E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
        return np.array([a * np.cos(E) - c, b * np.sin(E), z])
    orbit = [pos(M) for M in np.linspace(0, 2 * np.pi, 241)]
    sun = np.array([0, 0, z])
    out = [tex_prim(texture("quyosh_1024.jpg"), 0.3, "quyosh", centre=sun, seg=64, rings=32, gain=1.15),
           prim([tube_path(orbit, TUBE * 0.5, 8)], WIRE, "orbita", 0.4)]
    dt = 2 * np.pi / 12
    sectors = []
    for k, M0 in enumerate((-dt / 2, np.pi - dt / 2)):     # perigeliy va afeliy yonida — teng vaqt oralig'i
        pts = [pos(M) for M in np.linspace(M0, M0 + dt, 30)]
        for i in range(len(pts) - 1):
            sectors.append(plate_poly([sun, pts[i], pts[i + 1]], 0.01))
    out.append(prim(sectors[:29], (0.98, 0.62, 0.20, 1), "sektor_tez", 0.6))
    out.append(prim(sectors[29:], (0.30, 0.65, 0.95, 1), "sektor_sekin", 0.6))
    out.append(tex_prim(tex("mars"), 0.12, "sayyora", centre=pos(0.9), seg=48, rings=24))
    out.append(prim(dashed(np.array([-a - c, 0, z]), np.array([a - c, 0, z]), TUBE * 0.4), shade(WIRE, 0.8), "katta_o'q", 0.4))
    return out


def celestial_sphere():
    R = 1.5
    c = np.array([0, 0, 1.6])
    grid = []
    for k in range(6):
        a = np.pi * k / 6
        grid.append(tube_path(circle_pts(R, c, (-np.sin(a), np.cos(a), 0), 121), TUBE * 0.3, 6))
    for f in (-0.5, 0.5):
        grid.append(tube_path(circle_pts(R * np.sqrt(1 - f * f), c + [0, 0, R * f], (0, 0, 1), 121), TUBE * 0.3, 6))
    equator = tube_path(circle_pts(R, c, (0, 0, 1), 145), TUBE * 0.8, 8)
    ecl_n = rot_x(23.44) @ np.array([0, 0, 1.0])
    ecliptic = tube_path(circle_pts(R, c, ecl_n, 145), TUBE * 0.8, 8)
    axis = tube(c - [0, 0, R * 1.2], c + [0, 0, R * 1.2], TUBE * 0.6)
    sun_pos = c + R * (rot_x(23.44) @ np.array([np.cos(0.8), np.sin(0.8), 0]))
    return [prim(grid, WIRE, "osmon_to'ri", 0.4), prim([equator], (0.20, 0.52, 0.95, 1), "osmon_ekvatori", 0.4),
            prim([ecliptic], SLANT, "ekliptika", 0.4), prim([axis], (0.45, 0.48, 0.55, 1), "olam_o'qi", 0.4),
            tex_prim(tex("yer"), 0.32, "yer", centre=c, seg=96, rings=48, tilt=rot_y(23.4)),
            tex_prim(texture("quyosh_1024.jpg"), 0.13, "quyosh", centre=sun_pos, seg=48, rings=24, gain=1.15)]


NAMES = {"merkuriy": ("Merkuriy", "Mercury"), "venera": ("Venera", "Venus"), "yer": ("Yer sayyorasi", "Earth"),
         "mars": ("Mars", "Mars"), "yupiter": ("Yupiter", "Jupiter"), "saturn": ("Saturn halqalari bilan", "Saturn"),
         "uran": ("Uran", "Uranus"), "neptun": ("Neptun", "Neptune")}
RU = {"merkuriy": "меркурий", "venera": "венера", "yer": "земля", "mars": "марс", "yupiter": "юпитер", "saturn": "сатурн",
      "uran": "уран", "neptun": "нептун"}


def entries():
    J, H = "Astronomiya: osmon jismlari", "Astronomiya: hodisalar va qonunlar"
    pre = (14, -30, 0)
    out = [(f"ast_{k}", uz, en, FAN, J, [k, uz.split()[0].lower(), RU[k], en.lower(), "sayyora", "quyosh tizimi"],
            (lambda k=k: single(k)), pre) for k, (uz, en) in NAMES.items()]
    out += [
        ("ast_quyosh", "Quyosh", "Sun", FAN, J, ["quyosh", "солнце", "sun", "yulduz"], sun_model, pre),
        ("ast_oy", "Oy (Yerning yo'ldoshi)", "Moon", FAN, J, ["oy", "луна", "moon", "yo'ldosh", "kraterlar"],
         lambda: [tex_prim(texture("oy_1024.jpg"), 1.15, "oy", centre=(0, 0, 1.2))], pre),
        ("ast_quyosh_tizimi", "Quyosh tizimi (sayyoralar orbitalarda)", "Solar System", FAN, H,
         ["quyosh tizimi", "sayyoralar", "солнечная система", "orbita"], solar_system, (32, -10, 0)),
        ("ast_oy_fazalari", "Oy fazalari", "Phases of the Moon", FAN, H, ["oy fazalari", "фазы луны", "yangi oy", "to'lin oy"],
         moon_phases, (40, -10, 0)),
        ("ast_quyosh_tutilishi", "Quyosh tutilishi", "Solar eclipse", FAN, H, ["quyosh tutilishi", "солнечное затмение", "soya"],
         lambda: eclipse(True), (12, 0, 0)),
        ("ast_oy_tutilishi", "Oy tutilishi", "Lunar eclipse", FAN, H, ["oy tutilishi", "лунное затмение", "yer soyasi"],
         lambda: eclipse(False), (12, 0, 0)),
        ("ast_kepler", "Keplerning 2-qonuni (teng yuzalar)", "Kepler's second law", FAN, H,
         ["kepler qonunlari", "законы кеплера", "orbita", "ellips", "perigeliy"], kepler, (48, -8, 0)),
        ("ast_osmon_sferasi", "Osmon sferasi, ekliptika va osmon ekvatori", "Celestial sphere", FAN, H,
         ["osmon sferasi", "ekliptika", "небесная сфера", "osmon ekvatori"], celestial_sphere, (18, -30, 0)),
    ]
    return out


# Solar System Scope teksturali modellar — CC BY 4.0 (Yer — NASA, jamoat mulki).
LICENSES = {mid: SSS for mid in ["ast_merkuriy", "ast_venera", "ast_mars", "ast_yupiter", "ast_saturn", "ast_uran", "ast_neptun",
                                 "ast_quyosh", "ast_oy", "ast_quyosh_tizimi", "ast_oy_fazalari", "ast_quyosh_tutilishi",
                                 "ast_oy_tutilishi", "ast_kepler", "ast_osmon_sferasi"]}
