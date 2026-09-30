"""Taqdimot uslublari — bir xil bloklar, butunlay boshqacha ko'rinish.

Nega kerak. Bloklar (kartochka, vaqt o'qi, ko'rsatkich, iqtibos ...)
mazmunga qarab tanlanadi, lekin hammasi bitta dizayn tilida chizilsa —
bir xil sarlavha, bir xil gradientli karta, doira ichidagi ikonka —
taqdimot qaysi mavzuda bo'lmasin bir xil ko'rinadi. Uslub shu tilni
almashtiradi: karta qutimi yoki faqat chiziqmi, sarlavha qayerda,
shrift qaysi, fon och yoki to'q.

Uslub AI ga ta'sir qilmaydi (u CSS yozmaydi): faqat `deck_style`
ning oxiriga qo'shiladigan qoidalar va rang sxemasining o'zgarishi.
Shuning uchun token ham, xavf ham qo'shilmaydi.

MUHIM: slayd HTML dan PowerPointning haqiqiy shakllariga o'tkaziladi
(`html_extract`). U faqat DOM elementlarini ko'radi: `::before`,
radial gradient, matn konturi (`-webkit-text-stroke`), ko'p qatlamli
fon PowerPointda yo'qoladi. Shuning uchun bezaklar ham HAQIQIY
element bo'lib qo'yiladi (`decorate`), CSS esa faqat tekis rang,
chiziqli gradient, chegara va yumaloq burchakdan foydalanadi.
"""

import dataclasses
import re
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Style:
    key: str
    name: str            # tugma yozuvi
    note: str            # bir qatorlik tavsif
    css: str


def _mix(base: str, other: str, ratio: float) -> str:
    try:
        a = [int(base[i:i + 2], 16) for i in (0, 2, 4)]
        b = [int(other[i:i + 2], 16) for i in (0, 2, 4)]
    except (ValueError, IndexError):
        return base
    return "".join(f"{int(round(x * (1 - ratio) + y * ratio)):02X}" for x, y in zip(a, b))


# ── 1. Toza ────────────────────────────────────────────────────────────────
_TOZA = """
/* TOZA: qutisiz, faqat ingichka chiziqlar, ko'p bo'sh joy. */
.slide{padding:88px 130px;gap:44px}
.head{gap:16px}
.title{font-size:60px;font-weight:600;letter-spacing:-1px}
.title.big{font-size:104px;font-weight:600;letter-spacing:-3px}
.rule{width:72px;height:4px;border-radius:0}
.cols>.card,.steps>.card{background:none;border-radius:0;padding:30px 0 0;
min-height:0;border-top:3px solid #ACCENT;border-bottom:0;
justify-content:flex-start;gap:14px}
.cols>.card:has(>.ikon-dot:first-child),
.steps>.card:has(>.ikon-dot:first-child){border-bottom:0;border-radius:0;
justify-content:flex-start;border-top:3px solid #ACCENT}
.cols:has(>.card>.ikon-dot:first-child),
.steps:has(>.card>.ikon-dot:first-child){padding-top:0;row-gap:40px}
.cols>.card>.ikon-dot:first-child,.steps>.card>.ikon-dot:first-child{
margin-top:0;align-self:flex-start}
.ikon-dot{background:none!important;width:64px;height:64px;
justify-content:flex-start}
.ikon-dot .ikon{width:56px;height:56px}
.card-num{font-size:26px;color:#MUTED;font-weight:400;letter-spacing:3px}
.card-title{font-size:42px}
.list{gap:0;justify-content:flex-start}
.list>.item{padding:26px 0;border-bottom:2px solid #SOFT}
.list>.item:first-child{border-top:2px solid #SOFT}
.item-ikon{background:none!important;width:64px;height:64px}
.item-ikon .ikon{width:54px;height:54px}
.timeline .stop{border-top:2px solid #HEADING;align-items:flex-start;
text-align:left;padding:0 28px 0 0}
.timeline .bead{width:14px;height:14px;margin-top:-8px;background:#HEADING}
.timeline .when{font-size:44px;font-weight:600;color:#HEADING;margin-top:10px}
.slide.dark{background:#BACKGROUND;color:#HEADING}
.slide.dark .title,.slide.dark .lead{color:#HEADING}
.slide.dark .lead{color:#MUTED;font-size:40px}
.slide.dark .card,.slide.dark .formula,.slide.dark .misol{background:#SOFT}
.slide.dark .card-title,.slide.dark .item-text,.slide.dark .item-text b,
.slide.dark .kpi-value,.slide.dark .kpi-label,.slide.dark .misol-task,
.slide.dark .misol-answer,.slide.dark .formula-body,.slide.dark .quote,
.slide.dark .when,.slide.dark .what{color:#HEADING}
.slide.dark .card-note,.slide.dark .kpi-note,.slide.dark .misol-text,
.slide.dark .formula-note,.slide.dark .quote-by,.slide.dark .note{color:#MUTED}
.slide.dark .kpi-value{color:#ACCENT}
.bezak{display:none}
"""

