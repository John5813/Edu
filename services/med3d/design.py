"""3D Anatomiya taqdimotining dizayn tizimi: uslublar, sahna kompozitsiyalari, fon bezaklari.

Har slaydda hamma narsa Morph bilan birga harakatlanadi: 3D model, sarlavha va matn (nomi har slaydda bir xil —
`!!title`, `!!body`), fon bezaklari (`!!deco_N` — har slaydda boshqa joyda), model ostidagi soya (`!!shadow`).
Kompozitsiya almashganda matn slayd bo'ylab suriladi, bezaklar aylanadi va kattalashadi — slayd jonli ko'rinadi.

Uslub (`Style`) — fon, shriftlar, ranglar, yorliq turi, chiziq turi, bezak oilasi, 3D model ohangi va yorug'ligi.
Kompozitsiya (`Layout`) — matn va model qayerda turishi (dyuymda, slayd 13.333 × 7.5).
"""
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from lxml import etree
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

W, H = 13.333, 7.5


# ───────────────────────────────────────────── uslublar

@dataclass(frozen=True)
class Style:
    key: str
    uz: str                          # mijozga ko'rinadigan nom
    bg: str                          # fon (gradient bo'lsa — boshlanishi)
    bg2: str = ""                    # gradient oxiri ("" — tekis fon)
    bg_angle: int = 135
    ink: str = "F3F6FB"              # sarlavha
    body: str = "B8C4D6"             # asosiy matn
    muted: str = "8796AD"            # sahifa raqami, manba
    accent: str = "38BDF8"
    panel: str = "14213A"            # "karta" kompozitsiyasidagi panel
    panel_alpha: float = 0.92
    pill: str = "14213A"             # yorliq foni
    pill_ink: str = "E8F3FF"
    pill_line: str = "38BDF8"
    latin: str = "9FB0C8"            # lotincha nom rangi
    line: str = "38BDF8"             # yorliq chizig'i
    connector: str = "straight"      # straight | elbow | curve
    label: str = "pill"              # pill | tag | plain
    pill_round: float = 0.5
    head_font: str = "Segoe UI Semibold"
    body_font: str = "Segoe UI"
    title_caps: bool = False
    deco: str = "orbs"               # bezak oilasi (`DECO`)
    deco_color: str = "38BDF8"
    deco_alpha: float = 0.10
    shadow: str = "000000"           # model ostidagi soya
    shadow_alpha: float = 0.0        # 0 — soya yo'q (to'q fonda ko'rinmaydi)
    tone: str = "real"               # 3D model ohangi: real | pastel | xray | ivory | warm
    lights: str = "studio"           # 3D yorug'lik: studio | soft | rim | spot | cool
    light: bool = False              # ochiq fon (matn to'q)


