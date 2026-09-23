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

# Serverda mavjud shriftlar. Boshqasini so'rasa, brauzer o'zinikini
# qo'yadi va slayd rejadagidan boshqacha chiqadi.
FONT_STACK = "'DejaVu Sans', 'Liberation Sans', Arial, sans-serif"

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"```(?:html)?", re.IGNORECASE)

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

def shell_rules(theme, language: str) -> str:
    """Har slaydga baravar tegishli QOBIQ qoidalari.

    Bu yerda slaydning ichi emas, tashqi shartlari aytiladi: o'lcham,
    shrift, rang, tashqi faylning yo'qligi. Ichini AI o'zi chizadi.
    """
    target = _LANGUAGE.get(language, _LANGUAGE["uz"])
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
4. Shrift faqat shu qator: font-family: {FONT_STACK};
   Serverda boshqa shrift yo'q — boshqasini yozsang slayd buziladi.
5. Rasm o'rniga SVG yoki CSS bilan chiz. <img>, tashqi ikonka, emoji
   shrifti ishlatma. Belgi kerak bo'lsa — inline SVG.
6. Matn KESILMASIN: text-overflow, ellipsis, qat'iy height bilan
   overflow yashirish — taqiqlanadi. Matn uzun bo'lsa shriftni
   kichraytir yoki blokni kengaytir.
7. Bo'sh joy egasi ("Lorem ipsum", "Matn shu yerda") qoldirma. Biror
   blokka mazmun topolmasang — o'sha blokni butunlay olib tashla.
8. Slayd chetiga matn yopishmasin: hech bir element body chetidan
   48px dan yaqin bo'lmasin.

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
        slides.append(part)
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


def _write_chunk(system: str, user: str, count: int) -> List[str]:
    try:
        raw = llm_client._call_openrouter_text(
            system, user, temperature=0.75, max_tokens=4200 * count)
    except Exception as exc:
        log.error("Slayd bo'lagi olinmadi: %s", exc)
        return []
    return split_slides(raw)