# ── 2. Jurnal ──────────────────────────────────────────────────────────────
_JURNAL = """
/* JURNAL: serif, qog'oz foni, ingichka ramka, "01" raqamlar. */
.slide{padding:84px 120px;gap:44px}
.title,.card-title,.when,.kpi-value,.lead,.misol-task{font-family:SERIF}
.title{font-size:66px;font-weight:700;letter-spacing:-0.5px}
.title.big{font-size:110px;line-height:1.02;font-weight:700}
.head{gap:18px;border-bottom:3px solid #HEADING;padding-bottom:22px}
.rule{display:none}
.cols>.card,.steps>.card{background:none;border-radius:0;min-height:0;
padding:34px 30px;border:2px solid #HEADING;justify-content:flex-start;gap:14px}
.cols>.card:has(>.ikon-dot:first-child),
.steps>.card:has(>.ikon-dot:first-child){border:2px solid #HEADING;
border-radius:0;justify-content:flex-start}
.cols:has(>.card>.ikon-dot:first-child),
.steps:has(>.card>.ikon-dot:first-child){padding-top:0}
.ikon-dot,.item-ikon{display:none}
.card-num{font-family:SERIF;font-size:88px;font-weight:400;color:#ACCENT;
line-height:1}
.card-title{font-size:44px;font-style:italic}
.card-note{font-family:SERIF;font-size:32px}
.list{gap:30px}
.item{align-items:baseline}
.item-num{font-family:SERIF;font-size:54px;font-style:italic;color:#ACCENT;
width:92px;flex:none;line-height:1}
.item-text{font-family:SERIF;font-size:38px}
.item-text b{font-style:italic}
.timeline .stop{border-top:2px solid #HEADING}
.timeline .bead{border-radius:0;width:16px;height:16px;margin-top:-9px}
.timeline .when{font-size:54px;font-style:italic;font-weight:400;color:#ACCENT}
.timeline .what{font-family:SERIF;font-size:30px}
.kpi{border-left:0;border-top:3px solid #HEADING;padding:24px 0 0}
.quote-mark,.quote{color:#HEADING}
.slide.dark{background:#BACKGROUND;color:#HEADING}
.slide.dark .title{color:#HEADING}
.slide.dark .lead{color:#BODY;font-style:italic;font-size:44px}
.slide.dark .card,.slide.dark .formula,.slide.dark .misol{background:#SOFT}
.slide.dark .card-title,.slide.dark .item-text,.slide.dark .item-text b,
.slide.dark .kpi-value,.slide.dark .kpi-label,.slide.dark .misol-task,
.slide.dark .misol-answer,.slide.dark .formula-body,.slide.dark .quote,
.slide.dark .when,.slide.dark .what{color:#HEADING}
.slide.dark .card-note,.slide.dark .kpi-note,.slide.dark .misol-text,
.slide.dark .formula-note,.slide.dark .quote-by,.slide.dark .note{color:#MUTED}
.slide.dark .kpi-value,.slide.dark .quote-mark{color:#ACCENT}
.slide.dark .head{border-bottom-color:#HEADING}
.bezak{display:none}
"""