STYLES: Dict[str, Style] = {s.key: s for s in [
    Style("klinik", "Klinik qorong'u", bg="0B1220", bg2="111C33", deco="orbs"),
    Style("kobalt", "Kobalt", bg="3B4FD8", bg2="5C6CF2", bg_angle=120, ink="FFFFFF", body="E3E7FF",
          muted="C9CFF7", accent="FFFFFF", panel="2F40C0", pill="FFFFFF", pill_ink="3B4FD8", pill_line="FFFFFF",
          latin="DCE1FF", line="FFFFFF", connector="curve", label="tag", deco="band", deco_color="FFFFFF",
          deco_alpha=0.15, shadow="1A247A", shadow_alpha=0.35, tone="pastel", lights="soft"),
    Style("atlas", "Atlas (kitob)", bg="F6F1E7", bg2="EFE7D6", ink="2B2118", body="4A3F33", muted="8A7D6B",
          accent="9C3D2E", panel="FFFDF8", pill="FFFDF8", pill_ink="2B2118", pill_line="2B2118", latin="7A6E5E",
          line="2B2118", connector="elbow", label="plain", head_font="Georgia", body_font="Georgia",
          deco="frame", deco_color="2B2118", deco_alpha=0.55, shadow="5A4630", shadow_alpha=0.22, tone="real",
          lights="warm", light=True),
    Style("rentgen", "Rentgen", bg="02060C", bg2="06182A", ink="E6FBFF", body="9FD8E6", muted="5C8FA0",
          accent="22D3EE", panel="06202E", pill="02121C", pill_ink="CFFAFE", pill_line="22D3EE", latin="67C7DB",
          line="22D3EE", deco="grid", deco_color="22D3EE", deco_alpha=0.10, tone="xray", lights="cool"),
    Style("vitrina", "Muzey vitrinasi", bg="08080A", bg2="141418", ink="F5F0E6", body="C9C2B4", muted="8C8577",
          accent="D4AF37", panel="18181C", pill="0E0E10", pill_ink="F5E7C0", pill_line="D4AF37", latin="BFA76A",
          line="D4AF37", connector="elbow", head_font="Georgia", deco="spot", deco_color="F5E7C0",
          deco_alpha=0.17, tone="ivory", lights="spot"),
    Style("laboratoriya", "Laboratoriya", bg="F2F5F9", bg2="DFE7F0", ink="0F2433", body="3A5161", muted="7C8F9C",
          accent="0EA5A4", panel="FFFFFF", pill="FFFFFF", pill_ink="0F2433", pill_line="0EA5A4", latin="5C7480",
          line="0EA5A4", connector="curve", deco="orbs", deco_color="0EA5A4", deco_alpha=0.08, shadow="2A4A5E",
          shadow_alpha=0.20, light=True),
    Style("zumrad", "Zumrad", bg="052620", bg2="0B3D33", ink="ECFDF5", body="A7D9C5", muted="6FA593",
          accent="34D399", panel="0A3329", pill="073027", pill_ink="D1FAE5", pill_line="34D399", latin="86C9AE",
          line="34D399", connector="curve", deco="blob", deco_color="34D399", deco_alpha=0.08),
    Style("pastel", "Pastel", bg="F6F0FF", bg2="FCE7F3", ink="3B1F4A", body="5E4A6B", muted="9A86A8",
          accent="DB2777", panel="FFFFFF", pill="FFFFFF", pill_ink="7E1D52", pill_line="F472B6", latin="9D6C8B",
          line="F472B6", connector="curve", label="tag", pill_round=0.5, deco="blob", deco_color="F9A8D4",
          deco_alpha=0.16, shadow="7E3A6A", shadow_alpha=0.18, tone="pastel", lights="soft", light=True),
    Style("okean", "Okean", bg="0B3A47", bg2="137080", ink="F0FDFF", body="BFE6EC", muted="7FB4BE",
          accent="FF8A65", panel="0A3440", pill="F0FDFF", pill_ink="0B3A47", pill_line="FF8A65", latin="CDEBF0",
          line="FF8A65", connector="curve", label="tag", deco="band", deco_color="FFFFFF", deco_alpha=0.07),
    Style("grafit", "Grafit", bg="1A1D21", bg2="25292F", ink="F8FAFC", body="C3C8D0", muted="858C96",
          accent="F97316", panel="23272D", pill="23272D", pill_ink="FFEDD5", pill_line="F97316", latin="B9A79A",
          line="F97316", connector="elbow", head_font="Bahnschrift", body_font="Segoe UI", title_caps=True,
          deco="stripes", deco_color="F97316", deco_alpha=0.12, tone="real", lights="rim"),
    Style("oq", "Oq minimal", bg="FFFFFF", ink="111111", body="3F3F46", muted="8A8A93", accent="E11D48",
          panel="F4F4F5", pill="FFFFFF", pill_ink="111111", pill_line="111111", latin="71717A", line="111111",
          label="plain", deco="none", shadow="000000", shadow_alpha=0.16, lights="soft", light=True),
    Style("shafaq", "Shafaq", bg="24163A", bg2="7A2E4D", bg_angle=160, ink="FFF7ED", body="F3D9C9",
          muted="C9A0A0", accent="FBBF24", panel="3A1F45", pill="FFF7ED", pill_ink="5B1E3A", pill_line="FBBF24",
          latin="F6CFB0", line="FBBF24", connector="curve", label="tag", deco="orbs", deco_color="FBBF24",
          deco_alpha=0.12, tone="warm", lights="warm"),
]}
DEFAULT_STYLE = "klinik"
# Bot tugmalaridagi nomlar (o'zbekchasi — `Style.uz`).
STYLE_NAMES = {
    "ru": {"klinik": "Клинический тёмный", "kobalt": "Кобальт", "atlas": "Атлас (книга)", "rentgen": "Рентген",
           "vitrina": "Музейная витрина", "laboratoriya": "Лаборатория", "zumrad": "Изумруд", "pastel": "Пастель",
           "okean": "Океан", "grafit": "Графит", "oq": "Белый минимал", "shafaq": "Закат"},
    "en": {"klinik": "Clinical dark", "kobalt": "Cobalt", "atlas": "Atlas (book)", "rentgen": "X-ray",
           "vitrina": "Museum showcase", "laboratoriya": "Laboratory", "zumrad": "Emerald", "pastel": "Pastel",
           "okean": "Ocean", "grafit": "Graphite", "oq": "White minimal", "shafaq": "Sunset"},
    "kk": {"klinik": "Клиникалық қараңғы", "kobalt": "Кобальт", "atlas": "Атлас (кітап)", "rentgen": "Рентген",
           "vitrina": "Мұражай витринасы", "laboratoriya": "Зертхана", "zumrad": "Зүмірет", "pastel": "Пастель",
           "okean": "Мұхит", "grafit": "Графит", "oq": "Ақ минимал", "shafaq": "Шапақ"},
}
STYLE_EMOJI = {"klinik": "🌌", "kobalt": "🔷", "atlas": "📖", "rentgen": "🩻", "vitrina": "🏛", "laboratoriya": "🧪",
               "zumrad": "💚", "pastel": "🌸", "okean": "🌊", "grafit": "⚫", "oq": "⚪", "shafaq": "🌅"}
