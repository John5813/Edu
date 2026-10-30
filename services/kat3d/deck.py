"""3D taqdimotni rejadan yig'adi: uslub, fon bezaklari, katalogdagi haqiqiy 3D modellar va Morph.

Morph sahnasi: bir model qo'shni slaydlarda turganda (nomi `!!m_<id>`) PowerPoint uni yangi joyiga suzib
olib o'tadi va aylantiradi (har ko'rinishda boshqa burchak); sarlavha (`!!title`), bo'lim nomi (`!!kicker`),
fon bezaklari (`!!deco_N`) va model soyasi ham birga suriladi. Matn bandlari, raqam kartalari esa o'tishdan
keyin navbat bilan chiqadi.

Katalog modellari aniq sxema emas — qismlari yorliq-chiziq bilan ko'rsatilmaydi (3D Anatomiyadan farqi).
Telefon va 3D ni bilmaydigan dasturlar uchun har modelning o'rnida uning rasmi (fon olib tashlangan) turadi.
"""
import io
import logging
import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from lxml import etree
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.opc.package import Part
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from services import katalog3d
from services.med3d import design, glb
from services.med3d.pptx3d import CT_GLB, RT_MODEL3D, _PNG, _model_xml, _next_id
from services.pro3d.build import add_entrances, add_morph, fit_size

from .uslub import STYLES

log = logging.getLogger(__name__)

W, H = design.W, design.H
MORPH_MS = 1700
BASE_ROT = (14.0, -30.0, 0.0)              # preview rasmidagi burchakka yaqin: biroz yuqoridan, yon tomondan
SWING = (0.0, 28.0, -22.0, 16.0, -32.0, 10.0, 34.0, -14.0)   # har keyingi ko'rinishda Y bo'yicha burilish
NOTES_HEAD = {"uz": "3D modellar mualliflari", "ru": "Авторы 3D-моделей", "en": "3D model credits",
              "kk": "3D модельдер авторлары"}


class Ctx:
    """Bitta taqdimot yig'ilishi: uslub, GLB va zaxira rasmlar keshi, har model necha marta chiqqani."""

    def __init__(self, prs, st, plan: dict):
        self.prs, self.st, self.plan = prs, st, plan
        self.parts: Dict[str, Part] = {}
        self.data: Dict[str, Tuple[bytes, np.ndarray, np.ndarray]] = {}
        self.fallback: Dict[str, bytes] = {}
        self.seen: Dict[str, int] = {}
        self.cur = 0
        self.placed: Dict[int, Dict[str, tuple]] = {}      # slayd → {model: (cx, cy, size, rot)}
        self.ghosts: Dict[int, set] = {}
        self.credits: List[str] = []
        self.total = len(plan["slides"])

    def glb(self, mid: str):
        if mid not in self.data:
            path = katalog3d.model_yoli(mid)
            if not path:
                raise FileNotFoundError(f"3D model yo'q: {mid}")
            with open(path, "rb") as fh:
                raw = fh.read()
            lo, hi = glb.bounds(raw)
            self.data[mid] = (raw, lo, hi)
        return self.data[mid]

    def picture(self, mid: str) -> bytes:
        if mid not in self.fallback:
            self.fallback[mid] = _cutout(katalog3d.preview_yoli(mid), katalog3d.maska_yoli(mid))
        return self.fallback[mid]