# ── 3. Blok ────────────────────────────────────────────────────────────────
_BLOK = """
/* BLOK: rangli sarlavha tasmasi, to'la rangli kvadrat kartalar. */
.slide{padding:0;gap:0;position:relative}
.slide>.head{background:#BAND;padding:64px 96px 56px;gap:18px}
.slide>.head .title{color:#INVERT;font-size:62px}
.slide>.head .rule{background:#ACCENT;width:160px;height:8px;border-radius:0}
.slide>.body{padding:72px 96px}
.cols>*:nth-child(5n+1),.steps>.card:nth-child(4n+1),.list>.item:nth-child(5n+1){--deep:#DEEP1}
.cols>*:nth-child(5n+2),.steps>.card:nth-child(4n+3),.list>.item:nth-child(5n+2){--deep:#DEEP2}
.cols>*:nth-child(5n+3),.steps>.card:nth-child(4n+5),.list>.item:nth-child(5n+3){--deep:#DEEP3}
.cols>*:nth-child(5n+4),.steps>.card:nth-child(4n+7),.list>.item:nth-child(5n+4){--deep:#DEEP4}
.cols>*:nth-child(5n+5),.list>.item:nth-child(5n+5){--deep:#DEEP5}
.cols>.card,.steps>.card{background:var(--deep);border-radius:0;border:0;
padding:44px 40px;min-height:0;justify-content:flex-start;gap:16px}
.cols>.card:has(>.ikon-dot:first-child),
.steps>.card:has(>.ikon-dot:first-child){border-bottom:0;border-radius:0;
justify-content:flex-start}
.cols:has(>.card>.ikon-dot:first-child),
.steps:has(>.card>.ikon-dot:first-child){padding-top:0}
.cols>.card>.ikon-dot:first-child,.steps>.card>.ikon-dot:first-child{
margin-top:0;align-self:flex-start}
.ikon-dot{background:none!important;width:72px;height:72px;
justify-content:flex-start}
.ikon-dot .ikon{width:64px;height:64px}
.card-num{color:#FFFFFF;opacity:.6;font-size:64px}
.card-title,.card-note{color:#FFFFFF}
.card-title{font-size:44px}
.item-ikon{border-radius:0;width:88px;height:88px;background:var(--deep)}
.item-ikon .ikon{width:48px;height:48px}
.list{gap:30px}
.timeline .stop{border-top:10px solid #ACCENT;align-items:flex-start;
text-align:left;padding:0 26px 0 0}
.timeline .stop:nth-child(5n+1){border-top-color:#TONE1}
.timeline .stop:nth-child(5n+2){border-top-color:#TONE2}
.timeline .stop:nth-child(5n+3){border-top-color:#TONE3}
.timeline .stop:nth-child(5n+4){border-top-color:#TONE4}
.timeline .stop:nth-child(5n+5){border-top-color:#TONE5}
.timeline .bead{display:none}
.timeline .when{font-size:64px;font-weight:800;margin-top:22px;color:#HEADING}
.slide.dark{background:#BAND}
.slide.dark>.body{padding:96px 96px 96px 160px}
.slide.dark .title.big{font-size:112px;font-weight:800}
.slide.dark .rule{width:200px;height:10px;border-radius:0}
.blok-bar{position:absolute;left:0;top:0;bottom:0;width:56px;
background:#ACCENT;z-index:2}
.bezak{display:none}
"""

# ── 4. Kontur ──────────────────────────────────────────────────────────────
_KONTUR = """
/* KONTUR: to'ldirilmagan ramkalar, burchak belgilari, mono raqamlar. */
.slide{padding:88px 110px;gap:48px}
.title{font-size:58px}
.title.big{font-size:100px;line-height:1.05}
.rule{display:none}
.head{flex-direction:row;align-items:stretch;gap:28px}
.kbar{width:14px;flex:none;background:#ACCENT}
.cols>.card,.steps>.card{position:relative;background:#FFFFFF;
border:2px solid #ACCENT;border-radius:4px;min-height:0;padding:40px 36px;
justify-content:flex-start;gap:14px}
.cols>.card:has(>.ikon-dot:first-child),
.steps>.card:has(>.ikon-dot:first-child){border:2px solid #ACCENT;
border-radius:4px;justify-content:flex-start}
.cols:has(>.card>.ikon-dot:first-child),
.steps:has(>.card>.ikon-dot:first-child){padding-top:0}
.cols>.card>.ikon-dot:first-child,.steps>.card>.ikon-dot:first-child{
margin-top:0;align-self:flex-start}
.kor{position:absolute;width:34px;height:34px;z-index:2}
.kor-a{top:-6px;left:-6px;border-top:8px solid #ACCENT;
border-left:8px solid #ACCENT}
.kor-b{bottom:-6px;right:-6px;border-bottom:8px solid #ACCENT;
border-right:8px solid #ACCENT}
.ikon-dot,.item-ikon{background:none!important;border:3px solid #ACCENT;
width:84px;height:84px;border-radius:50%}
.item-ikon{width:76px;height:76px}
.card-num{font-family:'Courier New','Liberation Mono',monospace;font-size:28px;
letter-spacing:2px;color:#ACCENT;font-weight:400}
.card-title{font-size:36px;text-transform:uppercase;letter-spacing:1px}
.list{gap:26px}
.item{background:#FFFFFF;border:2px solid #SOFT;border-left:10px solid #ACCENT;
padding:20px 30px;border-radius:4px}
.timeline .stop{border-top:3px solid #ACCENT}
.timeline .bead{border-radius:0;width:26px;height:26px;margin-top:-15px;
background:#BACKGROUND;border:5px solid #ACCENT}
.timeline .when{font-family:'Courier New','Liberation Mono',monospace;
font-size:40px}
.bezak{display:none}
"""

