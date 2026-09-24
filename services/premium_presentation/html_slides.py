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

from . import (deck_charts, deck_math, deck_shape, deck_style,
               llm_client)

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


_LANGUAGE = {
    "ru": "русском языке",
    "en": "in English",
    "uz": "o'zbek tilida",
}

# Joylashuv kategoriyalari — qat'iy shablon emas, lug'at. AI ulardan
# tanlaydi va o'zicha aralashtiradi.
_CATEGORIES = (
    ("muqova", "katta sarlavha, ostida ingichka aksent chiziq, pastda "
               "muallif va fan qatori"),
    ("reja", "01, 02, 03 deb raqamlangan kartalar — ustun yoki panjara "
             "ko'rinishida, har birida qisqa izoh"),
    ("matn_rasm", "bir tomonda fikrni ochgan matn, bir tomonda rasm "
                  "(rasm chiqmasa o'rnida qo'shimcha matn)"),
    ("ikki_ustun", "chapda matn, o'ngda kartalar yoki jadval"),
    ("korsatkichlar", "2-4 ta juda yirik raqam, har birining ostida qisqa "
                      "izoh"),
    ("jarayon", "o'qlar bilan bog'langan qadamlar qatori"),
    ("vaqt_oqi", "gorizontal chiziq ustidagi sana va voqealar"),
    ("qiyoslash", "ikki ustunli qiyos yoki 2×2 matritsa (masalan SWOT)"),
    ("jadval", "HTML jadval — sarlavha qatori aksent rangda"),
    ("diagramma", "faqat diagramma (chiziqli, ustunli yoki halqa) va uni "
                  "tushuntiradigan matn"),
    ("tuzilma", "qutilar va ularni bog'lovchi chiziqlar — ierarxiya yoki "
                "tarkib sxemasi"),
    ("iqtibos", "yirik tirnoq belgisi, kursiv matn, muallif qatori"),
    ("formula", "tushunchaning formulasi yirik, ostida belgilar izohi va "
                "u nimani hisoblashi"),
    ("misol", "masala sharti, qadamma-qadam yechim va javob"),
    ("kartalar", "bir xil o'lchamdagi kartalar, har birida sarlavha va "
                 "bir-ikki gaplik izoh"),
    ("yakun", "faqat xulosa matni — rahmat va savollar qatorisiz"),
)

CATEGORY_KEYS = tuple(key for key, _ in _CATEGORIES)


