""""Rahmat" sahifasi — fonli (shaffofsiz) personajlar uchun.

Yashil fonli personajlar panel ustiga qo'yiladi; bular esa o'z foni bilan keladi. Chegara bilinmasligi uchun
sahifa foni GIF ning ISHLATILGAN (palitradan o'tgan) chekka ranglaridan qator bo'yicha quriladi: GIF va sahifa
orasida rang farqi bo'lmaydi. Personaj ustuni har doim sahifa balandligicha turadi (tepa/past chegarasi yo'q),
qolgan joyda har personajning o'z dizayni.

Dizayn — `Animation.design`: har biri o'z joylashuvi, shrifti, rangi va bezagiga ega (`DESIGNS`).
"""
import logging
import math
import os
import subprocess
from typing import Callable, Dict, List, Tuple

import numpy as np
from PIL import Image

from services import author_mark
from services.premium_presentation.designer import kit
from services.premium_presentation.designer.kit import (CENTER, LEFT, MIDDLE, SANS, SERIF, box, fill, line, mix, nofill,
                                                        oval, poly, px, rect, text)

from .catalog import Animation

log = logging.getLogger(__name__)

GIF_FPS = 10
GIF_HEIGHT = 640            # sahifada 1080 px ga cho'ziladi
W, H = 1920, 1080
WHITE = "FFFFFF"


# ───────────────────────────────────────────── GIF va fon

def _run(cmd) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    if res.returncode != 0:
        raise RuntimeError("ffmpeg: " + res.stderr[-400:])


def _packed_size(anim: Animation) -> Tuple[int, int]:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", anim.path("packed.mp4")],
                           capture_output=True, text=True).stdout
    pw, ph = (int(v) for v in probe.strip().split(",")[:2])
    return (pw // 2 if anim.alpha else pw), ph


CHAR_MAX_H, CHAR_MAX_W, CHAR_BOTTOM, CHAR_SIDE = 907, 940, 70, 60     # shaffof personaj: sahifadagi o'lcham (px)


def alpha_box(anim: Animation) -> Tuple[int, int]:
    """Shaffof personajning sahifadagi (kenglik, balandlik): nisbati saqlanadi, ustun juda keng bo'lib ketmaydi."""
    pw, ph = _packed_size(anim)
    aspect = pw / ph
    cw = min(CHAR_MAX_H * aspect, CHAR_MAX_W)
    return int(round(cw)), int(round(cw / aspect))


def _gif_size(anim: Animation) -> Tuple[int, int]:
    if anim.alpha:                                   # ustun = personaj + yon bo'sh joy; balandligi sahifaga teng
        cw, _ = alpha_box(anim)
        return int(round((cw + 2 * CHAR_SIDE) * GIF_HEIGHT / H)) // 2 * 2, GIF_HEIGHT
    pw, ph = _packed_size(anim)
    return int(pw * GIF_HEIGHT / ph) // 2 * 2, GIF_HEIGHT


def strip_geometry(anim: Animation) -> Tuple[int, int]:
    """Personaj ustunining sahifadagi joyi: (chap chekka, kenglik) — balandligi sahifaga teng."""
    gw, gh = _gif_size(anim)
    sw = round(H * gw / gh)
    where = (DESIGNS.get(anim.design) or DESIGNS["minimal"])[1]
    return {"r": W - sw, "l": 0, "c": (W - sw) // 2}[where], sw


def character_rect(anim: Animation) -> Tuple[int, int, int, int]:
    """Shaffof personajning sahifadagi (x, y, kenglik, balandlik) — namuna videolar shu joyga qo'yiladi."""
    sx, sw = strip_geometry(anim)
    cw, ch = alpha_box(anim)
    return sx + (sw - cw) // 2, H - CHAR_BOTTOM - ch, cw, ch


def _gradient_png(top: str, bottom: str, size: Tuple[int, int], out: str) -> str:
    t = np.linspace(0, 1, size[1])[:, None]
    a, b = np.array([int(top[i:i + 2], 16) for i in (0, 2, 4)]), np.array([int(bottom[i:i + 2], 16) for i in (0, 2, 4)])
    img = np.repeat((a + (b - a) * t)[:, None, :], size[0], 1)
    Image.fromarray(np.clip(img + 0.5, 0, 255).astype(np.uint8)).save(out)
    return out


def make_gif(anim: Animation, out: str) -> Tuple[int, int]:
    """Harakatlanuvchi GIF. Fonli personaj — butun kadr; shaffof personaj — temaning gradient foni ustida."""
    packed = anim.path("packed.mp4")
    w, h = _gif_size(anim)
    tail = ("split[a][b];[a]palettegen=max_colors=192:stats_mode=full[p];"
            "[b][p]paletteuse=dither=none:diff_mode=rectangle")
    if not anim.alpha:
        graph = f"[0:v]fps={GIF_FPS},scale={w}:{h}:flags=lanczos," + tail
        _run(["ffmpeg", "-v", "error", "-y", "-i", packed, "-filter_complex", graph, "-loop", "0", out])
        return w, h
    top, bottom = THEMES[anim.design]["bg"]
    bg = _gradient_png(top, bottom, (w, h), out + ".bg.png")
    k = h / H
    x, y, cw, ch = character_rect(anim)
    sx, _ = strip_geometry(anim)
    cwg, chg = int(round(cw * k)) // 2 * 2, int(round(ch * k)) // 2 * 2
    xg, yg = int(round((x - sx) * k)), int(round(y * k))
    graph = (f"[1:v]fps={GIF_FPS},split[l][r];[l]crop=iw/2:ih:0:0[c];[r]crop=iw/2:ih:iw/2:0,format=gray[m];"
             f"[c][m]alphamerge,scale={cwg}:{chg}:flags=lanczos[ca];[0:v][ca]overlay={xg}:{yg}:shortest=1," + tail)
    _run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(GIF_FPS), "-i", bg, "-i", packed,
          "-filter_complex", graph, "-loop", "0", out])
    os.remove(bg)
    return w, h


