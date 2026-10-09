"""Vektor uslublar: muqova, reja, rasmli varaq, infografikalar, qiyos va xulosa.

Har uslub — parametrli funksiya: punktlar soni (3-8) va rang palitrasi (mavzuga qarab tanlangan
temadan) bo'yicha o'zini quradi. Matnni faqat sahifadan oladi — o'zidan so'z qo'shmaydi (taqdimot
qaysi tilda bo'lsa ham to'g'ri chiqadi).
"""
import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .kit import (CENTER, LEFT, MIDDLE, RIGHT, SANS, SERIF, SHAPE, TOP, BOTTOM, Photo, arc_pts, box, fill,
                  glow, grad, icon, inner_shadow, line, luminance, mix, nofill, oval, photo, poly, rect,
                  ribbon, ring_sector, rotate, shadow, text)

WHITE = "FFFFFF"


# ───────────────────────────────────────────── palitra

@dataclass
class Palette:
    dark: str
    accent: str
    soft: str
    ink: str
    body: str
    muted: str
    tones: tuple
    head_font: str = SANS

    @classmethod
    def of(cls, theme) -> "Palette":
        return cls(dark=theme.band, accent=theme.accent, soft=theme.accent_soft, ink=theme.heading,
                   body=theme.body, muted=theme.muted, tones=tuple(theme.chart) or (theme.accent,),
                   head_font=SERIF if getattr(theme, "style", "") == "jurnal" else SANS)

    @property
    def deep(self) -> str:
        return mix(self.dark, "000000", 0.45)

    @property
    def glowing(self) -> str:
        return mix(self.accent, WHITE, 0.4)

    @property
    def light(self) -> str:
        return mix(WHITE, self.accent, 0.035)

    @property
    def on_dark(self) -> str:
        return mix(self.dark, WHITE, 0.72)

    def ramp(self, n: int, start: float = 0.55, end: float = 0.45) -> List[str]:
        """Och → to'q urg'u ranglari (n ta): mix(accent, oq) dan mix(accent, to'q) gacha."""
        out = []
        for i in range(n):
            t = i / max(n - 1, 1)
            k = -start + (start + end) * t
            out.append(mix(self.accent, WHITE, -k) if k < 0 else mix(self.accent, self.dark, k))
        return out


@dataclass
class Ctx:
    slide: object
    pal: Palette
    rng: object
    used_icons: set = field(default_factory=set)
    photo: Optional[Photo] = None
    cover: Optional[Photo] = None
    topic_icon: str = "globe"

    def icon_for(self, *texts: str) -> str:
        from .. import html_slides

        name = html_slides._pick_icon([t for t in texts if t], self.used_icons)
        self.used_icons.add(name)
        return name


# ───────────────────────────────────────────── umumiy bo'laklar

def bg_dark(c: Ctx, focus=(50, 45)):
    p = c.pal
    r = rect(c.slide, 0, 0, 1920, 1080)
    grad(r, [(0, mix(p.dark, p.accent, 0.28)), (60, p.dark), (100, p.deep)], radial=True, focus=focus)


def bg_light(c: Ctx):
    r = rect(c.slide, 0, 0, 1920, 1080)
    grad(r, [(0, WHITE), (100, mix(WHITE, c.pal.accent, 0.07))], radial=True)


def heading(c: Ctx, title: str, lead: str = "", dark: bool = False, align=LEFT, x=110, w=1700) -> float:
    p = c.pal
    text(c.slide, x, 52, w, 96, [[(title, 60, WHITE if dark else p.ink, True, p.head_font)]],
         align=align, anchor=BOTTOM)
    if lead:
        text(c.slide, x, 154, w, 70, [[(lead, 30, p.on_dark if dark else p.muted)]], align=align)
        return 240
    fill(rect(c.slide, x if align == LEFT else x + w / 2 - 60, 160, 120, 6), p.accent if not dark else p.glowing)
    return 200


def label(c: Ctx, x, y, w, h, item: Dict, align=LEFT, dark=False, tsize=35, nsize=31, anchor=TOP):
    p = c.pal
    paras = []
    if item.get("value"):
        paras.append([(item["value"], 46, p.glowing if dark else p.accent, True, p.head_font)])
    if item.get("title"):
        paras.append([(item["title"].upper(), tsize, WHITE if dark else p.ink, True, SANS, 60)])
    if item.get("note"):
        paras.append([(item["note"], nsize, p.on_dark if dark else p.muted)])
    return text(c.slide, x, y, w, h, paras, align=align, anchor=anchor, gap=8, line_spacing=1.1)


def spread(n: int, a: float, b: float) -> List[float]:
    if n == 1:
        return [(a + b) / 2]
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def no_photo_fill(c: Ctx, x, y, w, h):
    """Rasm yo'q (bepul sinov yoki rasm chizilmadi): o'rnida rangli maydon va katta ikonka."""
    p = c.pal
    r = rect(c.slide, x, y, w, h)
    grad(r, [(0, mix(p.accent, p.dark, 0.2)), (100, p.deep)], angle=60)
    icon(c.slide, c.topic_icon, x + w / 2, y + h / 2, min(w, h) * 0.45, mix(p.dark, WHITE, 0.18))


# ═════════════════════════════════════════════ MUQOVA