def catalogue_text() -> str:
    return "\n".join(f"  {key} — {note}" for key, note in _CATEGORIES)


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
    target = _LANGUAGE.get(language, _LANGUAGE["uz"])
    return f"""Sen taqdimot muallifi va kompozitorisan. Matnni {target}
yozasan.

Dizayn TAYYOR: shrift, rang, chet, oraliq va kartochkaning ko'rinishi
CSS da qat'iy berilgan. Sen CSS yozmaysan, rang tanlamaysan, o'lcham
bermaysan. Sen faqat SLAYD MAZMUNINI va uning tuzilishini yozasan —
tayyor bloklardan foydalanib.

{deck_style.BLOCKS}

IKONKA nomlari faqat shu ro'yxatdan olinadi:
{icon_list()}

QAT'IY QOIDALAR:
1. Javobda faqat `<section class="slide">` ... `</section>` bo'ladi.
   Har slayddan keyin alohida qatorda {MARKER} yoziladi.
2. `<style>`, `style="..."`, `<script>`, `<html>`, `<head>`, `<body>`
   YOZMA. Rang, shrift, piksel, `width`, `height`, `margin`, `padding`
   — hech qaysisi yozilmaydi. Faqat yuqoridagi sinf nomlari.
3. `<img>` faqat ikonka uchun: `<img class="ikon" data-icon="NOM" alt="">`.
   Rasm faqat MATN VA RASM blokidagi `rasm` orqali so'raladi.
   Tashqi havola, emoji — yo'q.
4. Diagrammani O'ZING chizma. `<svg>` yozma. Faqat `.chart` blokiga
   ma'lumot ber — qolganini tizim chizadi.
5. Bir varaqqa qancha sig'ishining YUQORI chegarasi (bu talab
   emas — shuncha bo'lishi kerak emas, shundan OSHMASIN):
   - kartochka 4 tadan oshmasin, izohi 2 gapdan oshmasin;
   - ro'yxat bandi 5 tadan oshmasin;
   - ko'rsatkich 4 tadan oshmasin; har birining ostidagi izoh
     yolg'iz yorliq emas, raqamning ma'nosi va sababini
     tushuntiruvchi 1-2 to'liq gap bo'lsin;
   - vaqt o'qida 5 tadan ortiq to'xtash bo'lmasin.
   Varaq 1920x1080 — bundan ko'pi sig'maydi va kesiladi.
6. BO'SH BLOK QOLDIRMA. Har kartochkaning sarlavhasi ham, izohi ham
   bo'lsin. Mazmun topolmasang kartochkani butunlay olib tashla va
   qolganlarini kamroq ustunga joyla. Slayd sarlavha va bitta
   jumladan iborat bo'lib qolmasin — sarlavhadagi fikr slaydda
   ochilsin; fikr bitta bo'lsa MATN VA RASM bloki bor.
7. BLOKNI MAZMUN TANLAYDI, xilma-xillik emas. Ketma-ketlik bo'lsa
   qadam yoki vaqt o'qi, tasnif bo'lsa jadval yoki kartochka,
   taqqoslash bo'lsa ikki ustun.
   Ikki slayd ketma-ket bir xil shaklda bo'lishi MUMKIN. Blokni
   "boshqacha bo'lsin" deb almashtirmang.
8. RAQAMNI O'YLAB TOPMANG. Foiz, statistika, o'sish sur'ati va
   kelajak prognozi faqat siz ishonadigan HAQIQIY ma'lumot bo'lsa
   yoziladi. Ishonchingiz komil bo'lmasa diagramma ham,
   ko'rsatkich ham qo'ymang — o'sha fikrni matn bilan ayting.
   Mavzu raqam talab qilmasa, butun taqdimotda birorta diagramma
   bo'lmasligi ham mumkin va bu TO'G'RI. Ko'rsatkich (kpi) raqami
   izohida uning manbasi va yili aytiladi (masalan: Statistika
   agentligi, 2024) — manbasini ayta olmaydigan raqam yozilmaydi.
9. Bir slaydda bir xil matnni ikki marta yozma.
10. Yorliqlar qisqa: kartochka sarlavhasi 1-4 so'z, vaqt o'qidagi
   izoh bir jumla.
11. Birinchi slayd — MUQOVA: unda muallif ismi, fan va yil
   YOZILMAYDI (ismni tizim o'zi qo'yadi). Oxirgisi — XULOSA: unda faqat xulosa
   matni bo'ladi, "Rahmat", "E'tiboringiz uchun rahmat", "Savollar"
   yozilmaydi va ular uchun alohida varaq ham yo'q. Xulosada rasm
   bloki ishlatilmaydi. Taqdimot bo'limlarga
   ajratilmaydi: faqat bo'lim nomi yozilgan alohida varaq bo'lmaydi,
   har varaq mazmun beradi.
12. Matn haqiqiy va aniq bo'lsin: nom, misol, manba bilan. "Lorem
   ipsum", "Matn shu yerda" kabi o'rin egallovchi yozma.
13. SARLAVHADA VA'DA QILINGAN NARSA SLAYDDA BO'LSIN. Sarlavhada
   "misollar" desangiz — ishlangan misol bo'lsin; "formula"
   desangiz — formula ko'rinsin; "qiyoslash" desangiz — ikki tomon
   yonma-yon tursin; ko'plikda "olimlar", "usullar" desangiz —
   bittasi emas, bir nechtasi bo'lsin (bitta iqtibosli varaqni
   "Mashhur olimlar" deb atamang). Va'dani bajarolmasangiz sarlavhani
   o'zgartiring.
14. Tushuncha formula bilan ta'riflansa (o'rtacha, dispersiya,
   korrelatsiya koeffitsiyenti, tezlanish, foiz stavkasi...), o'sha
   tushuncha kiritilgan slaydda uning formulasi `formula` blokida
   ko'rsatiladi — so'z bilan tasvirlab qo'yish yetmaydi. Formulani
   matn ichiga tiqmang va LaTeX bilan yozing — tizim uni belgilarga
   o'giradi. Mavzuda formula yo'q bo'lsa, bu blok ishlatilmaydi.
15. Qonun, farmon, qaror, nutq yoki dastur matnini so'zma-so'z
   KO'CHIRMANG. Hujjatning nomi, raqami va yilini ayting, mazmunini
   o'z so'zlaringiz bilan qisqa bayon qiling.
16. Imlo adabiy tilda: kirish qismi "Kirish" deb yoziladi
   ("Kiritish" emas), atamalar fan darsliklaridagidek."""


