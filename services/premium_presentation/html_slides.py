"""Slaydlarni HTML qilib yozdiradi — qat'iy shablonsiz.

Eski ikki tizimda joylashuv koddan kelardi: avval AI koordinata aytar,
keyin biz uni tuzatardik; so'ngra 24 ta qat'iy qolip qildik va AI faqat
o'rinlarni to'ldirardi. Ikkalasida ham slaydning ko'rinishi kodda
qamalib qolgan — dizayn boyimaydi.

Bu yerda boshqacha: AI butun slaydni HTML/CSS/SVG qilib chizadi, biz
uni brauzerda 1920×1080 da suratga olamiz va PowerPointga qo'yamiz.
Kod slaydning ichki ko'rinishiga aralashmaydi — u faqat QOBIQ qoidalarini
(o'lcham, shrift, rang, tashqi fayl yo'qligi) va joylashuv
KATEGORIYALARINI aytadi. Qolganini AI har safar yangidan chizadi.

Slaydlar bo'laklab so'raladi: bitta so'rovda o'nta to'liq HTML hujjat
so'ralsa, javob token chegarasiga urilib oxirgisi chala keladi.
"""

import logging
import os
import re
from typing import Callable, Dict, List, Optional

from . import (chart_data, deck_calc, deck_charts, deck_compose, deck_logic, deck_math, deck_shape, deck_style,
               deck_styles, llm_client, prompts)
from services import uz_script

log = logging.getLogger("html_slides")

SLIDE_W_PX = 1920
SLIDE_H_PX = 1080

# AI slaydlarni shu qator bilan ajratadi.
MARKER = "===SLIDE_BREAK==="

# Bitta so'rovda shuncha slayd. To'liq HTML hujjat uzun bo'ladi, shuning
# uchun bo'lak kichik.
CHUNK = 3

# Shrift ikki tomonga mos kelishi kerak: brauzer slaydni shu shrift
# bilan joylashtiradi, PowerPoint esa uni Arial (yoki Times New Roman)
# bilan chizadi. Liberation Sans/Serif aynan o'sha ikkisi bilan
# o'lchovdosh — harflar kengligi bir xil, shuning uchun matn
# PowerPointda ham o'sha joyni egallaydi va qutisidan toshmaydi.
FONT_STACK = "Arial, 'Liberation Sans', 'DejaVu Sans', sans-serif"
SERIF_STACK = "'Times New Roman', 'Liberation Serif', 'DejaVu Serif', serif"

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"```(?:html)?", re.IGNORECASE)

# Soya PowerPointga umuman o'tmaydi: shakl soyasini biz o'chiramiz,
# matn soyasi esa model uni matnning ikkinchi nusxasi bilan chizishga
# urinishiga olib keladi. Shuning uchun soya HTML dan butunlay
# kesib tashlanadi — model qoidani unutsa ham slaydda soya qolmaydi.
_SHADOW_DECL = re.compile(
    r"(?:-webkit-|-moz-|-ms-)?(?:box|text)-shadow\s*:[^;}\"']*;?",
    re.IGNORECASE)
# `drop-shadow(...)` `filter` qiymatining ichida turadi; ichida
# `rgba(...)` bo'lishi mumkin, shuning uchun bir qavat qavs hisobga
# olinadi.
_DROP_SHADOW = re.compile(
    r"drop-shadow\s*\([^()]*(?:\([^()]*\)[^()]*)*\)", re.IGNORECASE)
# Ichidagi yagona qiymat olib tashlangach bo'sh qolgan `filter:`.
_EMPTY_FILTER = re.compile(
    r"(?:-webkit-)?filter\s*:\s*([;}\"'])", re.IGNORECASE)


def strip_shadows(html: str) -> str:
    """Slayddan har qanday soyani olib tashlaydi."""
    text = _SHADOW_DECL.sub("", html)
    text = _DROP_SHADOW.sub("", text)
    text = _EMPTY_FILTER.sub(r"\1", text)
    text = re.sub(r";\s*;+", "; ", text)
    # Qoida olib tashlangach qolgan bo'sh nuqtali vergul.
    return re.sub(r"([{\"'])\s*;\s*", r"\1", text)


# "Matnni ... yozasan" — har til o'z promptida (prompts/*.py). Eski nom moslik uchun qoldi.
_LANGUAGE = {code: prompts.target(code) for code in ("uz", "uz-cyrl", "ru", "en", "kk")}

# Joylashuv kategoriyalari — qat'iy shablon emas, lug'at. AI ulardan tanlaydi va o'zicha aralashtiradi.
# Kalitlar (lotin) hamma tilda bir xil, izohi — taqdimot tilida (prompts/*.py).
_CATEGORIES = prompts.get("uz").CATEGORY_LIST

CATEGORY_KEYS = tuple(key for key, _ in _CATEGORIES)


def catalogue_text(language: str = "uz") -> str:
    notes = prompts.get(language).CATEGORIES
    return "\n".join(f"  {key} — {notes.get(key, note)}" for key, note in _CATEGORIES)


# ────────────────────────────────────────────────────────── qobiq qoidalari

def icon_list() -> str:
    """Mavjud ikonkalar nomi — promptga qo'yiladi."""
    try:
        from . import icon_render

        names = icon_render.icon_names()
    except Exception:
        names = ()
    if not names:
        return "  (ikonka yo'q)"
    # Uzun bitta qator o'rniga o'nta ustunli ro'yxat: model uni
    # oson o'qiydi.
    rows = []
    for start in range(0, len(names), 10):
        rows.append("  " + ", ".join(names[start:start + 10]))
    return "\n".join(rows)


def shell_rules(theme, language: str) -> str:
    """Modelga beriladigan qoidalar — dizayn emas, MAZMUN uchun.

    Ilgari bu yerda "shriftni shunday ber, rangni bunday qil" degan
    o'nlab qoida turardi va model ularning yarmini unutardi. Endi
    dizayn CSS da qat'iy turibdi (`deck_style`), shuning uchun model
    bilan faqat mazmun haqida gaplashamiz: qaysi blok va ichida
    qanday matn.
    """
    P = prompts.get(language)
    return prompts.fill(P.SHELL, target=prompts.target(language), blocks=P.BLOCKS, icons=icon_list(),
                        marker=MARKER)


def _shapes_note(shapes: Optional[List[tuple]], start: int, count: int, language: str = "uz") -> str:
    """Oldingi slaydlarda ISHLATILGAN blok kombinatsiyalari — modelga ko'rsatiladi.

    Slaydlar bo'laklab yoziladi va har bo'lak oldingilarning HTML'ini
    ko'rmaydi: "takrorlama" degan qoida modelga nimani takrorlamaslikni
    bilmasdan beriladi. Til sabab emas — ko'rinmaslik sabab. Shuning uchun
    aynan nima ishlatilgani (haqiqiy sinf nomlari bilan) aytiladi.
    """
    if not shapes:
        return ""
    T = prompts.get(language).SHAPES
    names = lambda sig: "+".join(sig) if sig else T["plain"]
    lines = [prompts.fill(T["line"], n=i, shape=names(sig)) for i, sig in enumerate(shapes, 1)]
    counts: Dict[tuple, int] = {}
    for sig in shapes[1:]:           # muqova hisobga olinmaydi
        if sig:
            counts[sig] = counts.get(sig, 0) + 1
    banned = [names(sig) for sig, n in counts.items() if n >= MAX_SAME_SHAPE]
    last = names(shapes[-1]) if shapes[-1] else ""
    rules = [prompts.fill(T["hard"], start=start, end=start + count - 1)]
    if last:
        rules.append(prompts.fill(T["previous"], shape=last))
    if banned:
        rules.append(prompts.fill(T["banned"], n=MAX_SAME_SHAPE, list="; ".join(f"[{b}]" for b in banned)))
    rules.append(T["advice"])
    return T["header"] + "\n" + "\n".join(lines) + "\n" + " ".join(rules)


def _user_prompt(topic: str, start: int, count: int, total: int,
                 outline: List[Dict], used: List[str], level: int,
                 source: str, preferences: str, author: str,
                 family: str = "umumiy",
                 shapes: Optional[List[tuple]] = None,
                 written: Optional[List[str]] = None,
                 language: str = "uz", volume: str = "kop") -> str:
    P = prompts.get(language)
    U = P.USER
    kam = volume == "kam"
    parts = [
        prompts.fill(U["topic"], topic=topic),
        prompts.fill(U["total"], total=total),
        prompts.fill(U["chunk"], start=start, count=count),
        P.DEPTH.get(level, P.DEPTH[2]),
        deck_shape.guidance(family, language),
        # Kam matnlida shaklni kompozitsiya (kod) belgilaydi — blok tanlash haqidagi yo'riqnoma kerak emas.
        P.KAM["user"] if kam else U["blocks"],
    ]

    if outline:
        lines = []
        for index, item in enumerate(outline, 1):
            if start <= index < start + count:
                mark = "  →"
            else:
                mark = "   "
            title = item.get("title") or ""
            shape = item.get("layout") if kam and item.get("layout") else item["category"]
            lines.append(f"{mark} {index}. [{shape}] "
                         + (f"«{title}» — " if title else "") + item["brief"]
                         + (" " + item["chart_note"]
                            if mark.strip() and item.get("chart_note") else ""))
        parts.append(prompts.fill(U["outline"], lines="\n".join(lines)))
    if written:
        parts.append(prompts.fill(U["written"], titles="; ".join(f"{i}. {t}" for i, t in enumerate(written, 1) if t)))
    if used:
        parts.append(prompts.fill(U["used"], ideas="; ".join(used[-5:])))
    if start <= 2 < start + count:
        parts.append(prompts.fill(U["plan_slide"], label=deck_logic.PLAN_LABEL.get(language, deck_logic.PLAN_LABEL["uz"])))
    if start + count - 1 >= total:
        parts.append(U["last"])
    note = "" if kam else _shapes_note(shapes, start, count, language)
    if note:
        parts.append(note)
    if preferences:
        parts.append(prompts.fill(U["prefs"], text=preferences))
    if source:
        parts.append(prompts.fill(U["source"], text=source[:4000]))

    return "\n\n".join(parts)