STYLE_ORDER = ("kobalt", "atlas", "vitrina", "rentgen", "pastel", "laboratoriya", "klinik", "zumrad", "okean",
               "grafit", "oq", "shafaq")


def style_name(key: str, lang: str = "uz") -> str:
    if lang in STYLE_NAMES:
        return STYLE_NAMES[lang].get(key, key)
    return STYLES[key].uz if key in STYLES else key


def style(key: Optional[str]) -> Style:
    return STYLES.get(key or "", STYLES[DEFAULT_STYLE])


def _hsl(hex_color: str):
    import colorsys
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def _hex(h: float, l: float, s: float) -> str:
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def tone(hex_color: str, kind: str) -> str:
    """3D model rangi uslubga moslanadi: real — atlas rangi, pastel — och va yumshoq (videodagi kabi),
    ivory — muzey haykali (fil suyagi), xray — rentgen (ko'kish nur), warm — iliqroq va to'qroq."""
    if kind == "real" or not kind:
        return hex_color
    h, l, s = _hsl(hex_color)
    if kind == "pastel":
        return _hex(h, l + (0.86 - l) * 0.42, s * 0.78)
    if kind == "ivory":
        # fil suyagi rangi, lekin asl rangdan ozgina iz qoladi — organlar bir-biridan ajralib turadi
        hx = hex_color.lstrip("#")
        r, g, b = (int(hx[i:i + 2], 16) for i in (0, 2, 4))
        ir, ig, ib = 0xEC, 0xE2, 0xCF
        # suyak (oqish, rangsiz) — deyarli fil suyagi; mushak, tomir (to'yingan rang) — rangi ko'proq qoladi,
        # aks holda suyak ustidagi mushak ajralmay, hammasi bir xil oq ko'rinadi
        k = 0.2 + 0.32 * s
        return "#%02X%02X%02X" % (round(ir + (r - ir) * k), round(ig + (g - ig) * k), round(ib + (b - ib) * k))
    if kind == "xray":
        # bitta rang emas: arteriya (qizil) — oqish-zangori, vena (ko'k) — to'q ko'k, suyak — deyarli oq
        import math as _m
        return _hex(0.53 + 0.05 * _m.cos(2 * _m.pi * h), 0.30 + l * 0.6, 0.45 + 0.2 * s)
    if kind == "warm":
        return _hex(h - 0.015, l * 0.96, min(1.0, s * 1.12))
    return hex_color