def _user_prompt(topic: str, start: int, count: int, total: int,
                 outline: List[Dict], used: List[str], level: int,
                 source: str, preferences: str, author: str,
                 family: str = "umumiy") -> str:
    depth = {
        1: "Tinglovchi — maktab o'quvchisi: sodda til, kundalik misollar.",
        2: "Tinglovchi — talaba: akademik, lekin ravon til.",
        3: "Tinglovchi — mutaxassis: atamalar, raqamlar, manbalar.",
    }.get(level, "Tinglovchi — talaba: akademik, lekin ravon til.")

    parts = [
        f'Mavzu: "{topic}"',
        f"Taqdimot jami {total} slayddan iborat.",
        f"Hozir {start}-slayddan boshlab {count} ta slayd kerak.",
        depth,
        deck_shape.guidance(family),
        "SHAKL MAZMUNDAN KELIB CHIQSIN. Blokni fikrga qarab tanlang: "
        "ketma-ketlik bo'lsa qadam yoki vaqt o'qi, tasnif bo'lsa jadval "
        "yoki kartochka, taqqoslash bo'lsa ikki ustun. Xilma-xillik "
        "uchun blok almashtirmang — ikki slayd ketma-ket bir xil "
        "shaklda bo'lishi MUMKIN, agar mazmun shuni talab qilsa.",
    ]

    if outline:
        lines = []
        for index, item in enumerate(outline, 1):
            if start <= index < start + count:
                mark = "  →"
            else:
                mark = "   "
            lines.append(f"{mark} {index}. [{item['category']}] {item['brief']}")
        parts.append("Taqdimot rejasi (→ bilan belgilangani hozir "
                     "yoziladi):\n" + "\n".join(lines))
    if used:
        parts.append("Oldingi slaydlarda ochilgan fikrlar (ularni qayta "
                     "aytmang): " + "; ".join(used[-5:]))
    if preferences:
        parts.append(f"Mijoz istagi: {preferences}")
    if source:
        parts.append("Mijoz bergan material (shundan foydalanib yoz):\n"
                     + source[:4000])

    return "\n\n".join(parts)


# ────────────────────────────────────────────────────────────── reja