# ────────────────────────────────────────────────────────────── reja

_CONCLUSION_WORDS = re.compile(
    r"xulosa|yakun|natija|conclusion|summary|takeaway|заключен|вывод|итог", re.IGNORECASE)
def _conclusion_brief(language: str) -> str:
    value = prompts.get(language).CONCLUSION_BRIEF
    return value.get(language, value.get("uz", "")) if isinstance(value, dict) else value


# Eski nom (testlar va boshqa modullar uchun).
_CONCLUSION_BRIEF = {code: _conclusion_brief(code) for code in ("uz", "uz-cyrl", "ru", "en", "kk")}


def plan_outline(topic: str, count: int, language: str,
                 level: int = 2, volume: str = "kop") -> Dict:
    """Har slayd uchun sarlavha, bir qatorli mazmun va joylashuv kategoriyasi.

    Slaydlar bo'laklab yoziladi va har bo'lak avvalgisining HTML'ini
    ko'rmaydi. Reja oldindan tuzilsa, har bo'lak o'z o'rnini biladi va
    bir mavzu ikki slaydda takrorlanmaydi. Sarlavhalar shu yerda
    belgilanadi: slaydlar ularni aynan ishlatadi, reja slaydi esa
    yozilgan slaydlarning sarlavhalaridan yig'iladi — shunda reja bilan
    taqdimot bir-biriga zid kelmaydi.
    """
    P = prompts.get(language)
    T = P.PLAN
    quota = deck_logic.chart_quota(count)
    chart_rule = prompts.fill(T["chart"], quota=quota, donut=T["donut"] if quota >= 2 else "") if quota else ""
    prompt = (
        prompts.fill(T["main"], topic=topic, count=count, categories=catalogue_text(language),
                     photos=deck_logic.PHOTOS_PER_10.get(volume, deck_logic.PHOTOS_PER_10["kop"]))
        + (P.KAM["plan"] if volume == "kam" else "")
        + chart_rule
        + (T["calc"] if deck_shape.is_calculation(topic) else "")
        + prompts.fill(T["family"], names=deck_shape.names())
        + prompts.fill(T["language"], target=prompts.target(language))
        + T["json"]
    )
    raw, hint = [], ""
    for attempt in range(2):
        try:
            data = llm_client._call_openrouter(
                T["system"], prompt, temperature=0.6, max_tokens=900 + 200 * count)
            raw = data.get("slides") or []
            hint = data.get("fan") or ""
        except llm_client.NoCredits:
            raise
        except Exception as exc:
            log.warning("Reja olinmadi, kategoriyalar o'zimiz tanlaymiz: %s", exc)
            raw, hint = [], ""
        # Chala reja (kam slayd) bir marta qayta so'raladi: yetmagan o'rinlar
        # mavzu nomi bilan to'ldirilsa, model o'sha slaydlarda mavzuning
        # ta'rifini qayta yozib yuboradi.
        if len(raw) >= count:
            break
        log.warning("Reja %d ta slayd uchun keldi, %d kerak", len(raw), count)

    family = deck_shape.of(topic, hint)
    log.info("Mavzu oilasi: %s", family)

    outline: List[Dict] = []
    for index in range(count):
        item = raw[index] if index < len(raw) and isinstance(raw[index], dict) else {}
        brief = str(item.get("brief") or "").strip()
        title = deck_logic.short_title(str(item.get("title") or ""))
        category = str(item.get("category") or "").strip().lower()
        if category not in CATEGORY_KEYS:
            category = _fallback_category(index, count)
        if index == 0:
            category = "muqova"
        elif index == 1:
            category = "reja"
            title = deck_logic.PLAN_LABEL.get(language, deck_logic.PLAN_LABEL["uz"])
        elif index == count - 1:
            category = "yakun"
            # Oxirgi slayd — XULOSA. Reja boshqa narsa yozgan bo'lsa (masalan
            # mavzu nomi), model uni shunday yozib yuboradi: ta'rif qayta chiqadi.
            if not _CONCLUSION_WORDS.search(brief):
                brief = _conclusion_brief(language)
        elif category in ("muqova", "yakun"):
            category = _fallback_category(index, count)
        elif category == "reja":
            # "Taqdimot rejasi" faqat 2-slayd; boshqa joyda u xulosa oldidan
            # yoki oxirida reja slaydini takrorlab yuborardi.
            category = _fallback_category(index, count)
        if not brief:
            brief = prompts.fill(P.BRIEF_FALLBACK, topic=topic, n=index + 1)
        if not title:
            title = deck_logic.short_title(deck_logic.short_note(brief, 60))
        outline.append({"title": title, "brief": brief, "category": category})

    outline = ensure_charts(outline, language)
    outline = ensure_photos(outline, volume, language)
    # Kod darajasida kategoriya almashtirilmaydi (ilgari shunday edi va
    # mantiqan ketma-ket kelishi kerak bo'lgan ikki ro'yxatni ajratib,
    # fikrni uzardi). Bir xillikdan qochishni model promptdagi yo'riqnoma
    # bo'yicha o'zi qiladi. Faqat diagramma soni kafolatlanadi.
    return {"family": family, "slides": outline}


# Diagramma soni promptdagi iltimosga qoldirilmaydi: ilgari "raqam
# bo'lmasa diagramma yozmang" qoidasi modelni diagrammani butunlay
# chetlab o'tishga olib kelgan edi. Reja yetarli diagramma bermasa, mos
# slaydlar shu yerda diagrammali qilib belgilanadi.
_CHART_CANDIDATES = ("korsatkichlar", "kartalar", "ikki_ustun", "qiyoslash",
                     "jadval", "tuzilma")


def ensure_charts(outline: List[Dict], language: str = "uz") -> List[Dict]:
    count = len(outline)
    want = deck_logic.chart_quota(count)
    have = [i for i, item in enumerate(outline) if item["category"] == "diagramma"]
    need = want - len(have)
    if need <= 0:
        return outline
    candidates = [i for i in range(2, count - 1)
                  if outline[i]["category"] in _CHART_CANDIDATES]
    if len(candidates) < need:       # mos kategoriya yetmasa boshqa oddiy slaydlardan
        extra = [i for i in range(2, count - 1)
                 if outline[i]["category"] not in ("diagramma", "formula", "misol", "iqtibos", "matn_rasm")
                 and i not in candidates]
        candidates += extra
    candidates = [i for i in candidates if i not in have]
    if not candidates:
        return outline
    chosen = deck_logic.pick_even(candidates, min(need, len(candidates)))
    for order, index in enumerate(chosen):
        item = outline[index]
        kind = deck_logic.chart_kind_for(f"{item['title']} {item['brief']}",
                                         order + len(have))
        if want >= 2 and order == 0 and not any(i.get("chart_kind") == "halqa" for i in outline):
            kind = "halqa"            # bir nechta diagrammadan biri halqa bo'lsin
        item["was"] = item["category"]      # haqiqiy ma'lumot topilmasa shu kategoriyaga qaytadi
        item["category"] = "diagramma"
        item["chart_kind"] = kind
        log.info("%d-slayd diagrammali qilib belgilandi (%s)", index + 1, kind)
    return outline


# Rasmli slaydlar soni ham promptga qoldirilmaydi: har 10 ta asosiy slaydning
# 4 tasida (kam matnlida 6 tasida) rasm bo'lsin (deck_logic.photo_quota). Reja kam
# rasmli slayd bersa, mos slaydlar shu yerda "matn_rasm" qilib belgilanadi.
_PHOTO_CANDIDATES = ("kartalar", "ikki_ustun", "qiyoslash", "tuzilma", "jarayon")


def ensure_photos(outline: List[Dict], volume: str = "kop", language: str = "uz") -> List[Dict]:
    count = len(outline)
    want = deck_logic.photo_quota(count, volume)
    # Kam matnlida iqtibos kompozitsiyasi ham rasmli.
    photo_categories = ("matn_rasm", "iqtibos") if volume == "kam" else ("matn_rasm",)
    have = [i for i, item in enumerate(outline) if item["category"] in photo_categories]
    need = want - len(have)
    if need <= 0:
        return outline
    candidates = [i for i in range(2, count - 1)
                  if outline[i]["category"] in _PHOTO_CANDIDATES and i not in have]
    if len(candidates) < need:
        extra = [i for i in range(2, count - 1)
                 if outline[i]["category"] not in ("diagramma", "formula", "misol", "iqtibos",
                                                   "korsatkichlar", "jadval", "vaqt_oqi", "matn_rasm")
                 and i not in candidates]
        candidates += extra
    if not candidates:
        return outline
    # Rasmli slaydlar bir-biriga tegib turmasin: mavjudlardan uzoqroqlar afzal.
    chosen = []
    pool = list(candidates)
    while pool and len(chosen) < need:
        taken = have + chosen
        best = max(pool, key=lambda i: min([abs(i - t) for t in taken] or [99]))
        chosen.append(best)
        pool.remove(best)
    P = prompts.get(language)
    for index in sorted(chosen):
        item = outline[index]
        item["category"] = "matn_rasm"
        item["brief"] = item["brief"] + (P.KAM["photo_brief"] if volume == "kam" else P.PHOTO_BRIEF)
        log.info("%d-slayd rasmli qilib belgilandi", index + 1)
    return outline


