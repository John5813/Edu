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
    ("bayonot", "bitta yirik fikr sahifa markazida, atrofida bo'sh joy"),
    ("ajratkich", "to'q aksent fon, ustida oq yirik sarlavha va bitta "
                  "jumla — bo'limlar orasidagi nafas"),
    ("rasmli", "butun slaydni yoki yarmini egallagan fotosurat, ustida "
               "yoki yonida qisqa matn"),
    ("ikki_ustun", "chapda matn, o'ngda vizual (SVG diagramma, sxema yoki "
                   "geometrik kompozitsiya)"),
    ("korsatkichlar", "2-4 ta juda yirik raqam, har birining ostida qisqa "
                      "izoh"),
    ("jarayon", "o'qlar bilan bog'langan qadamlar qatori"),
    ("vaqt_oqi", "gorizontal chiziq ustidagi sana va voqealar"),
    ("qiyoslash", "ikki ustunli qiyos yoki 2×2 matritsa (masalan SWOT)"),
    ("jadval", "HTML jadval — sarlavha qatori aksent rangda"),
    ("diagramma", "sahifani egallagan SVG diagramma: chiziqli, ustunli, "
                  "donut, voronka yoki radar; yonida qisqa xulosa"),
    ("tuzilma", "qutilar va ularni bog'lovchi chiziqlar — ierarxiya yoki "
                "tarkib sxemasi"),
    ("iqtibos", "yirik tirnoq belgisi, kursiv matn, muallif qatori"),
    ("kartalar", "3-6 ta bir xil o'lchamdagi karta, har birida sarlavha, "
                 "bir-ikki qator matn va oddiy SVG belgi"),
    ("yakun", "2-3 ta asosiy xulosa va yakuniy rahmat qatori"),
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
   Fotosurat, tashqi havola, emoji — yo'q.
4. Diagrammani O'ZING chizma. `<svg>` yozma. Faqat `.chart` blokiga
   ma'lumot ber — qolganini tizim chizadi.
5. Bir varaqqa qancha sig'ishining YUQORI chegarasi (bu talab
   emas — shuncha bo'lishi kerak emas, shundan OSHMASIN):
   - kartochka 4 tadan oshmasin, izohi 2 gapdan oshmasin;
   - ro'yxat bandi 5 tadan oshmasin;
   - ko'rsatkich 4 tadan oshmasin;
   - vaqt o'qida 5 tadan ortiq to'xtash bo'lmasin.
   Varaq 1920x1080 — bundan ko'pi sig'maydi va kesiladi.
6. BO'SH BLOK QOLDIRMA. Har kartochkaning sarlavhasi ham, izohi ham
   bo'lsin. Mazmun topolmasang kartochkani butunlay olib tashla va
   qolganlarini kamroq ustunga joyla.
7. BLOKNI MAZMUN TANLAYDI, xilma-xillik emas. Ketma-ketlik bo'lsa
   qadam yoki vaqt o'qi, tasnif bo'lsa jadval yoki kartochka,
   taqqoslash bo'lsa ikki ustun, kuchli fikr bo'lsa bayonot.
   Ikki slayd ketma-ket bir xil shaklda bo'lishi MUMKIN. Blokni
   "boshqacha bo'lsin" deb almashtirmang.
8. RAQAMNI O'YLAB TOPMANG. Foiz, statistika, o'sish sur'ati va
   kelajak prognozi faqat siz ishonadigan HAQIQIY ma'lumot bo'lsa
   yoziladi. Ishonchingiz komil bo'lmasa diagramma ham,
   ko'rsatkich ham qo'ymang — o'sha fikrni matn bilan ayting.
   Mavzu raqam talab qilmasa, butun taqdimotda birorta diagramma
   bo'lmasligi ham mumkin va bu TO'G'RI.
9. Bir slaydda bir xil matnni ikki marta yozma.
10. Yorliqlar qisqa: kartochka sarlavhasi 1-4 so'z, vaqt o'qidagi
   izoh bir jumla.
11. Birinchi slayd — MUQOVA, oxirgisi — xulosa. Mavzu bir necha
   qismga bo'linsa, qismlar orasiga AJRATKICH (`slide dark`)
   qo'ying va uni mavzuning o'z bo'lim nomi bilan ataang.