# ───────────────────────────────────────────── kompozitsiyalar

@dataclass(frozen=True)
class Layout:
    key: str
    title: Tuple[float, float, float, float]          # x, y, w, h
    body: Tuple[float, float, float, float]
    region: Tuple[float, float, float, float]         # model sig'adigan joy (yorliq bo'lsa)
    wide: Tuple[float, float, float, float]           # yorliqsiz slaydda
    area: Tuple[float, float, float, float]           # model chiqib turishi mumkin bo'lgan joy (matnga tegmaydi)
    labels_x: Tuple[float, float]
    labels_y: Tuple[float, float] = (0.6, H - 0.6)
    title_size: float = 34
    body_size: float = 16
    panel: Optional[Tuple[float, float, float, float]] = None   # matn ostidagi karta
    accent: Tuple[float, float] = (0.65, 0.75)                   # urg'u chizig'i joyi
    fill: float = 0.9
    zoom_limit: float = 2.2          # fokusga yaqinlashish: butun ko'rinishdan ko'pi bilan shuncha katta


LAYOUTS: Dict[str, Layout] = {lay.key: lay for lay in [
    # Chapda matn, o'ngda model (asosiy).
    Layout("chap_matn", title=(0.65, 1.05, 4.35, 1.7), body=(0.65, 2.9, 4.35, 3.6),
           region=(7.05, 0.6, 4.2, 6.3), wide=(5.4, 0.45, 7.5, 6.6), area=(5.15, -9, 99, 99),
           labels_x=(5.15, W - 0.2)),
    # O'ngda matn, chapda model — kompozitsiya almashganda model slayd bo'ylab suzib o'tadi.
    Layout("ong_matn", title=(8.6, 1.05, 4.2, 1.7), body=(8.6, 2.9, 4.2, 3.6),
           region=(2.05, 0.6, 4.2, 6.3), wide=(0.35, 0.45, 7.6, 6.6), area=(-99, -9, 8.25, 99),
           labels_x=(0.2, 8.2), accent=(8.6, 0.75)),
    # Model markazda, ikki yonida yorliqlar; sarlavha tepada, matn pastki chapda.
    Layout("markaz", title=(0.65, 0.5, 6.5, 0.9), body=(0.65, 4.5, 3.55, 2.5),
           region=(4.75, 0.9, 4.1, 6.2), wide=(4.4, 0.8, 5.4, 6.5), area=(4.35, 1.35, 99, 99),
           labels_x=(0.25, W - 0.25), labels_y=(1.6, 4.2), title_size=30, body_size=13, accent=(0.65, 0.35)),
    # Katta model (chetidan chiqib turadi), sarlavha tepada, matn yarim shaffof kartada.
    Layout("qahramon", title=(0.65, 0.6, 4.45, 2.4), body=(0.85, 4.75, 4.1, 2.0),
           region=(5.6, 0.1, 7.3, 7.3), wide=(4.8, 0.0, 8.3, 7.5), area=(5.2, 0.0, W - 0.05, H - 0.05),
           labels_x=(5.2, W - 0.2), title_size=40, body_size=14, panel=(0.55, 4.5, 4.7, 2.5), fill=0.97,
           zoom_limit=1.0),
    # Matn kartada (chap), model o'ngda.
    Layout("karta", title=(0.85, 1.0, 4.3, 1.7), body=(0.85, 2.85, 4.3, 3.6),
           region=(7.3, 0.6, 4.1, 6.3), wide=(5.9, 0.45, 7.1, 6.6), area=(5.75, -9, 99, 99),
           labels_x=(5.75, W - 0.2), panel=(0.45, 0.45, 5.05, 6.6), accent=(0.85, 0.75)),
    # Model tepada, matn pastki tasmada (ikki ustun).
    Layout("pastki", title=(0.65, 5.4, 4.6, 1.5), body=(5.6, 5.45, 7.1, 1.75),
           region=(4.55, 0.2, 4.3, 4.85), wide=(2.2, 0.2, 8.9, 4.85), area=(-99, -9, 99, 5.15),
           labels_x=(0.3, W - 0.3), labels_y=(0.45, 4.8), title_size=28, body_size=13, accent=(0.65, 5.15)),
]}
LAYOUT_ORDER = ("chap_matn", "ong_matn", "markaz", "qahramon", "karta", "pastki")


