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

from services import timeframe

from . import llm_client

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
    """Har slaydga baravar tegishli QOBIQ qoidalari.

    Bu yerda slaydning ichi emas, tashqi shartlari aytiladi: o'lcham,
    shrift, rang, tashqi faylning yo'qligi. Ichini AI o'zi chizadi.
    """
    target = _LANGUAGE.get(language, _LANGUAGE["uz"])
    icons = icon_list()
    return f"""Sen professional taqdimot dizaynerisan. Sen HTML/CSS/SVG yozasan.
Kodingiz brauzerda {SLIDE_W_PX}×{SLIDE_H_PX} o'lchamda suratga olinadi va
PowerPoint slaydiga aylanadi — shuning uchun quyidagi QOBIQ shartlari
qat'iy.

QOBIQ:
1. Har slayd — alohida, TO'LIQ HTML hujjat: <!DOCTYPE html> dan
   </html> gacha.
2. body: aniq {SLIDE_W_PX}px × {SLIDE_H_PX}px, margin 0, overflow hidden,
   ichki padding 72-96px. box-sizing: border-box.
3. Faqat ichki <style>. Tashqi CSS fayl, Google Fonts, JS kutubxona,
   tashqi rasm havolasi — YO'Q. Hammasi bitta faylda o'zi yetarli.
4. Shrift faqat shu ikkisidan biri:
   font-family: {FONT_STACK};
   font-family: {SERIF_STACK};
   Boshqasini yozsang slayd PowerPointda boshqacha joylashadi.
   Qalinlikni font-weight bilan bering (300-800).
5. Rasm o'rniga SVG yoki CSS bilan chiz. <img>, tashqi ikonka, emoji
   shrifti ishlatma. Belgi kerak bo'lsa — inline SVG.
6. Matn KESILMASIN: text-overflow, ellipsis, qat'iy height bilan
   overflow yashirish — taqiqlanadi. Matn uzun bo'lsa shriftni
   kichraytir yoki blokni kengaytir.
7. Bo'sh joy egasi ("Lorem ipsum", "Matn shu yerda") qoldirma. Biror
   blokka mazmun topolmasang — o'sha blokni butunlay olib tashla.
8. Slayd chetiga matn yopishmasin: hech bir element body chetidan
   48px dan yaqin bo'lmasin.
9. Slayd PowerPointda TAHRIRLANADI: har matn bo'lagi o'z elementida
   tursin. Bitta <p> ichiga <br> bilan uch xil fikrni tiqma — har biri
   alohida element bo'lsin. Matnni <span> ichida rangga bo'lib
   tashlama: bir gap — bir element.
10. Matn ustiga matn qo'yma (absolute joylashuv bilan ham). Bloklarni
   flex yoki grid bilan yonma-yon qo'y.
11. Mazmun BUTUN BALANDLIKNI egallasin. body ni shunday qil:
   display:flex; flex-direction:column; height:1080px;
   va bo'shliqni bloklar orasiga taqsimla (gap yoki
   justify-content:space-between). Hamma narsa yuqoriga to'planib,
   pastki yarmi bo'sh qolmasin.
12. position:absolute dan iloji boricha qochning; ishlatsangiz ham
   manfiy o'rin (top:-40px, margin-top:-...) BERMANG va element
   ota-onasidan chiqib ketmasin. Vaqt o'qi (timeline) kabi narsalarda
   kartochkalarni chiziqning OSTIGA oddiy flex bilan qo'ying.
13. Diagramma yozuvlari (izoh, legend, qiymat) ustunlar yoki
   chiziqlar USTIGA tushmasin — ular uchun alohida joy ajrating.
14. Bezak uchun shaffoflik (opacity, rgba) o'rniga TAYYOR och rangni
   yozing: PowerPointda shaffoflik boshqacha chiqadi.

RANG TIZIMI (hamma slaydda AYNAN shu ranglar):
  aksent:        #{theme.accent}
  to'q aksent:   #{theme.band}
  yumshoq fon:   #{theme.accent_soft}
  sahifa foni:   #{theme.background}
  sarlavha matn: #{theme.heading}
  tana matn:     #{theme.body}
  ikkilamchi:    #{theme.muted}
  to'q fon ustidagi matn: #{theme.invert}
Diagrammalarda shu ranglardan foydalaning: {", ".join("#" + c for c in theme.chart[:5])}

TIPOGRAFIKA:
  slayd sarlavhasi 52-72px, bo'lim sarlavhasi 30-40px,
  tana matn 22-28px, izoh 18-20px. Qalin va ingichka qalinlikni
  aralashtir — ierarxiya ko'rinsin.

FOTOSURAT (majburiy):
Rasm kerak joyga shunday belgi qo'y — `src` yozma, uni tizim o'zi
to'ldiradi:

  <img data-prompt="wide documentary photograph of ..., natural light"
       class="photo" alt="">

- `data-prompt` INGLIZ tilida, 15-25 so'z, mavzuga aniq mos real
  sahna. Ichida YOZUV so'rama (text, label, sign, caption) — modellar
  harflarni buzib chizadi.
- `src` ni O'ZINGIZ yozmang va tashqi havola bermang: `data-prompt`siz
  `<img>` slaydda buzuq belgi bo'lib qoladi.
- CSS da rasmga o'lcham va `object-fit: cover` ber, kerak bo'lsa
  `border-radius`.
- MUQOVADA albatta bitta katta rasm bo'lsin (butun slaydni yoki
  yarmini egallagan), undan tashqari yana kamida ikkita slaydda rasm
  bo'lsin. Jami uchtadan kam bo'lmasin, oltitadan oshmasin.

IKONKA (tekin, tez — ko'p ishlating):
Kartochka, qadam, ro'yxat bandi va ko'rsatkich yonida ikonka tursin.
Rasmdek belgilanadi, faqat `data-icon` bilan:

  <img data-icon="education" class="ikon" alt="">

- Nom faqat shu ro'yxatdan olinadi:
{icons}
- Rang kerak bo'lsa: `data-icon-color="FFFFFF"` (to'q fon ustida).
  Berilmasa aksent rangida chiqadi.
- CSS da o'lcham bering (48-72px). Ikonkalar bir rangli siluet —
  ularni och fonli doira yoki kvadrat ichiga qo'ysangiz chiroyli
  chiqadi.
- Bir slaydda bir xil ikonkani takrorlamang.

DIZAYN (slaydlar bir-biriga o'xshab ketmasin):
- MUQOVA: butun slaydni egallagan rasm + ustidan to'q parda
  (masalan `background: linear-gradient(...)` yoki to'q rangli qatlam)
  + oq sarlavha. Oq fonli quruq muqova YOZMA.
- Har 3-4 slaydda bitta AJRATKICH slayd: to'q aksent fon
  (#{theme.band}), ustida oq yirik sarlavha va bitta jumla.
- Qolgan slaydlar och fonda, lekin har birida bitta kuchli vizual
  langar bo'lsin: rasm, SVG diagramma, yirik raqam yoki ikonkalar
  qatori. Faqat matndan iborat slayd bo'lmasin.
- SOYA UMUMAN ISHLATILMAYDI: na `box-shadow`, na `text-shadow`, na
  `filter: drop-shadow`. PowerPointda soya chiqmaydi, kodda esa u
  butunlay kesib tashlanadi — yozsangiz shunchaki yo'qoladi.
  Hajm kerak bo'lsa: och fon (#{theme.accent_soft}), 16-20px yumaloq
  burchak va tepasida yoki chapida 4-6px aksent chizig'i.
- Bir slaydda ikkitadan ortiq turli rang ishlatma.
- BIR MATNNI IKKI MARTA YOZMANG. Soya, kontur yoki nur berish uchun
  sarlavhaning ikkinchi nusxasini (`<span>` ichida, `position:absolute`
  bilan yoki `filter: blur` qo'yilgan qatlamda) qo'ymang: brauzerda
  ular ustma-ust tushib bittadek ko'rinadi, PowerPointda esa matn ikki
  marta yozilgan bo'lib chiqadi. Har matn — bitta element, soyasiz.
- Sarlavhaga gradient bermang (`-webkit-background-clip: text`):
  PowerPointda harf rangi yo'qoladi. Oddiy `color` yetarli.

DIAGRAMMA VA KO'RSATKICH:
- Har diagramma yoki ko'rsatkichlar qatoridan keyin 2-3 gaplik IZOH
  bo'lsin: raqam nimani bildiradi, nega shunday, undan qanday xulosa
  chiqadi. Quruq raqam qoldirma.
- Diagramma o'qlarida yozuv bo'lsin; qiymatlar ustun tepasida tursin,
  ustun ichiga kirmasin.
- Ko'rsatkich (KPI) kartochkasida: yirik raqam, ostida nima ekani,
  ostida bir qatorli izoh.

VAQT O'QI uchun aniq usul (eng ko'p shu buziladi):
Gorizontal chiziq chizib, kartochkalarni `position:absolute` bilan
osma. Buning o'rniga: `display:flex` qatori, har ustunda tepada
sana, ostida 14px doira, ostida matn. Chiziqni doiralar qatorining
orqasiga `::before` bilan emas, alohida `div` bilan qo'y.

MAZMUN:
- Matn {target} bo'lsin.
- Har slaydda BITTA asosiy g'oya. O'rtacha 60 so'z — undan ortig'i
  o'qilmaydi.
- Aniq bo'l: raqam, sana, misol. Umumiy gaplardan qoch.
- Diagrammadagi raqamlar mavzuga oid va ishonarli bo'lsin.

{timeframe.year_rule(language)}

CHIQISH FORMATI:
Har slaydni to'liq HTML hujjat qilib yoz va slaydlar orasiga AYNAN shu
qatorni qo'y:
{MARKER}
Boshqa hech qanday izoh, tushuntirish yoki markdown yozma — faqat xom
HTML va ajratuvchi."""


