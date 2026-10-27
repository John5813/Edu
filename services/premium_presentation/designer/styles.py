"""Vektor uslublar: muqova, reja, rasmli varaq, infografikalar, qiyos va xulosa.

Har uslub — parametrli funksiya: punktlar soni (3-8) va rang palitrasi (mavzuga qarab tanlangan
temadan) bo'yicha o'zini quradi. Matnni faqat sahifadan oladi — o'zidan so'z qo'shmaydi (taqdimot
qaysi tilda bo'lsa ham to'g'ri chiqadi).
"""
import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from services.author_mark import mark

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
    backdrop: Optional[Photo] = None      # xira fon rasmi (ba'zi infografik varaqlarda)
    clear_backdrop: bool = False          # matn oq kartalarda — rasm aniqroq ko'rinadi

    def icon_for(self, *texts: str) -> str:
        from .. import html_slides

        name = html_slides._pick_icon([t for t in texts if t], self.used_icons)
        self.used_icons.add(name)
        return name


# ───────────────────────────────────────────── umumiy bo'laklar

def bg_dark(c: Ctx, focus=(50, 45)):
    p = c.pal
    # To'q fonga xira rasm qo'yilmaydi (faqat och fonli varaqlarga) — `backdrop` bu yerda e'tiborsiz.
    r = rect(c.slide, 0, 0, 1920, 1080)
    grad(r, [(0, mix(p.dark, p.accent, 0.28)), (60, p.dark), (100, p.deep)], radial=True, focus=focus)


def bg_light(c: Ctx):
    if c.backdrop is not None:
        # Rasm ustida oq parda: o'rtasi qalinroq (infografika), chetlarida rasm ko'proq ko'rinadi. Matn oq
        # kartalarda bo'lsa (kartalar, vaqt chizig'i) parda yupqa; yozuv to'g'ridan-to'g'ri fonda bo'lsa —
        # qalinroq, aks holda kulrang izohlar rasm ustida o'qilmaydi.
        photo(c.slide, c.backdrop, 0, 0, 1920, 1080)
        r = rect(c.slide, 0, 0, 1920, 1080)
        veil = (74, 62, 48) if c.clear_backdrop else (86, 80, 70)
        grad(r, [(0, WHITE, veil[0]), (65, WHITE, veil[1]), (100, mix(WHITE, c.pal.accent, 0.08), veil[2])],
             radial=True)
        return
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
    """Rasm yo'q (bepul sinov yoki rasm topilmadi): o'rnida rangli maydon va yumshoq halqalar.

    Ilgari o'rtada katta xira ikonka (lampochka, globus) turardi — u "rasm chiqmay qolgan"
    bo'lib ko'rinardi. Endi bu bezakli fon: halqalar maydon ichida qoladi.
    """
    p = c.pal
    r = rect(c.slide, x, y, w, h)
    grad(r, [(0, mix(p.accent, p.dark, 0.15)), (100, p.deep)], angle=60)
    side = min(w, h)
    cx, cy = x + w * 0.6, y + h * 0.5
    glow_ = oval(c.slide, cx, cy, side * 0.42)
    grad(glow_, [(0, p.glowing, 45), (100, p.accent, 0)], radial=True)
    for k, a in ((0.46, 22), (0.34, 16), (0.22, 12)):
        ring = oval(c.slide, cx, cy, side * k)
        nofill(ring); line(ring, WHITE, 3, a)


# ═════════════════════════════════════════════ MUQOVA