def layout(key: Optional[str]) -> Layout:
    return LAYOUTS.get(key or "", LAYOUTS["chap_matn"])


# ───────────────────────────────────────────── chizish yordamchilari

def rgb(hex_color: str) -> RGBColor:
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _alpha(shape, alpha: float) -> None:
    fill = shape._element.spPr.find(qn("a:solidFill"))
    if fill is None or not len(fill) or alpha >= 1:
        return
    node = etree.SubElement(fill[0], qn("a:alpha"))
    node.set("val", str(int(max(0.0, min(1.0, alpha)) * 100000)))


def _soft_edge(shape, inches: float) -> None:
    sp = shape._element.spPr
    eff = sp.find(qn("a:effectLst"))
    if eff is None:
        eff = etree.SubElement(sp, qn("a:effectLst"))
    node = etree.SubElement(eff, qn("a:softEdge"))
    node.set("rad", str(int(Inches(inches))))


def shape(slide, name: str, kind, x, y, w, h, color: str, *, alpha: float = 1.0, rotation: float = 0.0,
          soft: float = 0.0, line: Optional[str] = None, line_pt: float = 0.0, round_: Optional[float] = None,
          fill: bool = True):
    """Oddiy shakl (Morph uchun nomi `name`). kind — MSO_SHAPE qiymati."""
    sp = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(max(w, 0.01)), Inches(max(h, 0.01)))
    sp.name = name
    if round_ is not None and len(sp.adjustments):
        sp.adjustments[0] = max(0.0, min(0.5, round_))
    if fill:
        sp.fill.solid()
        sp.fill.fore_color.rgb = rgb(color)
        _alpha(sp, alpha)
    else:
        sp.fill.background()
    if line:
        sp.line.color.rgb = rgb(line)
        sp.line.width = Pt(line_pt or 1)
    else:
        sp.line.fill.background()
    sp.shadow.inherit = False
    if rotation:
        sp.rotation = rotation
    if soft:
        _soft_edge(sp, soft)
    if sp.has_text_frame:
        sp.text_frame.text = ""
    return sp


def textbox(slide, name: str, x, y, w, h, value: str, *, size: float, color: str, font: str,
            bold: bool = False, italic: bool = False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
            smallest: Optional[float] = None, line: float = 1.15, caps: bool = False):
    from services.pro3d.build import fit_size

    value = str(value or "")
    if caps:
        value = value.upper()
    if smallest:
        size = fit_size(value, w, h, size, smallest, line + 0.06)
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tb.name = name
    frame = tb.text_frame
    frame.word_wrap = True
    frame.auto_size = None
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = anchor
    for index, part in enumerate(value.split("\n")):
        para = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        para.alignment = align
        para.line_spacing = line
        run = para.add_run()
        run.text = part
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = rgb(color)
    return tb


def background(slide, st: Style) -> None:
    fill = slide.background.fill
    if st.bg2:
        fill.gradient()
        fill.gradient_angle = st.bg_angle
        stops = fill.gradient_stops
        stops[0].color.rgb = rgb(st.bg)
        stops[0].position = 0.0
        stops[1].color.rgb = rgb(st.bg2)
        stops[1].position = 1.0
    else:
        fill.solid()
        fill.fore_color.rgb = rgb(st.bg)