def _user_prompt(topic: str, start: int, count: int, total: int,
                 outline: List[Dict], used: List[str], level: int,
                 source: str, preferences: str, author: str) -> str:
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
        "JOYLASHUV KATEGORIYALARI (tanlab, aralashtirib ishlat — bu "
        "shablon emas, yo'nalish):\n" + catalogue_text(),
        "- Ketma-ket ikki slayd bir xil kategoriyada bo'lmasin.\n"
        "- Butun taqdimotda kamida oltita turli kategoriya ishlatilsin.\n"
        "- Har uch slaydning birida SVG diagramma yoki sxema bo'lsin.\n"
        "- Kategoriya ichida ham har safar yangicha chiz: bir xil "
        "kompozitsiyani takrorlama.",
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
        parts.append("Oldingi slaydlarda ishlatilgan kategoriyalar "
                     "(takrorlama): " + ", ".join(used[-6:]))
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
                 level: int = 2) -> List[Dict]:
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
        "Birinchisi — muqova, oxirgisi — yakun. Ketma-ket ikki slayd bir "
        "xil kategoriyada bo'lmasin, jami kamida oltita turli kategoriya "
        "ishlatilsin. Slaydlar mavzuni bosqichma-bosqich ochsin.\n\n"
        f"Matn {_LANGUAGE.get(language, _LANGUAGE['uz'])}.\n"
        'Faqat JSON: {"slides": [{"brief": "...", "category": "..."}]}'
    )
    try:
        data = llm_client._call_openrouter(
            "Sen taqdimot rejasini tuzasan. Faqat JSON qaytar.",
            prompt, temperature=0.6, max_tokens=300 + 90 * count)
        raw = data.get("slides") or []
    except Exception as exc:
        log.warning("Reja olinmadi, kategoriyalar o'zimiz tanlaymiz: %s", exc)
        raw = []

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

    # Ketma-ket takror qolmasin — AI reja bosqichida ham takrorlashi mumkin.
    for index in range(1, len(outline) - 1):
        if outline[index]["category"] == outline[index - 1]["category"]:
            outline[index]["category"] = _fallback_category(index + 3, count)
    return outline