def plan_outline(topic: str, count: int, language: str,
                 level: int = 2) -> Dict:
    """Har slayd uchun bir qatorli mazmun va joylashuv kategoriyasi.

    Slaydlar bo'laklab yoziladi va har bo'lak avvalgisining HTML'ini
    ko'rmaydi. Reja oldindan tuzilsa, har bo'lak o'z o'rnini biladi va
    bir mavzu ikki slaydda takrorlanmaydi.
    """
    prompt = (
        f'Mavzu: "{topic}"\n\n'
        f"Shu mavzuda {count} slaydli taqdimot rejasini tuz. Har slayd "
        "uchun bir qatorli mazmun va unga mos joylashuv kategoriyasini "
        "ayt.\n\n"
        "Kategoriyalar:\n" + catalogue_text() + "\n\n"
        "Birinchisi — muqova, oxirgisi — yakun. Qolganlari mavzuni "
        "MANTIQIY ketma-ketlikda ochsin: nimadan boshlash, nima bilan "
        "davom etish va qayerda yakunlash kerakligini mavzuning o'zi "
        "aytadi.\n"
        "Kategoriyani xilma-xillik uchun emas, MAZMUNGA QARAB tanlang. "
        "Ikki slayd ketma-ket bir xil kategoriyada bo'lishi mumkin. "
        "Mavzu raqam talab qilmasa, diagramma va statistika "
        "kategoriyalarini umuman ishlatmang.\n\n"
        "Shuningdek mavzu qaysi oilaga tegishli ekanini ayting: "
        + deck_shape.names() + "\n\n"
        f"Matn {_LANGUAGE.get(language, _LANGUAGE['uz'])}.\n"
        'Faqat JSON: {"fan": "...", '
        '"slides": [{"brief": "...", "category": "..."}]}'
    )
    try:
        data = llm_client._call_openrouter(
            "Sen taqdimot rejasini tuzasan. Faqat JSON qaytar.",
            prompt, temperature=0.6, max_tokens=600 + 160 * count)
        raw = data.get("slides") or []
        hint = data.get("fan") or ""
    except llm_client.NoCredits:
        raise
    except Exception as exc:
        log.warning("Reja olinmadi, kategoriyalar o'zimiz tanlaymiz: %s", exc)
        raw, hint = [], ""

    family = deck_shape.of(topic, hint)
    log.info("Mavzu oilasi: %s", family)

    outline: List[Dict] = []
    for index in range(count):
        item = raw[index] if index < len(raw) and isinstance(raw[index], dict) else {}
        brief = str(item.get("brief") or "").strip()
        category = str(item.get("category") or "").strip().lower()
        if category not in CATEGORY_KEYS:
            category = _fallback_category(index, count)
        if index == 0:
            category = "muqova"
        elif index == count - 1:
            category = "yakun"
        elif category in ("muqova", "yakun"):
            category = _fallback_category(index, count)
        outline.append({"brief": brief or topic, "category": category})

    # Ilgari bu yerda ketma-ket takrorlangan kategoriya kod darajasida
    # almashtirilardi. Bu xato edi: mantiqan ketma-ket kelishi kerak
    # bo'lgan ikki ro'yxat sun'iy ravishda ajratilib, taqdimotning
    # fikri uzilardi. Endi takror ruxsat etiladi — shaklni mazmun
    # tanlaydi.
    return {"family": family, "slides": outline}


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


def build_pages(bodies: List[str], theme) -> List[str]:
    """Slayd mazmunlarini chizishga tayyor HTML hujjatlarga aylantiradi.

    Diagrammalar shu yerda chiziladi: model faqat ma'lumot beradi,
    SVG ni kod yasaydi — shunda ustunning balandligi ham, yozuvning
    o'rni ham har safar to'g'ri chiqadi.
    """
    drawn = [deck_charts.draw(
        _half_charts(deck_math.render(
            _whiten_icons(_auto_icons(_decorate(body))))),
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
                 progress_cb: Optional[Callable] = None) -> List[str]:
    """Butun taqdimotni HTML hujjatlar ro'yxati qilib qaytaradi."""
    slide_count = max(4, int(slide_count or 8))
    plan = plan_outline(topic, slide_count, language, level)
    outline = plan["slides"]
    family = plan["family"]
    system = shell_rules(theme, language)

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
                            family)
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
                                  author, family)
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
            if 1 < number and _thin(body):
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
    return build_pages(slides, theme)


# Muqovadagi "Tayyorladi: ... | Fan: ... | 2026" qatori. Model uni namunadan
# ko'chirib, ism, fan va yilni o'zi o'ylab topardi — mijoz ism kiritmagan
# bo'lsa ham muqovada begona ism turardi. Endi bunday qator kod bilan
# olib tashlanadi, ism esa faqat mijoz kiritgan bo'lsa qo'yiladi.
_CREDIT_LABEL = {"uz": "Tayyorladi", "ru": "Подготовил(а)", "en": "Prepared by"}
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