def _cutout(path: Optional[str], mask: Optional[str] = None) -> bytes:
    """Preview rasmidan shaffof PNG — 3D ko'rinmaydigan dasturda (telefon, WPS) model o'rnida turadi.

    Asosiy yo'l — renderer chizgan shaffoflik niqobi (`mask/<id>.png`, xuddi shu burchak va kadr). Niqob
    bo'lmasa: fon va soya rasm chetidan "suv quyish" bilan olib tashlanadi."""
    if not path:
        return _PNG
    from PIL import Image, ImageDraw, ImageFilter

    with Image.open(path) as im:
        rgb = np.asarray(im.convert("RGB")).astype(np.int16)
    h, w = rgb.shape[:2]
    bg = np.array([242, 242, 240], dtype=np.int16)
    if mask:
        with Image.open(mask) as m:
            alpha = np.asarray(m.convert("L").resize((w, h)))
        a = alpha.astype(np.float32)[..., None] / 255.0
        # chetdagi piksellardan kulrang fon "aralashmasi" ayiriladi — to'q fonda oq hoshiya qolmaydi
        clean = np.where(a > 0.04, (rgb - (1.0 - a) * bg) / np.maximum(a, 0.04), rgb)
        out = Image.fromarray(np.dstack([np.clip(clean, 0, 255).astype(np.uint8), alpha]), "RGBA")
        buf = io.BytesIO()
        out.save(buf, "PNG", optimize=True)
        return buf.getvalue()
    dist = np.abs(rgb - bg).max(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    cand = (dist <= 55) & (chroma <= 12)
    cand[:max(6, h // 48), :] = True                 # tepadagi yuklanish chizig'i ham fon
    mask = Image.fromarray(np.where(cand, 255, 0).astype(np.uint8), "L").copy()   # copy: numpy xotirasi o'qishga'
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1)):
        if mask.getpixel(xy) == 255:
            ImageDraw.floodfill(mask, xy, 128)
    alpha = np.where(np.asarray(mask) == 128, 0, 255).astype(np.uint8)
    alpha = np.asarray(Image.fromarray(alpha, "L").filter(ImageFilter.GaussianBlur(0.8)))
    out = Image.fromarray(np.dstack([rgb.astype(np.uint8), alpha]), "RGBA")
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ───────────────────────────────────────────── chizish

def _place(ctx: Ctx, slide, mid: str, cx: float, cy: float, size: float, rot) -> None:
    """3D ob'ekt (am3d:model3d) — GLB taqdimotda bir marta, hamma slaydlar unga havola qiladi."""
    raw, lo, hi = ctx.glb(mid)
    pkg = slide.part.package
    part = ctx.parts.get(mid)
    if part is None:
        part = Part(pkg.next_partname("/ppt/media/model3d%d.glb"), CT_GLB, pkg, raw)
        ctx.parts[mid] = part
    rid_model = slide.part.relate_to(part, RT_MODEL3D)
    _, rid_png = slide.part.get_or_add_image_part(io.BytesIO(ctx.picture(mid)))
    x, y = cx - size / 2, cy - size / 2
    tree = slide.shapes._spTree
    node = etree.fromstring(_model_xml(_next_id(tree), "!!m_" + mid[:24], int(Inches(x)), int(Inches(y)),
                                       int(Inches(size)), int(Inches(size)), rid_model, rid_png, lo, hi, rot,
                                       ctx.st.lights))
    for sppr in node.iter(qn("p:spPr")):          # zaxira ko'rinish ramkasiz
        ln = etree.SubElement(sppr, qn("a:ln"))
        etree.SubElement(ln, qn("a:noFill"))
    tree.append(node)


def _model(ctx: Ctx, slide, mid: str, cx: float, cy: float, size: float, turn: float = 0.0) -> Tuple:
    """3D modelni (cx, cy) markazli `size` dyuymli kvadrat ramkaga qo'yadi. Qaytaradi: (chap, tepa, o'ng, past).
    Har keyingi ko'rinishda model boshqa burchakda — Morph uni slayddan slaydga aylantirib olib o'tadi."""
    k = ctx.seen.get(mid, 0)
    ctx.seen[mid] = k + 1
    rot = (BASE_ROT[0], BASE_ROT[1] + SWING[k % len(SWING)] + turn, BASE_ROT[2])
    _place(ctx, slide, mid, cx, cy, size, rot)
    ctx.placed.setdefault(ctx.cur, {})[mid] = (cx, cy, size, rot)
    m = katalog3d.katalog()[mid]
    if m["attribution_full"] not in ctx.credits:
        ctx.credits.append(m["attribution_full"])
    x, y = cx - size / 2, cy - size / 2
    return (x + size * 0.12, y + size * 0.12, x + size * 0.88, y + size * 0.88)


# Slayddan ketayotgan model keyingi slaydda chetdan tashqarida, aylangan va kichraygan holda turadi — Morph
# uni aylantirib uchirib chiqaradi; yangi model esa oldingi slaydda chetda turadi — aylanib uchib kiradi.
SPIN_OUT = (24.0, 150.0, 18.0)
SPIN_IN = (-18.0, -135.0, -12.0)


def _offstage(cx: float, cy: float, size: float, side: str, scale: float) -> Tuple[float, float, float]:
    s = size * scale
    if side == "right":
        return W + s * 0.7, cy + 0.6, s
    if side == "left":
        return -s * 0.7, cy + 0.6, s
    if side == "down":
        return cx + 0.8, H + s * 0.7, s
    return cx - 0.8, -s * 0.7, s


def _choreography(ctx: Ctx, slides) -> int:
    """Kirish/chiqish "arvohlari": qo'shni slaydda yo'q modellar uchun slayddan tashqaridagi nusxa."""
    added = 0
    n = len(slides)
    for i in range(n - 1):
        here, nxt = ctx.placed.get(i, {}), ctx.placed.get(i + 1, {})
        ghosts_next = ctx.ghosts.setdefault(i + 1, set())
        ghosts_here = ctx.ghosts.setdefault(i, set())
        for k, (mid, (cx, cy, size, rot)) in enumerate(here.items()):
            if mid in nxt or mid in ghosts_next:
                continue
            side = ("right" if cx > W / 2 else "left") if (i + k) % 3 else ("down" if cy > H / 2 else "up")
            gx, gy, gs = _offstage(cx, cy, size, side, 0.55)
            spin = tuple(r + d for r, d in zip(rot, SPIN_OUT))
            _place(ctx, slides[i + 1], mid, gx, gy, gs, spin)
            ghosts_next.add(mid)
            added += 1
        for k, (mid, (cx, cy, size, rot)) in enumerate(nxt.items()):
            if mid in here or mid in ghosts_here:
                continue
            side = "right" if cx > W / 2 else "left"
            side = side if (i + k) % 2 else ("down" if cy > H / 2 else "up")
            gx, gy, gs = _offstage(cx, cy, size, side, 0.7)
            spin = tuple(r + d for r, d in zip(rot, SPIN_IN))
            _place(ctx, slides[i], mid, gx, gy, gs, spin)
            ghosts_here.add(mid)
            added += 1
    return added


def _caption(ctx: Ctx, slide, mids: Sequence[str], x: float, y: float, w: float, align=PP_ALIGN.LEFT,
             name: str = "credit") -> None:
    """Muallif va litsenziya (CC BY uchun majburiy) — kichik, xira yozuv."""
    cat = katalog3d.katalog()
    text = "   ".join(dict.fromkeys(cat[m]["attribution"] for m in mids))
    if text:
        design.textbox(slide, name, x, y, w, 0.26, text, size=8, color=ctx.st.muted, font=ctx.st.body_font,
                       align=align, smallest=6.5)


def _bullets(ctx: Ctx, slide, name: str, points: Sequence[str], x, y, w, h, size: float, smallest: float,
             color: Optional[str] = None):
    """Haqiqiy PowerPoint ro'yxati (belgisi urg'u rangida), shrift o'lchami qutiga moslanadi."""
    st = ctx.st
    joined = "\n".join(points)
    size = fit_size(joined, w - 0.3, h - 0.12 * len(points), size, smallest, 1.24)
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, text in enumerate(points):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.line_spacing = 1.12
        p.space_after = Pt(size * 0.75)
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(int(Inches(0.3))))
        pPr.set("indent", str(-int(Inches(0.3))))
        clr = etree.SubElement(pPr, qn("a:buClr"))
        etree.SubElement(clr, qn("a:srgbClr")).set("val", st.accent)
        etree.SubElement(pPr, qn("a:buSzPct")).set("val", "100000")
        etree.SubElement(pPr, qn("a:buFont")).set("typeface", "Arial")
        etree.SubElement(pPr, qn("a:buChar")).set("char", "•")
        r = p.add_run()
        r.text = text
        r.font.size = Pt(size)
        r.font.name = st.body_font
        r.font.color.rgb = design.rgb(color or st.body)
    return tb