# Reja kelmaganda ishlatiladigan zaxira. Unda raqamga tayanadigan
# kategoriyalar YO'Q: mavzu qanday ekanini bilmay turib diagramma yoki
# ko'rsatkich so'rash — modelni statistika o'ylab topishga majburlash
# demakdir. Zaxira har doim mazmunga neytral bloklardan boshlanadi.
_SAFE_CATEGORIES = ("kartalar", "matn_rasm", "ikki_ustun", "reja",
                    "jarayon", "tuzilma", "qiyoslash", "iqtibos")


def _fallback_category(index: int, count: int) -> str:
    """Reja kelmaganda tanlanadigan neytral kategoriya."""
    return _SAFE_CATEGORIES[index % len(_SAFE_CATEGORIES)]


# ───────────────────────────────────────────────────────── slayd yozish

_SECTION = re.compile(r"<section\b[^>]*\bclass\s*=\s*[\"'][^\"']*\bslide\b"
                      r"[^\"']*[\"'][^>]*>.*?</section>",
                      re.IGNORECASE | re.DOTALL)
# Model ba'zan sinf nomiga qo'shimcha yozadi yoki `style=` tiqadi —
# ikkalasi ham dizayn tizimini buzadi.
_STYLE_ATTR = re.compile(r"\sstyle\s*=\s*([\"'])(.*?)\1",
                         re.IGNORECASE | re.DOTALL)
_STYLE_TAG = re.compile(r"<style\b.*?</style>|<script\b.*?</script>",
                        re.IGNORECASE | re.DOTALL)


def split_slides(raw: str) -> List[str]:
    """Javobni slayd mazmunlariga ajratadi.

    Model endi to'liq HTML hujjat emas, `<section class="slide">`
    bloklarini yozadi. Chala kelgani (yopilmagani) tashlab
    yuboriladi: uni chizsak yarim slayd chiqadi.
    """
    text = _FENCE.sub("", _THINK.sub("", str(raw or "")))
    text = _STYLE_TAG.sub("", text)
    bodies = []
    for part in text.split(MARKER):
        for match in _SECTION.finditer(part):
            body = _STYLE_ATTR.sub("", match.group(0))
            bodies.append(strip_shadows(body).strip())
    if not bodies:
        log.warning("Javobda slayd topilmadi (%d belgi)", len(text))
    return bodies


_DARK_SLIDE = re.compile(
    r'(<section\b[^>]*\bclass\s*=\s*(["\'])[^"\']*\bdark\b[^"\']*\2'
    r'[^>]*>)', re.IGNORECASE)


_ROW_OPEN = re.compile(
    r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])(?:cols|steps)(?![-\w])'
    r'[^"\']*["\'][^>]*>', re.IGNORECASE)
_LIST_OPEN = re.compile(
    r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])list(?![-\w])'
    r'[^"\']*["\'][^>]*>', re.IGNORECASE)
_DIV_TAG = re.compile(r"<div\b[^>]*>|</div\s*>", re.IGNORECASE)
_CARD_OPEN = re.compile(
    r'^<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])card(?![-\w])',
    re.IGNORECASE)
_ITEM_OPEN = re.compile(
    r'^<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])item(?![-\w])',
    re.IGNORECASE)
