"""Zamonaviy taqdimotning san'at rahbari: har slaydga sahna (fon, sarlavha, blok varianti) tanlaydi.

Nega kerak. Bloklar (kartochka, ro'yxat, ko'rsatkich ...) mazmunga qarab tanlanadi, lekin har biri doim
bitta ko'rinishda chizilardi: oq varaq, chapda sarlavha, ostida ingichka chiziq, och kartochkalar. Ikki
kartochkali slayd aynan bir xil, butun taqdimot esa bitta varaqning nusxalaridek ko'rinardi.

Endi slaydlar yozib bo'lingach, kod butun taqdimotga qaraydi va har slaydga uch narsa beradi:
  • fon (`art-c-*`): oq, och tusli, chap tasma, rangli sarlavha tasmasi yoki to'q;
  • sarlavha (`art-h-*`): chiziq, katta tartib raqami yoki yon chiziq;
  • blok varianti (`art-<tur>-*`): masalan kartochka — ikonkali, raqamli, gorizontal qator yoki to'la rangli.
Tanlov taqdimot bo'yicha eng kam ishlatilganini oladi va qo'shni slayd bilan bir xil bo'lmaydi; tasodif
yo'q (sarlavhalardan hisoblanadi), shuning uchun sahifa qayta yig'ilganda ko'rinish o'zgarmaydi.

Qaror faqat `<section>` sinflarida saqlanadi (manba HTML toza qoladi, AI bezakni ko'rmaydi). Bezak
elementlari (raqam, doira, tasma) `dress` da HAQIQIY element bo'lib qo'shiladi: PowerPointga o'tkazgich
(`html_extract`) `::before` ni ko'rmaydi.
"""
import re
import zlib
from typing import Dict, List, Optional, Tuple

ART = "art"

# Tur → variantlar (birinchisi — oldingi dizayn).
VARIANTS: Dict[str, Tuple[str, ...]] = {
    "cards": ("icon", "num", "rows", "solid"),
    "list": ("dots", "grid", "panel", "strip"),
    "kpi": ("tiles", "giant", "ring"),
    "steps": ("cards", "road", "stairs"),
    "timeline": ("line", "pills"),
    "compare": ("cards", "versus"),
    "photo": ("bleed", "frame"),
    "quote": ("card", "stage"),
    "mixed": ("plain", "panel"),
    "plan": ("tiles", "index"),
    "chart": ("plain",),
    "table": ("plain",),
    "formula": ("plain",),
    "misol": ("plain",),
    "text": ("plain",),
}

# Qaysi turga qaysi fonlar yarashadi. To'q fon faqat qisqa matnli bloklarga (uzun abzats to'q fonda og'ir).
CANVASES: Dict[str, Tuple[str, ...]] = {
    "cards": ("light", "tint", "side", "top", "dark"),
    "list": ("light", "tint", "side", "top"),
    "kpi": ("light", "tint", "top", "dark"),
    "steps": ("light", "tint", "side", "dark"),
    "timeline": ("light", "tint", "top", "dark"),
    "compare": ("light", "tint", "side", "top"),
    "photo": ("light", "tint"),
    "quote": ("light", "tint", "dark"),
    "mixed": ("light", "tint", "side", "top"),
    "plan": ("light", "top", "side"),
    "chart": ("light", "side", "top"),
    "table": ("light", "side", "top"),
    "formula": ("light", "tint", "side", "top"),
    "misol": ("light", "side", "top"),
    "text": ("light", "tint", "side", "top"),
}
HEADS = ("rule", "kicker", "bar")

# Variantning o'ziga xos foni bo'lsa, umumiy fon tanlanmaydi.
_OWN_CANVAS = {("quote", "stage"): "dark", ("list", "panel"): "light", ("photo", "frame"): "tint"}

_SECTION = re.compile(r'<section\b([^>]*)\bclass\s*=\s*"([^"]*)"', re.IGNORECASE)


def _has(body: str, css_class: str) -> bool:
    return bool(re.search(r'class\s*=\s*["\'][^"\']*(?<![\w-])' + re.escape(css_class) + r'(?![\w-])', body))


def _classes(body: str) -> List[str]:
    match = _SECTION.search(body or "")
    return match.group(2).split() if match else []


def _own_classes(body: str) -> List[str]:
    """Slaydning o'z sinflari (oldingi sahna qo'shgan `art-*` va to'q fon olib tashlanadi)."""
    classes = _classes(body)
    if "art-dk" in classes:             # to'q fonni sahna bergan, slaydning o'zi to'q emas
        classes = [c for c in classes if c != "dark"]
    return [c for c in classes if not c.startswith(ART)]