HEAD_EM = 0.6                 # sarlavha shriftida o'rtacha harf eni (em) — Georgia/Segoe Semibold qalin
BODY_EM = 0.52
VALUE_EM = 0.7                # qalin raqamlar (ayniqsa serif) o'rtacha harfdan kengroq


def _lines(text: str, w: float, size: float, em: float) -> int:
    per_line = max(1, int(w * 72 / (size * em)))
    words, lines, cur = str(text or "").split(), 1, 0
    for word in words:
        add = len(word) + (1 if cur else 0)
        if cur and cur + add > per_line:
            lines, cur = lines + 1, len(word)
        else:
            cur += add
    return lines


def _fit(text: str, w: float, h: float, start: float, smallest: float, em: float, line: float = 1.08) -> float:
    size = start
    while size > smallest and _lines(text, w, size, em) * size * line / 72 > h:
        size -= 1
    return size


def _kicker(ctx: Ctx, slide, text: str, x, y, w, align=PP_ALIGN.LEFT):
    return design.textbox(slide, "!!kicker", x, y, w, 0.36, text, size=13, color=ctx.st.accent,
                          font=ctx.st.head_font, bold=True, caps=True, align=align, smallest=10)


def _title(ctx: Ctx, slide, text: str, x, y, w, h, size: float, smallest: float, align=PP_ALIGN.LEFT,
           anchor=MSO_ANCHOR.TOP) -> float:
    """Sarlavha; qaytaradi — haqiqiy pastki cheti (dyuym), undan keyingi matn shunga qarab suriladi."""
    st = ctx.st
    text = text.upper() if st.title_caps else text
    em = HEAD_EM * (1.12 if st.title_caps else 1.0)
    size = _fit(text, w, h, size, smallest, em)
    design.textbox(slide, "!!title", x, y, w, h, text, size=size, color=st.ink, font=st.head_font,
                   bold=True, align=align, anchor=anchor, line=1.02)
    return y + _lines(text, w, size, em) * size * 1.12 / 72