def _fallback_category(index: int, count: int) -> str:
    """Reja kelmaganda ham slaydlar xilma-xil bo'lsin."""
    middle = [key for key in CATEGORY_KEYS if key not in ("muqova", "yakun")]
    return middle[index % len(middle)]


# ───────────────────────────────────────────────────────── slayd yozish

def split_slides(raw: str) -> List[str]:
    """Javobni to'liq HTML hujjatlarga ajratadi.

    Chala kelgan hujjat tashlab yuboriladi: uni suratga olsak, yarim
    slayd chiqadi.
    """
    text = _FENCE.sub("", _THINK.sub("", str(raw or ""))).strip()
    slides = []
    for part in text.split(MARKER):
        part = part.strip()
        if not part:
            continue
        lower = part.lower()
        if "<html" not in lower:
            continue
        if "</html>" not in lower:
            log.warning("Chala kelgan slayd tashlandi (%d belgi)", len(part))
            continue
        slides.append(strip_shadows(part))
    return slides


def write_slides(topic: str, slide_count: int, theme, language: str = "uz",
                 level: int = 2, preferences: str = "", source_text: str = "",
                 author: str = "",
                 progress_cb: Optional[Callable] = None) -> List[str]:
    """Butun taqdimotni HTML hujjatlar ro'yxati qilib qaytaradi."""
    slide_count = max(4, int(slide_count or 8))
    outline = plan_outline(topic, slide_count, language, level)
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
                            used, level, source_text, preferences, author)
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
        used.extend(item["category"] for item in outline[start - 1:start - 1 + count])
        start += count

    log.info("HTML slaydlar tayyor: %d ta", len(slides))
    if not slides:
        raise RuntimeError("AI birorta to'liq slayd qaytarmadi")
    return slides