def kind_of(body: str) -> str:
    """Slaydning asosiy bloki (sahna tanlash uchun)."""
    if _has(body, "chart") or _has(body, "calc") or _has(body, "chart-stack"):
        return "chart"
    if _has(body, "photo-in") or (_has(body, "rasm") and _has(body, "split")):
        return "photo"
    if _has(body, "quote"):
        return "quote"
    if _has(body, "misol"):
        return "misol"
    if _has(body, "formula"):
        return "formula"
    if _has(body, "steps"):
        return "steps"
    if _has(body, "timeline"):
        return "timeline"
    if _has(body, "kpi"):
        return "kpi"
    if _has(body, "split"):
        return "mixed"
    if "<table" in body.lower():
        return "table"
    if _has(body, "cols-2") and _has(body, "card") and len(re.findall(r'class\s*=\s*"card[ "]', body)) == 2 \
            and _has(body, "list"):
        return "compare"
    if _has(body, "card"):
        return "cards"
    if _has(body, "list"):
        return "list"
    return "text"


def _count(body: str, css_class: str) -> int:
    return len(re.findall(r'class\s*=\s*"(?:[^"]*\s)?' + re.escape(css_class) + r'(?:\s[^"]*)?"', body))


def _fits(kind: str, variant: str, body: str) -> bool:
    """Variant shu slayd mazmuniga sig'adimi (masalan, halqa faqat qisqa raqamlarga)."""
    if kind == "kpi" and variant == "ring":
        values = re.findall(r'class\s*=\s*"kpi-value[^"]*"[^>]*>([^<]*)<', body)
        return bool(values) and all(len(v.strip()) <= 6 for v in values) and len(values) <= 4
    if kind == "cards" and variant == "rows":
        return 2 <= _count(body, "card") <= 6 and _has(body, "card-note")
    if kind == "cards" and variant == "solid":
        return not _has(body, "list")
    if kind == "list" and variant == "panel":
        return _has(body, "lead") and 2 <= _count(body, "item") <= 5
    if kind == "list" and variant == "grid":
        return 3 <= _count(body, "item") <= 6
    if kind == "steps" and variant == "stairs":
        return 3 <= _count(body, "card") <= 5
    if kind == "photo" and variant == "frame":
        return _has(body, "photo-in") or _has(body, "photo")
    if kind == "compare" and variant == "versus":
        return bool(re.search(r'class\s*=\s*"card solid', body))
    if kind == "mixed" and variant == "panel":
        return not _has(body, "chart") and _has(body, "split")
    return True


def _pick(options, used: Dict[str, int], avoid: Tuple[str, ...], salt: int) -> str:
    """Eng kam ishlatilgan variant; teng bo'lsa — sarlavhadan hisoblangan tartibda."""
    pool = [o for o in options if o not in avoid] or list(options)
    order = {o: (used.get(o, 0), (zlib.crc32(o.encode()) + salt) % 997) for o in pool}
    return min(pool, key=lambda o: order[o])