_CARD_TITLE = re.compile(
    r'class\s*=\s*["\'][^"\']*\bcard-title\b[^"\']*["\'][^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL)
_HAS_DOT = re.compile(r'^\s*<div\b[^>]*\bikon-dot\b', re.IGNORECASE)
_ITEM_DOT = re.compile(
    r'<span\b[^>]*\bclass\s*=\s*["\']item-dot["\'][^>]*>\s*</span>',
    re.IGNORECASE)
_ANY_TAG = re.compile(r"<[^>]+>")
# Kalit so'z bo'yicha topilmasa beriladigan umumiy ikonkalar.
_SPARE_ICONS = ("idea", "target", "star", "strategy", "success",
                "research", "project", "innovation", "award", "team")


def _pick_icon(texts, used: set) -> str:
    """Kartochka yoki band matniga mos ikonka nomi.

    Matnlar tartib bilan sinaladi: avval sarlavha (u mavzuni aniq
    aytadi), keyin butun matn. Aks holda izohdagi tasodifiy so'z
    sarlavhadan ustun kelardi.
    """
    if isinstance(texts, str):
        texts = [texts]
    name, known = "", set()
    try:
        from . import icon_render

        known = set(icon_render.icon_names())
        for text in texts:
            if not text:
                continue
            path = icon_render.resolve(None, text,
                                       used={n + ".png" for n in used})
            name = os.path.basename(path)[:-4] if path else ""
            if name and name != "default" and name not in used:
                return name
    except Exception as exc:
        log.warning("Ikonka tanlanmadi: %s", exc)
    for spare in _SPARE_ICONS:
        if spare not in used and (not known or spare in known):
            return spare
    return name or _SPARE_ICONS[0]


def _plain(fragment: str, limit: int = 120) -> str:
    return " ".join(_ANY_TAG.sub(" ", fragment).split())[:limit]


def _children(body: str, opening):
    """Blokning bevosita bola `<div>` lari: (ochuvchi teg, butun blok)."""
    depth, child = 1, None
    for tag in _DIV_TAG.finditer(body, opening.end()):
        if tag.group(0).startswith("</"):
            depth -= 1
            if depth == 1 and child is not None:
                yield child, body[child.start():tag.end()]
                child = None
            if depth == 0:
                return
        else:
            if depth == 1:
                child = tag
            depth += 1


def _inside_card(body: str, at: int) -> bool:
    """`at` o'rni kartochka ichidami."""
    stack = []
    for tag in _DIV_TAG.finditer(body, 0, at):
        if tag.group(0).startswith("</"):
            if stack:
                stack.pop()
        else:
            stack.append(bool(_CARD_OPEN.match(tag.group(0))))
    return any(stack)


def _auto_icons(body: str) -> str:
    """Kartochka, qadam va ro'yxat bandlariga ikonka qo'yadi.

    Eski tizimda promptda "har kartochka yonida ikonka tursin" degan
    talab bor edi. Kvotalar olib tashlanganda u ham ketdi va model
    ixtiyoriy ikonkani deyarli qo'ymay qo'ydi — slaydlar yana quruq
    bo'lib qoldi. Ikonka — dizayn, mazmun emas, shuning uchun uni
    modeldan so'ramaymiz: kod har kartochka va bandning matniga
    qarab o'zi tanlaydi. Bir slaydda ikonka takrorlanmaydi.

    Kartochka ichidagi kichik ro'yxatga tegilmaydi — u yerda
    kartochkaning o'z ikonkasi yetarli.
    """
    inserts = []
    used: set = set(re.findall(r'data-icon\s*=\s*["\']([^"\']+)', body))

    for opening in _ROW_OPEN.finditer(body):
        for child, card in _children(body, opening):
            inner = card[len(child.group(0)):]
            if not _CARD_OPEN.match(child.group(0)) or _HAS_DOT.match(inner):
                continue
            title = _CARD_TITLE.search(card)
            name = _pick_icon([_plain(title.group(1)) if title else "",
                               _plain(card, 160)], used)
            used.add(name)
            inserts.append((child.end(), child.end(),
                            '<div class="ikon-dot"><img class="ikon" '
                            f'data-icon="{name}" alt=""></div>'))

    for opening in _LIST_OPEN.finditer(body):
        if _inside_card(body, opening.start()):
            continue
        for child, item in _children(body, opening):
            if not _ITEM_OPEN.match(child.group(0)):
                continue
            dot = _ITEM_DOT.search(item)
            if not dot:
                continue
            bold = re.search(r"<b>(.*?)</b>", item, re.IGNORECASE | re.DOTALL)
            name = _pick_icon([_plain(bold.group(1)) if bold else "",
                               _plain(item)], used)
            used.add(name)
            start = child.start() + dot.start()
            inserts.append((start, child.start() + dot.end(),
                            '<span class="item-ikon"><img class="ikon" '
                            f'data-icon="{name}" data-icon-color="FFFFFF" '
                            'alt=""></span>'))

    for start, end, piece in sorted(inserts, reverse=True):
        body = body[:start] + piece + body[end:]
    return body


_DOT_ICON = re.compile(
    r'(class\s*=\s*["\'][^"\']*\bikon-dot\b[^"\']*["\'][^>]*>\s*<img\b)'
    r'(?![^>]*data-icon-color)', re.IGNORECASE)


def _whiten_icons(body: str) -> str:
    """Rangli doira ichidagi ikonka oq rangga bo'yalsin.

    Doira endi kartochka rangida to'la bo'yalgan — ikonka o'sha rangda
    bo'lsa ko'rinmay qoladi. Doiradan tashqaridagi ikonka esa aksent
    rangida qoladi.
    """
    return _DOT_ICON.sub(lambda m: m.group(1) + ' data-icon-color="FFFFFF"',
                         body)


def _decorate(body: str) -> str:
    """To'q varaqqa yumshoq bezak doiralarini qo'yadi.

    Yassi to'q fon quruq ko'rinadi. Ikkita katta, kam farq qiladigan
    doira unga chuqurlik beradi. Ular `position:fixed` bilan
    qo'yilgani uchun joylashuvga tegmaydi va matnning orqasida
    turadi; PowerPointda oddiy shakl bo'lib chiqadi.
    """
    if not _DARK_SLIDE.search(body):
        return body
    bits = '<div class="bezak bezak-a"></div><div class="bezak bezak-b"></div>'
    return _DARK_SLIDE.sub(lambda m: m.group(1) + bits, body, count=1)


# `quote-by`dagi "— Tashkilot, 2026-yil hisobotidan": yil bugungi yoki
# kelgusi bo'lsa, bu o'ylab topilgan manba — yil va hisobot nomi olib
# tashlanadi, muallif nomi qoladi.
_QUOTE_BY = re.compile(
    r'(<p\b[^>]*class\s*=\s*["\'][^"\']*quote-by[^"\']*["\'][^>]*>)(.*?)(</p>)',
    re.IGNORECASE | re.DOTALL)
_BY_YEAR = re.compile(r",?\s*(?:\w+\s+)?((?:19|20)\d\d)\b[^<]*$")


def guard_quote_sources(body: str) -> str:
    """Iqtibos muallifidagi bugungi/kelgusi yilli "hisobot"ni olib tashlaydi."""
    from services import timeframe

    limit = timeframe.current_year()

    def swap(match):
        found = _BY_YEAR.search(match.group(2))
        if not found or int(found.group(1)) < limit:
            return match.group(0)
        return match.group(1) + match.group(2)[:found.start()].rstrip(" ,") \
            + match.group(3)

    return _QUOTE_BY.sub(swap, body)


# "(BMT, 2026)" — model bugungi yil ma'lumotini bilmaydi, shuning uchun bunday
# manba o'ylab topilgan bo'ladi. Yil o'rniga "taxminiy" yoziladi.
_SOURCE_YEAR = re.compile(r"\(([^()<>]{2,60}?),\s*((?:19|20)\d\d)\)")
_ESTIMATE = {"uz": "taxminiy", "uz-cyrl": "тахминий", "ru": "оценка", "en": "estimate", "kk": "болжамды"}


def guard_source_years(body: str, language: str = "uz") -> str:
    """Manbaga yozilgan bugungi/kelgusi yilni "taxminiy" ga almashtiradi."""
    from services import timeframe

    limit = timeframe.current_year()
    label = _ESTIMATE.get(language, _ESTIMATE["uz"])

    def swap(match):
        return (f"({match.group(1)}, {label})" if int(match.group(2)) >= limit
                else match.group(0))

    return _SOURCE_YEAR.sub(swap, body)


def build_pages(bodies: List[str], theme, language: str = "uz") -> List[str]:
    """Slayd mazmunlarini chizishga tayyor HTML hujjatlarga aylantiradi.

    Diagrammalar shu yerda chiziladi: model faqat ma'lumot beradi,
    SVG ni kod yasaydi — shunda ustunning balandligi ham, yozuvning
    o'rni ham har safar to'g'ri chiqadi.
    """
    # O'zbekcha taqdimotda barcha matn tanlangan yozuvda bo'ladi: model
    # adashib boshqa yozuvda yozgan yoki kod qo'ygan so'zlar shu yerda tuzatiladi.
    script = uz_script.script_of_language(language)
    if script:
        bodies = [uz_script.normalize_html(body, script) for body in bodies]

    # Hisob-kitobni kod bajaradi: `calc` va `data-calc` shu yerda raqamga
    # aylanadi, so'ng diagramma chiziladi.
    drawn = [deck_charts.draw(
        _half_charts(deck_math.render(deck_styles.decorate(
            _whiten_icons(_auto_icons(_decorate(
                guard_quote_sources(guard_source_years(deck_calc.apply(body), language))))), theme))),
        theme)
             for body in bodies]
    try:
        from . import html_images

        drawn, placed = html_images.apply_icons(drawn, theme)
        # Ikonkasi topilmagani rangli belgiga aylanadi — buzuq rasm
        # belgisi slaydga tushmaydi.
        drawn = html_images.sweep(drawn, theme)
        log.info("Ikonkalar: %d ta", placed)
    except Exception as exc:
        log.warning("Ikonkalar qo'yilmadi: %s", exc)
    return [_keep_source(deck_style.page(theme, page), body)
            for page, body in zip(drawn, bodies)]


# Modelning o'zi yozgan slayd sahifaning boshida izoh sifatida
# saqlanadi. Tuzatish kerak bo'lsa modelga AYNAN shu yuboriladi —
# ikonkalar data-URI, diagrammalar tayyor SVG bo'lib ketgan chizilgan
# nusxa emas. U nusxa minglab token bo'lardi: model uni qayta yoza
# olmay, o'rniga yangi, sodda slayd yozib qo'yardi.
_SOURCE = re.compile(r"<!--manba:([A-Za-z0-9+/=]*)-->")


def _keep_source(page: str, body: str) -> str:
    import base64

    token = base64.b64encode(body.encode("utf-8")).decode("ascii")
    return page.replace("</head>", f"<!--manba:{token}--></head>", 1)


def source_of(page: str) -> str:
    """Sahifadan modelning asl yozgan slaydini oladi ("" — topilmasa)."""
    import base64

    match = _SOURCE.search(page or "")
    if not match:
        return ""
    try:
        return base64.b64decode(match.group(1)).decode("utf-8")
    except Exception:
        return ""


def write_slides(topic: str, slide_count: int, theme, language: str = "uz",
                 level: int = 2, preferences: str = "", source_text: str = "",
                 author: str = "",
                 progress_cb: Optional[Callable] = None,
                 outline_out: Optional[dict] = None,
                 plan_cb: Optional[Callable[[List[Dict]], None]] = None) -> List[str]:
    """Butun taqdimotni HTML hujjatlar ro'yxati qilib qaytaradi.

    `outline_out` berilsa, unga reja (`outline`: sarlavha, mazmun, kategoriya) va mavzu oilasi
    (`family`) yoziladi — keyin bitta sahifani qayta yozishda kerak bo'ladi.
    `plan_cb([{title, category}, ...])` — reja tayyor bo'lishi bilan (slaydlar yozilishidan oldin)
    chaqiriladi: sayt kutish animatsiyasida haqiqiy sarlavhalarni ko'rsatadi.
    """
    # Hamma so'rovlarga qo'shiladigan umumiy qoidalar (bugungi sana) ham taqdimot tilida bo'lsin.
    with prompts.use(language):
        return _write_slides(topic, slide_count, theme, language, level, preferences, source_text, author,
                             progress_cb, outline_out, plan_cb)


def _write_slides(topic, slide_count, theme, language, level, preferences, source_text, author,
                  progress_cb, outline_out, plan_cb) -> List[str]:
    # Mijoz tanlagan son — muqova va rejadan KEYINGI slaydlar (xulosa shu songa
    # kiradi). Muqova va reja slaydi qo'shimcha yoziladi: ilgari ular ham
    # hisobga kirar, 10 slaydda asosiy mavzuga 8 tadan kam slayd qolardi.
    slide_count = max(4, int(slide_count or 8)) + 2
    # Matn hajmi rang sxemasida turadi: "kam" — kompozitsiyalar (deck_compose), aks holda ko'p matnli bloklar.
    volume = "kam" if getattr(theme, "layout", "") == "kam" else "kop"
    kam = volume == "kam"
    plan = plan_outline(topic, slide_count, language, level, volume)
    outline = chart_data.ground(plan["slides"], topic, language, level, sentences="1-2" if kam else "2-3")
    if kam:
        # Kompozitsiya diagramma ma'lumoti aniqlangandan keyin beriladi: ma'lumot topilmasa slayd o'z
        # kategoriyasiga qaytadi.
        outline = deck_compose.assign(outline, topic)
    family = plan["family"]
    if plan_cb:
        try:
            plan_cb([{"title": str(o.get("title") or ""), "category": str(o.get("category") or "")} for o in outline])
        except Exception:
            log.debug("plan_cb xatosi", exc_info=True)
    system = deck_compose.shell(language, MARKER) if kam else shell_rules(theme, language)

    slides: List[str] = []
    used: List[str] = []
    start = 1
    while start <= slide_count:
        count = min(CHUNK, slide_count - start + 1)
        if progress_cb:
            try:
                progress_cb(start - 1, slide_count)
            except Exception:
                pass

        user = _user_prompt(topic, start, count, slide_count, outline,
                            used, level, source_text, preferences, author,
                            family, shapes=[shape_signature(b) for b in slides],
                            written=[deck_logic.title_of(b) for b in slides], language=language,
                            volume=volume)
        chunk = _write_chunk(system, user, count)
        if len(chunk) < count:
            # Bir marta qayta so'raymiz: chala javob har safar emas,
            # ba'zan keladi.
            log.warning("%s-%s slaydlardan %d tasi keldi, qayta so'raladi",
                        start, start + count - 1, len(chunk))
            retry = _write_chunk(system, user, count)
            if len(retry) > len(chunk):
                chunk = retry
        # Hali ham yetmasa — yetmaganlari BITTADAN so'raladi. Uch
        # slaydlik katta so'rov vaqt chegarasiga, hisobdagi mablag'
        # chegarasiga yoki model javob uzunligi chegarasiga urilishi
        # mumkin; bitta slaydlik kichik so'rov esa o'tadi. Ilgari
        # yetmagan slaydlar jimgina tashlab yuborilardi va mijozga
        # ikki slaydlik taqdimot borardi.
        for number in range(start + len(chunk), start + count):
            single = _user_prompt(topic, number, 1, slide_count, outline,
                                  used, level, source_text, preferences,
                                  author, family,
                                  shapes=[shape_signature(b) for b in slides]
                                  + [shape_signature(b) for b in chunk],
                                  written=[deck_logic.title_of(b) for b in slides + chunk],
                                  language=language, volume=volume)
            one = _write_chunk(system, single, 1)
            if not one:
                # Oxirgi chora: kichik JSON so'rov, slaydni kod yig'adi.
                # Katta HTML javobni filtr kesadigan mavzularda ham u
                # odatda o'tadi — mijoz taqdimotsiz qolmaydi.
                item = outline[number - 1] if number <= len(outline) else {}
                plain = _plain_slide(topic, item.get("brief") or topic,
                                     number, slide_count, language, author)
                one = [plain] if plain else []
            if one:
                chunk.append(one[0])
            else:
                log.error("%d-slayd yozilmadi", number)

        for offset, body in enumerate(chunk[:count]):
            number = start + offset
            if number == 1:
                body = _cover_credit(body, author, language)
            if number == slide_count:
                body = _drop_thanks(body)
            body = chart_data.enforce(body, outline[number - 1] if number <= len(outline) else None, language)
            if 1 < number and not kam and _thin(body):
                body = _thicken(body, system, theme)
            if number == slide_count:
                body = _no_photo(body)
            slides.append(body)
        used.extend(item["brief"] for item in outline[start - 1:start - 1 + count])
        start += count

    log.info("HTML slaydlar tayyor: %d/%d ta", len(slides), slide_count)
    if not slides:
        raise RuntimeError("AI birorta to'liq slayd qaytarmadi")
    # Chala taqdimot mijozga berilmaydi: pul qaytariladi va qayta
    # urinish mumkin. Bir-ikki slayd yetmasa — taqdimot baribir to'liq
    # ko'rinadi, u topshiriladi.
    if len(slides) < _enough(slide_count):
        raise RuntimeError(
            f"AI {slide_count} ta slayddan faqat {len(slides)} tasini yozdi")
    ctx = _Deck(topic, slide_count, outline, family, system, theme, language, level,
                source_text, preferences, author, volume)
    if outline_out is not None:
        outline_out["family"] = family
        outline_out["outline"] = [{"title": str(o.get("title") or ""), "brief": str(o.get("brief") or ""),
                                   "category": str(o.get("category") or ""), "layout": str(o.get("layout") or "")}
                                  for o in outline]
    slides = repair_deck(slides, ctx)
    if not kam:     # kam matnlida xilma-xillikni kompozitsiyalar navbati beradi
        slides = diversify(slides, theme, language)
    # Diagramma raqamlari faqat Claude bergan ma'lumot: qayta yozish va xilma-xillashtirish
    # davomida paydo bo'lgan to'qima raqamlar shu yerda tozalanadi.
    slides = [chart_data.enforce(b, outline[i] if i < len(outline) else None, language)
              for i, b in enumerate(slides)]
    return build_pages(slides, theme, language)


# ───────────────────────────────────────────── mantiq va sifat tekshiruvi

MAX_FIXES = 6               # bitta taqdimotda ko'pi bilan shuncha slayd qayta yoziladi


class _Deck:
    """Taqdimotni yozishda ishlatilgan sozlamalar (qayta yozish uchun kerak)."""

    def __init__(self, topic, total, outline, family, system, theme, language, level,
                 source_text, preferences, author, volume="kop"):
        self.topic, self.total, self.outline, self.family = topic, total, outline, family
        self.system, self.theme, self.language, self.level = system, theme, language, level
        self.source_text, self.preferences, self.author = source_text, preferences, author
        self.volume = volume


def _rewrite_slide(slides: List[str], index: int, note: str, ctx: "_Deck") -> Optional[str]:
    """`index`-slaydni ko'rsatma bilan qayta yozdiradi; yaroqli natija bo'lmasa None."""
    number = index + 1
    others = [b for i, b in enumerate(slides) if i != index]
    user = _user_prompt(
        ctx.topic, number, 1, ctx.total, ctx.outline,
        [o.get("brief", "") for i, o in enumerate(ctx.outline) if i != index][:8],
        ctx.level, ctx.source_text, ctx.preferences, ctx.author, ctx.family,
        shapes=[shape_signature(b) for b in others],
        written=[deck_logic.title_of(b) for i, b in enumerate(slides) if i != index], language=ctx.language,
        volume=getattr(ctx, "volume", "kop"))
    user += "\n\n" + note
    try:
        fresh = _write_chunk(ctx.system, user, 1)
    except Exception as exc:
        log.warning("%d-slayd qayta yozilmadi: %s", number, exc)
        return None
    if not fresh:
        return None
    return fresh[0]


def repair_deck(slides: List[str], ctx: "_Deck") -> List[str]:
    """Yozilgan slaydlarni mantiq jihatidan tekshiradi va nuqsonlisini qayta yozdiradi.

    1. O'rtada yoki oxirda takrorlangan "reja" slaydi;
    2. avvalgi slaydning takrori (bir xil sarlavha yoki bir xil matn);
    3. zich jadval (butun varaq jadval — auditoriyada o'qib bo'lmaydi);
    4. diagramma bo'lishi kerak edi, lekin yozilmagan;
    keyin: umumlashtiruvchi gap, kartochka raqamlarini olib tashlash va reja
    slaydini HAQIQIY sarlavhalardan yig'ish.
    """
    result = list(slides)
    count = len(result)
    if count < 4:
        return result
    fixes = 0
    last = count - 1

    def fix(index: int, note: str, accept) -> bool:
        nonlocal fixes
        if fixes >= MAX_FIXES:
            return False
        fixes += 1
        fresh = _rewrite_slide(result, index, note, ctx)
        if fresh and accept(fresh):
            result[index] = fresh
            log.info("%d-slayd mantiq tekshiruvi bo'yicha qayta yozildi", index + 1)
            return True
        log.info("%d-slaydning qayta yozilishi qabul qilinmadi", index + 1)
        return False

    def own_brief(index: int) -> str:
        item = ctx.outline[index] if index < len(ctx.outline) else {}
        title = item.get("title") or ""
        return (f"«{title}» — " if title else "") + (item.get("brief") or "")

    # 1) Boshqa joydagi "reja" slaydlari
    for index in deck_logic.stray_plans(result):
        if index == last:
            continue
        fix(index,
            prompts.fill(prompts.get(ctx.language).REPAIR["stray_plan"], brief=own_brief(index)),
            lambda body: not deck_logic.is_plan_title(deck_logic.title_of(body)))

    # 2) Takrorlangan slaydlar
    for later, earlier in sorted(deck_logic.duplicates(result).items()):
        before = deck_logic.title_of(result[earlier])
        fix(later,
            prompts.fill(prompts.get(ctx.language).REPAIR["duplicate"], n=earlier + 1, title=before, brief=own_brief(later)),
            lambda body, e=earlier: not (
                deck_logic.similar_titles(deck_logic.title_of(body), deck_logic.title_of(result[e]))
                or deck_logic.same_content(body, result[e])))

    # 3) Zich jadval
    for index in range(2, last):
        if deck_logic.oversized_table(result[index]):
            fix(index,
                prompts.fill(prompts.get(ctx.language).REPAIR["table"], slide=source_of(result[index]) or result[index]),
                lambda body: not deck_logic.oversized_table(body))

    # 4) Diagramma bo'lishi kerak bo'lgan slaydlar (faqat Claude haqiqiy ma'lumot bergan)
    for index in range(2, last):
        item = ctx.outline[index] if index < len(ctx.outline) else {}
        if (item.get("chart") or item.get("chart_fallback")) and not deck_logic.has_chart(result[index]):
            fix(index,
                prompts.fill(prompts.get(ctx.language).REPAIR["chart"], note=item.get("chart_note", ""), brief=own_brief(index)),
                deck_logic.has_chart)

    # 4c) Reja diagramma demagan, lekin model diagramma yozgan slaydlar: avval Claude'dan haqiqiy
    # ma'lumot so'raladi; topilsa slayd shu ma'lumot bilan qayta yoziladi (matn raqamlarga mos bo'lsin).
    for index in chart_data.research_strays(result, ctx.outline, ctx.topic, ctx.language):
        item = ctx.outline[index]
        fix(index,
            prompts.fill(prompts.get(ctx.language).REPAIR["chart_replaced"], note=item.get("chart_note", ""), brief=own_brief(index)),
            deck_logic.has_chart)

    kam = getattr(ctx, "volume", "kop") == "kam"
    P = prompts.get(ctx.language)

    # 4b) Rasmli bo'lishi kerak bo'lgan slaydlar
    for index in range(2, last):
        item = ctx.outline[index] if index < len(ctx.outline) else {}
        if item.get("category") == "matn_rasm" and not deck_logic.has_photo(result[index]):
            note = (prompts.fill(P.KAM["photo"], layout=item.get("layout") or "", brief=own_brief(index)) if kam
                    else prompts.fill(P.REPAIR["photo"], brief=own_brief(index)))
            fix(index, note, deck_logic.has_photo)

    # 4d) Juda uzun slaydlar: matn kichraytirilmaydi, slaydning o'zi qisqaroq qayta yoziladi.
    result = shorten_long(result, ctx)

    # 5) Umumlashtiruvchi gap (kam matnlida bosh gap kompozitsiya qolipida bor)
    if not kam:
        result = add_leads(result, ctx)

    # 6) Kartochka raqamlari (faqat reja slaydida qoladi)
    result = [deck_logic.strip_numbering(b) for b in result]

    # 6b) Sarlavha harflari (birinchi so'z bosh harf) va yolg'iz qolgan kartochka (3+1).
    # Bu ikki narsa kod bilan tuzatiladi: modelga "shunday yozma" deyish o'rniga natija to'g'rilanadi.
    result = [b if i == 0 else deck_logic.fix_columns(deck_logic.fix_title_case(b))
              for i, b in enumerate(result)]
    # 6c) Rasmli slayd: matn yaxlit abzatslar bo'lsin (mayda bandlar va ikonkali qatorlar emas).
    if not kam:
        result = [b if i == 0 else deck_logic.flow_photo_text(b) for i, b in enumerate(result)]

    # 7) Reja slaydi — yozilgan slaydlarning haqiqiy sarlavhalaridan
    items = []
    for index in range(2, last):
        title = deck_logic.title_of(result[index]) or (
            ctx.outline[index].get("title", "") if index < len(ctx.outline) else "")
        brief = ctx.outline[index].get("brief", "") if index < len(ctx.outline) else ""
        if title:
            items.append((title, brief))
    if items:
        result[1] = deck_logic.plan_slide(items, ctx.language)
    return result


MAX_SHORTEN = 6             # bitta taqdimotda ko'pi bilan shuncha uzun slayd qisqartiriladi


def shorten_long(slides: List[str], ctx: "_Deck") -> List[str]:
    """Matni chegaradan uzun slaydlarni (`deck_compose.WORD_LIMIT`) qisqaroq qayta yozdiradi.

    Ilgari uzun matn sig'masa shrift kichraytirilardi va varaq mayda yozuv bilan to'lib ketardi.
    Endi uzunlik yozilgan zahoti o'lchanadi: eng uzun slaydlar birinchi, natija qisqaroq bo'lsagina
    qabul qilinadi (aks holda eski slayd qoladi, `html_render.fit` uni sig'diradi).
    """
    volume = getattr(ctx, "volume", "kop")
    limit = deck_compose.WORD_LIMIT.get(volume, deck_compose.WORD_LIMIT["kop"])
    last = len(slides) - 1
    long = sorted((i for i in range(2, last) if deck_compose.too_long(slides[i], volume)),
                  key=lambda i: -deck_compose.words(slides[i]))[:MAX_SHORTEN]
    if not long:
        return slides
    result = list(slides)
    P = prompts.get(ctx.language)
    for index in long:
        before = deck_compose.words(result[index])
        note = prompts.fill(P.REPAIR["long"], n=before, limit=limit, slide=source_of(result[index]) or result[index])
        fresh = _rewrite_slide(result, index, note, ctx)
        if fresh and deck_compose.words(fresh) < before and (
                not deck_logic.has_photo(result[index]) or deck_logic.has_photo(fresh)) and (
                not deck_logic.has_chart(result[index]) or deck_logic.has_chart(fresh)):
            result[index] = fresh
            log.info("%d-slayd qisqartirildi: %d → %d so'z", index + 1, before, deck_compose.words(fresh))
        else:
            log.info("%d-slaydning qisqa varianti qabul qilinmadi (%d so'z)", index + 1, before)
    return result


def add_leads(slides: List[str], ctx: "_Deck") -> List[str]:
    """Umumlashtiruvchi gapi yo'q slaydlarga bitta bosh fikr jumlasi qo'shadi.

    Model slaydni faqat bandlar bilan to'ldirib qo'ysa, tinglovchi nima
    haqida ekanini bilmay qoladi va matn sun'iy ko'rinadi. Jumla slaydning
    o'z matnidan olinadi: yangi fakt qo'shilmaydi.
    """
    last = len(slides) - 1
    wanted = [i for i in range(2, last) if deck_logic.needs_lead(slides[i])]
    if not wanted:
        return slides
    L = prompts.get(ctx.language).LEADS
    listing = "\n\n".join(
        prompts.fill(L["item"], n=i + 1, title=deck_logic.title_of(slides[i]), text=deck_logic.plain(slides[i])[:420])
        for i in wanted[:20])
    prompt = prompts.fill(L["prompt"], topic=ctx.topic, target=prompts.target(ctx.language), listing=listing)
    try:
        data = llm_client._call_openrouter(
            L["system"], prompt,
            temperature=0.4, max_tokens=300 + 120 * len(wanted[:20]))
    except Exception as exc:
        log.warning("Umumlashtiruvchi gaplar olinmadi: %s", exc)
        return slides
    result = list(slides)
    added = 0
    for item in (data.get("leads") or []):
        try:
            index = int(item.get("n")) - 1
        except (TypeError, ValueError, AttributeError):
            continue
        lead = str(item.get("lead") or "").strip()
        if index in wanted and lead and 4 <= len(lead.split()) <= 40:
            result[index] = deck_logic.insert_lead(result[index], lead)
            added += 1
    log.info("Umumlashtiruvchi gap: %d ta slaydga qo'shildi", added)
    return result


# ───────────────────────────────────────────── bir xil slaydlarga qarshi

# Taqdimot bir xil ko'rinadigan bo'lib qolsa (masalan, uch slayd "ro'yxat +
# rasm"), mijoz buni darhol payqaydi. Prompt va reja modelga "takrorlama"
# deydi, lekin model baribir eng oson shaklga qaytadi. Shuning uchun yozib
# bo'lingach slaydlar shakli solishtiriladi va takrorlangan slayd boshqa blok
# bilan QAYTA yozdiriladi — mazmuni saqlanadi, faqat shakl o'zgaradi.
# Bu qat'iy kvota emas: mazmun uchun boshqa shakl topilmasa, qayta yozish
# rad etiladi va slayd o'zgarmaydi.
MAX_SAME_SHAPE = 2          # bir shakl butun taqdimotda ko'pi bilan shuncha
MAX_REWORKS = 3             # bitta taqdimotda ko'pi bilan shuncha qayta yozish



def shape_signature(body: str) -> tuple:
    """Slaydning asosiy bloklari (masalan, ('list', 'rasm', 'split'))."""
    counts = _shape(body)
    return tuple(sorted(name for name, n in counts.items() if n and name != "ikon-row"))


def repeated_slides(bodies: List[str]) -> List[int]:
    """Shakli takrorlangan slaydlar indekslari (muqova va yakundan tashqari)."""
    flagged, seen = [], {}
    last = len(bodies) - 1
    previous = None
    for index, body in enumerate(bodies):
        signature = shape_signature(body)
        if index in (0, 1, last) or not signature:
            previous = None
            continue
        seen[signature] = seen.get(signature, 0) + 1
        # Rasmli slaydlar soni kvota bilan belgilanadi (har 10 tada 3 ta): ularni
        # "bir xil shakl" deb qayta yozish rasmni yo'qotardi. Faqat ketma-ket kelsa belgilanadi.
        repeated_too_often = seen[signature] > MAX_SAME_SHAPE and "rasm" not in signature
        if signature == previous or repeated_too_often:
            flagged.append(index)
        previous = signature
    return flagged


def _shape_label(signature: tuple, language: str = "uz") -> str:
    names = prompts.get(language).SHAPE_NAMES
    return " + ".join(dict.fromkeys(names.get(n, n) for n in signature)) or names[""]


def rework_slide(body: str, signature: tuple, used: List[tuple], theme,
                 language: str = "uz") -> str:
    """Takrorlangan slaydni boshqa blok bilan qayta yozdiradi (yoki o'zini qaytaradi)."""
    import difflib

    taken = "; ".join(sorted({_shape_label(u, language) for u in used if u}))
    user = prompts.fill(prompts.get(language).REWORK, shape=_shape_label(signature, language), taken=taken,
                        slide=source_of(body) or body)
    try:
        raw = llm_client._call_openrouter_text(
            shell_rules(theme, language), user, temperature=0.6,
            max_tokens=max(2600, len(body) // 2))
    except Exception as exc:
        log.warning("Takrorlangan slayd qayta yozilmadi: %s", exc)
        return body

    fresh = split_slides(raw)
    if not fresh:
        return body
    new_signature = shape_signature(fresh[0])
    if not new_signature or new_signature == signature or new_signature in used:
        log.info("Qayta yozish qabul qilinmadi: shakl baribir takror (%s)", _shape_label(new_signature))
        return body
    if bool(_DARK_SLIDE.search(body)) != bool(_DARK_SLIDE.search(fresh[0])):
        return body
    words = lambda text: _plain(text, 100000).lower().split()
    before, after = words(body), words(fresh[0])
    if before and difflib.SequenceMatcher(None, before, after).ratio() < 0.3:
        log.info("Qayta yozish qabul qilinmadi: mazmun yo'qolgan")
        return body
    return fresh[0]


def diversify(bodies: List[str], theme, language: str = "uz") -> List[str]:
    """Bir xil shakldagi slaydlarni boshqa blok bilan almashtiradi."""
    result = list(bodies)
    reworked = 0
    for index in repeated_slides(result):
        if reworked >= MAX_REWORKS:
            break
        # Oldingi qayta yozish bu slaydni allaqachon hal qilgan bo'lishi mumkin.
        if index not in repeated_slides(result):
            continue
        signature = shape_signature(result[index])
        # Muqova va reja slaydi (kartochkalar) o'zgartirish uchun taqiqlangan shakllarga kirmaydi.
        used = [shape_signature(b) for i, b in enumerate(result) if i not in (index, 0, 1)]
        updated = rework_slide(result[index], signature, used, theme, language)
        if updated is not result[index]:
            result[index] = updated
            reworked += 1
            log.info("%d-slayd boshqa shaklda qayta yozildi", index + 1)
    return result


# Muqovadagi "Tayyorladi: ... | Fan: ... | 2026" qatori. Model uni namunadan
# ko'chirib, ism, fan va yilni o'zi o'ylab topardi — mijoz ism kiritmagan
# bo'lsa ham muqovada begona ism turardi. Endi bunday qator kod bilan
# olib tashlanadi, ism esa faqat mijoz kiritgan bo'lsa qo'yiladi.
_CREDIT_LABEL = {"uz": "Tayyorladi", "uz-cyrl": "Тайёрлади", "ru": "Подготовил(а)", "en": "Prepared by", "kk": "Дайындаған"}
_CREDIT_LINE = re.compile(
    r"<(p|div|span)\b[^>]*>(?:(?!</?\1\b).)*?"
    r"(?:tayyorladi|bajardi|muallif|topshirdi|fan\s*:|yo.nalish\s*:|"
    r"подготовил|выполнил|автор|предмет\s*:|prepared\s+by|author|subject\s*:)"
    r"(?:(?!</?\1\b).)*?</\1>",
    re.IGNORECASE | re.DOTALL)
_NOTE_LINE = re.compile(r"<p\b[^>]*\bclass\s*=\s*[\"'][^\"']*\bnote\b[^\"']*[\"'][^>]*>.*?</p>",
                        re.IGNORECASE | re.DOTALL)


def _cover_credit(body: str, author: str = "", language: str = "uz") -> str:
    """Muqovadan ism/fan/yil qatorini olib, mijoz ismini (bo'lsa) qo'yadi."""
    body = _NOTE_LINE.sub("", body)
    body = _CREDIT_LINE.sub("", body)
    author = (author or "").strip()
    if not author:
        return body
    label = _CREDIT_LABEL.get(language, _CREDIT_LABEL["uz"])
    note = f'<p class="note">{_escape(label)}: {_escape(author)}</p>'
    # Muqova `.body` ichining oxiriga qo'yiladi.
    match = re.search(r"</div>\s*</section>\s*$", body, re.IGNORECASE)
    if match:
        return body[:match.start()] + note + body[match.start():]
    return re.sub(r"</section>\s*$", note + "</section>", body, count=1,
                  flags=re.IGNORECASE)


def _enough(slide_count: int) -> int:
    """Topshirish uchun kerakli eng kam slayd soni."""
    return max(3, -(-slide_count * 4 // 5))


# Varaqni mazmunli qiladigan bloklar. Ularning birortasi ham bo'lmasa
# varaq faqat sarlavha va bir-ikki jumladan iborat — bunday varaq
# (bo'lim ajratkichi ham) taqdimotda kerak emas.
_CONTENT_CLASSES = ("cols", "steps", "list", "timeline", "split", "formula",
                    "misol", "chart", "kpi", "quote", "ikon-row", "rasm",
                    "card")


# Xulosa varag'idagi "rahmat" va "savollar" qatorlari. Qisqa matnli
# elementgina olib tashlanadi — mazmunli gap ichida "savol" so'zi
# uchrasa tegilmaydi.
_THANKS = re.compile(
    r"rahmat|e[\'ʼ‘’`]?tiboringiz|savollar|savolingiz|спасибо|"
    r"благодар|вопрос|thank|questions", re.IGNORECASE)
_SHORT_TEXT = re.compile(
    r"<(p|h[1-6]|div|span)\b[^>]*>((?:(?!<div\b|</div>|<p\b|</p>).){0,120}?)"
    r"</\1\s*>", re.IGNORECASE | re.DOTALL)
_TITLE_CLASS = re.compile(r'class\s*=\s*["\'][^"\']*\btitle\b', re.IGNORECASE)


def _drop_thanks(body: str) -> str:
    """Xulosadan "rahmat" va "savollar" qatorlarini olib tashlaydi."""

    def drop(match):
        text = _plain(match.group(2), 200)
        if (text and len(text) <= 80 and _THANKS.search(text)
                and not _TITLE_CLASS.search(match.group(0))):
            return ""
        return match.group(0)

    return _SHORT_TEXT.sub(drop, body)


_SPLIT_OPEN = re.compile(
    r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])split(?![-\w])'
    r'[^"\']*["\'][^>]*>', re.IGNORECASE)
_RASM_OPEN = re.compile(
    r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])rasm(?![-\w])'
    r'[^"\']*["\'][^>]*>', re.IGNORECASE)
_RASM_TEXT = re.compile(
    r'<p\b[^>]*\bclass\s*=\s*["\'][^"\']*\brasm-matn\b[^"\']*["\'][^>]*>'
    r'(.*?)</p>', re.IGNORECASE | re.DOTALL)


def _close_of(body: str, opening) -> int:
    """Ochuvchi `<div>` ning yopuvchi tegidan keyingi o'rin (-1 — yo'q)."""
    depth = 1
    for tag in _DIV_TAG.finditer(body, opening.end()):
        depth += -1 if tag.group(0).startswith("</") else 1
        if depth == 0:
            return tag.end()
    return -1


def _no_photo(body: str) -> str:
    """Xulosadagi rasm blokini oddiy matnga aylantiradi.

    Xulosaga rasm kerak emas. Rasm o'rnidagi qo'shimcha matn
    yo'qotilmaydi — u xulosa matnining davomi bo'lib, to'liq enli
    qatorga o'tadi; rasm bloki turgan `split` esa yechiladi.
    """
    while True:
        opening = _RASM_OPEN.search(body)
        if not opening:
            return body
        end = _close_of(body, opening)
        if end < 0:
            return body
        texts = _RASM_TEXT.findall(body[opening.start():end])
        plain = "".join(f'<p class="note">{text.strip()}</p>'
                        for text in texts if _plain(text))
        # Rasm bloki turgan `split` (bo'lsa) yechiladi.
        holder = None
        for split in _SPLIT_OPEN.finditer(body, 0, opening.start()):
            close = _close_of(body, split)
            if close >= end:
                holder = (split, close)
        body = body[:opening.start()] + plain + body[end:]
        if holder:
            split, close = holder
            close += len(plain) - (end - opening.start())
            inner = body[split.end():close]
            inner = inner[:inner.lower().rfind("</div")]
            body = body[:split.start()] + inner + body[close:]


_CHART_OPEN = re.compile(
    r'<div\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bchart\b)'
    r'(?![^>]*\bdata-size\s*=)', re.IGNORECASE)


def _half_charts(body: str) -> str:
    """Ikki ustunli joydagi diagramma yarim o'lchamda chizilsin.

    To'liq enli chizma yarim ustunga siqilsa, yozuvlari o'qib
    bo'lmas darajada mayda chiqadi.
    """
    spans = []
    for split in _SPLIT_OPEN.finditer(body):
        close = _close_of(body, split)
        if close > 0:
            spans.append((split.end(), close))

    def mark(match):
        inside = any(start <= match.start() < end for start, end in spans)
        return match.group(0) + (' data-size="half"' if inside else "")

    return _CHART_OPEN.sub(mark, body)


def _thin(body: str) -> bool:
    """Varaq faqat sarlavha va qisqa matndan iboratmi."""
    if re.search(r"<table\b", body, re.IGNORECASE):
        return False
    for value in _CLASS_ATTR.findall(body):
        if any(name in _CONTENT_CLASSES for name in value.split()):
            return False
    return True


def _thicken(body: str, system: str, theme, language: str = "") -> str:
    """Yupqa varaqni MATN VA RASM varag'iga aylantiradi (til — joriy taqdimot tili, `prompts.use`)."""
    user = prompts.fill(prompts.get(language or prompts.current()).THICKEN, slide=body)
    try:
        raw = llm_client._call_openrouter_text(
            system, user, temperature=0.5, max_tokens=3000)
    except Exception as exc:
        log.warning("Yupqa slayd to'ldirilmadi: %s", exc)
        return body
    fixed = split_slides(raw)
    if not fixed or _thin(fixed[0]):
        log.warning("Yupqa slayd to'ldirilmadi: javob ham yupqa")
        return body
    log.info("Yupqa slayd matn va rasm bilan to'ldirildi")
    return fixed[0]


_DATA_SRC = re.compile(r'src\s*=\s*(["\'])\s*(data:[^"\']+)\1',
                       re.IGNORECASE)


def _park_images(html: str) -> tuple:
    """Rasmlarni qisqa belgiga almashtiradi."""
    store = {}

    def hide(match):
        token = f"#rasm{len(store) + 1}"
        store[token] = match.group(2)
        return f'src="{token}"'

    return _DATA_SRC.sub(hide, html), store


def _unpark_images(html: str, store: dict) -> str:
    """Belgilarni rasmning o'ziga qaytaradi."""
    for token, uri in store.items():
        html = html.replace(token, uri)
    return html


def _localize_problem(text: str, P) -> str:
    """Brauzer topgan xato (o'zbekcha, html_extract) — taqdimot tilidagi ifodalar bilan."""
    for uz_words, words in P.PROBLEM_WORDS.items():
        text = text.replace(uz_words, words)
    return text


def fix_slide(html: str, problems: List[str], theme, language: str = "uz") -> str:
    """Joylashuvi buzilgan slaydning O'ZINI tuzattiradi.

    Yangi slayd yozdirilmaydi. Modelga o'zi yozgan slayd va unda
    brauzer topgan xatolar — qaysi matn, qayerda — aniq aytiladi va
    faqat o'sha joylar tuzatiladi. Javob asl slaydga solishtiriladi:
    tuzilishi o'zgargan yoki mazmuni yo'qolgan bo'lsa, u tuzatish
    emas, qayta yozish — qabul qilinmaydi.
    """
    if not problems:
        return html

    source = source_of(html)
    if not source:
        match = _SECTION.search(html)
        if not match:
            return html
        source = _park_images(match.group(0))[0]

    P = prompts.get(language)
    listed = "\n".join(f"- {_localize_problem(item, P)}" for item in problems)
    user = prompts.fill(P.FIX, problems=listed, slide=source)

    try:
        raw = llm_client._call_openrouter_text(
            shell_rules(theme, language), user,
            temperature=0.2, max_tokens=max(2600, len(source) // 2))
    except Exception as exc:
        log.error("Slaydni tuzatib bo'lmadi: %s", exc)
        return html

    fixed = split_slides(raw)
    if not fixed:
        return html
    reason = _rewritten(source, fixed[0],
                        any("mayda" in item for item in problems))
    if reason:
        log.warning("Tuzatish qabul qilinmadi — slayd qayta yozilgan: %s",
                    reason)
        return html
    return build_pages(fixed[:1], theme, language)[0]


# Slaydning tuzilishini belgilaydigan bloklar. Tuzatishda ularning
# biri yo'qolsa yoki yangisi paydo bo'lsa — bu tuzatish emas.
_BLOCK_CLASSES = ("cols", "steps", "list", "timeline", "split", "formula",
                  "misol", "chart", "calc", "kpi", "quote", "ikon-row", "lead",
                  "rasm")
_CLASS_ATTR = re.compile(r'class\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def _shape(body: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in _CLASS_ATTR.findall(body):
        for name in value.split():
            if name in _BLOCK_CLASSES:
                counts[name] = counts.get(name, 0) + 1
    counts["table"] = len(re.findall(r"<table\b", body, re.IGNORECASE))
    return counts


def _rewritten(before: str, after: str, shrunk: bool = False) -> str:
    """Tuzatilgan slayd asl slaydning o'zimi. Bo'lmasa — sababi."""
    import difflib

    dark = lambda body: bool(_DARK_SLIDE.search(body))
    if dark(before) != dark(after):
        return "slayd turi (dark) o'zgargan"
    old, new = _shape(before), _shape(after)
    changed = sorted(name for name in set(old) | set(new)
                     if bool(old.get(name)) != bool(new.get(name)))
    if changed:
        return "bloklar o'zgargan: " + ", ".join(changed)
    words = lambda body: _plain(body, 100000).lower().split()
    first, second = words(before), words(after)
    if first:
        kept = difflib.SequenceMatcher(None, first, second).ratio()
        # Mayda matn xatosida mazmunni sezilarli qisqartirish — aynan
        # kerakli tuzatish, shuning uchun chegara pastroq.
        if kept < (0.3 if shrunk else 0.55):
            return f"matnning faqat {kept:.0%} i qolgan"
    return ""


# Bo'sh yonga qo'yiladigan izohning uzunligi. Uzun matn qutisidan
# toshib, diagrammaning ustiga chiqib ketadi.
_GAP_WORDS = 45


def explain_visual(html: str, theme, language: str = "uz") -> str:
    """Slayddagi diagrammani tushuntiruvchi qisqa matn.

    Slaydning bir yoni bo'sh qolganda ishlatiladi: slaydni qayta
    chizish shart emas, bo'sh joyga diagrammaning ma'nosini
    aytadigan matn qo'yilsa yetadi.
    """
    E = prompts.get(language).EXPLAIN
    match = _SECTION.search(html)
    parked = _park_images(match.group(0) if match else html)[0]
    system = prompts.fill(E["system"], target=prompts.target(language))
    user = prompts.fill(E["prompt"], words=_GAP_WORDS, slide=parked)

    try:
        raw = llm_client._call_openrouter_text(
            system, user, temperature=0.5, max_tokens=400)
    except Exception as exc:
        log.warning("Diagramma izohi olinmadi: %s", exc)
        return ""

    text = _THINK.sub("", str(raw or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip().strip('"').strip()
    words = text.split()
    if len(words) > _GAP_WORDS:
        text = " ".join(words[:_GAP_WORDS]).rstrip(".,;:") + "."
    return text


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def fill_gap(html: str, area: Dict, theme, language: str = "uz") -> str:
    """Slaydning bo'sh yoniga diagramma izohini qo'yadi.

    Slayd qayta chizilmaydi: mavjud joylashuvga tegilmay, bo'sh
    maydonga bitta matn bloki qo'shiladi. Blok `position: fixed`
    bilan qo'yiladi — slayd aynan brauzer oynasi o'lchamida
    (1920x1080) bo'lgani uchun u varaqning o'sha joyiga tushadi.
    Ko'rinishi dizayn tizimidan olinadi: aksent chizig'i va `note`.
    """
    if not area:
        return html
    # Izoh diagramma, jadval yoki ko'rsatkichni tushuntiradi. Ular
    # bo'lmagan varaqda "bo'sh joy" — rasm kartochkasi yoki ataylab
    # qoldirilgan nafas; u yerga matn qo'yilsa kartochka ustiga
    # chiqib qolardi.
    section = _SECTION.search(html)
    visual = section.group(0) if section else html
    if not re.search(r"<svg\b|<table\b|\bkpi\b", visual, re.IGNORECASE):
        return html

    pad = 48
    x = float(area.get("x") or 0) + pad
    y = float(area.get("y") or 0)
    width = float(area.get("w") or 0) - pad * 2
    height = float(area.get("h") or 0)
    if width < 220 or height < 120:
        return html

    text = explain_visual(html, theme, language)
    if not text:
        return html

    block = (
        f'<div style="position:fixed;left:{x:.0f}px;top:{y:.0f}px;'
        f'width:{width:.0f}px;height:{height:.0f}px;display:flex;'
        'flex-direction:column;justify-content:center;gap:24px">'
        '<div class="rule"></div>'
        f'<p class="note">{_escape(text)}</p></div>'
    )

    lower = html.lower()
    cut = lower.rfind("</body>")
    if cut < 0:
        return html + block
    return html[:cut] + block + html[cut:]


def _restore(html: str, theme) -> str:
    """Qayta chizilgan slaydning rasmlarini joyiga qo'yadi.

    Model belgini tushirib qoldirsa yoki yangi `<img>` qo'shsa, u
    brauzerda buzuq rasm belgisi bo'lib, alt matni bilan slaydga
    tushardi. Shuning uchun ikonkalar qaytadan qo'yiladi, egasiz
    qolgan `<img>` esa o'sha o'lchamdagi rangli blokka aylanadi.
    """
    try:
        from . import html_images

        page = html_images.apply_icons([html], theme)[0][0]
        return html_images.sweep([page], theme)[0]
    except Exception as exc:
        log.warning("Tuzatilgan slayd rasmlari tiklanmadi: %s", exc)
        return html


def _write_chunk(system: str, user: str, count: int) -> List[str]:
    try:
        # Birorta ham yopilgan slayd bo'lmagan javob (filtr kesgan, token
        # chegarasida uzilgan) keyingi modelga o'tkaziladi.
        raw = llm_client._call_openrouter_text(
            system, user, temperature=0.75, max_tokens=4200 * count,
            accept=lambda text: bool(split_slides(text)))
    except llm_client.NoCredits:
        raise
    except Exception as exc:
        log.error("Slayd bo'lagi olinmadi: %s", exc)
        return []
    return split_slides(raw)


def _plain_slide(topic: str, brief: str, number: int, total: int,
                 language: str = "uz", author: str = "") -> str:
    """Hech bir model HTML slayd bermaganda — oddiy ro'yxatli slayd.

    Muqovaga AI kerak emas: u mavzu va muallifdan yig'iladi.
    """
    if number == 1:
        note = (f'<p class="note">{_escape(_CREDIT_LABEL.get(language, _CREDIT_LABEL["uz"]))}: '
                f'{_escape(author)}</p>') if author else ""
        return ('<section class="slide dark"><div class="body">'
                f'<h1 class="title big">{_escape(topic)}</h1>'
                f'<div class="rule"></div>{note}</div></section>')
    T = prompts.get(language).PLAIN
    kind = T["conclusion"] if number == total else T["content"]
    prompt = prompts.fill(T["prompt"], topic=topic, n=number, kind=kind, brief=brief,
                          target=prompts.target(language))
    try:
        data = llm_client._call_openrouter(T["system"], prompt, temperature=0.5, max_tokens=1500)
    except llm_client.NoCredits:
        raise
    except Exception as exc:
        log.error("%d-slayd zaxira yo'li bilan ham yozilmadi: %s", number, exc)
        return ""
    if not isinstance(data, dict):
        data = {}
    title = str(data.get("title") or brief).strip()
    items = []
    for point in data.get("points") or []:
        if not isinstance(point, dict):
            continue
        text = str(point.get("text") or "").strip()
        if not text:
            continue
        key = str(point.get("key") or "").strip()
        lead = f"<b>{_escape(key)}.</b> " if key else ""
        items.append('<div class="item"><span class="item-dot"></span>'
                     f'<div class="item-text">{lead}{_escape(text)}</div></div>')
    if len(items) < 2:
        log.error("%d-slayd zaxira javobi bo'sh", number)
        return ""
    log.warning("%d-slayd zaxira yo'li bilan yozildi", number)
    return ('<section class="slide"><div class="head">'
            f'<h2 class="title">{_escape(title)}</h2><div class="rule"></div>'
            '</div><div class="body"><div class="list">'
            + "".join(items[:5]) + '</div></div></section>')