12. Matn haqiqiy va aniq bo'lsin: nom, misol, manba bilan. "Lorem
   ipsum", "Matn shu yerda" kabi o'rin egallovchi yozma.
13. SARLAVHADA VA'DA QILINGAN NARSA SLAYDDA BO'LSIN. Sarlavhada
   "misollar" desangiz — ishlangan misol bo'lsin; "formula"
   desangiz — formula ko'rinsin; "qiyoslash" desangiz — ikki tomon
   yonma-yon tursin. Va'dani bajarolmasangiz sarlavhani
   o'zgartiring.
14. Formula BO'LSA, uni matn ichiga tiqmang: `formula` bloki bor,
   u yirik va o'qiladigan chiqadi. Formulani LaTeX bilan yozing —
   tizim uni belgilarga o'giradi. Mavzuda formula yo'q bo'lsa,
   bu blok ishlatilmaydi."""


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
        "yoki kartochka, taqqoslash bo'lsa ikki ustun, kuchli fikr "
        "bo'lsa bayonot. Xilma-xillik uchun blok almashtirmang — ikki "
        "slayd ketma-ket bir xil shaklda bo'lishi MUMKIN, agar mazmun "
        "shuni talab qilsa.",
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
    if author and start == 1:
        parts.append(f"Muqovada muallif: {author}")
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
            prompt, temperature=0.6, max_tokens=300 + 90 * count)
        raw = data.get("slides") or []
        hint = data.get("fan") or ""
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
_SAFE_CATEGORIES = ("kartalar", "bayonot", "ikki_ustun", "reja",
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


def build_pages(bodies: List[str], theme) -> List[str]:
    """Slayd mazmunlarini chizishga tayyor HTML hujjatlarga aylantiradi.

    Diagrammalar shu yerda chiziladi: model faqat ma'lumot beradi,
    SVG ni kod yasaydi — shunda ustunning balandligi ham, yozuvning
    o'rni ham har safar to'g'ri chiqadi.
    """
    drawn = [deck_charts.draw(deck_math.render(body), theme)
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
    return [deck_style.page(theme, body) for body in drawn]


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

        slides.extend(chunk[:count])
        used.extend(item["brief"] for item in outline[start - 1:start - 1 + count])
        start += count

    log.info("HTML slaydlar tayyor: %d ta", len(slides))
    if not slides:
        raise RuntimeError("AI birorta to'liq slayd qaytarmadi")
    return build_pages(slides, theme)


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
    """Joylashuvi buzilgan slaydni qayta yozdiradi.

    Modelga butun hujjat emas, faqat slaydning MAZMUNI yuboriladi:
    CSS o'zgarmaydi, shuning uchun uni so'rovga qo'shish bekorga
    token sarflash bo'lardi. Javob ham mazmun bo'lib keladi va
    o'sha dizayn tizimiga qaytadan o'raladi.
    """
    if not problems:
        return html

    match = _SECTION.search(html)
    if not match:
        return html
    body = match.group(0)

    listed = "\n".join(f"- {item}" for item in problems)
    user = (
        "Quyidagi slayd brauzerda noto'g'ri joylashdi. Topilgan "
        f"kamchiliklar:\n{listed}\n\n"
        "Shu slaydni QAYTA yoz. Mazmunini saqla, lekin:\n"
        "- mazmun ko'p bo'lsa qisqart: kartochka yoki band sonini "
        "kamaytir, izohlarni kaltaroq qil;\n"
        "- bo'sh kartochka va bo'sh blok qoldirma;\n"
        "- bir matnni ikki marta yozma;\n"
        "- faqat tanish sinf nomlaridan foydalan, yangi uslub yozma.\n\n"
        "Javobda faqat bitta <section class=\"slide\"> ... </section> "
        "bo'lsin.\n\nSlayd:\n" + body
    )

    try:
        raw = llm_client._call_openrouter_text(
            shell_rules(theme, language), user,
            temperature=0.4, max_tokens=2600)
    except Exception as exc:
        log.error("Slaydni tuzatib bo'lmadi: %s", exc)
        return html

    fixed = split_slides(raw)
    if not fixed:
        return html
    return build_pages(fixed[:1], theme)[0]


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
        raw = llm_client._call_openrouter_text(
            system, user, temperature=0.75, max_tokens=4200 * count)
    except Exception as exc:
        log.error("Slayd bo'lagi olinmadi: %s", exc)
        return []
    return split_slides(raw)