def _number(ctx: Ctx, slide, index: int) -> None:
    design.textbox(slide, "!!num", W - 1.55, 0.46, 0.95, 0.3, f"{index + 1:02d} / {ctx.total:02d}", size=10,
                   color=ctx.st.muted, font=ctx.st.body_font, align=PP_ALIGN.RIGHT)


def _panel(ctx: Ctx, slide, name: str, x, y, w, h):
    st = ctx.st
    return design.shape(slide, name, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, st.panel,
                        alpha=st.panel_alpha, round_=0.07)


def _decorate(ctx: Ctx, slide, index: int, box) -> None:
    design.background(slide, ctx.st)
    design.draw_deco(slide, design.deco_specs(ctx.st, None, index + 1, box))


# ───────────────────────────────────────────── kompozitsiyalar

def _muqova(ctx: Ctx, slide, s: dict, i: int) -> List:
    mids = s["models"]
    _decorate(ctx, slide, i, (6.6, 0.6, 12.4, 6.8))
    box = _model(ctx, slide, mids[0], 9.55, 3.7, 6.3)
    design.ground_shadow(slide, ctx.st, box)
    if len(mids) > 1:
        _model(ctx, slide, mids[1], 11.75, 5.85, 2.0, turn=20)        # ramkali uslublarda ham ichkarida
    _kicker(ctx, slide, s["kicker"] or ctx.plan.get("topic", ""), 0.8, 1.85, 6.0)
    bottom = _title(ctx, slide, s["title"] or ctx.plan.get("topic", ""), 0.8, 2.3, 6.2, 2.75, 54, 30)
    if s["subtitle"]:
        top = max(4.6, bottom + 0.35)
        design.textbox(slide, "sub", 0.8, top, 5.9, 6.75 - top, s["subtitle"], size=19, color=ctx.st.body,
                       font=ctx.st.body_font, smallest=13)
    _caption(ctx, slide, mids, 0.8, H - 0.5, 6.2)
    return []


def _body_h(points: Sequence[str], w: float, size: float) -> float:
    """`_bullets` ro'yxatining taxminiy balandligi (dyuym)."""
    return sum(_lines(p, w - 0.3, size, BODY_EM) * size * 1.12 * 1.24 + size * 0.75 for p in points) / 72


def _stack(ctx: Ctx, slide, s: dict, i: int, x: float, w: float, head: Tuple[float, float],
           body: Tuple[float, float], points: Sequence[str], panel: bool = False, cy: float = 3.75) -> List:
    """Bo'lim nomi + sarlavha + ro'yxat bitta blok: model markaziga (cy) nisbatan vertikal markazda —
    qisqa matnda ham slayd muvozanatli. `panel` — ro'yxat yarim shaffof kartada."""
    st = ctx.st
    title = s["title"].upper() if st.title_caps else s["title"]
    em = HEAD_EM * (1.12 if st.title_caps else 1.0)
    tsize = _fit(title, w, 2.4, head[0], head[1], em)
    th = _lines(title, w, tsize, em) * tsize * 1.12 / 72
    pad = 0.3 if panel else 0.0
    bw = w - 2 * pad
    bsize = fit_size("\n".join(points), bw - 0.3, 3.6 - 0.12 * len(points), body[0], body[1], 1.24)
    bh = _body_h(points, bw, bsize) if points else 0.0
    gap = 0.45 if panel else 0.35
    total = 0.4 + th + (gap + bh + 2 * pad * 0.9 if points else 0)
    y0 = min(max(0.8, cy - total / 2), max(0.8, 6.85 - total))
    _kicker(ctx, slide, s["kicker"], x, y0, w)
    bottom = _title(ctx, slide, s["title"], x, y0 + 0.4, w, 2.4, tsize, tsize)
    if not points:
        return []
    top = bottom + gap
    steps = []
    if panel:
        ph = bh + 2 * pad * 0.9
        steps.append((_panel(ctx, slide, f"panel_{i}", x - 0.15, top, w + 0.3, ph), "fade", 150))
        top += pad * 0.9
    box = _bullets(ctx, slide, f"body_{i}", points, x + pad, top, bw, max(bh + 0.2, 0.6), bsize, body[1])
    steps.append((box, "float", 350 if panel else 250))
    return steps