# ───────────────────────────────────────────── fon bezaklari (Morph bilan harakatlanadi)

def _rng(seed: int) -> random.Random:
    return random.Random(seed * 7919 + 17)


def deco_specs(st: Style, lay: Layout, variant: int, model_box: Tuple[float, float, float, float]) -> List[dict]:
    """Bezak shakllari ro'yxati. Soni va nomlari uslubga bog'liq (har slaydda bir xil) — joyi, o'lchami va
    burchagi `variant` ga qarab o'zgaradi: Morph ularni slayddan slaydga suradi, aylantiradi, kattalashtiradi."""
    r = _rng(variant)
    cx = (model_box[0] + model_box[2]) / 2
    cy = (model_box[1] + model_box[3]) / 2
    out: List[dict] = []
    c, a = st.deco_color, st.deco_alpha
    if st.deco == "band":            # qiya shaffof yorug'lik tasmalari (videodagi kabi)
        angle = r.choice((-24, -18, -30, 20, 26))
        x0 = r.uniform(3.0, 8.0)
        out.append(dict(kind=MSO_SHAPE.RECTANGLE, x=x0, y=-3.0, w=r.uniform(2.6, 4.2), h=H + 6, color=c,
                        alpha=a, rotation=angle))
        out.append(dict(kind=MSO_SHAPE.RECTANGLE, x=x0 + r.uniform(3.2, 5.0), y=-3.0, w=r.uniform(0.5, 1.2),
                        h=H + 6, color=c, alpha=a * 0.8, rotation=angle))
    elif st.deco == "orbs":          # yumshoq doiralar
        for k in range(3):
            d = r.uniform(1.6, 4.6) if k else r.uniform(4.5, 7.0)
            x = cx - d / 2 + r.uniform(-3.5, 3.5) if k else cx - d / 2
            y = cy - d / 2 + r.uniform(-2.8, 2.8) if k else cy - d / 2
            out.append(dict(kind=MSO_SHAPE.OVAL, x=x, y=y, w=d, h=d, color=c, alpha=a * (1.0 if k else 0.8),
                            soft=d * 0.18))
    elif st.deco == "blob":          # katta yumaloq dog'lar
        for k in range(2):
            w = r.uniform(4.5, 8.0)
            h = w * r.uniform(0.6, 0.9)
            out.append(dict(kind=MSO_SHAPE.OVAL, x=r.uniform(-2.5, W - w + 2.5), y=r.uniform(-2.5, H - h + 2.5),
                            w=w, h=h, color=c, alpha=a, rotation=r.uniform(-30, 30), soft=0.6))
    elif st.deco == "spot":          # muzey nuri: model ortida yorug' dog'
        d = max(model_box[2] - model_box[0], model_box[3] - model_box[1]) * 1.25 + 1.0
        out.append(dict(kind=MSO_SHAPE.OVAL, x=cx - d / 2, y=cy - d * 0.45, w=d, h=d * 0.9, color=c, alpha=a,
                        soft=d * 0.3))
        out.append(dict(kind=MSO_SHAPE.RECTANGLE, x=cx - 0.02, y=-0.2, w=0.04, h=0.5, color=st.accent, alpha=0.6))
    elif st.deco == "frame":         # atlas: ingichka ramka va burchak belgilar
        inset = r.choice((0.28, 0.34, 0.4))
        out.append(dict(kind=MSO_SHAPE.RECTANGLE, x=inset, y=inset, w=W - 2 * inset, h=H - 2 * inset, color=c,
                        fill=False, line=c, line_pt=0.75))
        out.append(dict(kind=MSO_SHAPE.RECTANGLE, x=r.uniform(5.5, 11.5), y=H - inset - 0.04, w=1.2, h=0.04,
                        color=st.accent, alpha=1.0))
    elif st.deco == "grid":          # rentgen: gorizontal skaner chiziqlari
        for k in range(5):
            y = r.uniform(0.3, H - 0.3)
            out.append(dict(kind=MSO_SHAPE.RECTANGLE, x=-0.2, y=y, w=W + 0.4, h=0.012 if k % 2 else 0.025,
                            color=c, alpha=a * (1.6 if k == 0 else 1.0)))
    elif st.deco == "stripes":       # grafit: qiya chiziqlar
        angle = r.choice((32, 38, -32))
        x0 = r.uniform(8.0, 11.5)
        for k in range(3):
            out.append(dict(kind=MSO_SHAPE.RECTANGLE, x=x0 + k * 0.55, y=-2.0, w=0.12, h=H + 4, color=c,
                            alpha=a * (1.6 - 0.4 * k), rotation=angle))
    elif st.deco == "lines":         # tungi ko'k: qiya nur chiziqlari, yorug' izlar va nuqtalar — Morph ularni suradi
        angle = r.uniform(-30, -14)
        for k in range(4):
            out.append(dict(kind=MSO_SHAPE.RECTANGLE, x=r.uniform(-2.0, W - 1.0), y=-4.0, w=(0.035, 0.018, 0.05, 0.012)[k],
                            h=H + 8, color=c, alpha=a * (1.0, 0.7, 0.45, 0.9)[k], rotation=angle + r.uniform(-4, 4)))
        for k in range(2):
            w = r.uniform(3.5, 7.5)
            out.append(dict(kind=MSO_SHAPE.RECTANGLE, x=r.uniform(-1.0, W - w + 1.0), y=r.uniform(0.4, H - 0.4), w=w,
                            h=0.018, color=c, alpha=a * 1.3))
        d = max(model_box[2] - model_box[0], model_box[3] - model_box[1]) * 1.1 + 1.0
        out.append(dict(kind=MSO_SHAPE.OVAL, x=cx - d / 2 + r.uniform(-0.6, 0.6), y=cy - d / 2 + r.uniform(-0.4, 0.4),
                        w=d, h=d, color=c, alpha=a * 0.45, soft=d * 0.3))
        for k in range(4):                # nuqtalar faqat chetlarda — matn ustiga tushmaydi
            s = r.uniform(0.06, 0.12)
            x, y = (r.uniform(0.2, W - 0.2), r.choice((r.uniform(0.15, 0.45), r.uniform(H - 0.4, H - 0.15)))) if k % 2 \
                else (r.choice((r.uniform(0.15, 0.45), r.uniform(W - 0.45, W - 0.15))), r.uniform(0.3, H - 0.3))
            out.append(dict(kind=MSO_SHAPE.OVAL, x=x, y=y, w=s, h=s, color=st.accent, alpha=r.uniform(0.55, 0.95)))
    for k, spec in enumerate(out):
        spec["name"] = f"!!deco_{k}"
    return out


def draw_deco(slide, specs: List[dict]) -> List:
    shapes = []
    for s in specs:
        shapes.append(shape(slide, s["name"], s["kind"], s["x"], s["y"], s["w"], s["h"], s["color"],
                            alpha=s.get("alpha", 1.0), rotation=s.get("rotation", 0.0), soft=s.get("soft", 0.0),
                            line=s.get("line"), line_pt=s.get("line_pt", 0.0), fill=s.get("fill", True)))
    return shapes


def ground_shadow(slide, st: Style, model_box: Tuple[float, float, float, float]):
    """Model ostidagi yumshoq soya — model havoda osilib turmaydi. Ochiq fonli uslublarda."""
    if st.shadow_alpha <= 0:
        return None
    left, top, right, bottom = model_box
    w = max(0.8, (right - left) * 0.75)
    if bottom > H - 0.1:                       # model pastki chetdan chiqib ketgan — soya ko'rinmaydi
        return None
    h = max(0.18, min(0.5, w * 0.12))
    return shape(slide, "!!shadow", MSO_SHAPE.OVAL, (left + right) / 2 - w / 2, bottom - h * 0.35, w, h,
                 st.shadow, alpha=st.shadow_alpha, soft=h * 0.45)