# ── 5. Qorong'u ────────────────────────────────────────────────────────────
_QORONGU = """
/* QORONG'U: to'q fon, yorqin urg'u, shaffof kartalar. Ranglar `adapt`
   da to'q sxemaga o'tkazilgan. */
.slide{padding:92px 110px;gap:48px;
background:linear-gradient(160deg,#BACKGROUND 0%,#BANDDEEP 100%)}
.title{font-size:62px}
.rule{background:#ACCENT;width:160px;height:6px}
.cols>.card,.steps>.card{background:#SOFT;border:2px solid #EDGE;
border-radius:26px;min-height:0;padding:44px;justify-content:flex-start;
gap:16px;border-bottom:2px solid #EDGE}
.cols>.card:has(>.ikon-dot:first-child),
.steps>.card:has(>.ikon-dot:first-child){border-bottom:2px solid #EDGE;
border-radius:26px;justify-content:flex-start}
.cols:has(>.card>.ikon-dot:first-child),
.steps:has(>.card>.ikon-dot:first-child){padding-top:0}
.cols>.card>.ikon-dot:first-child,.steps>.card>.ikon-dot:first-child{
margin-top:0;align-self:flex-start}
.ikon-dot,.item-ikon{background:linear-gradient(135deg,#ACCENT,#TONE2)!important}
.card-num{font-size:34px;letter-spacing:4px}
.list>.item{background:#SOFT;border:2px solid #EDGE;border-radius:22px;
padding:22px 30px}
.timeline .stop{border-top:3px solid #EDGE}
.timeline .bead{width:26px;height:26px;margin-top:-15px}
.timeline .when{font-size:46px}
th{color:#BACKGROUND}
td{border-bottom:2px solid #EDGE}
tr:nth-child(even) td{background:#SOFT}
.slide.dark{background:linear-gradient(160deg,#BAND 0%,#BANDDEEP 100%)}
.bezak{display:block}
.bezak-a{background:#BANDGLOW}
.bezak-b{background:#BANDSOFT}
"""

STYLES: Dict[str, Style] = {s.key: s for s in (
    Style("toza", "Toza", "qutisiz, ingichka chiziqlar, ko'p bo'sh joy", _TOZA),
    Style("jurnal", "Jurnal", "serif shrift, qog'oz foni, ramkalar", _JURNAL),
    Style("blok", "Blok", "rangli tasma va to'la rangli kartalar", _BLOK),
    Style("kontur", "Kontur", "kontur ramka, burchak belgilari, texnik", _KONTUR),
    Style("qorongu", "Qorong'u", "to'q fon, yorqin urg'u", _QORONGU),
)}
STYLE_KEYS: List[str] = list(STYLES)

# Mavzuga qarab avtomatik tanlov (mijoz tanlamasa yoki "Avto").
_HINTS = (
    ("jurnal", ("falsafa", "adabiyot", "tarix", "til ", "tilshunos", "din", "madaniyat",
                "san'at", "филосо", "литерат", "истор", "культур", "philosoph",
                "literature", "history", "culture", "art")),
    ("qorongu", ("sun'iy intellekt", "texnologi", "dastur", "kiber", "raqamli", "robot",
                 "internet", "innovatsi", "технолог", "цифров", "кибер", "software",
                 "cyber", "digital", "artificial", "tech")),
    ("kontur", ("fizika", "kimyo", "matematik", "muhandis", "informatika", "biologiya",
                "fan", "физик", "хими", "математ", "инженер", "physics", "chemistry",
                "math", "engineer", "science")),
    ("blok", ("biznes", "marketing", "iqtisod", "moliya", "bank", "savdo", "startap",
              "бизнес", "маркетинг", "эконом", "финанс", "business", "marketing",
              "econom", "finance")),
)


def suggest(topic: str) -> str:
    text = (topic or "").lower()
    for key, words in _HINTS:
        if any(word in text for word in words):
            return key
    return "toza"


def css(key: str) -> str:
    style = STYLES.get(key)
    return style.css if style else ""