def gif_row_colours(gif: str) -> np.ndarray:
    """GIF chekkalaridagi qator ranglari (kadrlar bo'yicha eng ko'p uchraydigan) — sahifa foni shundan quriladi."""
    rows = []
    with Image.open(gif) as im:
        n = getattr(im, "n_frames", 1)
        for i in range(0, n, max(1, n // 8)):
            im.seek(i)
            a = np.asarray(im.convert("RGB"))
            rows.append(np.concatenate([a[:, :2], a[:, -2:]], 1).mean(1))      # (H, 3)
    stack = np.stack(rows)                                                    # (kadr, H, 3)
    return np.median(stack, 0)


def background_png(colours: np.ndarray, out: str) -> str:
    """Qator bo'yicha rangli (gorizontal bo'yicha o'zgarmas) 1920x1080 fon."""
    h = colours.shape[0]
    ys = np.linspace(0, h - 1, H)
    col = np.stack([np.interp(ys, np.arange(h), colours[:, c]) for c in range(3)], 1)
    img = np.repeat(col[:, None, :], W, 1)
    Image.fromarray(np.clip(img + 0.5, 0, 255).astype(np.uint8)).save(out)
    return out


def _hex(rgb) -> str:
    r, g, b = (int(round(v)) for v in rgb)
    return f"{r:02X}{g:02X}{b:02X}"


# ───────────────────────────────────────────── bezak asboblari

def dot(s, cx, cy, r, colour, alpha=100):
    sh = oval(s, cx, cy, r)
    fill(sh, colour, alpha)
    return sh


def ring(s, cx, cy, r, colour, width=3, alpha=100):
    sh = oval(s, cx, cy, r)
    nofill(sh)
    line(sh, colour, width, alpha)
    return sh


def bar(s, x, y, w, h, colour, alpha=100, rounded=False, rot=0):
    if rounded:
        sh = box(s, x, y, w, h, kit.SHAPE.ROUNDED_RECTANGLE, rot=rot, adj=(0.5,))
    else:
        sh = rect(s, x, y, w, h, rot=rot)
    fill(sh, colour, alpha)
    return sh


def card(s, x, y, w, h, colour, alpha=100, radius=0.06, border=None, border_alpha=100):
    sh = box(s, x, y, w, h, kit.SHAPE.ROUNDED_RECTANGLE, adj=(radius,))
    fill(sh, colour, alpha)
    if border:
        line(sh, border, 3, border_alpha)
    return sh


def sparkle(s, cx, cy, r, colour, alpha=100):
    pts = []
    for i in range(8):
        rad = r if i % 2 == 0 else r * 0.28
        a = math.radians(i * 45 - 90)
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    sh = poly(s, pts)
    fill(sh, colour, alpha)
    return sh


def flower(s, cx, cy, r, colour, alpha=100, petals=8, centre=None):
    pr = r * 0.42
    for i in range(petals):
        a = math.radians(i * 360 / petals)
        dot(s, cx + r * 0.58 * math.cos(a), cy + r * 0.58 * math.sin(a), pr, colour, alpha)
    if centre:
        dot(s, cx, cy, r * 0.36, centre, 100)


def cloud(s, cx, cy, size, colour=WHITE, alpha=80):
    for dx, dy, r in ((-0.55, 0.12, 0.34), (-0.15, -0.12, 0.46), (0.3, 0.0, 0.4), (0.62, 0.14, 0.3)):
        dot(s, cx + dx * size, cy + dy * size, r * size, colour, alpha)
    bar(s, cx - 0.85 * size, cy + 0.1 * size, 1.8 * size, 0.36 * size, colour, alpha, rounded=True)


def diamond(s, cx, cy, r, colour, alpha=100, rot=0):
    return bar(s, cx - r, cy - r, 2 * r, 2 * r, colour, alpha, rot=45 + rot)


def confetti(s, rects, palette):
    """rects: [(x, y, tur, o'lcham, burchak)] — tur: 0 to'rtburchak, 1 aylana, 2 yulduzcha."""
    for i, (x, y, kind, size, rot) in enumerate(rects):
        c = palette[i % len(palette)]
        if kind == 0:
            bar(s, x, y, size * 1.8, size * 0.7, c, 100, rot=rot)
        elif kind == 1:
            dot(s, x, y, size * 0.5, c)
        else:
            sparkle(s, x, y, size, c)


# ───────────────────────────────────────────── sahifa konteksti

class Ctx:
    def __init__(self, s, bg: str, sx: float, sw: float, label: str, title: str, sub: str, author_line: str):
        self.s, self.bg = s, bg
        self.sx, self.sw = sx, sw            # personaj ustuni
        self.label, self.title, self.sub, self.author = label, title, sub, author_line
        self.steps: List = []                # animatsiya tartibi (shakllar)

    @property
    def right(self) -> Tuple[float, float]:   # personajdan keyingi bo'sh joy
        return self.sx + self.sw, W - (self.sx + self.sw)

    @property
    def left(self) -> Tuple[float, float]:    # personajdan oldingi bo'sh joy
        return 0, self.sx

    def t(self, x, y, w, h, paras, **k):
        tb = text(self.s, x, y, w, h, paras, **k)
        self.steps.append(tb)
        return tb

    def note(self, shape):
        self.steps.append(shape)
        return shape

    def author_box(self, x, y, w, colour, align=LEFT, size=24):
        if not self.author:
            return None
        tb = text(self.s, x, y, w, 50, [[(self.author, size, colour)]], align=align)
        author_mark.mark(tb)
        self.steps.append(tb)
        return tb


# ───────────────────────────────────────────── dizaynlar (har personajga o'zi)

def d_balet(c: Ctx):
    """Balerina: pushti fon, sariq-oq yumshoq doiralar, oq kartada kursiv serif sarlavha."""
    s, wine = c.s, "7B1E40"
    for cx, cy, r, a in ((250, 980, 420, 16), (110, 1010, 280, 18), (1050, 130, 230, 14)):
        dot(s, cx, cy, r, WHITE, a)
    for cx, cy, r in ((980, 110, 60), (170, 150, 40), (1170, 870, 34)):
        ring(s, cx, cy, r, WHITE, 3, 70)
    for x, y, r in ((1200, 250, 30), (130, 300, 22), (1150, 760, 26), (560, 70, 18)):
        sparkle(s, x, y, r, WHITE, 90)
    card(s, 100, 215, 1090, 650, WHITE, 78, 0.07, WHITE, 90)
    pill = card(s, 150, 262, 360, 62, wine, 100, 0.5)
    c.note(pill)
    c.t(150, 262, 360, 62, [[(c.label, 26, WHITE, True, SANS, 300)]], align=CENTER, anchor=MIDDLE)
    c.t(150, 360, 990, 330, [[(c.title, 104, wine, True, SERIF, 0, True)]], anchor=MIDDLE, line_spacing=1.0)
    bar(s, 150, 708, 190, 6, "E46A8E")
    c.t(150, 735, 990, 70, [[(c.sub, 36, "9C3A5C", False, SERIF, 0, True)]])
    c.author_box(150, 805, 990, "9C3A5C", size=24)


def d_quyosh(c: Ctx):
    """Mushuk: kulrang fon, to'q karta, to'q sariq quyosh halqalari."""
    s, orange = c.s, "F28A1E"
    x0, w0 = c.right
    for r, a in ((470, 14), (360, 20), (250, 28)):
        dot(s, W - 140, 80, r, orange, a)
    dot(s, W - 140, 80, 120, orange, 85)
    card(s, x0 + 90, 235, w0 - 180, 610, "262630", 92, 0.07)
    pill = card(s, x0 + 150, 285, 340, 62, orange, 100, 0.5)
    c.note(pill)
    c.t(x0 + 150, 285, 340, 62, [[(c.label, 26, "2A1A0A", True, SANS, 300)]], align=CENTER, anchor=MIDDLE)
    c.t(x0 + 150, 385, w0 - 300, 290, [[(c.title, 92, WHITE, True, SANS)]], anchor=MIDDLE, line_spacing=1.02)
    bar(s, x0 + 150, 695, 170, 8, orange)
    c.t(x0 + 150, 725, w0 - 300, 60, [[(c.sub, 34, "D9D9E3")]])
    c.author_box(x0 + 150, 780, w0 - 300, orange, size=24)


def d_gul(c: Ctx):
    """Kapibara: marjon fon, oq gullar, yirik oq sarlavha."""
    s = c.s
    x0, w0 = c.right
    flower(s, W - 230, 170, 250, WHITE, 24, 8, None)
    flower(s, W - 90, 920, 170, WHITE, 20, 7, None)
    flower(s, x0 + w0 - 560, 960, 70, WHITE, 40, 6, "FFE08A")
    flower(s, x0 + 90, 150, 56, WHITE, 45, 6, "FFE08A")
    for x, y, r in ((x0 + 400, 90, 20), (W - 560, 330, 14), (x0 + 120, 880, 18)):
        sparkle(s, x, y, r, WHITE, 90)
    c.t(x0 + 100, 250, 600, 50, [[(c.label, 28, "FFF3C4", True, SANS, 400)]])
    bar(s, x0 + 100, 312, 150, 8, "FFF3C4")
    c.t(x0 + 100, 345, w0 - 200, 360, [[(c.title, 98, WHITE, True, SANS)]], anchor=MIDDLE, line_spacing=1.03)
    c.t(x0 + 100, 730, w0 - 200, 70, [[(c.sub, 36, "FFEFEA")]])
    c.author_box(x0 + 100, 880, w0 - 200, "FFF3C4", size=24)


def d_konfetti(c: Ctx):
    """Kapibara (tutu): markazda personaj, ikki yonda konfetti va yozuvlar."""
    s, purple = c.s, "47195C"
    palette = ["FFD93D", WHITE, "5EEAD4", "A78BFA", "FDE68A", "FB7185"]
    spots = [(90, 120, 0, 34, 20), (300, 70, 1, 30, 0), (520, 160, 2, 24, 0), (60, 560, 1, 26, 0), (230, 980, 0, 34, -25),
             (520, 1000, 1, 28, 0), (150, 420, 2, 20, 0), (1660, 110, 0, 34, -20), (1790, 260, 1, 30, 0),
             (1700, 520, 2, 24, 0), (1830, 700, 0, 34, 35), (1680, 930, 1, 32, 0), (1560, 1020, 2, 22, 0),
             (1860, 960, 2, 20, 0), (620, 70, 0, 30, 40), (1620, 360, 2, 18, 0)]
    confetti(s, spots, palette)
    c.t(70, 190, 540, 50, [[(c.label, 26, purple, True, SANS, 250)]])
    bar(s, 70, 248, 130, 8, purple)
    c.t(70, 280, 560, 470, [[(c.title, 82, purple, True, SANS)]], anchor=MIDDLE, line_spacing=1.04)
    x0 = c.sx + c.sw
    card(s, x0 + 40, 360, 1920 - x0 - 90, 260, WHITE, 85, 0.12)
    c.t(x0 + 75, 385, 1920 - x0 - 160, 160, [[(c.sub, 38, purple, True, SANS)]], anchor=MIDDLE)
    c.author_box(x0 + 75, 555, 1920 - x0 - 160, "8A4BA8", size=24)


def d_gazeta(c: Ctx):
    """Quyoncha: oq fon, gazetaga o'xshash qora serif va ko'k urg'u."""
    s, blue, ink = c.s, "3E78B5", "15181F"
    x0, w0 = c.right
    left = x0 + 110
    width = w0 - 220
    bar(s, left, 150, width, 6, ink)
    bar(s, left, 166, width, 2, ink)
    c.t(left, 190, width, 50, [[(c.label, 26, blue, True, SANS, 500)]])
    c.t(left, 270, width, 380, [[(c.title, 104, ink, True, SERIF)]], anchor=MIDDLE, line_spacing=0.98)
    bar(s, left, 690, 220, 14, blue)
    c.t(left, 735, width, 130, [[(c.sub, 38, "3B4252", False, SERIF, 0, True)]])
    bar(s, left, 905, width, 2, ink)
    bar(s, left, 921, width, 6, ink)
    c.author_box(left, 945, width, blue, size=24)
    dot(s, W - 170, 80, 20, blue, 100)
    dot(s, W - 110, 80, 20, "9CC0E8", 100)


def d_shokolad(c: Ctx):
    """Ayiqcha: oq fon, tepada asal tomchilari, shokolad rangli matn."""
    s, brown, honey = c.s, "5A2E18", "F2A81D"
    x0 = 0
    bar(s, -40, -20, c.sx - 50, 90, honey, 100, rounded=True)
    for x, ln in ((70, 150), (210, 95), (370, 190), (560, 120), (760, 170), (930, 100), (1090, 150)):
        if x < c.sx - 140:
            bar(s, x, 40, 54, ln, honey, 100, rounded=True)
            dot(s, x + 27, 40 + ln, 27, honey)
    for cx, cy, r in ((120, 960, 190), (330, 1040, 120)):
        dot(s, cx, cy, r, "F6E3C3", 100)
    pill = card(s, 130, 300, 340, 60, brown, 100, 0.5)
    c.note(pill)
    c.t(130, 300, 340, 60, [[(c.label, 25, "FBE9C6", True, SANS, 300)]], align=CENTER, anchor=MIDDLE)
    c.t(130, 395, c.sx - 200, 320, [[(c.title, 98, brown, True, SERIF)]], anchor=MIDDLE, line_spacing=1.02)
    c.t(130, 745, c.sx - 200, 70, [[(c.sub, 36, "8A5A3A", False, SERIF, 0, True)]])
    c.author_box(130, 830, c.sx - 200, honey, size=24)


def d_muz(c: Ctx):
    """Pingvin: muzdek moviy geometriya, qor dumaloqlari, to'q ko'k sarlavha."""
    s, navy, ice = c.s, "12315E", "BFD9F2"
    x0, w0 = c.right
    for x, y, r, a in ((x0 + w0 - 200, 160, 120, 40), (x0 + w0 - 360, 280, 70, 35), (x0 + w0 - 90, 380, 50, 50)):
        diamond(s, x, y, r, ice, a, rot=0)
    for x, y, r in ((x0 + 120, 940, 90), (x0 + 330, 1010, 50), (x0 + 520, 960, 28)):
        dot(s, x, y, r, ice, 60)
    for i, (x, y) in enumerate(((x0 + 560, 150), (x0 + 700, 90), (x0 + 220, 90), (x0 + w0 - 520, 960),
                                (x0 + w0 - 140, 860), (x0 + 60, 520))):
        sparkle(s, x, y, 16 + (i % 3) * 5, "7FB3E6", 85)
    bar(s, x0 + 100, 255, 8, 520, "3A7BD5")
    pill = card(s, x0 + 150, 245, 330, 60, "3A7BD5", 100, 0.5)
    c.note(pill)
    c.t(x0 + 150, 245, 330, 60, [[(c.label, 25, WHITE, True, SANS, 300)]], align=CENTER, anchor=MIDDLE)
    c.t(x0 + 150, 335, w0 - 300, 330, [[(c.title, 96, navy, True, SANS)]], anchor=MIDDLE, line_spacing=1.02)
    c.t(x0 + 150, 695, w0 - 300, 70, [[(c.sub, 36, "3C5C8C")]])
    c.author_box(x0 + 150, 790, w0 - 300, "3A7BD5", size=24)


def d_bulut(c: Ctx):
    """Momiq quyoncha: markazda personaj, bulutlar, lavanda rangli matn."""
    s, plum = c.s, "4A3B6B"
    for cx, cy, size, a in ((250, 120, 120, 85), (590, 220, 80, 75), (1500, 140, 130, 85), (1780, 300, 80, 75),
                            (120, 880, 90, 70), (1640, 900, 110, 70)):
        cloud(s, cx, cy, size, WHITE, a)
    for x, y, r in ((420, 60, 16), (1260, 90, 14), (1840, 640, 16), (60, 520, 14)):
        sparkle(s, x, y, r, "F6B8D2", 100)
    c.t(70, 300, 520, 50, [[(c.label, 26, "8B6FC0", True, SANS, 250)]])
    bar(s, 70, 358, 130, 8, "F28DB6")
    c.t(70, 390, 540, 420, [[(c.title, 80, plum, True, SANS)]], anchor=MIDDLE, line_spacing=1.04)
    x0 = c.sx + c.sw
    card(s, x0 + 40, 410, 1920 - x0 - 90, 250, WHITE, 82, 0.14)
    c.t(x0 + 75, 435, 1920 - x0 - 160, 160, [[(c.sub, 38, plum, True, SANS)]], anchor=MIDDLE)
    c.author_box(x0 + 75, 600, 1920 - x0 - 160, "8B6FC0", size=24)


def d_minimal(c: Ctx):
    """Pushti momiq: oppoq fon, ingichka ramka, katta yupqa yozuv va bitta pushti nuqta."""
    s, ink, pink = c.s, "111111", "F08CB1"
    x0, w0 = c.left                                  # personaj o'ngda — bo'sh joy chapda
    left = x0 + 140
    width = w0 - 280
    rect_ = rect(s, x0 + 60, 60, w0 - 120, 960)
    nofill(rect_)
    line(rect_, ink, 2, 100)
    dot(s, left + 18, 238, 18, pink)
    c.t(left + 56, 215, width, 50, [[(c.label, 26, ink, True, SANS, 600)]])
    c.t(left, 320, width, 380, [[(c.title, 108, ink, True, SANS)]], anchor=MIDDLE, line_spacing=0.98)
    bar(s, left, 730, 100, 5, pink)
    c.t(left, 770, width, 80, [[(c.sub, 36, "555555")]])
    c.author_box(left, 870, width, pink, size=24)


# ───────────────────────────────────────────── shaffof (eski) personajlar: tema + umumiy chizuvchi
# Har bir temaning o'z gradient foni (personaj shu fon ustida), joylashuvi, kartasi, bezagi va shrifti bor.

THEMES: Dict[str, dict] = {
    "t_paxmoq": dict(bg=("FBEBD7", "F3C9A0"), side="r", card="white", ink="5B3A1E", acc="E58E4D", sub="8A6444",
                     decor="clouds", font="serif", italic=True, label="pill"),
    "t_qizcha": dict(bg=("F6D9F2", "D7B8F5"), side="l", card="white", ink="5B2A86", acc="B76BE8", sub="7E4FB0",
                     decor="sparkles", font="sans", label="pill"),
    "t_anime_qiz": dict(bg=("FFB3D1", "C2438F"), side="r", card="glass", ink="FFFFFF", acc="FFE3F0", sub="FFE9F4",
                        decor="flowers", font="serif", label="plain"),
    "t_pul_mushuk": dict(bg=("12351F", "07130C"), side="l", card="dark", ink="F5E7B2", acc="E4B83B", sub="CDBE86",
                         decor="coins", font="sans", label="pill", pill_ink="1A1405"),
    "t_hamster": dict(bg=("FFE27A", "F6A21E"), side="r", card="white", ink="5A3410", acc="D9730D", sub="8A5A22",
                      decor="stripes", font="sans", label="pill"),
    "t_parik_hamster": dict(bg=("3A1A6E", "14083A"), side="l", card="glass", ink="FFFFFF", acc="FF5CC8", sub="E5D7FF",
                            decor="confetti", font="sans", label="pill", pill_ink="FFFFFF"),
    "t_raqs_mushuk": dict(bg=("0E6B7A", "0A1F3F"), side="c", card="none", ink="FFFFFF", acc="7CF3E0", sub="D3F7F1",
                          decor="waves", font="sans", label="line"),
    "t_mushukchalar": dict(bg=("CFE6FF", "F4F9FF"), side="r", card="white", ink="1F4E8C", acc="5AA9F5", sub="4C79B3",
                           decor="bubbles", font="sans", label="pill", border="9CC8F5"),
    "t_kuchukcha": dict(bg=("C9F2D8", "8BD9A9"), side="l", card="none", ink="0F4D2C", acc="1FA463", sub="2A7A4D",
                        decor="dots", font="sans", label="plain"),
    "t_timsoh": dict(bg=("2E7D32", "0B2E13"), side="r", card="dark", ink="E8F8D0", acc="B6E34A", sub="BFD9A0",
                     decor="leaves", font="serif", label="pill", pill_ink="14240A"),
    "t_robot": dict(bg=("1B2433", "070B12"), side="l", card="none", ink="EAF6FF", acc="35D6FF", sub="9FB6C9",
                    decor="grid", font="sans", label="line"),
    "t_pul_yomgiri": dict(bg=("0F6B3A", "063B20"), side="c", card="none", ink="FFF6CC", acc="FFD24A", sub="E6F2C4",
                          decor="coins", font="sans", label="pill", pill_ink="2A2000"),
    "t_kok_bolakay": dict(bg=("3E7BFA", "A6D0FF"), side="r", card="white", ink="123A8F", acc="FFC83D", sub="3D63B8",
                          decor="stars", font="sans", label="pill", pill_ink="3A2A00"),
    "t_oshpaz": dict(bg=("7A1230", "3B0716"), side="l", card="cream", ink="5A1020", acc="C8892B", sub="86485A",
                     decor="diamonds", font="serif", label="pill", pill_ink="FFF3DD"),
    "t_qahramon": dict(bg=("20232B", "6A0F16"), side="r", card="dark", ink="FFFFFF", acc="FF3B3B", sub="E0C9CB",
                       decor="slashes", font="sans", label="line"),
}


def _decor(c: Ctx, kind: str, zones, acc: str, bg_top: str) -> None:
    """Bezak: faqat matn tomonidagi bo'sh joyda (personaj ustuniga tegmaydi)."""
    s = c.s
    for (x0, x1) in zones:
        w = x1 - x0
        if w < 200:
            continue
        pts = [(x0 + w * fx, H * fy) for fx, fy in ((0.12, 0.10), (0.78, 0.08), (0.9, 0.55), (0.18, 0.92),
                                                    (0.62, 0.94), (0.05, 0.5), (0.5, 0.05))]
        if len(zones) == 2:                           # ustun o'rtada: matn ikki chetda — bezak faqat tepa va pastda
            pts = [p_ for p_ in pts if p_[1] < H * 0.18 or p_[1] > H * 0.88]
        if kind == "clouds":
            for (px_, py_), size, a in zip(pts, (110, 80, 90, 100, 70, 60, 75), (85, 70, 70, 80, 60, 60, 60)):
                cloud(s, px_, py_, size, WHITE, a)
        elif kind == "sparkles":
            for i, (px_, py_) in enumerate(pts):
                sparkle(s, px_, py_, 18 + (i % 3) * 9, acc, 85)
            dot(s, x0 + w * 0.88, H * 0.9, 150, WHITE, 25)
        elif kind == "flowers":
            flower(s, x1 - 40, 90, 190, WHITE, 22, 8, None)
            flower(s, x0 + 40, H - 60, 150, WHITE, 18, 7, None)
            for (px_, py_) in pts[:4]:
                flower(s, px_, py_, 34, WHITE, 50, 6, "FFE08A")
        elif kind == "coins":
            for i, (px_, py_) in enumerate(pts):
                r = 38 + (i % 3) * 14
                dot(s, px_, py_, r, "F2C64A", 95)
                ring(s, px_, py_, r * 0.68, "B8860B", 4, 90)
        elif kind == "stripes":
            for i in range(5):
                bar(s, x0 + w * (0.05 + i * 0.22), -100, 90, H + 300, WHITE, 16, rot=18)
        elif kind == "confetti":
            confetti(s, [(px_, py_, i % 3, 26 + (i % 2) * 8, i * 37 % 90) for i, (px_, py_) in enumerate(pts)] +
                     [(x0 + w * 0.3, H * 0.96, 1, 24, 0), (x0 + w * 0.95, H * 0.3, 2, 18, 0)],
                     ["FF5CC8", "7CF3E0", "FFE066", "A78BFA"])
        elif kind == "waves":
            for i in range(4):
                bar(s, x0 - 40, H * (0.62 + i * 0.1), w + 80, 46, WHITE, 10 + i * 3, rounded=True)
        elif kind == "bubbles":
            for i, (px_, py_) in enumerate(pts):
                ring(s, px_, py_, 34 + (i % 4) * 20, acc, 4, 70)
                dot(s, px_ + 8, py_ - 8, 8, acc, 55)
        elif kind == "dots":
            for gx in range(7):                          # nuqtalar faqat tepa va pastki qatorlarda — yozuv ustiga tushmaydi
                for gy in (60, 150, H - 150, H - 60):
                    dot(s, x0 + 50 + gx * (w - 100) / 6, gy, 7, acc, 55)
        elif kind == "leaves":
            for i, (px_, py_) in enumerate(pts):
                fill(box(s, px_ - 90, py_ - 36, 180, 72, kit.SHAPE.OVAL, rot=(i * 47) % 160 - 40), acc, 28)
        elif kind == "grid":
            for gx in range(0, int(w), 90):
                bar(s, x0 + gx, 0, 2, H, acc, 10)
            for gy in range(0, H, 90):
                bar(s, x0, gy, w, 2, acc, 10)
            for (px_, py_) in pts[:4]:
                dot(s, px_, py_, 9, acc, 90)
        elif kind == "stars":
            for i, (px_, py_) in enumerate(pts):
                sparkle(s, px_, py_, 24 + (i % 3) * 10, "FFE066", 95)
            for i in range(3):
                dot(s, x0 + w * (0.2 + i * 0.3), H * 0.97, 50 + i * 18, WHITE, 28)
        elif kind == "diamonds":
            for i, (px_, py_) in enumerate(pts):
                diamond(s, px_, py_, 28 + (i % 3) * 16, acc, 55)
        elif kind == "slashes":
            for i in range(4):
                bar(s, x0 + w * (0.1 + i * 0.25), -120, 26 + i * 14, H + 300, acc, 30, rot=22)


def _title_runs(sp: dict, c: Ctx, size: int):
    font = SERIF if sp["font"] == "serif" else SANS
    return [[(c.title, size, sp["ink"], True, font, 0, bool(sp.get("italic")))]]


def _label(c: Ctx, sp: dict, x: float, y: float, w: float = 520) -> None:
    """Yorliq («SO'NGGI SO'Z»): pill / chiziqli / oddiy."""
    kind, acc = sp["label"], sp["acc"]
    if kind == "pill":
        pill = card(c.s, x, y, 360, 60, acc, 100, 0.5)
        c.note(pill)
        c.t(x, y, 360, 60, [[(c.label, 25, sp.get("pill_ink", "FFFFFF"), True, SANS, 300)]], align=CENTER,
            anchor=MIDDLE)
    elif kind == "line":
        bar(c.s, x, y + 14, 90, 6, acc)
        c.t(x + 110, y, max(w - 110, 200), 40, [[(c.label, 26, acc, True, SANS, 400)]], anchor=MIDDLE)
    else:
        c.t(x, y, w, 44, [[(c.label, 26, acc, True, SANS, 400)]])


def d_theme(c: Ctx, sp: dict) -> None:
    s = c.s
    left, right = (0, c.sx), (c.sx + c.sw, W)
    side = sp["side"]
    zones = [left, right] if side == "c" else [right if side == "l" else left]
    _decor(c, sp["decor"], zones, sp["acc"], sp["bg"][0])
    ink, acc, subc = sp["ink"], sp["acc"], sp["sub"]
    style = sp["card"]

    def panel(x, y, w, h):
        if style == "white":
            card(s, x, y, w, h, WHITE, 82, 0.07, sp.get("border", WHITE), 90)
        elif style == "cream":
            card(s, x, y, w, h, "FFF3DD", 93, 0.07, acc, 100)
        elif style == "dark":
            card(s, x, y, w, h, mix(sp["bg"][1], "000000", 0.55), 90, 0.07, acc, 70)
        elif style == "glass":
            card(s, x, y, w, h, WHITE, 16, 0.07, WHITE, 70)

    if side == "c":                                      # ustun o'rtada: chapda sarlavha, o'ngda izoh kartasi
        lx0, lx1 = left
        _label(c, sp, 70, 230, lx1 - 110)
        bar(s, 70, 305, 130, 8, acc)
        c.t(70, 335, lx1 - 110, 470, _title_runs(sp, c, 84), anchor=MIDDLE, line_spacing=1.04)
        rx0, rx1 = right
        panel(rx0 + 40, 390, rx1 - rx0 - 90, 280) if style != "none" else card(s, rx0 + 40, 390, rx1 - rx0 - 90, 280,
                                                                                WHITE, 14, 0.12, WHITE, 60)
        c.t(rx0 + 80, 415, rx1 - rx0 - 170, 170, [[(c.sub, 38, ink, True, SANS)]], anchor=MIDDLE)
        c.author_box(rx0 + 80, 595, rx1 - rx0 - 170, acc, size=24)
        return
    x0, x1 = zones[0]
    zw = x1 - x0
    inner = 70
    if style != "none":
        panel(x0 + 60, 190, zw - 120, 700)
        inner = 120
    tx, tw = x0 + inner, zw - 2 * inner
    _label(c, sp, tx, 245, tw)
    c.t(tx, 340, tw, 330, _title_runs(sp, c, 92), anchor=MIDDLE, line_spacing=1.02)
    bar(s, tx, 700, 170, 8, acc)
    font = SERIF if sp["font"] == "serif" else SANS
    c.t(tx, 730, tw, 70, [[(c.sub, 36, subc, False, font, 0, bool(sp.get("italic")))]])
    c.author_box(tx, 815, tw, acc, size=24)


DESIGNS: Dict[str, Tuple[Callable[[Ctx], None], str]] = {
    # nom: (chizuvchi, personaj ustuni joyi: "r" — o'ngda, "l" — chapda, "c" — o'rtada)
    "balet": (d_balet, "r"),
    "quyosh": (d_quyosh, "l"),
    "gul": (d_gul, "l"),
    "konfetti": (d_konfetti, "c"),
    "gazeta": (d_gazeta, "l"),
    "shokolad": (d_shokolad, "r"),
    "muz": (d_muz, "l"),
    "bulut": (d_bulut, "c"),
    "minimal": (d_minimal, "r"),
}
for _key, _spec in THEMES.items():                     # shaffof personajlar: umumiy chizuvchi, har biriga o'z temasi
    DESIGNS[_key] = ((lambda c, sp=_spec: d_theme(c, sp)), _spec["side"])


# ───────────────────────────────────────────── yig'ish

def _timing_steps(shapes) -> List[Tuple[int, int]]:
    steps, delay = [], 200
    for sh in shapes:
        if sh is None:
            continue
        steps.append((sh.shape_id, delay))
        delay += 450
    return steps


def build_slide(s, anim: Animation, work: str, language: str, author: str):
    """`s` slaydiga fon, personaj GIF i va dizaynni chizadi. Qaytaradi: (animatsiya qadamlari, GIF yo'li)."""
    from .slide import texts

    gif = os.path.join(work, "thanks_character.gif")
    gw, gh = make_gif(anim, gif)
    bg = background_png(gif_row_colours(gif), os.path.join(work, "thanks_bg.png"))
    colours = gif_row_colours(gif)
    mid = _hex(colours[len(colours) // 2])

    draw = (DESIGNS.get(anim.design) or DESIGNS["minimal"])[0]
    sx, sw = strip_geometry(anim)

    s.shapes.add_picture(bg, 0, 0, px(W), px(H))
    label, title, sub, author_word = texts(language)
    ctx = Ctx(s, mid, sx, sw, label, title, sub, f"{author_word}: {author}" if author else "")
    draw(ctx)
    s.shapes.add_picture(gif, px(sx), 0, px(sw), px(H))
    return _timing_steps(ctx.steps)