def cover_x(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    navy = p.dark
    fill(rect(s, 0, 0, 1920, 1080), navy)
    pic = spec.get("photo_obj")
    if pic:
        photo(s, pic, 700, 0, 1220, 1080)
    else:
        no_photo_fill(c, 700, 0, 1220, 1080)
    fill(poly(s, [(1300, 0), (1920, 0), (1920, 380)]), WHITE, 10)
    fill(poly(s, [(1180, 1080), (1560, 520), (1920, 1080)]), WHITE, 8)
    fill(poly(s, [(1150, 0), (1192, 0), (1720, 1080), (1678, 1080)]), navy)
    fill(poly(s, [(1520, 0), (1562, 0), (1012, 1080), (970, 1080)]), navy)
    left = poly(s, [(0, 0), (760, 0), (1060, 480), (830, 1080), (0, 1080)])
    grad(left, [(0, mix(navy, WHITE, 0.08)), (100, mix(navy, "000000", 0.15))], angle=90)
    shadow(left, blur=40, dist=0, alpha=55)
    icon(s, c.topic_icon, 250, 230, 480, mix(navy, WHITE, 0.12))
    t = text(s, 110, 170, 860, 440, [[(spec["title"].upper(), 104, WHITE, True, p.head_font, -60)]],
             anchor=BOTTOM, line_spacing=1.0, min_scale=0.38)
    shadow(t, blur=18, dist=8, alpha=55)
    if spec.get("lead"):
        text(s, 116, 630, 820, 170, [[(spec["lead"], 46, p.glowing, True, SERIF, 0, True)]], line_spacing=1.05)
    if spec.get("credit"):
        text(s, 118, 900, 820, 80, [[(spec["credit"], 24, p.on_dark)]])


def cover_hex(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    base = rect(s, 0, 0, 1920, 1080)
    grad(base, [(0, mix(p.accent, WHITE, 0.12)), (100, mix(p.accent, p.dark, 0.3))], angle=60)
    for cx, cy, r, a in [(180, 90, 140, 25), (520, 230, 60, 40), (210, 760, 230, 18), (640, 960, 90, 30)]:
        h = box(s, cx - r, cy - r * 0.87, 2 * r, 1.74 * r, SHAPE.HEXAGON)
        nofill(h); line(h, WHITE, 3, a)
    pic = spec.get("photo_obj")
    region = (860, -60, 1060, 1200)
    R = 150
    hgt = math.sqrt(3) * R
    ramp = p.ramp(4, 0.3, 0.5)
    k = 0
    for col in range(5):
        for row in range(-1, 7):
            cx = 980 + col * (1.5 * R + 10)
            cy = row * (hgt + 10) + (col % 2) * (hgt + 10) / 2
            if cy + hgt / 2 < 0 or cy - hgt / 2 > 1080:
                continue
            if col == 0 and row in (-1, 0, 5, 6):
                continue
            if pic:
                photo(s, pic, cx - R, cy - hgt / 2, 2 * R, hgt, geom="hexagon", region=region)
            else:
                hx = box(s, cx - R, cy - hgt / 2, 2 * R, hgt, SHAPE.HEXAGON)
                grad(hx, [(0, ramp[k % 4]), (100, mix(ramp[k % 4], p.dark, 0.25))], angle=90)
                k += 1
    t = text(s, 110, 90, 740, 470, [[(spec["title"].upper(), 100, WHITE, True, p.head_font, -60)]],
             anchor=BOTTOM, line_spacing=1.0, min_scale=0.36)
    shadow(t, blur=20, dist=6, alpha=30, color=mix(p.accent, "000000", 0.6))
    if spec.get("lead"):
        text(s, 120, 590, 700, 200, [[(spec["lead"], 44, WHITE, True, SERIF, 0, True)]], line_spacing=1.05)
    if spec.get("credit"):
        text(s, 120, 900, 700, 80, [[(spec["credit"], 24, mix(p.accent, p.dark, 0.75))]])


# ═════════════════════════════════════════════ REJA

def plan_glass(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    if c.cover:
        photo(s, c.cover, 0, 0, 1920, 1080)
    else:
        bg_dark(c, focus=(30, 50))
    shade = rect(s, 0, 0, 1920, 1080)
    grad(shade, [(0, p.deep, 88), (55, p.deep, 62), (100, p.deep, 38)], angle=0)
    for dx, a in [(0, 30), (120, 18)]:
        ch = poly(s, [(-200 + dx, 120), (220 + dx, 540), (-200 + dx, 960)], close=False)
        nofill(ch); line(ch, WHITE, 6, a)
    cols = 3 if n in (3, 5, 6) else 2 if n == 4 else 4
    rows = math.ceil(n / cols)
    if cols <= 2:
        area = (980, 150, 1820, 930)
        num_box, title_box = (150, 280, 760, 320), (160, 620, 700, 220)
    elif cols == 3:
        area = (860, 170, 1820, 910)
        num_box, title_box = (140, 300, 660, 300), (150, 620, 640, 220)
    else:
        area = (110, 330, 1810, 970)
        num_box, title_box = (110, 40, 460, 270), (560, 120, 1200, 150)
    x0, y0, x1, y1 = area
    gap = 36
    cw = (x1 - x0 - gap * (cols - 1)) / cols
    chh = (y1 - y0 - gap * (rows - 1)) / rows
    text(s, *num_box, [[(f"{n:02d}", 280, WHITE, True, p.head_font, -200)]], anchor=MIDDLE)
    text(s, *title_box, [[(spec["title"], 50, WHITE, True, p.head_font)]], anchor=TOP if cols <= 3 else MIDDLE)
    for i, item in enumerate(items):
        x = x0 + (i % cols) * (cw + gap)
        y = y0 + (i // cols) * (chh + gap)
        card = box(s, x, y, cw, chh, SHAPE.ROUNDED_RECTANGLE, adj=[0.07])
        grad(card, [(0, WHITE, 22), (100, WHITE, 8)], angle=135)
        line(card, WHITE, 2, 55)
        shadow(card, blur=40, dist=12, alpha=35)
        ic = c.icon_for(item["title"])
        size = min(cw, chh) * 0.24
        icon(s, ic, x + cw / 2, y + chh * 0.27, size, WHITE)
        text(s, x + 20, y + chh * 0.46, cw - 40, 44, [[(f"{i + 1:02d}", 30, p.glowing, True, p.head_font)]],
             align=CENTER)
        text(s, x + 24, y + chh * 0.46 + 46, cw - 48, chh * 0.54 - 66,
             [[(item["title"].upper(), 28, WHITE, True, SANS, 40)]], align=CENTER, line_spacing=1.08)


def plan_wave(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    heading(c, spec["title"], "")
    xs = spread(n, 230, 1690)
    step = (xs[1] - xs[0]) if n > 1 else 600
    r = min(118.0, step * 0.34)
    hi, lo = 440, 730
    ys = [lo if i % 2 == 0 else hi for i in range(n)]
    pts = []
    for i in range(n - 1):
        for k in range(36):
            t = k / 36
            pts.append((xs[i] + (xs[i + 1] - xs[i]) * t, ys[i] + (ys[i + 1] - ys[i]) * (1 - math.cos(math.pi * t)) / 2))
    pts.append((xs[-1], ys[-1]))
    road = poly(s, ribbon(pts, r * 0.5))
    grad(road, [(0, mix(p.accent, WHITE, 0.3)), (100, p.accent)], angle=0)
    shadow(road, blur=24, dist=8, alpha=25)
    ramp = p.ramp(n, 0.3, 0.3)
    tw = min(340, step * 0.8)
    for i, item in enumerate(items):
        cx, cy = xs[i], ys[i]
        outer = oval(s, cx, cy, r)
        grad(outer, [(0, mix(ramp[i], WHITE, 0.25)), (100, mix(ramp[i], p.dark, 0.15))], angle=45)
        shadow(outer, blur=30, dist=12, alpha=35)
        inner = oval(s, cx, cy, r * 0.78)
        grad(inner, [(0, WHITE), (100, mix(WHITE, p.ink, 0.12))], angle=90)
        inner_shadow(inner, blur=16, dist=6, alpha=30)
        text(s, cx - r, cy - r * 0.45, 2 * r, r * 0.9, [[(f"{i + 1:02d}", r * 0.6, p.ink, True, p.head_font)]],
             align=CENTER, anchor=MIDDLE, fit=False)
        # Pastdagi doira — yozuv ostida, yuqoridagi doira — yozuv ustida (lentaga tegmaydi).
        if cy > 600:
            ty, th, anchor = cy + r + 22, min(150, 1050 - (cy + r + 22)), TOP
        else:
            ty, th, anchor = 215, cy - r - 14 - 215, BOTTOM
        text(s, cx - tw / 2, ty, tw, th, [[(item["title"].upper(), 28, p.ink, True, SANS, 30)]],
             align=CENTER, anchor=anchor, line_spacing=1.08)


# ═════════════════════════════════════════════ RASMLI VARAQ (tasodifiy shakl)

def _band_text(c: Ctx, spec: Dict, x, w):
    s, p = c.slide, c.pal
    soft = mix(p.accent, WHITE, 0.82)
    if spec.get("quote"):
        paras = [[(spec["title"].upper(), 24, soft, True, SANS, 200)],
                 [("“" + spec["quote"] + "”", 42, WHITE, False, SERIF, 0, True)]]
        if spec.get("by"):
            paras.append([("— " + spec["by"], 24, soft, True)])
        if spec.get("text"):
            paras.append([(spec["text"], 22, soft)])
    else:
        paras = [[(spec["title"].upper(), 62, WHITE, True, p.head_font)]]
        if spec.get("lead"):
            paras.append([(spec["lead"], 34, WHITE, True)])
        if spec.get("text"):
            paras.append([(spec["text"], 28, soft)])
    text(s, x, 150, w, 780, paras, anchor=MIDDLE, gap=26, line_spacing=1.12)


def _band_photo(c: Ctx, spec: Dict, x, y, w, h):
    if spec.get("photo_obj"):
        photo(c.slide, spec["photo_obj"], x, y, w, h)
    else:
        no_photo_fill(c, x, y, w, h)


def band_right(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    slant = c.rng.randint(330, 470)
    _band_photo(c, spec, 0, 0, 1920, 1080)
    band = poly(s, [(800, 0), (1920, 0), (1920, 1080), (800 + slant, 1080)])
    grad(band, [(0, p.accent, 93), (100, mix(p.accent, p.dark, 0.4), 96)], angle=90)
    shadow(band, blur=40, dist=0, alpha=40)
    edge = poly(s, [(770, 0), (790, 0), (790 + slant, 1080), (770 + slant, 1080)])
    fill(edge, p.glowing, 70)
    _band_text(c, spec, 800 + slant + 40, 1920 - (800 + slant + 40) - 100)


def band_left(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    slant = c.rng.randint(330, 470)
    _band_photo(c, spec, 0, 0, 1920, 1080)
    band = poly(s, [(0, 0), (1120 - slant, 0), (1120, 1080), (0, 1080)])
    grad(band, [(0, p.dark, 94), (100, mix(p.dark, p.accent, 0.35), 92)], angle=90)
    shadow(band, blur=40, dist=0, alpha=40)
    edge = poly(s, [(1120 - slant, 0), (1144 - slant, 0), (1144, 1080), (1120, 1080)])
    fill(edge, p.accent, 85)
    _band_text(c, spec, 110, 1120 - slant - 160)


def band_chevron(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    tip = c.rng.randint(760, 860)
    _band_photo(c, spec, 0, 0, 1920, 1080)
    band = poly(s, [(tip + 200, 0), (1920, 0), (1920, 1080), (tip + 200, 1080), (tip, 540)])
    grad(band, [(0, mix(p.accent, p.dark, 0.15), 94), (100, p.dark, 96)], angle=135)
    shadow(band, blur=40, dist=0, alpha=45)
    for k, a in ((0, 70), (60, 35)):
        ch = poly(s, [(tip + 140 - k, 0), (tip - 60 - k, 540), (tip + 140 - k, 1080)], close=False)
        nofill(ch); line(ch, p.glowing, 6, a)
    _band_text(c, spec, tip + 260, 1920 - tip - 360)


# ═════════════════════════════════════════════ INFOGRAFIKALAR

def info_swirl(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_dark(c)
    heading(c, spec["title"], spec.get("lead", ""), dark=True)
    cx, cy, d, r = 960, 625, 112, 165
    ramp = p.ramp(n, 0.6, 0.4)
    centers = []
    for i in range(n):
        a = -90 + i * 360 / n
        x, y = cx + d * math.cos(math.radians(a)), cy + d * math.sin(math.radians(a))
        centers.append((x, y, a))
        o = oval(s, x, y, r)
        grad(o, [(0, mix(ramp[i], WHITE, 0.2)), (100, ramp[i])], angle=a + 90)
        shadow(o, blur=45, dist=14, angle=a + 120, alpha=55)
    x, y, a = centers[0]
    half = poly(s, arc_pts(x, y, r, 90, 270, 60))
    grad(half, [(0, mix(ramp[0], WHITE, 0.2)), (100, ramp[0])], angle=a + 90)
    shadow(half, blur=45, dist=14, angle=a + 120, alpha=55)
    hole = oval(s, cx, cy, 56)
    fill(hole, p.dark)
    inner_shadow(hole, blur=24, dist=8, alpha=70)
    left = math.ceil(n / 2)
    for i, item in enumerate(items):
        on_left = i < left
        k = i if on_left else i - left
        m = left if on_left else n - left
        y = spread(m, 330, 900)[k] - 80
        num = item.get("value") or str(i + 1)
        if on_left:
            text(s, 500, y, 150, 160, [[(num if not item.get("value") else str(i + 1), 110, p.on_dark, False, SANS)]],
                 align=CENTER, anchor=MIDDLE, fit=False)
            label(c, 40, y - 45, 470, 250, item, align=RIGHT, dark=True, tsize=34, nsize=30, anchor=MIDDLE)
        else:
            text(s, 1270, y, 150, 160, [[(str(i + 1), 110, p.on_dark, False, SANS)]],
                 align=CENTER, anchor=MIDDLE, fit=False)
            label(c, 1410, y - 45, 480, 250, item, align=LEFT, dark=True, tsize=34, nsize=30, anchor=MIDDLE)


def info_tree(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_dark(c)
    heading(c, spec["title"], spec.get("lead", ""), dark=True, align=CENTER, x=110, w=1700)
    trunk = poly(s, [(925, 1060), (995, 1060), (980, 840), (1060, 660), (1040, 650), (972, 790), (966, 580),
                     (950, 580), (946, 780), (870, 630), (850, 642), (938, 840)])
    grad(trunk, [(0, "8D6E63"), (100, "5D4037")], angle=0)
    for x, y, r in [(790, 540, 60), (870, 450, 68), (1060, 440, 64), (1150, 540, 58), (960, 380, 62),
                    (720, 660, 46), (1210, 670, 44), (1000, 580, 54), (900, 590, 48), (1100, 350, 42)]:
        o = oval(s, x, y, r)
        grad(o, [(0, WHITE), (100, mix(WHITE, p.dark, 0.15))], angle=60)
        shadow(o, blur=26, dist=8, alpha=45)
    spots = [(700, 490, 74), (880, 320, 76), (1080, 290, 74), (1240, 450, 76), (1020, 490, 70), (820, 660, 68)]
    ramp = p.ramp(n, 0.35, 0.35)
    for i, item in enumerate(items):
        x, y, r = spots[i]
        o = oval(s, x, y, r)
        grad(o, [(0, mix(ramp[i], WHITE, 0.25)), (100, ramp[i])], angle=45)
        shadow(o, blur=30, dist=10, alpha=50)
        ic = c.icon_for(item.get("title", ""), item.get("note", ""))
        item["_icon"] = ic
        icon(s, ic, x, y, r * 0.95, WHITE)
    left = math.ceil(n / 2)
    for i, item in enumerate(items):
        on_left = i < left
        k = i if on_left else i - left
        m = left if on_left else n - left
        y = spread(m, 330, 860)[k] - 30
        x = 110 if on_left else 1430
        icon(s, item["_icon"], x + 380 - 26 if on_left else x + 26, y - 6, 48, ramp[i])
        label(c, x - (70 if on_left else 0), y + 30, 470, 240, item, align=RIGHT if on_left else LEFT, dark=True, tsize=34, nsize=30)


def info_fan(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_dark(c, focus=(50, 75))
    heading(c, spec["title"], spec.get("lead", ""), dark=True, align=CENTER, x=110, w=1700)
    cx, cy = 960, 1060
    span = 180 / n
    tones = p.ramp(n, 0.25, 0.25)
    for i, item in enumerate(items):
        a0, a1 = 180 - i * span - 1.2, 180 - (i + 1) * span + 1.2
        mid = (a0 + a1) / 2
        tip = (cx + 470 * math.cos(math.radians(mid)), cy - 470 * math.sin(math.radians(mid)))
        half1 = poly(s, arc_pts(cx, cy, 150, a0, mid, 12) + [tip] + arc_pts(cx, cy, 330, a0, a0, 1)[:1])
        grad(half1, [(0, mix(tones[i], p.dark, 0.1)), (100, mix(tones[i], p.dark, 0.5))], angle=90 - mid)
        half2 = poly(s, arc_pts(cx, cy, 150, mid, a1, 12) + arc_pts(cx, cy, 330, a1, a1, 1)[:1] + [tip])
        grad(half2, [(0, mix(tones[i], WHITE, 0.15)), (100, mix(tones[i], p.dark, 0.3))], angle=90 - mid)
        shadow(half2, blur=30, dist=10, angle=270, alpha=50)
        rr = 640 if n <= 4 else 650
        # Yozuv pat uchidan YUQORIDA turadi (pastki cheti uchdan 20 px tepada) — patga tegmaydi.
        lx = cx + rr * math.cos(math.radians(mid))
        bottom = min(tip[1] - 20, 1040)
        w = 470 if n <= 4 else 390 if n <= 5 else 330
        h = 230
        bx = max(40, min(lx - w / 2, 1880 - w))
        ic = c.icon_for(item.get("title", ""), item.get("note", ""))
        icon(s, ic, bx + w / 2, bottom - h - 30, 54, p.glowing)
        label(c, bx, bottom - h, w, h, item, align=CENTER, dark=True, tsize=33, nsize=29, anchor=BOTTOM)
    hub = oval(s, cx, cy, 175)
    grad(hub, [(0, mix(p.accent, p.dark, 0.35)), (100, p.deep)], angle=90)
    shadow(hub, blur=40, dist=0, alpha=70)
    text(s, cx - 150, cy - 165, 300, 160, [[(str(n), 150, p.glowing, True, p.head_font)]], align=CENTER,
         anchor=MIDDLE, fit=False)


def info_pencil(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    heading(c, spec["title"], spec.get("lead", ""))
    cx = 960
    ys = spread(n, 330, 820)
    tones = [p.accent, mix(p.accent, p.dark, 0.3)]
    for i, y in enumerate(ys):
        side = -1 if i % 2 == 0 else 1
        x0, x1 = cx - side * 70, cx + side * 10
        fold = poly(s, [(x0, y - 20), (x1, y - 50), (x1, y + 20), (x0, y + 50)])
        grad(fold, [(0, mix(WHITE, p.ink, 0.15)), (100, mix(WHITE, p.ink, 0.45))], angle=0 if side > 0 else 180)
    top, bottom = 250, 880
    for x, w, a, b in [(cx - 40, 27, "F9C74F", "F3A712"), (cx - 13, 26, "FFE08A", "F9C74F"),
                       (cx + 13, 27, "F3A712", "D98C00")]:
        grad(rect(s, x, top, w, bottom - top), [(0, a), (100, b)], angle=0)
    grad(box(s, cx - 40, top - 90, 80, 50, SHAPE.ROUNDED_RECTANGLE, adj=[0.3]), [(0, "F48FB1"), (100, "D81B60")], angle=0)
    grad(rect(s, cx - 42, top - 45, 84, 50), [(0, "9EA4AA"), (50, "F2F4F6"), (100, "7D838A")], angle=0)
    for k in range(3):
        fill(rect(s, cx - 42, top - 36 + k * 13, 84, 3), "6D737A", 70)
    grad(poly(s, [(cx - 40, bottom), (cx + 40, bottom), (cx + 10, bottom + 85), (cx - 10, bottom + 85)]),
         [(0, "F1D3A8"), (100, "C99A62")], angle=0)
    fill(poly(s, [(cx - 10, bottom + 85), (cx + 10, bottom + 85), (cx, bottom + 115)]), "2F2F2F")
    for i, (item, y) in enumerate(zip(items, ys)):
        side = -1 if i % 2 == 0 else 1
        L, hgt, head = 400, 76, 56
        base = cx + side * 30
        tipx = cx + side * L
        pts = [(base, y - hgt / 2), (tipx - side * head, y - hgt / 2), (tipx - side * head, y - hgt / 2 - 14),
               (tipx, y), (tipx - side * head, y + hgt / 2 + 14), (tipx - side * head, y + hgt / 2), (base, y + hgt / 2)]
        arr = poly(s, pts)
        col = tones[i % 2]
        grad(arr, [(0, mix(col, WHITE, 0.2)), (100, col)], angle=90)
        shadow(arr, blur=20, dist=8, alpha=35)
        tx = base + (34 if side > 0 else -330)
        text(s, tx, y - 34, 300, 68, [[(f"{i + 1:02d}  ", 30, WHITE, True, p.head_font),
                                       ((item.get("value") or item.get("title", "")).upper(), 21, WHITE, True, SANS, 40)]],
             align=LEFT if side > 0 else RIGHT, anchor=MIDDLE, line_spacing=1.0)
        bx = tipx + 50 if side > 0 else tipx - 50 - 400
        ic = c.icon_for(item.get("title", ""), item.get("note", ""))
        icon(s, ic, bx + (28 if side > 0 else 372), y - 74, 50, mix(p.muted, WHITE, 0.2))
        note = item.get("note") or ""
        if item.get("value"):
            note = (item.get("title", "") + ". " + note).strip(". ")
        text(s, bx - (0 if side > 0 else 40), y - 44, 460, 160, [[(note, 30, p.body)]], align=LEFT if side > 0 else RIGHT)


def info_leaves(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    heading(c, spec["title"], spec.get("lead", ""))
    greens = [(mix(p.accent, WHITE, 0.35), mix(p.accent, p.dark, 0.2)),
              (p.accent, mix(p.accent, p.dark, 0.45)),
              (mix(p.accent, WHITE, 0.55), mix(p.accent, p.dark, 0.05))]

    def leaf(x, y, L, wd, ang, a, b):
        half = [(L * k / 24, -wd / 2 * math.sin(math.pi * k / 24) ** 0.7) for k in range(25)]
        other = [(L * k / 24, wd / 2 * math.sin(math.pi * k / 24) ** 0.7) for k in range(24, -1, -1)]
        lf = poly(s, rotate(half + other, ang, x, y))
        grad(lf, [(0, a), (100, b)], angle=ang)
        shadow(lf, blur=14, dist=5, angle=ang + 90, alpha=28)
        v = poly(s, rotate([(L * 0.08, 0), (L * 0.8, 0)], ang, x, y), close=False)
        nofill(v); line(v, WHITE, 1.5, 40)

    # "S" chizig'i: ikki yarim aylana. Barglar shu chiziq bo'ylab zich, pat kabi ustma-ust taxlanadi:
    # har biri chiziqqa urinma bo'yicha bir tomonga qiyshaygan, o'rtada kattaroq, uchlarida kichikroq.
    cx, top_y, bot_y, R = 960, 480, 760, 140
    path = []
    for k in range(13):
        a = 20 + 250 * k / 12                       # yuqori yoy: o'ng-yuqoridan chapga, pastga
        path.append((cx + R * math.cos(math.radians(a)), top_y - R * math.sin(math.radians(a))))
    for k in range(1, 13):
        a = 90 - 250 * k / 12                       # pastki yoy: tepadan o'ngga, pastga, chapga
        path.append((cx + R * math.cos(math.radians(a)), bot_y - R * math.sin(math.radians(a))))
    m = len(path)
    for i in range(m):
        x, y = path[i]
        nx, ny = path[min(i + 1, m - 1)]
        px_, py_ = path[max(i - 1, 0)]
        tangent = math.degrees(math.atan2(ny - py_, nx - px_))
        t = i / (m - 1)
        size = 112 + 70 * math.sin(math.pi * t)
        shade = greens[i % 3]
        leaf(x, y, size, size * 0.42, tangent - 50, *shade)
    left = math.ceil(n / 2)
    for i, item in enumerate(items):
        on_left = i < left
        k = i if on_left else i - left
        m = left if on_left else n - left
        y = spread(m, 360, 760)[k] if m > 1 else 560
        x = 140 if on_left else 1380
        ic = c.icon_for(item.get("title", ""), item.get("note", ""))
        icon(s, ic, x + (400 - 28 if on_left else 28), y - 30, 50, p.accent)
        label(c, x - (90 if on_left else 0), y + 6, 490, 250, item, align=RIGHT if on_left else LEFT, tsize=35, nsize=31)


def info_arcs(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_dark(c, focus=(40, 50))
    ring = oval(s, 0, 1000, 380)
    nofill(ring); line(ring, mix(p.dark, p.accent, 0.5), 3)
    top = heading(c, spec["title"], spec.get("lead", ""), dark=True)
    cx, base, R = 880, 1030, 370 if top > 210 else 395
    ramp = p.ramp(n, 0.55, 0.3)[::-1]
    for i in range(n):
        r = R * (1 - i / (n + 0.6))
        half = poly(s, arc_pts(cx, base - r, r, 90, 270, 90))
        grad(half, [(0, mix(ramp[i], WHITE, 0.15)), (100, mix(ramp[i], p.dark, 0.35))], angle=135)
        shadow(half, blur=50, dist=14, angle=0, alpha=60)
    y0 = top + 40
    step = (1030 - y0) / n
    for i, item in enumerate(items):
        y = y0 + i * step
        num = f"{i + 1:02d}"
        text(s, 970, y, 130, step, [[(num, 58, p.glowing, True, p.head_font)]], anchor=MIDDLE, fit=False)
        sub = dict(item)
        label(c, 1100, y + 4, 720, step - 8, sub, dark=True, tsize=34 if n <= 5 else 29, nsize=30 if n <= 5 else 25,
              anchor=MIDDLE)
        if i < n - 1:
            ln_ = rect(s, 1100, y + step - 1, 700, 2)
            grad(ln_, [(0, mix(p.dark, p.accent, 0.5)), (100, mix(p.dark, p.accent, 0.5), 0)], angle=0)


def info_arrows(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    heading(c, spec["title"], spec.get("lead", ""), align=CENTER)
    cx, cy = 960, 640
    seg = 360 / n
    for i, item in enumerate(items):
        a0 = 90 - i * seg - 4
        a1 = a0 - seg + 16
        sec = ring_sector(s, cx, cy, 220, 280, a0, a1)
        grad(sec, [(0, mix(p.accent, WHITE, 0.3)), (100, mix(p.accent, p.dark, 0.25))], angle=-a0)
        tip = (cx + 250 * math.cos(math.radians(a1 - 12)), cy - 250 * math.sin(math.radians(a1 - 12)))
        head = poly(s, [(cx + 200 * math.cos(math.radians(a1)), cy - 200 * math.sin(math.radians(a1))),
                        (cx + 300 * math.cos(math.radians(a1)), cy - 300 * math.sin(math.radians(a1))), tip])
        fill(head, mix(p.accent, p.dark, 0.3))
        am = math.radians(a0 - seg / 2 + 6)
        ic = c.icon_for(item.get("title", ""), item.get("note", ""))
        icon(s, ic, cx + 250 * math.cos(am), cy - 250 * math.sin(am), 40, WHITE)
        lx, ly = cx + 470 * math.cos(am), cy - 360 * math.sin(am)
        cs = math.cos(am)
        al = LEFT if cs > 0.25 else RIGHT if cs < -0.25 else CENTER
        w = 470 if al != CENTER else 600
        bx = lx - 10 if al == LEFT else lx - w + 10 if al == RIGHT else lx - w / 2
        bx = max(60, min(bx, 1860 - w))
        by = max(225, min(ly - 90, 880))
        label(c, bx, by, w, 190, item, align=al, tsize=32, nsize=29, anchor=MIDDLE)
    hub = oval(s, cx, cy, 165)
    fill(hub, WHITE); shadow(hub, blur=30, dist=0, alpha=25)
    icon(s, c.topic_icon, cx, cy, 130, p.accent)


def info_pie(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    heading(c, spec["title"], spec.get("lead", ""))
    cx, cy = 960, 630
    seg = 360 / n
    shades = [p.accent, mix(p.accent, WHITE, 0.45), p.dark, mix(p.dark, WHITE, 0.4), mix(p.accent, p.dark, 0.5),
              mix(p.accent, WHITE, 0.7)]
    for i, item in enumerate(items):
        a0, a1 = 90 - i * seg - 0.8, 90 - (i + 1) * seg + 0.8
        sec = ring_sector(s, cx, cy, 120, 330, a0, a1)
        col = shades[i % len(shades)]
        fill(sec, col); shadow(sec, blur=20, dist=6, alpha=30)
        mid = math.radians((a0 + a1) / 2)
        mx, my = cx + 225 * math.cos(mid), cy - 225 * math.sin(mid)
        ink = WHITE if luminance(col) < 0.6 else p.ink
        ic = c.icon_for(item.get("title", ""), item.get("note", ""))
        icon(s, ic, mx, my - 18, 52, ink)
        text(s, mx - 60, my + 16, 120, 40, [[(f"{i + 1:02d}", 22, ink, True, p.head_font)]], align=CENTER, fit=False)
        right = math.cos(mid) >= 0
        ly = cy - 330 * math.sin(mid)
        bx = 1340 if right else 110
        label(c, bx - (0 if right else 40), max(225, min(ly - 100, 850)), 510, 210, item, align=LEFT if right else RIGHT,
              anchor=MIDDLE, tsize=34, nsize=30)
    hub = oval(s, cx, cy, 110); fill(hub, WHITE); shadow(hub, blur=20, dist=0, alpha=30)
    icon(s, c.topic_icon, cx, cy, 90, p.accent)


def info_cross(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    bg_light(c)
    heading(c, spec["title"], spec.get("lead", ""), align=CENTER)
    cx, cy = 960, 640
    for ang, col in ((45, p.accent), (-45, mix(p.accent, p.dark, 0.3))):
        bar = box(s, cx - 330, cy - 70, 660, 140, SHAPE.ROUNDED_RECTANGLE, rot=ang, adj=[0.5])
        grad(bar, [(0, col), (100, mix(p.accent, WHITE, 0.35))], angle=0)
        shadow(bar, blur=24, dist=8, alpha=30)
    hub = oval(s, cx, cy, 110); fill(hub, WHITE); line(hub, p.accent, 10); shadow(hub, blur=20, dist=0, alpha=30)
    icon(s, c.topic_icon, cx, cy, 110, p.accent)
    for item, (sx, sy) in zip(items, [(-1, -1), (1, -1), (-1, 1), (1, 1)]):
        ic = c.icon_for(item.get("title", ""), item.get("note", ""))
        icon(s, ic, cx + sx * 215, cy + sy * 215, 64, WHITE)
        x = cx + sx * 380 + (0 if sx > 0 else -520)
        label(c, x - (0 if sx > 0 else 30), cy + sy * 250 - 125, 560, 250, item, align=LEFT if sx > 0 else RIGHT, anchor=MIDDLE)


def info_diamond(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    bg_light(c)
    heading(c, spec["title"], spec.get("lead", ""), align=CENTER)
    cx, cy = 960, 660
    for i, item in enumerate(items):
        a = 90 - i * 90
        x, y = cx + 130 * math.cos(math.radians(a)), cy - 130 * math.sin(math.radians(a))
        d = box(s, x - 95, y - 95, 190, 190, SHAPE.ROUNDED_RECTANGLE, rot=45, adj=[0.22])
        grad(d, [(0, mix(p.accent, WHITE, 0.35)), (100, p.accent if i % 2 == 0 else mix(p.accent, p.dark, 0.3))],
             angle=45)
        shadow(d, blur=24, dist=8, alpha=30)
        ic = c.icon_for(item.get("title", ""), item.get("note", ""))
        icon(s, ic, x, y, 70, WHITE)
    oval_ = oval(s, cx, cy, 30); fill(oval_, WHITE)
    spots = [(cx - 420, 222, 840, 160, CENTER, BOTTOM), (1260, cy - 130, 600, 260, LEFT, MIDDLE),
             (cx - 420, 935, 840, 135, CENTER, TOP), (60, cy - 130, 600, 260, RIGHT, MIDDLE)]
    for item, (x, y, w, h, al, an) in zip(items, spots):
        label(c, x, y, w, h, item, align=al, anchor=an, tsize=34, nsize=30)


# ═════════════════════════════════════════════ QIYOS

def compare_gears(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    bg_dark(c)
    text(s, 110, 40, 1700, 90, [[(spec["title"], 50, WHITE, True, p.head_font)]], align=CENTER, anchor=MIDDLE)
    bar = box(s, 690, 520, 540, 80, SHAPE.ROUNDED_RECTANGLE, adj=[0.5])
    grad(bar, [(0, WHITE), (100, mix(WHITE, p.dark, 0.25))], angle=90)
    shadow(bar, blur=30, dist=8, alpha=50)
    for gx, letter, side, angles in [(560, "A", spec["sides"][0], (270, 210, 150, 90)),
                                     (1360, "B", spec["sides"][1], (270, 330, 30, 90))]:
        for k, (t, a) in enumerate(zip(side["items"][:4], angles)):
            hx = gx + 300 * math.cos(math.radians(a))
            hy = 570 + 300 * math.sin(math.radians(a))
            hexa = box(s, hx - 130, hy - 112, 260, 224, SHAPE.HEXAGON)
            grad(hexa, [(0, WHITE), (100, mix(WHITE, p.dark, 0.18))], angle=90)
            shadow(hexa, blur=30, dist=10, alpha=55)
            text(s, hx - 100, hy - 98, 200, 34, [[(f"{k + 1:02d}", 24, p.accent, True, p.head_font)]],
                 align=CENTER, fit=False)
            ic = c.icon_for(t)
            icon(s, ic, hx, hy - 32, 46, mix(p.dark, WHITE, 0.15))
            text(s, hx - 100, hy, 200, 100, [[(t, 25, p.ink, True)]], align=CENTER, anchor=TOP, line_spacing=1.05)
        g = box(s, gx - 140, 430, 280, 280, SHAPE.GEAR_9)
        grad(g, [(0, mix(p.accent, WHITE, 0.35)), (100, mix(p.accent, p.dark, 0.25))], angle=45)
        shadow(g, blur=30, dist=8, alpha=60)
        glow(g, 18, p.accent, 35)
        core = oval(s, gx, 570, 82)
        grad(core, [(0, WHITE), (100, mix(WHITE, p.accent, 0.2))], angle=90)
        inner_shadow(core, blur=14, dist=5, alpha=35)
        text(s, gx - 80, 510, 160, 120, [[(letter, 80, p.accent, True, p.head_font)]], align=CENTER, anchor=MIDDLE,
             fit=False)
        text(s, gx - 260, 960, 520, 70, [[(side["name"].upper(), 28, p.glowing, True, SANS, 200)]], align=CENTER,
             anchor=MIDDLE)


# ═════════════════════════════════════════════ XULOSA

def finale(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    base = rect(s, 0, 0, 1920, 1080)
    grad(base, [(0, mix(p.dark, p.accent, 0.3)), (100, p.deep)], angle=45)
    for r, a in ((520, 30), (400, 22), (280, 14)):
        ring = oval(s, 1920, 1080, r)
        nofill(ring); line(ring, p.glowing, 3, a)
    big = oval(s, 1790, 160, 210)
    grad(big, [(0, p.accent, 40), (100, p.accent, 0)], radial=True)
    text(s, 160, 110, 1500, 60, [[(spec.get("title", "").upper(), 28, p.glowing, True, SANS, 300)]])
    fill(rect(s, 160, 180, 140, 8), p.accent)
    text(s, 160, 220, 1440, 330, [[(spec.get("lead", ""), 60, WHITE, True, p.head_font)]], anchor=MIDDLE,
         line_spacing=1.1)
    points = spec.get("points") or []
    ys = spread(len(points), 640, 920) if points else []
    for i, (t, y) in enumerate(zip(points[:4], ys)):
        o = oval(s, 200, y, 34)
        grad(o, [(0, mix(p.accent, WHITE, 0.25)), (100, p.accent)], angle=90)
        shadow(o, blur=14, dist=4, alpha=40)
        text(s, 170, y - 30, 60, 60, [[(str(i + 1), 28, WHITE, True, p.head_font)]], align=CENTER, anchor=MIDDLE,
             fit=False)
        text(s, 270, y - 40, 1380, 80, [[(t, 32, p.on_dark)]], anchor=MIDDLE)


# ═════════════════════════════════════════════ ro'yxat

@dataclass(frozen=True)
class Style:
    name: str
    kinds: tuple
    min_items: int
    max_items: int
    draw: Callable


STYLES = [
    Style("cover_x", ("cover",), 0, 99, cover_x),
    Style("cover_hex", ("cover",), 0, 99, cover_hex),
    Style("plan_glass", ("plan",), 3, 8, plan_glass),
    Style("plan_wave", ("plan",), 3, 8, plan_wave),
    Style("band_right", ("photo",), 0, 99, band_right),
    Style("band_left", ("photo",), 0, 99, band_left),
    Style("band_chevron", ("photo",), 0, 99, band_chevron),
    Style("swirl", ("group", "numbers"), 4, 6, info_swirl),
    Style("tree", ("group",), 3, 6, info_tree),
    Style("fan", ("group", "sequence", "numbers"), 3, 4, info_fan),   # 5+ punktda yozuvlar ustma-ust tushadi
    Style("pencil", ("sequence", "group"), 3, 5, info_pencil),
    Style("leaves", ("group",), 2, 4, info_leaves),
    Style("arcs", ("group", "sequence", "numbers"), 3, 7, info_arcs),
    Style("arrows", ("sequence", "group"), 3, 8, info_arrows),
    Style("pie", ("group", "numbers"), 3, 6, info_pie),
    Style("cross", ("group", "numbers"), 4, 4, info_cross),
    Style("diamond", ("group", "numbers"), 4, 4, info_diamond),
    Style("gears", ("compare",), 0, 99, compare_gears),
    Style("finale", ("finale",), 0, 99, finale),
]
BY_NAME = {s.name: s for s in STYLES}