def cover_x(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    navy = p.dark
    fill(rect(s, 0, 0, 1920, 1080), navy)
    pic = spec.get("photo_obj")
    # Rasm faqat panel yopmaydigan joyda: ilgari u 700 dan boshlanib, ustidan oq uchburchaklar va katta "X"
    # chiziqlar o'tardi — tabiiy rasm (bemor, tish) to'silib qolardi.
    if pic:
        photo(s, pic, 900, 0, 1020, 1080)
    else:
        no_photo_fill(c, 900, 0, 1020, 1080)
    left = poly(s, [(0, 0), (760, 0), (1060, 480), (830, 1080), (0, 1080)])
    grad(left, [(0, mix(navy, WHITE, 0.08)), (100, mix(navy, "000000", 0.15))], angle=90)
    shadow(left, blur=40, dist=0, alpha=55)
    t = text(s, 110, 170, 860, 440, [[(spec["title"].upper(), 104, WHITE, True, p.head_font, -60)]],
             anchor=BOTTOM, line_spacing=1.0, min_scale=0.38)
    shadow(t, blur=18, dist=8, alpha=55)
    if spec.get("lead"):
        text(s, 116, 630, 820, 170, [[(spec["lead"], 46, p.glowing, True, SERIF, 0, True)]], line_spacing=1.05)
    _cover_credit(s, spec, 118, 820, p.on_dark)


def _cover_credit(s, spec: Dict, x: float, w: float, color: str) -> None:
    """Muqova pastidagi izoh va mijoz ismi — har biri o'z qutisida.

    Ism qutisi belgilanadi (`author_mark`): do'kon nusxasida faqat u bo'shatiladi.
    """
    y = 900
    if spec.get("author"):
        mark(text(s, x, y, w, 60, [[(spec["author"], 24, color)]]))
        y += 60
    if spec.get("credit"):
        text(s, x, y, w, 1060 - y, [[(spec["credit"], 24, color)]])


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
    _cover_credit(s, spec, 120, 700, mix(p.accent, p.dark, 0.75))


# ═════════════════════════════════════════════ REJA

def plan_glass(c: Ctx, spec: Dict):
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    # Muqova rasmi bu varaqda qayta chiqmasin — Reja oddiy qoramtir fonda.
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

def _band_paras(c: Ctx, spec: Dict, title_pt=70, body_pt=36):
    """Sarlavha + bitta matn qatlami (ilgari uch qatlam edi: sarlavha, qalin gap, mayda matn)."""
    p = c.pal
    soft = mix(p.accent, WHITE, 0.85)
    if spec.get("quote"):
        paras = [[(spec["title"].upper(), 24, soft, True, SANS, 200)],
                 [("“" + spec["quote"] + "”", 46, WHITE, False, SERIF, 0, True)]]
        if spec.get("by"):
            paras.append([("— " + spec["by"], 26, soft, True)])
        if spec.get("text"):
            paras.append([(spec["text"], body_pt - 4, soft)])
        return paras
    paras = [[(spec["title"].upper(), title_pt, WHITE, True, p.head_font)]]
    body = " ".join(t for t in (spec.get("lead"), spec.get("text")) if t)
    if body:
        paras.append([(body, body_pt, soft)])
    return paras


def _band_text(c: Ctx, spec: Dict, x, w):
    text(c.slide, x, 140, w, 800, _band_paras(c, spec), anchor=MIDDLE, gap=30, line_spacing=1.15, grow=True)


def band_plain(c: Ctx, spec: Dict):
    """Rasm topilmagan rasmli varaq: rasm o'rnida bo'sh maydon emas — keng matnli bezakli sahifa."""
    s, p = c.slide, c.pal
    bg_dark(c, focus=(80, 40))
    for r, a in ((620, 18), (470, 14), (320, 10)):
        ring = oval(s, 1720, 900, r)
        nofill(ring); line(ring, p.glowing, 3, a)
    blob = oval(s, 1720, 900, 260)
    grad(blob, [(0, p.accent, 45), (100, p.accent, 0)], radial=True)
    bar = box(s, 110, 300, 12, 480, SHAPE.ROUNDED_RECTANGLE, adj=[0.5])
    grad(bar, [(0, p.glowing), (100, p.accent)], angle=90)
    text(s, 170, 120, 1300, 840, _band_paras(c, spec, title_pt=80, body_pt=40), anchor=MIDDLE, gap=36,
         line_spacing=1.15, grow=True)


def _panel_accent(c: Ctx, x, y):
    """Panel ichidagi kichik urg'u chizig'i (rasm ustiga hech narsa chizilmaydi)."""
    bar = box(c.slide, x, y, 120, 8, SHAPE.ROUNDED_RECTANGLE, adj=[0.5])
    fill(bar, c.pal.glowing, 80)


def _band_photo(c: Ctx, spec: Dict, x, y, w, h):
    photo(c.slide, spec["photo_obj"], x, y, w, h)


# Rasm va matn taxminan teng bo'linadi: matn paneli ~52%, rasm ~48% ko'rinadi (ilgari panel rasmning
# ko'p qismini yopardi, matn esa tor ustunga siqilardi).
# Rasm faqat o'z yarmiga qo'yiladi (ilgari butun varaq bo'ylab qo'yilib markazdan kesilardi — rasmning asosiy
# qismi panel ostida qolardi); rasm ustidan chiziq va chetlik chizilmaydi.
def band_right(c: Ctx, spec: Dict):
    if not spec.get("photo_obj"):
        return band_plain(c, spec)
    s, p = c.slide, c.pal
    slant = c.rng.randint(150, 230)
    left = 900
    _band_photo(c, spec, 0, 0, left, 1080)
    band = poly(s, [(left, 0), (1920, 0), (1920, 1080), (left - slant, 1080)])
    grad(band, [(0, p.accent), (100, mix(p.accent, p.dark, 0.4))], angle=90)
    shadow(band, blur=40, dist=0, alpha=40)
    _panel_accent(c, left + 70, 1080 - 110)
    _band_text(c, spec, left + 70, 1920 - left - 70 - 110)


def band_left(c: Ctx, spec: Dict):
    if not spec.get("photo_obj"):
        return band_plain(c, spec)
    s, p = c.slide, c.pal
    slant = c.rng.randint(150, 230)
    right = 1020
    _band_photo(c, spec, right - slant, 0, 1920 - right + slant, 1080)
    band = poly(s, [(0, 0), (right, 0), (right - slant, 1080), (0, 1080)])
    grad(band, [(0, p.dark), (100, mix(p.dark, p.accent, 0.35))], angle=90)
    shadow(band, blur=40, dist=0, alpha=40)
    _panel_accent(c, 110, 1080 - 110)
    _band_text(c, spec, 110, right - slant - 170)


def band_chevron(c: Ctx, spec: Dict):
    if not spec.get("photo_obj"):
        return band_plain(c, spec)
    s, p = c.slide, c.pal
    tip = c.rng.randint(700, 760)
    _band_photo(c, spec, 0, 0, tip + 200, 1080)
    band = poly(s, [(tip + 200, 0), (1920, 0), (1920, 1080), (tip + 200, 1080), (tip, 540)])
    grad(band, [(0, mix(p.accent, p.dark, 0.15)), (100, p.dark)], angle=135)
    shadow(band, blur=40, dist=0, alpha=45)
    _panel_accent(c, tip + 250, 1080 - 110)
    _band_text(c, spec, tip + 250, 1920 - tip - 250 - 110)


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
        y = spread(m, 380, 900)[k] - 80
        num = item.get("value") or str(i + 1)
        if on_left:
            text(s, 500, y, 150, 160, [[(num if not item.get("value") else str(i + 1), 110, p.on_dark, False, SANS)]],
                 align=CENTER, anchor=MIDDLE, fit=False)
            label(c, 40, y - 45, 470, 250, item, align=RIGHT, dark=True, tsize=34, nsize=30, anchor=MIDDLE)
        else:
            text(s, 1270, y, 150, 160, [[(str(i + 1), 110, p.on_dark, False, SANS)]],
                 align=CENTER, anchor=MIDDLE, fit=False)
            label(c, 1410, y - 45, 480, 250, item, align=LEFT, dark=True, tsize=34, nsize=30, anchor=MIDDLE)


def info_cards(c: Ctx, spec: Dict):
    """Ikonkali kartalar: oq kartalar, yumaloq ikonka, raqam va yozuv (3-6 punkt)."""
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    top = heading(c, spec["title"], spec.get("lead", ""))
    cols = n if n <= 4 else 3
    rows = math.ceil(n / cols)
    gap = 36
    x0, x1 = 110, 1810
    cw = (x1 - x0 - gap * (cols - 1)) / cols
    area_top, area_bottom = top + 40, 1010
    ch = min(420, (area_bottom - area_top - gap * (rows - 1)) / rows)
    y0 = area_top + (area_bottom - area_top - rows * ch - gap * (rows - 1)) / 2
    ramp = p.ramp(n, 0.2, 0.35)
    for i, item in enumerate(items):
        row, col = divmod(i, cols)
        in_row = min(cols, n - row * cols)
        shift = (cols - in_row) * (cw + gap) / 2          # oxirgi qatordagi kartalar o'rtada
        x = x0 + shift + col * (cw + gap)
        y = y0 + row * (ch + gap)
        card = box(s, x, y, cw, ch, SHAPE.ROUNDED_RECTANGLE, adj=[0.06])
        fill(card, WHITE)
        line(card, mix(WHITE, p.accent, 0.14), 1.5)
        shadow(card, blur=34, dist=10, alpha=16)
        fill(rect(s, x + 32, y, cw - 64, 7), ramp[i])
        r = min(48.0, ch * 0.13)
        badge = oval(s, x + 40 + r, y + 40 + r, r)
        grad(badge, [(0, mix(ramp[i], WHITE, 0.2)), (100, ramp[i])], angle=90)
        shadow(badge, blur=16, dist=6, alpha=30)
        icon(s, c.icon_for(item.get("title", ""), item.get("note", "")), x + 40 + r, y + 40 + r, r * 1.05, WHITE)
        text(s, x + cw - 150, y + 30, 120, 2 * r + 20, [[(f"{i + 1:02d}", 44, mix(WHITE, p.accent, 0.3), True,
                                                          p.head_font)]], align=RIGHT, anchor=MIDDLE, fit=False)
        ty = y + 60 + 2 * r
        label(c, x + 40, ty, cw - 80, y + ch - ty - 30, item, tsize=36 if cols <= 3 else 32,
              nsize=32 if cols <= 3 else 28)


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


def info_timeline(c: Ctx, spec: Dict):
    """Vaqt chizig'i: gorizontal chiziq, raqamli tugunlar va navbat bilan tepada/pastda kartalar."""
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    top = heading(c, spec["title"], spec.get("lead", ""))
    y = 625 if top > 210 else 610
    xs = spread(n, 250, 1670)
    step = (xs[1] - xs[0]) if n > 1 else 800
    cw = min(470.0, step * 1.8 - 40)
    bar = box(s, 130, y - 7, 1660, 14, SHAPE.ROUNDED_RECTANGLE, adj=[0.5])
    grad(bar, [(0, mix(p.accent, WHITE, 0.6)), (100, p.accent)], angle=0)
    ramp = p.ramp(n, 0.25, 0.35)
    up_top, up_bottom = top + 30, y - 46 - 44
    down_top, down_bottom = y + 46 + 44, 1030
    for i, (item, x) in enumerate(zip(items, xs)):
        up = i % 2 == 0
        cy0, cy1 = (up_top, up_bottom) if up else (down_top, down_bottom)
        cx0 = max(40, min(x - cw / 2, 1880 - cw))
        stem = rect(s, x - 2, cy1 if up else y + 46, 4, 44)
        fill(stem, ramp[i], 80)
        card = box(s, cx0, cy0, cw, cy1 - cy0, SHAPE.ROUNDED_RECTANGLE, adj=[0.07])
        fill(card, WHITE)
        line(card, mix(WHITE, p.accent, 0.14), 1.5)
        shadow(card, blur=30, dist=10, alpha=16)
        fill(rect(s, cx0 + 28, cy0 if up else cy1 - 7, cw - 56, 7), ramp[i])
        label(c, cx0 + 28, cy0 + 22, cw - 56, cy1 - cy0 - 44, item, align=CENTER, anchor=MIDDLE,
              tsize=34 if n <= 4 else 30, nsize=30 if n <= 4 else 27)
        node = oval(s, x, y, 46)
        grad(node, [(0, mix(ramp[i], WHITE, 0.2)), (100, ramp[i])], angle=90)
        line(node, WHITE, 6)
        shadow(node, blur=18, dist=6, alpha=30)
        text(s, x - 46, y - 46, 92, 92, [[(f"{i + 1:02d}", 30, WHITE, True, p.head_font)]], align=CENTER,
             anchor=MIDDLE, fit=False)


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


# ═════════════════════════════════════════════ YANGI INFOGRAFIKALAR (2-to'plam)

def _polar(cx, cy, r, a):
    """Burchak gradusda (0 — o'ngga, soat strelkasiga teskari; y pastga)."""
    return cx + r * math.cos(math.radians(a)), cy - r * math.sin(math.radians(a))


def _side_labels(c: Ctx, items, n: int, y0: float, y1: float, left_box, right_box, num_left, num_right,
                 dark: bool, num_color: str, reverse_right: bool = True):
    """Chap va o'ng ustunlardagi katta raqamli yozuvlar (chapda yuqoridan pastga, o'ngda pastdan yuqoriga)."""
    left = math.ceil(n / 2)
    for i, item in enumerate(items):
        on_left = i < left
        k = i if on_left else i - left
        m = left if on_left else n - left
        if not on_left and reverse_right:
            k = m - 1 - k
        y = spread(m, y0, y1)[k]
        lx, lw = left_box if on_left else right_box
        nx = num_left if on_left else num_right
        text(c.slide, nx, y - 80, 120, 160, [[(str(i + 1), 120, num_color, False, SANS)]], align=CENTER,
             anchor=MIDDLE, fit=False)
        label(c, lx, y - 115, lw, 230, item, align=RIGHT if on_left else LEFT, dark=dark, tsize=32, nsize=28,
              anchor=MIDDLE)


def info_shutter(c: Ctx, spec: Dict):
    """Fotoapparat diafragmasi: buralgan pallalar halqasi, har pallada ikonka; yozuvlar ikki yonda."""
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_dark(c, focus=(50, 55))
    heading(c, spec["title"], spec.get("lead", ""), dark=True)
    cx, cy, r_in, R = 960, 650, 105, 330
    seg = 360 / n
    tw = seg * 0.9                                    # pallaning buralishi
    ramp = p.ramp(n, 0.62, 0.15)
    for i, item in enumerate(items):
        a0 = 90 - i * seg - 1.6
        a1 = a0 - seg + 3.2
        pts = arc_pts(cx, cy, r_in, a0, a1, 10) + arc_pts(cx, cy, R, a1 + tw, a0 + tw, 24)
        blade = poly(s, pts)
        grad(blade, [(0, mix(ramp[i], WHITE, 0.18)), (100, mix(ramp[i], p.dark, 0.18))], angle=a0 + 120)
        shadow(blade, blur=36, dist=12, angle=-a0, alpha=55)
        mid = (a0 + a1) / 2 + tw * 0.55
        ix, iy = _polar(cx, cy, (r_in + R) / 2 + 18, mid)
        ink = WHITE if luminance(ramp[i]) < 0.62 else mix(p.dark, "000000", 0.2)
        icon(s, c.icon_for(item.get("title", ""), item.get("note", "")), ix, iy, 58, ink)
    hole = oval(s, cx, cy, r_in - 6)
    fill(hole, p.deep)
    inner_shadow(hole, blur=26, dist=8, alpha=70)
    _side_labels(c, items, n, 360, 960, (40, 420), (1470, 420), 470, 1330, True, p.on_dark)


def info_honeycomb(c: Ctx, spec: Dict):
    """Asalari uyasi: olti burchaklar zigzag qatorda, yozuvlar navbat bilan tepada va pastda."""
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    top = heading(c, spec["title"], spec.get("lead", ""))
    R = 150 if n <= 4 else 125 if n <= 5 else 108
    hgt = math.sqrt(3) * R
    step = 1.5 * R + 14
    x0 = 960 - (n - 1) * step / 2
    up_y = 600 if top <= 210 else 615
    down_y = up_y + hgt / 2 + 8
    ramp = p.ramp(n, 0.35, 0.35)
    tw = min(2 * step - 30, 430)
    for i, item in enumerate(items):
        x = x0 + i * step
        y = up_y if i % 2 == 0 else down_y
        hx = box(s, x - R, y - hgt / 2, 2 * R, hgt, SHAPE.HEXAGON)
        grad(hx, [(0, mix(ramp[i], WHITE, 0.22)), (100, mix(ramp[i], p.dark, 0.2))], angle=60)
        line(hx, WHITE, 5)
        shadow(hx, blur=26, dist=10, alpha=28)
        icon(s, c.icon_for(item.get("title", ""), item.get("note", "")), x, y - 22, 64, WHITE)
        text(s, x - 60, y + 22, 120, 50, [[(f"{i + 1:02d}", 30, WHITE, True, p.head_font)]], align=CENTER,
             anchor=MIDDLE, fit=False)
        bx = max(40, min(x - tw / 2, 1880 - tw))
        if i % 2 == 0:
            label(c, bx, top + 20, tw, y - hgt / 2 - 24 - (top + 20), item, align=CENTER, anchor=BOTTOM,
                  tsize=31, nsize=27)
        else:
            ly = y + hgt / 2 + 24
            label(c, bx, ly, tw, 1050 - ly, item, align=CENTER, anchor=TOP, tsize=31, nsize=27)


def info_stairs(c: Ctx, spec: Dict):
    """Zinapoya: o'ngga qarab ko'tariladigan hajmli pog'onalar, matn pog'onaning old yuzida."""
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    top = heading(c, spec["title"], spec.get("lead", ""))
    base, depth = 1015, 46
    x0, x1 = 110, 1790
    w = (x1 - x0) / n
    lo, hi = 340, 1015 - (top + 70)
    ramp = p.ramp(n, 0.3, 0.45)
    for i, item in enumerate(items):
        h = lo + (hi - lo) * i / max(n - 1, 1)
        x, y = x0 + i * w, base - h
        side = poly(s, [(x + w, y), (x + w + depth, y - depth), (x + w + depth, base - depth), (x + w, base)])
        fill(side, mix(ramp[i], p.dark, 0.45))
        roof = poly(s, [(x, y), (x + depth, y - depth), (x + w + depth, y - depth), (x + w, y)])
        fill(roof, mix(ramp[i], WHITE, 0.35))
        face = rect(s, x, y, w, h)
        grad(face, [(0, ramp[i]), (100, mix(ramp[i], p.dark, 0.25))], angle=90)
        shadow(face, blur=24, dist=6, angle=0, alpha=22)
        text(s, x + 22, y + 14, w - 44, 96, [[(f"{i + 1:02d}", 80, mix(ramp[i], WHITE, 0.55), True, p.head_font)]],
             anchor=TOP, fit=False)
        label(c, x + 22, y + 112, w - 44, h - 130, item, dark=True, tsize=29 if n >= 5 else 32,
              nsize=25 if n >= 5 else 28)


def info_funnel(c: Ctx, spec: Dict):
    """Voronka: yuqoridan pastga torayadigan qatlamlar, yozuvlar o'ngda tutashtiruvchi chiziq bilan."""
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    top = heading(c, spec["title"], spec.get("lead", ""))
    cx, y0, y1 = 520, top + 40, 1020
    w_top, w_bot = 820, 230
    gap = 12
    hh = (y1 - y0 - gap * (n - 1)) / n
    ramp = p.ramp(n, 0.45, 0.4)

    def width_at(y):
        return w_top + (w_bot - w_top) * (y - y0) / (y1 - y0)

    for i, item in enumerate(items):
        ya, yb = y0 + i * (hh + gap), y0 + i * (hh + gap) + hh
        wa, wb = width_at(ya), width_at(yb)
        layer = poly(s, [(cx - wa / 2, ya), (cx + wa / 2, ya), (cx + wb / 2, yb), (cx - wb / 2, yb)])
        grad(layer, [(0, mix(ramp[i], WHITE, 0.15)), (100, mix(ramp[i], p.dark, 0.2))], angle=0)
        shadow(layer, blur=22, dist=8, alpha=26)
        ym = (ya + yb) / 2
        icon(s, c.icon_for(item.get("title", ""), item.get("note", "")), cx - 50, ym, min(hh * 0.5, 64), WHITE)
        text(s, cx, ym - 40, 120, 80, [[(f"{i + 1:02d}", 40, WHITE, True, p.head_font)]], anchor=MIDDLE, fit=False)
        edge = cx + (wa + wb) / 4 + 14
        ln_ = poly(s, [(edge, ym), (1010, ym)], close=False)
        nofill(ln_); line(ln_, mix(ramp[i], WHITE, 0.2), 3, dash="dash")
        dot = oval(s, 1022, ym, 12); fill(dot, ramp[i])
        label(c, 1056, ya - 6, 780, hh + 12, item, anchor=MIDDLE, tsize=32 if n <= 4 else 29,
              nsize=28 if n <= 4 else 25)


def info_pyramid(c: Ctx, spec: Dict):
    """Piramida: qatlamlarga bo'lingan uchburchak, yozuvlar navbat bilan o'ng va chapda."""
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    top = heading(c, spec["title"], spec.get("lead", ""), align=CENTER)
    cx, apex, base, half = 960, top + 30, 1025, 470
    gap = 10
    hh = (base - apex - gap * (n - 1)) / n
    ramp = p.ramp(n, 0.1, 0.55)[::-1]

    def half_at(y):
        return half * (y - apex) / (base - apex)

    for i, item in enumerate(items):
        ya, yb = apex + i * (hh + gap), apex + i * (hh + gap) + hh
        ha, hb = half_at(ya), half_at(yb)
        pts = [(cx, ya)] if ha < 1 else [(cx - ha, ya), (cx + ha, ya)]
        layer = poly(s, pts + [(cx + hb, yb), (cx - hb, yb)])
        grad(layer, [(0, mix(ramp[i], WHITE, 0.2)), (100, mix(ramp[i], p.dark, 0.2))], angle=90)
        shadow(layer, blur=22, dist=8, alpha=24)
        ym = ya + hh * (0.62 if i == 0 else 0.5)
        text(s, cx - 80, ym - 36, 160, 72, [[(f"{i + 1:02d}", 40 if i else 34, WHITE, True, p.head_font)]],
             align=CENTER, anchor=MIDDLE, fit=False)
        right = i % 2 == 0
        edge = cx + (ha + hb) / 2 + 16 if right else cx - (ha + hb) / 2 - 16
        tx = max(1330, edge + 60) if right else min(590, edge - 60)
        ln_ = poly(s, [(edge, ym), (tx, ym)], close=False)
        nofill(ln_); line(ln_, ramp[i], 3)
        dot = oval(s, tx, ym, 11); fill(dot, ramp[i])
        bw = min(520, 1880 - tx - 26) if right else min(520, tx - 26 - 40)
        label(c, tx + 26 if right else tx - 26 - bw, ym - 110, bw, 220, item, align=LEFT if right else RIGHT,
              anchor=MIDDLE, tsize=31, nsize=27)


def info_mindmap(c: Ctx, spec: Dict):
    """Aqliy xarita: markazdagi katta doira, egri chiziqlar bilan bog'langan tugunlar va yozuvlar."""
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_dark(c, focus=(50, 58))
    heading(c, spec["title"], spec.get("lead", ""), dark=True, align=CENTER)
    cx, cy, rx, ry, r = 960, 645, 520, 285, 54
    start = 90 + 180 / n
    nodes = []
    for i in range(n):
        a = start - i * 360 / n
        nodes.append((a, *_polar(cx, cy, 1, a)))
    ramp = p.ramp(n, 0.55, 0.15)
    for i, (a, ux, uy) in enumerate(nodes):
        x, y = cx + rx * (ux - cx), cy + ry * (uy - cy)
        bend = _polar(cx, cy, 1, a + 18)
        ctrl = (cx + rx * 0.55 * (bend[0] - cx), cy + ry * 0.55 * (bend[1] - cy))
        curve = [((1 - t) ** 2 * cx + 2 * (1 - t) * t * ctrl[0] + t * t * x,
                  (1 - t) ** 2 * cy + 2 * (1 - t) * t * ctrl[1] + t * t * y) for t in (k / 24 for k in range(25))]
        wire = poly(s, curve, close=False)
        nofill(wire); line(wire, mix(ramp[i], WHITE, 0.15), 5, 85)
    hub = oval(s, cx, cy, 150)
    grad(hub, [(0, mix(p.accent, WHITE, 0.25)), (100, mix(p.accent, p.dark, 0.35))], angle=90)
    glow(hub, 30, p.accent, 35)
    icon(s, c.topic_icon, cx, cy, 130, WHITE)
    for i, ((a, ux, uy), item) in enumerate(zip(nodes, items)):
        x, y = cx + rx * (ux - cx), cy + ry * (uy - cy)
        node = oval(s, x, y, r)
        grad(node, [(0, mix(ramp[i], WHITE, 0.2)), (100, ramp[i])], angle=90)
        line(node, WHITE, 4, 80)
        shadow(node, blur=22, dist=6, alpha=45)
        icon(s, c.icon_for(item.get("title", ""), item.get("note", "")), x, y, 56, WHITE)
        right = math.cos(math.radians(a)) > 0
        lw = 1880 - (x + r + 22) if right else (x - r - 22) - 40
        lw = min(lw, 470)
        lx = x + r + 22 if right else x - r - 22 - lw
        item_ = dict(item, title=f"{i + 1}. {item.get('title', '')}" if item.get("title") else item.get("title", ""))
        label(c, lx, y - 100, lw, 200, item_, align=LEFT if right else RIGHT, dark=True, tsize=29, nsize=25,
              anchor=MIDDLE)


def info_pins(c: Ctx, spec: Dict):
    """Yo'l xaritasi: to'lqinli yo'l va undagi raqamli belgi-ignalar; yozuvlar navbat bilan tepada va pastda."""
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    top = heading(c, spec["title"], spec.get("lead", ""))
    mid_y, amp = 760, 60
    pts = [(x, mid_y + amp * math.sin((x - 60) / 1800 * 2.2 * math.pi)) for x in range(-20, 1960, 40)]
    road = poly(s, ribbon(pts, 70))
    fill(road, mix(p.dark, WHITE, 0.15))
    shadow(road, blur=20, dist=6, alpha=25)
    dash = poly(s, pts, close=False)
    nofill(dash); line(dash, WHITE, 4, 90, dash="dash")
    xs = spread(n, 260, 1660)
    step = (xs[1] - xs[0]) if n > 1 else 700
    tw = min(2 * step - 40, 470)
    ramp = p.ramp(n, 0.25, 0.35)
    for i, (item, x) in enumerate(zip(items, xs)):
        ground = mid_y + amp * math.sin((x - 60) / 1800 * 2.2 * math.pi)
        r = 58
        head_y = ground - 150
        outline = arc_pts(x, head_y, r, -58, 238, 40) + [(x, ground - 8)]
        pin = poly(s, outline)
        grad(pin, [(0, mix(ramp[i], WHITE, 0.2)), (100, mix(ramp[i], p.dark, 0.25))], angle=90)
        shadow(pin, blur=18, dist=10, alpha=35)
        shade = oval(s, x, ground, 30, 9); fill(shade, "000000", 25)
        inner = oval(s, x, head_y, r * 0.66); fill(inner, WHITE)
        text(s, x - 40, head_y - 30, 80, 60, [[(f"{i + 1}", 34, ramp[i], True, p.head_font)]], align=CENTER,
             anchor=MIDDLE, fit=False)
        bx = max(40, min(x - tw / 2, 1880 - tw))
        if i % 2 == 0:
            label(c, bx, top + 20, tw, head_y - r - 24 - (top + 20), item, align=CENTER, anchor=BOTTOM,
                  tsize=31, nsize=27)
        else:
            # Yozuv ostidagi yo'lning eng past nuqtasidan pastda boshlanadi (to'lqin yozuvga tegmasin).
            lowest = max(mid_y + amp * math.sin((xx - 60) / 1800 * 2.2 * math.pi)
                         for xx in range(int(bx), int(bx + tw) + 1, 20))
            ly = lowest + 52
            label(c, bx, ly, tw, 1060 - ly, item, align=CENTER, anchor=TOP, tsize=29, nsize=25)


def info_pillars(c: Ctx, spec: Dict):
    """Ustunlar: balandligi o'sib boradigan hajmli silindrlar, raqam silindrda, yozuv tepasida."""
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_dark(c, focus=(50, 80))
    top = heading(c, spec["title"], spec.get("lead", ""), dark=True)
    base = 1005
    slot = 1700 / n
    cw = min(230, slot * 0.62)
    ramp = p.ramp(n, 0.5, 0.1)
    floor = oval(s, 960, base + 6, 900, 30)
    grad(floor, [(0, p.accent, 30), (100, p.accent, 0)], radial=True)
    for i, item in enumerate(items):
        x = 110 + slot * (i + 0.5)
        h = 230 + 230 * i / max(n - 1, 1)
        topy = base - h
        ry = cw * 0.16
        body = rect(s, x - cw / 2, topy, cw, h)
        grad(body, [(0, mix(ramp[i], p.dark, 0.35)), (45, mix(ramp[i], WHITE, 0.18)), (100, mix(ramp[i], p.dark, 0.4))],
             angle=0)
        bottom = oval(s, x, base, cw / 2, ry)
        grad(bottom, [(0, mix(ramp[i], p.dark, 0.35)), (100, mix(ramp[i], p.dark, 0.4))], angle=0)
        cap = oval(s, x, topy, cw / 2, ry)
        grad(cap, [(0, mix(ramp[i], WHITE, 0.45)), (100, mix(ramp[i], WHITE, 0.1))], angle=90)
        shadow(body, blur=30, dist=10, angle=0, alpha=40)
        number = item.get("value") or f"{i + 1:02d}"
        text(s, x - cw / 2 + 6, topy + ry + 20, cw - 12, 110, [[(number, 46 if item.get("value") else 64, WHITE, True,
                                                                  p.head_font)]], align=CENTER, anchor=TOP)
        sub = {k: v for k, v in item.items() if k != "value"}
        lw = slot - 24
        label(c, x - lw / 2, top + 20, lw, topy - ry - 24 - (top + 20), sub, align=CENTER, anchor=BOTTOM, dark=True,
              tsize=27 if n >= 6 else 29 if n == 5 else 32, nsize=24 if n >= 6 else 25 if n == 5 else 28)


def info_chevrons(c: Ctx, spec: Dict):
    """O'qlar zanjiri: yuqorida raqamli strelkalar, har biri ostida o'z kartasi."""
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    top = heading(c, spec["title"], spec.get("lead", ""))
    x0, x1 = 90, 1830
    tip = 60
    w = (x1 - x0 + tip * (n - 1)) / n
    y, h = top + 40, 150
    ramp = p.ramp(n, 0.4, 0.4)
    for i, item in enumerate(items):
        x = x0 + i * (w - tip)
        notch = 0 if i == 0 else tip
        arrow = poly(s, [(x, y), (x + w - tip, y), (x + w, y + h / 2), (x + w - tip, y + h), (x, y + h),
                         (x + notch, y + h / 2)])
        grad(arrow, [(0, mix(ramp[i], WHITE, 0.15)), (100, mix(ramp[i], p.dark, 0.15))], angle=90)
        line(arrow, WHITE, 4)
        shadow(arrow, blur=18, dist=6, alpha=22)
        cxm = x + (w - tip) / 2 + notch / 2
        icon(s, c.icon_for(item.get("title", ""), item.get("note", "")), cxm - 42, y + h / 2, 54, WHITE)
        text(s, cxm - 6, y + h / 2 - 40, 110, 80, [[(f"{i + 1:02d}", 40, WHITE, True, p.head_font)]], anchor=MIDDLE,
             fit=False)
        cx0, cw = x + notch / 2 + 8, w - tip - 16
        cy0 = y + h + 48
        stem = rect(s, cxm - 2, y + h, 4, 48); fill(stem, ramp[i])
        card = box(s, cx0, cy0, cw, 1030 - cy0, SHAPE.ROUNDED_RECTANGLE, adj=[0.05])
        fill(card, WHITE)
        line(card, mix(WHITE, p.accent, 0.16), 1.5)
        shadow(card, blur=28, dist=8, alpha=14)
        fill(rect(s, cx0 + 24, cy0, cw - 48, 7), ramp[i])
        label(c, cx0 + 24, cy0 + 30, cw - 48, 1030 - cy0 - 60, item, align=CENTER, anchor=MIDDLE,
              tsize=31 if n <= 4 else 27, nsize=27 if n <= 4 else 24)


def info_target(c: Ctx, spec: Dict):
    """Nishon: ichma-ich halqalar (tashqaridan markazga), har halqadan yozuvga ko'rsatkich chiziq."""
    s, p = c.slide, c.pal
    items = spec["items"]
    n = len(items)
    bg_light(c)
    top = heading(c, spec["title"], spec.get("lead", ""))
    cx, cy, R = 560, 655, 380
    band = R / (n + 0.4)
    ramp = p.ramp(n, 0.5, 0.35)
    for i in range(n):
        r = R - i * band
        ring = oval(s, cx, cy, r)
        grad(ring, [(0, mix(ramp[i], WHITE, 0.15)), (100, mix(ramp[i], p.dark, 0.15))], angle=90)
        line(ring, WHITE, 4)
        shadow(ring, blur=24, dist=8, alpha=26 if i == 0 else 14)
    core = oval(s, cx, cy, R - n * band + 2)
    fill(core, WHITE)
    icon(s, c.topic_icon, cx, cy, (R - n * band) * 1.2, p.accent)
    ys = spread(n, top + 90, 990)
    for i, item in enumerate(items):
        r_mid = R - i * band - band / 2
        ax, ay = _polar(cx, cy, r_mid, 24)              # raqamlar bitta nur bo'ylab — ustma-ust tushmaydi
        text(s, ax - 34, ay - 30, 68, 60, [[(f"{i + 1}", 30, WHITE, True, p.head_font)]], align=CENTER,
             anchor=MIDDLE, fit=False)
        ln_ = poly(s, [(ax + 30, ay), (1060, ys[i]), (1110, ys[i])], close=False)
        nofill(ln_); line(ln_, mix(ramp[i], p.dark, 0.1), 3)
        dot = oval(s, 1116, ys[i], 10); fill(dot, ramp[i])
        hh = (990 - top - 90) / max(n - 1, 1) if n > 1 else 300
        label(c, 1150, ys[i] - min(hh, 260) / 2, 700, min(hh, 260), item, anchor=MIDDLE,
              tsize=32 if n <= 4 else 29, nsize=28 if n <= 4 else 25)


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
        text(s, 270, y - 40, 1380, 80, [[(t, 32, p.on_dark)]], anchor=MIDDLE, grow=True)


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
    Style("cards", ("group", "numbers"), 3, 6, info_cards),
    Style("fan", ("group", "sequence", "numbers"), 3, 4, info_fan),   # 5+ punktda yozuvlar ustma-ust tushadi
    Style("timeline", ("sequence", "group"), 3, 6, info_timeline),
    Style("leaves", ("group",), 2, 4, info_leaves),
    Style("arcs", ("group", "sequence", "numbers"), 3, 7, info_arcs),
    Style("arrows", ("sequence", "group"), 3, 8, info_arrows),
    Style("pie", ("group", "numbers"), 3, 6, info_pie),
    Style("cross", ("group", "numbers"), 4, 4, info_cross),
    Style("diamond", ("group", "numbers"), 4, 4, info_diamond),
    Style("shutter", ("group", "sequence", "numbers"), 4, 8, info_shutter),
    Style("honeycomb", ("group", "numbers"), 3, 7, info_honeycomb),
    Style("stairs", ("sequence", "group"), 3, 5, info_stairs),
    Style("funnel", ("sequence", "group"), 3, 6, info_funnel),
    Style("pyramid", ("group", "sequence"), 3, 5, info_pyramid),
    Style("mindmap", ("group",), 4, 8, info_mindmap),
    Style("pins", ("sequence", "group"), 3, 6, info_pins),
    Style("pillars", ("numbers", "sequence", "group"), 3, 6, info_pillars),
    Style("chevrons", ("sequence", "group"), 3, 5, info_chevrons),
    Style("target", ("group", "numbers"), 3, 5, info_target),
    Style("gears", ("compare",), 0, 99, compare_gears),
    Style("finale", ("finale",), 0, 99, finale),
]
BY_NAME = {s.name: s for s in STYLES}
# Och fonli uslublar — faqat ularga xira fon rasmi qo'yiladi (to'q fonga kerak emas).
LIGHT = frozenset({"cards", "timeline", "leaves", "arrows", "pie", "cross", "diamond", "honeycomb", "stairs",
                   "funnel", "pyramid", "pins", "chevrons", "target"})
# Ulardan matni oq kartalarda turadiganlari — fon rasmi aniqroq ko'rsatiladi.
CLEAR = frozenset({"cards", "timeline", "chevrons"})