def _side(ctx: Ctx, slide, s: dict, i: int, left_text: bool) -> List:
    tx = 0.75 if left_text else 7.05
    mx = 9.8 if left_text else 3.5
    _decorate(ctx, slide, i, (mx - 2.6, 1.0, mx + 2.6, 6.6))
    box = _model(ctx, slide, s["models"][0], mx, 3.75, 5.8)
    design.ground_shadow(slide, ctx.st, box)
    steps = _stack(ctx, slide, s, i, tx, 5.6, (34, 24), (18, 12.5), s["points"][:4])
    _caption(ctx, slide, s["models"][:1], mx - 2.9, H - 0.55, 5.8, align=PP_ALIGN.CENTER)
    _number(ctx, slide, i)
    return steps


def _qahramon(ctx: Ctx, slide, s: dict, i: int) -> List:
    _decorate(ctx, slide, i, (6.0, 0.4, 12.6, 7.1))
    box = _model(ctx, slide, s["models"][0], 9.25, 3.75, 7.3)
    design.ground_shadow(slide, ctx.st, box)
    steps = _stack(ctx, slide, s, i, 0.75, 4.95, (44, 26), (17, 11.5), s["points"][:3], panel=True)
    _caption(ctx, slide, s["models"][:1], 6.6, H - 0.45, 6.2, align=PP_ALIGN.RIGHT)
    _number(ctx, slide, i)
    return steps


def _raqamlar(ctx: Ctx, slide, s: dict, i: int) -> List:
    st = ctx.st
    _decorate(ctx, slide, i, (0.6, 2.2, 5.6, 6.9))
    box = _model(ctx, slide, s["models"][0], 3.05, 4.55, 4.9)
    design.ground_shadow(slide, st, box)
    _kicker(ctx, slide, s["kicker"], 0.75, 0.8, 7.5)
    _title(ctx, slide, s["title"], 0.75, 1.2, 11.6, 1.2, 34, 24)
    stats = s["stats"][:4]
    n = len(stats)
    cols = 2
    rows = 1 if n <= 2 else 2
    cw, gap = 3.25, 0.3
    ch = 2.45 if rows == 1 else 1.95
    top = 3.0 if rows == 1 else 2.65
    steps = []
    for k, item in enumerate(stats):
        r, c = divmod(k, cols)
        x, y = 5.95 + c * (cw + gap), top + r * (ch + gap)
        w = cw * 2 + gap if (n == 3 and k == 2) else cw      # uchta raqamda oxirgisi butun qatorga
        card = _panel(ctx, slide, f"card_{i}_{k}", x, y, w, ch)
        one_line = (w - 0.6) * 72 / (max(1, len(item["value"])) * VALUE_EM)
        val = design.textbox(slide, f"val_{i}_{k}", x + 0.3, y + 0.22, w - 0.6, ch * 0.48, item["value"],
                             size=max(18, min(40, int(one_line))), color=st.accent, font=st.head_font,
                             bold=True, anchor=MSO_ANCHOR.BOTTOM)
        lab = design.textbox(slide, f"lab_{i}_{k}", x + 0.3, y + 0.28 + ch * 0.48, w - 0.6, ch * 0.42,
                             item["label"], size=14, color=st.body, font=st.body_font, smallest=10.5)
        steps += [(card, "zoom", 200 + 180 * k), (val, "fade", 260 + 180 * k), (lab, "fade", 300 + 180 * k)]
    if s["points"] and n <= 2:
        steps.append((_bullets(ctx, slide, f"body_{i}", s["points"][:2], 5.95, 5.75, 6.85, 1.1, 14, 11),
                      "float", 700))
    _caption(ctx, slide, s["models"][:1], 0.75, H - 0.45, 4.6, align=PP_ALIGN.CENTER)
    _number(ctx, slide, i)
    return steps