def _thicken(body: str, system: str, theme) -> str:
    """Yupqa varaqni MATN VA RASM varag'iga aylantiradi."""
    user = (
        "Quyidagi slayd faqat sarlavha va bir-ikki jumladan iborat "
        "(yoki faqat bo'lim nomi yozilgan ajratkich). Bunday varaq "
        "taqdimotda kerak emas.\n\n"
        "Shu slaydni MATN VA RASM bloki bilan qayta yozing: sarlavhadagi "
        "fikr o'sha qolsin, chap tomonda u ro'yxat bilan ochilsin, o'ng "
        "tomonda `rasm` bloki (ichida rasm chiqmasa turadigan qo'shimcha "
        "matn) bo'lsin. Oddiy `<section class=\"slide\">` — `dark` va "
        "`title big` emas.\n\n"
        "Javobda faqat bitta <section class=\"slide\"> ... </section> "
        "bo'lsin.\n\nSlayd:\n" + body
    )
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

    listed = "\n".join(f"- {item}" for item in problems)
    user = (
        "Bu slaydni siz yozgansiz. Brauzerda ochilganda quyidagi xatolar "
        f"topildi (« » ichida — xato turgan matn):\n{listed}\n\n"
        "SHU SLAYDNI QAYTARING — yangisini yozmang. Faqat xato "
        "ko'rsatilgan joylarni tuzating. Qolgan hamma narsa — "
        "`<section>` sinfi, sarlavha, bloklar, ularning tartibi, "
        "sinf nomlari va matnlar — o'zgarmasin.\n\n"
        "Tuzatish yo'llari:\n"
        "- matn qutisiga sig'magan yoki varaqdan chiqib ketgan bo'lsa — "
        "o'sha matnni qisqartiring (ma'nosini saqlab); faqat bu yetmasa "
        "o'sha blokdagi bitta band yoki kartochkani olib tashlang;\n"
        "- matn ustiga matn tushgan bo'lsa — ikkalasidan biri keraksiz "
        "bo'lsa o'chiring, aks holda ikkalasini qisqartiring;\n"
        "- matn ikki marta yozilgan bo'lsa — nusxasini o'chiring;\n"
        "- varaqda katta bo'sh joy qolgan bo'lsa — mavjud izohlarni "
        "to'liqroq yozing, yangi blok qo'shmang.\n\n"
        "Javobda faqat bitta <section class=\"slide\"> ... </section> "
        "bo'lsin.\n\nSlayd:\n" + source
    )

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
    reason = _rewritten(source, fixed[0])
    if reason:
        log.warning("Tuzatish qabul qilinmadi — slayd qayta yozilgan: %s",
                    reason)
        return html
    return build_pages(fixed[:1], theme)[0]


# Slaydning tuzilishini belgilaydigan bloklar. Tuzatishda ularning
# biri yo'qolsa yoki yangisi paydo bo'lsa — bu tuzatish emas.
_BLOCK_CLASSES = ("cols", "steps", "list", "timeline", "split", "formula",
                  "misol", "chart", "kpi", "quote", "ikon-row", "lead",
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


def _rewritten(before: str, after: str) -> str:
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
        if kept < 0.55:
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
    target = _LANGUAGE.get(language, _LANGUAGE["uz"])
    match = _SECTION.search(html)
    parked = _park_images(match.group(0) if match else html)[0]
    system = ("Sen taqdimot matnlarini yozadigan muharrirsan. "
              f"Javobni {target} yozasan.")
    user = (
        "Quyida taqdimot slaydining mazmuni berilgan. Undagi "
        "diagramma, jadval yoki ko'rsatkichlarni tushuntiruvchi "
        f"2-3 gaplik matn yoz ({_GAP_WORDS} so'zdan oshmasin): raqamlar "
        "nimani bildiradi, nega shunday va undan qanday xulosa "
        "chiqadi.\n"
        "Slaydda allaqachon yozilgan gaplarni takrorlama. Sarlavha, "
        "ro'yxat belgisi, HTML teg va qo'shtirnoq yozma — faqat "
        "tayyor matnning o'zini ber.\n\nSlayd:\n" + parked
    )

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
    target = _LANGUAGE.get(language, _LANGUAGE["uz"])
    kind = "xulosa" if number == total else "mazmun"
    prompt = (
        f'Mavzu: "{topic}". Taqdimotning {number}-slaydi ({kind}): {brief}\n\n'
        f"Matn {target}. Hujjat yoki nutq matnini so'zma-so'z ko'chirmang, "
        "o'z so'zlaringiz bilan yozing.\n"
        'Faqat JSON: {"title": "slayd sarlavhasi (2-7 so\'z)", '
        '"points": [{"key": "kalit so\'z", "text": "bir-ikki to\'liq gap"}]} '
        "— 3 tadan 5 tagacha band."
    )
    try:
        data = llm_client._call_openrouter(
            "Sen taqdimot slaydi matnini yozasan. Faqat JSON qaytar.",
            prompt, temperature=0.5, max_tokens=1500)
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