def adapt(theme, key: str):
    """Uslubga mos rang sxemasi (yangi Theme); uslub yo'q bo'lsa — o'zi."""
    if key not in STYLES:
        return theme
    changes = {"style": key}
    if key == "jurnal":
        changes.update(background="FBF7EE",
                       accent_soft=_mix(theme.accent, "FBF7EE", 0.90))
    elif key == "kontur":
        changes.update(background="F3F7FB",
                       accent_soft=_mix(theme.accent, "F3F7FB", 0.85))
    elif key == "qorongu":
        night = _mix(theme.dark or theme.heading, "000000", 0.50)
        light = _mix(theme.accent, "FFFFFF", 0.38)
        deep = _mix(night, theme.accent, 0.14)
        changes.update(
            background=night, heading="FFFFFF", body="D4DBEA", muted="98A4BD",
            accent=light, accent_soft=_mix(night, "FFFFFF", 0.08),
            invert="FFFFFF", dark=_mix(night, "000000", 0.25),
            chart=tuple(_mix(c, "FFFFFF", 0.30) for c in theme.chart) or (light,))
        # Kartochka chegarasi uchun: fon bilan kartochka orasidagi tus.
        changes["dark"] = deep
    return dataclasses.replace(theme, **changes)


# ── HTML bezaklari ─────────────────────────────────────────────────────────

def _tag(name: str, css_class: str, opening_only: bool = True) -> "re.Pattern":
    """`<name class="... css_class ...">` — sinf nomi ANIQ (card-num ga mos kelmaydi)."""
    token = rf'(?<![\w-]){re.escape(css_class)}(?![\w-])'
    return re.compile(rf'<{name}\b[^>]*\bclass\s*=\s*["\'][^"\']*{token}[^"\']*["\'][^>]*>',
                      re.IGNORECASE)


_CARD_OPEN = _tag("div", "card")
_SLIDE_OPEN = re.compile(r'(' + _tag("section", "slide").pattern + r')', re.IGNORECASE)
_LIST_OPEN = _tag("div", "list")
_HEAD_OPEN = _tag("div", "head")
_ITEM_ICON = re.compile(_tag("span", "item-ikon").pattern + r'.*?</span>',
                        re.IGNORECASE | re.DOTALL)
_CARD_NUM = re.compile(r'(' + _tag("div", "card-num").pattern + r')\s*([^<]+)', re.IGNORECASE)


def decorate(body: str, theme) -> str:
    """Uslubga kerakli HAQIQIY elementlarni qo'shadi (pseudo-element emas)."""
    key = getattr(theme, "style", "")
    if key in ("toza", "kontur"):
        # Bu uslublarda ikonka rangli doirasiz turadi: oq ikonka ko'rinmaydi.
        body = body.replace('data-icon-color="FFFFFF"',
                            f'data-icon-color="{theme.accent.lstrip("#")}"')
    if key == "jurnal":
        return _number_items(body)
    if key == "blok":
        return _SLIDE_OPEN.sub(lambda m: m.group(1) + '<div class="blok-bar"></div>'
                               if 'dark' in m.group(1) else m.group(1), body)
    if key == "kontur":
        body = _HEAD_OPEN.sub(lambda m: m.group(0) + '<div class="kbar"></div>', body)
        body = _CARD_OPEN.sub(lambda m: m.group(0)
                              + '<i class="kor kor-a"></i><i class="kor kor-b"></i>', body)
        return _CARD_NUM.sub(lambda m: m.group(1) + "// " + m.group(2).strip(), body)
    if key == "qorongu":
        glow = '<div class="bezak bezak-a"></div><div class="bezak bezak-b"></div>'
        if "bezak-a" in body:
            return body
        return _SLIDE_OPEN.sub(lambda m: m.group(1) + glow, body, count=1)
    return body


def _number_items(body: str) -> str:
    """Ro'yxat bandlaridagi ikonka o'rniga 01, 02 ... raqam (har ro'yxatda qaytadan)."""
    out, pos, count = [], 0, 0
    marks = sorted([(m.start(), "list") for m in _LIST_OPEN.finditer(body)]
                   + [(m.start(), "icon", m) for m in _ITEM_ICON.finditer(body)],
                   key=lambda t: t[0])
    for mark in marks:
        if mark[1] == "list":
            count = 0
            continue
        match = mark[2]
        count += 1
        out.append(body[pos:match.start()])
        out.append(f'<span class="item-num">{count:02d}</span>')
        pos = match.end()
    out.append(body[pos:])
    return "".join(out)