def plan(bodies: List[str], style: str = "") -> List[Optional[Dict[str, str]]]:
    """Har slayd uchun sahna: {'kind', 'variant', 'canvas', 'head'} (muqova va reja uchun None)."""
    out: List[Optional[Dict[str, str]]] = []
    used_variant: Dict[str, Dict[str, int]] = {}
    used_canvas: Dict[str, int] = {}
    used_head: Dict[str, int] = {}
    last_canvas, last_head, last_kind_variant = "", "", ("", "")
    dark_budget = max(1, len(bodies) // 5)
    last = len(bodies) - 1
    for index, body in enumerate(bodies):
        classes = _own_classes(body)
        if index == 0 or not classes:
            out.append(None)
            # Muqova va xulosa to'q: ularning yonida to'q fon tanlanmasin.
            last_canvas = "dark" if "dark" in classes else "light"
            continue
        kind = "plan" if "reja" in classes else kind_of(body)
        salt = zlib.crc32(re.sub(r"<[^>]+>", "", body)[:200].encode("utf-8"))
        # To'q fon: har 5 slaydga bittagacha, yonma-yon emas (xulosa ham to'q — undan oldingi slayd to'q bo'lmaydi).
        next_dark = index + 1 < len(bodies) and "dark" in _own_classes(bodies[index + 1])
        dark_ok = dark_budget > 0 and last_canvas != "dark" and not next_dark
        options = [v for v in VARIANTS.get(kind, ("plain",)) if _fits(kind, v, body)
                   and (dark_ok or _OWN_CANVAS.get((kind, v)) != "dark")] or ["plain"]
        avoid = (last_kind_variant[1],) if last_kind_variant[0] == kind else ()
        # Eski (birinchi) variant oxirgi navbatda: yangi ko'rinishlar avval ishlatiladi.
        used = used_variant.setdefault(kind, {VARIANTS.get(kind, ("plain",))[0]: 0.5})
        variant = _pick(options, used, avoid, salt)
        used_variant[kind][variant] = used_variant[kind].get(variant, 0) + 1
        canvas = _OWN_CANVAS.get((kind, variant))
        if not canvas:
            allowed = list(CANVASES.get(kind, ("light",)))
            if style == "qorongu":          # fon allaqachon to'q — faqat tuzilish fonlari
                allowed = [c for c in allowed if c in ("light", "side", "top")]
            if style == "blok":             # blokda sarlavha o'zi tasma ustida
                allowed = [c for c in allowed if c != "top"]
            if "dark" in classes:
                allowed = ["dark"]
            elif not dark_ok:
                allowed = [c for c in allowed if c != "dark"] or ["light"]
            # Yonma-yon kelmasin; to'q fon kam ishlatilsin (har 5 slaydga bitta).
            canvas = _pick(allowed, used_canvas, (last_canvas,), salt >> 3)
        if canvas == "dark":
            dark_budget -= 1
        used_canvas[canvas] = used_canvas.get(canvas, 0) + 1
        head = "rule" if canvas == "top" else _pick(HEADS, used_head, (last_head,), salt >> 5)
        used_head[head] = used_head.get(head, 0) + 1
        out.append({"kind": kind, "variant": variant, "canvas": canvas, "head": head, "n": f"{index:02d}"})
        last_canvas, last_head, last_kind_variant = canvas, head, (kind, variant)
    return out


def _tagged(body: str, scene: Dict[str, str]) -> str:
    extra = [ART, f"art-{scene['kind']}-{scene['variant']}", f"art-c-{scene['canvas']}",
             f"art-h-{scene['head']}", f"art-n{scene['n']}"]
    def put(match):
        names = [c for c in match.group(2).split() if not c.startswith("art")]
        if "art-dk" in match.group(2).split():
            names = [c for c in names if c != "dark"]
        if scene["canvas"] == "dark" and "dark" not in names:
            names.append("dark")
            names.append("art-dk")
        names += [c for c in extra if c not in names]
        return f'<section{match.group(1)}class="{" ".join(names)}"'
    return _SECTION.sub(put, body, count=1)


def direct(bodies: List[str], style: str = "") -> List[str]:
    """Butun taqdimotga sahnalarni yozadi (faqat `<section>` sinflari)."""
    scenes = plan(bodies, style)
    return [body if scene is None else _tagged(body, scene) for body, scene in zip(bodies, scenes)]


def direct_one(bodies: List[str], index: int, style: str = "") -> str:
    """Bitta qayta yozilgan slayd uchun sahna: butun taqdimotga qarab (saytda sahifani almashtirish)."""
    if not 0 <= index < len(bodies):
        return bodies[index] if 0 <= index < len(bodies) else ""
    return direct(bodies, style)[index]


def strip(body: str) -> str:
    """Sahna sinflarisiz slayd (manbani solishtirish uchun)."""
    match = _SECTION.search(body or "")
    if not match or ART not in match.group(2).split():
        return body
    names = _own_classes(body)
    return body[:match.start()] + f'<section{match.group(1)}class="{" ".join(names)}"' + body[match.end():]


def carry(old: str, new: str) -> str:
    """Qayta yozilgan slaydga eski sahnasini qaytaradi (tuzatishda AI sinflarni tushirib qoldirishi mumkin)."""
    keep = [c for c in _classes(old) if c.startswith("art") or (c == "dark" and "art" in _classes(old))]
    if not keep or not _SECTION.search(new or ""):
        return new

    def put(match):
        names = [c for c in match.group(2).split() if not c.startswith("art")]
        names += [c for c in keep if c not in names]
        return f'<section{match.group(1)}class="{" ".join(names)}"'
    return _SECTION.sub(put, new, count=1)


# ─────────────────────────────────────────────── bezak elementlari

def _scene_of(body: str) -> Optional[Dict[str, str]]:
    classes = _classes(body)
    if ART not in classes:
        return None
    scene = {"kind": "", "variant": "", "canvas": "light", "head": "rule", "n": ""}
    for name in classes:
        if name.startswith("art-c-"):
            scene["canvas"] = name[6:]
        elif name.startswith("art-h-"):
            scene["head"] = name[6:]
        elif re.fullmatch(r"art-n\d+", name):
            scene["n"] = name[5:]
        elif name.startswith("art-") and name.count("-") >= 2:
            kind, _, variant = name[4:].partition("-")
            scene["kind"], scene["variant"] = kind, variant
    return scene


_OPEN_SECTION = re.compile(r'(<section\b[^>]*>)', re.IGNORECASE)
_HEAD_TITLE = re.compile(r'(<div\b[^>]*class\s*=\s*"head[^"]*"[^>]*>)', re.IGNORECASE)
_CARD = re.compile(r'(<div\b[^>]*class\s*=\s*"card(?:\s[^"]*)?"[^>]*>)', re.IGNORECASE)
_ITEM_MARK = re.compile(r'<span\b[^>]*class\s*=\s*"(?:item-dot|item-ikon)[^"]*"[^>]*>(?:.*?</span>)?', re.IGNORECASE | re.DOTALL)
_SOLID = re.compile(r'(<div\b[^>]*class\s*=\s*"card solid[^"]*"[^>]*>)', re.IGNORECASE)


def _number_cards(body: str, css: str, fmt: str) -> str:
    count = [0]

    def put(match):
        count[0] += 1
        return match.group(1) + f'<div class="{css}">{fmt.format(count[0])}</div>'
    return _CARD.sub(put, body)


def dress(body: str) -> str:
    """Sahna sinflariga ko'ra haqiqiy bezak elementlarini qo'yadi (takror chaqirilsa ham bir marta)."""
    scene = _scene_of(body)
    if scene is None or 'class="art-pg"' in body:
        return body
    kind, variant, canvas, head, n = (scene[k] for k in ("kind", "variant", "canvas", "head", "n"))
    decor = f'<div class="art-pg">{n}</div>' if n else ""
    if canvas == "light":
        decor += '<div class="art-orb"></div><div class="art-ring"></div>'
    elif canvas == "side":
        decor += '<div class="art-side"></div>'
    elif canvas == "tint":
        decor += '<div class="art-orb art-orb-b"></div>'
    if kind == "photo" and variant == "frame":
        decor += '<div class="art-back"></div>'
    body = _OPEN_SECTION.sub(lambda m: m.group(1) + decor, body, count=1)
    if head == "kicker" and n:
        body = _HEAD_TITLE.sub(lambda m: m.group(1) + f'<div class="art-kick">{n}</div>', body, count=1)
    if kind == "cards" and variant == "num":
        body = _number_cards(body, "art-cn", "{:02d}")
    elif kind == "steps" and variant in ("road", "stairs"):
        body = _number_cards(body, "art-sn", "{}")
    elif kind == "list" and variant == "grid":
        count = [0]

        def num(match):
            count[0] += 1
            return f'<span class="art-ln">{count[0]:02d}</span>'
        body = _ITEM_MARK.sub(num, body)
    elif kind == "compare" and variant == "versus":
        # Doira ikkinchi (to'q) kartaning ichida: PowerPointda u karta foni ustida chiziladi.
        body = _SOLID.sub(lambda m: m.group(1) + '<div class="art-vs">VS</div>', body, count=1)
    return body


# ─────────────────────────────────────────────── CSS
# Faqat tekis rang, chiziqli gradient, chegara va yumaloq burchak: PowerPointga shu narsalar o'tadi.
# Selektorlar `.slide.art-...` bilan boshlanadi — uslub (toza, blok ...) qoidalaridan ustun turadi.
CSS = """
/* ══ San'at rahbari: umumiy ══════════════════════════════════════ */
.slide.art{position:relative}
.slide.art>.head,.slide.art>.body{position:relative;z-index:1}
.art-pg{position:absolute;right:72px;bottom:44px;font-size:26px;font-weight:700;letter-spacing:3px;
color:#MUTED;z-index:2}
.slide.dark .art-pg{color:#SOFTINK}
.slide.art-photo-bleed:has(.rasm.photo-in:last-child) .art-pg{right:auto;left:96px}
/* Fon: oq varaqda burchakdan chiqib turgan katta yumshoq doira. */
.art-orb{position:absolute;width:620px;height:620px;border-radius:50%;right:-230px;bottom:-300px;
background:#SOFT;z-index:0}
.slide.art-c-light .art-orb{border:0}
.art-ring{position:absolute;width:300px;height:300px;border-radius:50%;right:150px;bottom:-170px;
border:4px solid #ACCENT;opacity:.35;z-index:0}
.art-orb.art-orb-b{width:520px;height:520px;right:-180px;top:-260px;bottom:auto;background:#BACKGROUND}
.slide.art-c-tint{background:linear-gradient(160deg,#SOFTER 0%,#BACKGROUND 100%)}
.slide.art-c-tint .cols>.card:not(.solid),.slide.art-c-tint .cols>.kpi,.slide.art-c-tint .steps>.card,
.slide.art-c-tint .timeline .what,.slide.art-c-tint .misol,.slide.art-c-tint .formula{background:#BACKGROUND}
.slide.art-photo-bleed.art-c-tint .art-orb-b{display:none}
/* Chap tasma: varaqning butun bo'yi bo'ylab rangli ustun. */
.art-side{position:absolute;left:0;top:0;bottom:0;width:30px;
background:linear-gradient(180deg,#ACCENT 0%,#BAND 100%);z-index:0}
.slide.art-c-side{padding-left:136px}
/* Rangli sarlavha tasmasi: sarlavha to'q tasma ustida oq yozuv. */
.slide.art-c-top>.head{margin:-96px -96px 0;padding:70px 96px 54px;
background:linear-gradient(120deg,#BAND 0%,#BANDDEEP 100%)}
.slide.art-c-top>.head .title{color:#INVERT}
.slide.art-c-top>.head .rule{background:#GLOWINK}
.slide.art-c-top .art-pg{top:58px;bottom:auto;color:#SOFTINK}

/* ── Sarlavha variantlari ─────────────────────────────────────── */
.art-kick{font-size:64px;font-weight:800;letter-spacing:-1px;color:#ACCENT;line-height:1;
border-bottom:6px solid #ACCENT;align-self:flex-start;padding-bottom:14px;margin-bottom:-6px}
.slide.art-h-kicker .art-pg{display:none}
.slide.dark .art-kick{color:#GLOWINK;border-bottom-color:#GLOWINK}
.slide.art-h-kicker>.head .rule{display:none}
.slide.art-h-bar>.head{border-left:12px solid #ACCENT;padding-left:36px}
.slide.art-h-bar>.head .rule{display:none}
.slide.dark.art-h-bar>.head{border-left-color:#GLOWINK}

/* ══ Kartochkalar ═══════════════════════════════════════════════ */
/* Raqamli: ikonka o'rnida katta tartib raqami, oq karta, chapda rangli chiziq. */
.slide.art-cards-num .cols>.card{background:#BACKGROUND;border:0;border-left:12px solid var(--tone);
border-radius:0 22px 22px 0;padding:44px 40px;justify-content:flex-start;margin-top:0}
.slide.art-cards-num:not(.art-c-tint) .cols>.card{background:var(--tint)}
.slide.art-cards-num .cols{padding-top:0}
.slide.art-cards-num .cols>.card>.ikon-dot{display:none}
.art-cn{font-size:92px;font-weight:800;line-height:1;color:var(--tone,#ACCENT);letter-spacing:-3px}
.slide.dark .art-cn{color:#GLOWINK}
.slide.dark.art-cards-num .cols>.card{background:#BANDCARD}
/* Gorizontal qatorlar: chapda ikonka doirasi, o'ngda sarlavha va izoh; ikki ustunli panjara. */
.slide.art-cards-rows .cols{grid-template-columns:repeat(2,1fr);padding-top:0;row-gap:36px}
.slide.art-cards-rows .cols>.card{display:grid;grid-template-columns:120px 1fr;column-gap:34px;
row-gap:10px;align-items:center;align-content:center;border:0;border-radius:24px;padding:36px 40px;
min-height:0;background:var(--tint)}
.slide.art-cards-rows .cols>.card>.ikon-dot{grid-row:1 / span 3;grid-column:1;margin:0;width:120px;height:120px}
.slide.art-cards-rows .cols>.card>:not(.ikon-dot){grid-column:2}
.slide.dark.art-cards-rows .cols>.card{background:#BANDCARD}
/* To'la rangli: karta o'z rangida, oq yozuv. */
.slide.art-cards-solid .cols>.card{background:linear-gradient(160deg,var(--tone) 0%,var(--ink,#BAND) 100%);
border:0;border-radius:26px}
.slide.art-cards-solid .cols>.card .card-title{color:#FFFFFF}
.slide.art-cards-solid .cols>.card .card-note{color:#FFFFFF;opacity:.92}
.slide.art-cards-solid .cols>.card>.ikon-dot{background:rgba(255,255,255,.22);margin-top:0;align-self:flex-start;
width:96px;height:96px}
.slide.art-cards-solid .cols{padding-top:0}

/* ══ Ro'yxat ════════════════════════════════════════════════════ */
/* Panjara: ikki ustun, har band ustida katta raqam va chiziq. */
.slide.art-list-grid .list{display:grid;grid-template-columns:repeat(2,1fr);column-gap:72px;row-gap:44px;
align-content:center}
.slide.art-list-grid .list>.item{flex-direction:column;gap:14px;border-top:5px solid var(--tone,#ACCENT);
padding-top:22px}
.art-ln{font-size:54px;font-weight:800;line-height:1;color:var(--tone,#ACCENT);letter-spacing:-1px}
.slide.dark .art-ln{color:#GLOWINK}
/* Panel: bosh gap chapda to'q panelda yirik yozuv, ro'yxat o'ngda. */
.slide.art-list-panel>.body{display:grid;grid-template-columns:40% 1fr;column-gap:72px;align-items:stretch}
.slide.art-list-panel>.body>.lead{background:linear-gradient(150deg,#BAND 0%,#BANDDEEP 100%);color:#INVERT;
font-size:46px;line-height:1.35;font-weight:700;padding:64px 56px;border-radius:28px;display:flex;
align-items:center;max-width:none;align-self:stretch}
.slide.art-list-panel>.body>.list{align-self:center}
/* Tasma: har band o'z rangidagi och qatorda, chapda rangli chiziq. */
.slide.art-list-strip .list{gap:22px}
.slide.art-list-strip .list>.item{background:var(--tint,#SOFT);border-left:10px solid var(--tone,#ACCENT);
border-radius:0 20px 20px 0;padding:24px 34px;align-items:center}
.slide.art-list-strip .list>.item:nth-child(5n+1){--tint:#TINT1}
.slide.art-list-strip .list>.item:nth-child(5n+2){--tint:#TINT2}
.slide.art-list-strip .list>.item:nth-child(5n+3){--tint:#TINT3}
.slide.art-list-strip .list>.item:nth-child(5n+4){--tint:#TINT4}
.slide.art-list-strip .list>.item:nth-child(5n+5){--tint:#TINT5}
.slide.art-list-strip .item-dot{margin-top:0}
.slide.dark.art-list-strip .list>.item{background:#BANDCARD}

/* ══ Ko'rsatkichlar ═════════════════════════════════════════════ */
/* Ulkan raqamlar: qutisiz, oralarida tik chiziq. */
.slide.art-kpi-giant .cols>.kpi{background:none;border:0;border-left:4px solid #EDGE;border-radius:0;
padding:20px 0 20px 52px;min-height:0;justify-content:center}
.slide.art-kpi-giant .cols>.kpi:first-child{border-left:0;padding-left:0}
.slide.art-kpi-giant .cols>.kpi>.kpi-value{font-size:136px;color:var(--tone,#ACCENT);letter-spacing:-4px}
.slide.art-kpi-giant .cols>.kpi>.kpi-value.kpi-long{font-size:84px}
.slide.dark.art-kpi-giant .cols>.kpi{border-left-color:#BANDGRID}
.slide.dark.art-kpi-giant .cols>.kpi>.kpi-value{color:#GLOWINK}
/* Halqa: raqam katta rangli doira ichida. */
.slide.art-kpi-ring .cols>.kpi{background:none;border:0;border-radius:0;padding:0;min-height:0;
align-items:center;text-align:center;justify-content:flex-start}
.slide.art-kpi-ring .cols>.kpi>.kpi-value{width:270px;height:270px;border-radius:50%;
border:14px solid var(--tone,#ACCENT);display:flex;align-items:center;justify-content:center;
font-size:84px;color:var(--ink,#HEADING);background:var(--tint,#SOFT);letter-spacing:-2px;flex:none}
.slide.dark.art-kpi-ring .cols>.kpi>.kpi-value{background:#BANDCARD;color:#INVERT}

/* ══ Qadamlar ═══════════════════════════════════════════════════ */
/* Yo'l: kartasiz, tepada raqamli doira, ostida rangli yo'l bo'lagi. */
.slide.art-steps-road .steps{padding-top:0;gap:28px}
.slide.art-steps-road .steps>.arrow{display:none}
.slide.art-steps-road .steps>.card{background:none;border:0;border-top:10px solid var(--tone,#ACCENT);
border-radius:0;padding:0 8px;margin-top:62px;min-height:0;justify-content:flex-start;gap:16px}
.slide.art-steps-road .steps>.card>.ikon-dot{display:none}
.slide.art-steps-road .art-sn{width:112px;height:112px;border-radius:50%;background:var(--tone,#ACCENT);
color:#FFFFFF;font-size:52px;font-weight:800;display:flex;align-items:center;justify-content:center;
margin-top:-62px;border:10px solid #BACKGROUND;flex:none}
.slide.dark.art-steps-road .art-sn{border-color:#BAND}
/* Zinapoya: har qadam oldingisidan balandroq, to'la rangli. */
.slide.art-steps-stairs .steps{align-items:flex-end;gap:22px;padding-top:0}
.slide.art-steps-stairs .steps>.arrow{display:none}
.slide.art-steps-stairs .steps>.card{background:linear-gradient(170deg,var(--tone,#ACCENT) 0%,var(--ink,#BAND) 100%);
border:0;border-radius:24px 24px 0 0;justify-content:flex-start;padding:36px 34px;min-height:0}
.slide.art-steps-stairs .steps>.card:nth-child(1){min-height:300px}
.slide.art-steps-stairs .steps>.card:nth-child(3){min-height:370px}
.slide.art-steps-stairs .steps>.card:nth-child(5){min-height:440px}
.slide.art-steps-stairs .steps>.card:nth-child(7){min-height:510px}
.slide.art-steps-stairs .steps>.card:nth-child(9){min-height:580px}
.slide.art-steps-stairs .steps>.card .card-title{color:#FFFFFF}
.slide.art-steps-stairs .steps>.card .card-note{color:#FFFFFF;opacity:.92}
.slide.art-steps-stairs .steps>.card>.ikon-dot{display:none}
.slide.art-steps-stairs .art-sn{font-size:64px;font-weight:800;line-height:1;color:#FFFFFF;opacity:.9}
.steps>.card:nth-child(4n+1){--ink:#DEEP1}
.steps>.card:nth-child(4n+3){--ink:#DEEP2}
.steps>.card:nth-child(4n+5){--ink:#DEEP3}
.steps>.card:nth-child(4n+7){--ink:#DEEP4}

/* ══ Vaqt o'qi ══════════════════════════════════════════════════ */
/* Tabletkalar: yil rangli tabletka ichida, voqea ostida och kartada. */
.slide.art-timeline-pills .timeline .when{background:var(--tone,#ACCENT);color:#FFFFFF;border-radius:40px;
padding:10px 30px;font-size:44px}
.slide.art-timeline-pills .timeline .bead{width:28px;height:28px;margin-top:-17px;border-width:6px}
.slide.art-timeline-pills .timeline .what{border-top:6px solid var(--tone,#ACCENT);border-radius:0 0 18px 18px}
.slide.dark .timeline .what{background:#BANDCARD;color:#INVERT}
.slide.dark .timeline .bead{border-color:#BAND}
.slide.dark .timeline .when{color:#GLOWINK}
.slide.dark.art-timeline-pills .timeline .when{color:#FFFFFF}

/* ══ Qiyos ══════════════════════════════════════════════════════ */
/* VS: ikki yarim bir-biriga tegib turadi, o'rtada doira. */
.slide.art-compare-versus .cols-2{position:relative;column-gap:0;padding-top:0}
.slide.art-compare-versus .cols-2>.card{border-radius:28px 0 0 28px;padding:56px 110px 56px 56px;border:0}
.slide.art-compare-versus .cols-2>.card:last-child{border-radius:0 28px 28px 0;padding:56px 56px 56px 110px}
.slide.art-compare-versus .cols-2>.card>.ikon-dot{display:none}
.slide.art-compare-versus .cols-2>.card.solid{position:relative}
.art-vs{position:absolute;left:-75px;top:50%;width:150px;height:150px;margin-top:-75px;border-radius:50%;
background:#ACCENT;color:#FFFFFF;font-size:50px;font-weight:800;display:flex;align-items:center;
justify-content:center;border:12px solid #BACKGROUND;z-index:3}

/* ══ Rasm ═══════════════════════════════════════════════════════ */
/* Ramka: rasm chetdan chetga emas, yumaloq ramkada; orqasida siljigan rangli blok. */
.slide.art-photo-frame:has(.rasm.photo-in:last-child){padding-right:calc(42% + 150px)}
.slide.art-photo-frame:has(.rasm.photo-in:first-child){padding-left:calc(42% + 150px)}
.slide.art-photo-frame>.body>.split>.rasm.photo-in{top:130px;bottom:150px;width:42%;border-radius:30px;z-index:2}
.slide.art-photo-frame>.body>.split>.rasm.photo-in:last-child{right:110px}
.slide.art-photo-frame>.body>.split>.rasm.photo-in:first-child{left:110px}
.slide.art-photo-frame>.body>.split>.rasm.photo-in>.photo{border-radius:30px}
.art-back{position:absolute;top:80px;bottom:200px;width:42%;right:60px;border-radius:30px;
background:linear-gradient(150deg,#ACCENT 0%,#BAND 100%);z-index:1}
.slide.art-photo-frame:has(.rasm.photo-in:first-child) .art-back{right:auto;left:60px}
.slide.art-photo-frame:has(.rasm.photo-in:last-child) .art-pg{right:auto;left:96px}

/* ══ Iqtibos ════════════════════════════════════════════════════ */
/* Sahna: to'q varaq markazida yirik iqtibos. */
.slide.art-quote-stage>.body{align-items:center;text-align:center}
.slide.art-quote-stage>.body>div:has(>.quote){background:none;border:0;padding:0 120px;align-items:center}
.slide.art-quote-stage>.body>div:has(>.quote)>.quote{font-size:64px;line-height:1.3;color:#INVERT}
.slide.art-quote-stage>.body>div:has(>.quote)>.quote-mark{font-size:220px;color:#GLOWINK;margin-bottom:-90px}
.slide.art-quote-stage>.body>div:has(>.quote)>.quote-by{color:#GLOWINK}
/* ══ Ikki ustun: panel ══════════════════════════════════════════ */
/* Ikkinchi ustun (kartochka yoki jadval) och rangli katta panel ichida. */
.slide.art-mixed-panel .split{align-items:stretch}
.slide.art-mixed-panel .split>:last-child{background:#SOFT;border-radius:32px;padding:56px 48px;align-self:stretch;
align-content:center}
.slide.art-mixed-panel .split>.cols:last-child{padding-top:84px}
.slide.art-mixed-panel .split>:last-child .card{background:#BACKGROUND}
.slide.dark.art-mixed-panel .split>:last-child{background:#BANDCARD}

/* ══ Reja ═══════════════════════════════════════════════════════ */
/* Mundarija: kartochkasiz, chapda katta raqam, ostida ingichka chiziq; ikki ustun. */
section.slide.art-plan-index .cols{grid-template-columns:repeat(2,1fr);column-gap:80px;row-gap:8px;padding-top:0}
section.slide.art-plan-index .cols>.card{background:none;border:0;border-bottom:3px solid #EDGE;border-radius:0;
display:grid;grid-template-columns:120px 1fr;column-gap:28px;align-items:center;padding:22px 0;min-height:0}
section.slide.art-plan-index .cols>.card>.ikon-dot{display:none}
section.slide.art-plan-index .cols>.card .card-num{grid-row:1 / span 2;font-size:64px;font-weight:800;
color:var(--tone,#ACCENT);letter-spacing:-2px}
section.slide.art-plan-index .cols>.card>:not(.card-num):not(.ikon-dot){grid-column:2}
section.slide.art-plan-index .cols>.card .card-title{font-size:38px}
"""

# Kartochka varianti foni och bo'lsa, yozuv rangi aniq beriladi: ba'zi uslublarda (blok) karta yozuvi oq.
_TEXT_FIX = """
.slide.art-cards-rows .cols>.card .card-title,.slide.art-cards-num .cols>.card .card-title,
section.slide.art-plan-index .cols>.card .card-title,
.slide.art-compare-versus .cols-2>.card:not(.solid) .card-title{color:#HEADING}
.slide.art-cards-rows .cols>.card .card-note,.slide.art-cards-num .cols>.card .card-note,
section.slide.art-plan-index .cols>.card .card-note,
.slide.art-compare-versus .cols-2>.card:not(.solid) .item-text,
.slide.art-compare-versus .cols-2>.card:not(.solid) .item-text b{color:#BODY}
.slide.art-compare-versus .cols-2>.card:not(.solid){background:#SOFT}
.slide.art-mixed-panel .split>:last-child .card .card-title{color:#HEADING}
.slide.art-mixed-panel .split>:last-child .card .ikon-dot{background:var(--tone,#ACCENT)}
.slide.art-mixed-panel .split>:last-child .card .card-note{color:#BODY}
.slide.dark.art-cards-rows .cols>.card .card-title,.slide.dark.art-cards-num .cols>.card .card-title{color:#INVERT}
.slide.dark.art-cards-rows .cols>.card .card-note,.slide.dark.art-cards-num .cols>.card .card-note{color:#SOFTINK}
"""

# Uslubga xos tuzatishlar.
_STYLE_FIX = {
    # To'q fonda och tuslar (tint) va to'q rangli raqamlar ko'rinmaydi.
    "qorongu": """
.slide.art .cols>*,.slide.art .list>*,.slide.art .steps>*,.slide.art .timeline>*{--tint:#SOFT !important}
.slide.art-c-tint .cols>.card:not(.solid),.slide.art-c-tint .cols>.kpi,.slide.art-c-tint .steps>.card{background:#SOFT}
.art-cn,.art-ln,section.slide.art-plan-index .cols>.card .card-num,
.slide.art-kpi-giant .cols>.kpi>.kpi-value{color:#ACCENT !important}
.slide.art-cards-rows .cols>.card .card-title,.slide.art-cards-num .cols>.card .card-title,
section.slide.art-plan-index .cols>.card .card-title,
.slide.art-compare-versus .cols-2>.card:not(.solid) .card-title{color:#HEADING}
.slide.art-cards-rows .cols>.card .card-note,.slide.art-cards-num .cols>.card .card-note{color:#BODY}
""",
    # Konturda ro'yxat bandi oq qutida turadi: to'q varaqda quti ham to'q bo'lsin.
    "kontur": """
.slide.dark .list>.item,.card.solid .list>.item{background:#BANDCARD !important;border-color:#BANDGRID}
.slide.dark .list>.item .item-text,.slide.dark .list>.item .item-text b,
.card.solid .list>.item .item-text,.card.solid .list>.item .item-text b{color:#INVERT}
""",
}


def css(style: str = "") -> str:
    """Zamonaviy taqdimot uchun san'at rahbari CSS i (uslubga moslangan)."""
    return CSS + _TEXT_FIX + _STYLE_FIX.get(style, "")