def ensure_photos(pages: List[str], theme, language: str = "uz",
                  minimum: int = 3) -> List[str]:
    """Taqdimotda kamida shuncha fotosurat so'ralganiga ishonch hosil qiladi.

    Promptda aytilgan bo'lsa ham, model ba'zan rasmsiz slayd yozadi.
    Shunda faqat o'sha slaydlar qayta so'raladi — muqovadan boshlab.
    """
    from . import html_images

    have = html_images.count_requests(pages)
    if have >= minimum or not pages:
        return pages

    log.warning("Taqdimotda %d ta rasm so'ralgan, kamida %d kerak",
                have, minimum)
    result = list(pages)
    # Muqova birinchi navbatda, keyin o'rtadagi slaydlar.
    order = [0] + [i for i in range(1, len(result) - 1)]
    for index in order:
        if have >= minimum:
            break
        if html_images.requests_in(result[index]):
            continue
        problem = ("slaydda fotosurat yo'q — bitta <img data-prompt=\"...\"> "
                   "qo'shing va unga CSS da o'lcham hamda object-fit: cover "
                   "bering")
        fixed = fix_slide(result[index], [problem], theme, language)
        if fixed and html_images.requests_in(fixed):
            result[index] = fixed
            have += 1
    return result


# Slaydga joylashtirilgan rasm `src="data:image/png;base64,...."`
# ko'rinishida turadi va bitta fotosurat bir necha yuz ming belgi
# bo'ladi. Uni modelga yuborib bo'lmaydi: so'rov kontekstga sig'maydi,
# sig'sa ham model uzun satrni qayta yoza olmay rasmni tushirib
# qoldiradi va slaydda "buzuq rasm" belgisi alt matni bilan qoladi.
# Shuning uchun rasmlar so'rovdan OLDIN qisqa belgiga almashtiriladi
# va javob kelgach o'z joyiga qaytariladi.
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
    """Joylashuvi buzilgan slaydni qayta chizdiradi.

    Brauzer slaydni joylashtirgandan keyin tekshiriladi: element
    varaqdan chiqib ketgani, matn ustiga matn tushgani yoki mazmun
    yuqoriga to'planib qolgani ko'rinadi. Shu ro'yxat modelga aytiladi
    va u FAQAT o'sha slaydni qayta yozadi — butun taqdimot emas.

    Slayddagi fotosurat va ikonkalar so'rovga qo'shilmaydi: ular
    qisqa belgiga almashtirilib, javob kelgach joyiga qaytariladi.
    """
    if not problems:
        return html

    parked, store = _park_images(html)
    listed = "\n".join(f"- {item}" for item in problems)
    keep = ("- `src=\"#rasm1\"` kabi qisqa belgilar — bu tayyor rasmlar. "
            "Ularni AYNAN o'sha holicha ko'chiring, o'zgartirmang va "
            "o'chirmang; yangi `<img>` qo'shmang.\n") if store else ""
    user = (
        "Quyidagi slayd brauzerda noto'g'ri joylashdi. Topilgan "
        f"kamchiliklar:\n{listed}\n\n"
        "Shu slaydni QAYTA yoz. Mazmunini saqla — faqat joylashuvini "
        "to'g'rila:\n"
        "- hech bir element 1920x1080 dan chiqmasin, manfiy o'rin "
        "ishlatma;\n"
        "- matn ustiga matn tushmasin — bloklarni flex yoki grid bilan "
        "yonma-yon qo'y, ustma-ust emas;\n"
        "- mazmun butun balandlikni egallasin: body ni flex ustun qilib, "
        "bo'shliqni bloklar orasiga taqsimla;\n"
        "- diagramma yozuvlari ustunlar ustiga tushmasin;\n"
        "- bir matnni ikki marta yozma, soya ishlatma.\n"
        + keep +
        "\nJavobda faqat to'liq HTML hujjat bo'lsin, boshqa hech narsa "
        "yozma.\n\nSlayd:\n" + parked
    )

    try:
        raw = llm_client._call_openrouter_text(
            shell_rules(theme, language), user,
            temperature=0.4, max_tokens=5200)
    except Exception as exc:
        log.error("Slaydni tuzatib bo'lmadi: %s", exc)
        return html

    fixed = split_slides(raw)
    if not fixed:
        return html
    return _restore(_unpark_images(fixed[0], store), theme)


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