def _uchlik(ctx: Ctx, slide, s: dict, i: int) -> List:
    st = ctx.st
    _decorate(ctx, slide, i, (0.8, 1.8, 12.5, 5.6))
    _kicker(ctx, slide, s["kicker"], 0.75, 0.75, 11.8)
    _title(ctx, slide, s["title"], 0.75, 1.15, 11.8, 1.0, 32, 22)
    steps = []
    for k, item in enumerate(s["items"][:3]):
        cx = 2.45 + k * 4.215
        box = _model(ctx, slide, item["model"], cx, 3.6, 3.55, turn=-10 + 10 * k)
        if k == 1:
            design.ground_shadow(slide, st, box)
        name = design.textbox(slide, f"name_{i}_{k}", cx - 1.95, 5.42, 3.9, 0.42, item["name"], size=19,
                              color=st.accent, font=st.head_font, bold=True, align=PP_ALIGN.CENTER, smallest=13)
        steps.append((name, "fade", 200 + 200 * k))
        if item["text"]:
            txt = design.textbox(slide, f"text_{i}_{k}", cx - 1.95, 5.88, 3.9, 0.85, item["text"], size=14,
                                 color=st.body, font=st.body_font, align=PP_ALIGN.CENTER, smallest=10.5)
            steps.append((txt, "fade", 280 + 200 * k))
    _caption(ctx, slide, [it["model"] for it in s["items"][:3]], 0.75, H - 0.45, 11.0, align=PP_ALIGN.CENTER)
    _number(ctx, slide, i)
    return steps


def _yakun(ctx: Ctx, slide, s: dict, i: int) -> List:
    mids = s["models"][:4]
    n = len(mids)
    _decorate(ctx, slide, i, (1.0, 1.9, 12.3, 4.7))
    _kicker(ctx, slide, s["kicker"], 0.75, 0.75, 11.8, align=PP_ALIGN.CENTER)
    _title(ctx, slide, s["title"], 0.75, 1.15, 11.83, 0.95, 34, 24, align=PP_ALIGN.CENTER)
    size = min(3.3, 11.6 / max(n, 1))
    span = size * n + 0.25 * (n - 1)
    for k, mid in enumerate(mids):
        cx = W / 2 - span / 2 + size / 2 + k * (size + 0.25)
        _model(ctx, slide, mid, cx, 3.55, size, turn=8 * (k - n / 2))
    steps = []
    if s["points"]:
        panel = _panel(ctx, slide, f"panel_{i}", 1.4, 5.25, 10.53, 1.5)
        body = _bullets(ctx, slide, f"body_{i}", s["points"][:3], 1.75, 5.45, 9.9, 1.15, 15, 11)
        steps = [(panel, "fade", 200), (body, "float", 400)]
    _caption(ctx, slide, mids, 0.75, H - 0.4, 11.0, align=PP_ALIGN.CENTER)
    _number(ctx, slide, i)
    return steps


LAYOUT_FN = {"muqova": _muqova, "chap": lambda c, sl, s, i: _side(c, sl, s, i, True),
             "ong": lambda c, sl, s, i: _side(c, sl, s, i, False), "qahramon": _qahramon,
             "raqamlar": _raqamlar, "uchlik": _uchlik, "yakun": _yakun}


def build(plan: dict, out_path: str) -> str:
    st = STYLES.get(plan.get("style") or "") or STYLES["vitrina"]
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    blank = prs.slide_layouts[6]
    ctx = Ctx(prs, st, plan)
    slides = []
    for i, s in enumerate(plan["slides"]):
        slide = prs.slides.add_slide(blank)
        slides.append(slide)
        ctx.cur = i
        steps = LAYOUT_FN.get(s["layout"], LAYOUT_FN["chap"])(ctx, slide, s, i)
        add_morph(slide, MORPH_MS)
        if steps:
            add_entrances(slide, steps)
        notes = s.get("notes") or ""
        if i == len(plan["slides"]) - 1 and ctx.credits:
            head = NOTES_HEAD.get((plan.get("language") or "uz")[:2]) or NOTES_HEAD["en"]
            notes = (notes + "\n\n" if notes else "") + head + ":\n" + "\n".join(ctx.credits)
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    ghosts = _choreography(ctx, slides)
    prs.save(out_path)
    log.info("3D katalog: %d slayd, %d model, %d kirish/chiqish, uslub %s, %.1f MB", len(plan["slides"]),
             len(ctx.parts), ghosts, st.key, os.path.getsize(out_path) / 1e6)
    return out_path
