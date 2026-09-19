"""AI dan qolip va mazmun so'raydi — koordinatasiz.

Eski tizimda AI butun slaydni koordinatalari bilan chizib berardi va
kod uni tuzatib chiqardi. Endi savol ancha sodda: "shu bo'lak uchun
qaysi qolipni olasan va uning o'rinlariga nima yozasan". Javob kichik,
tekshirish oson, natija esa har safar bir xil darajada chiqadi.

Slaydlar bo'laklab so'raladi: bitta so'rovda hamma slayd so'ralsa,
javob token chegarasiga urilib chala kelardi.
"""

import json
import logging
import re
from typing import Callable, Dict, List, Optional

from services import timeframe

from . import llm_client
from .deck import PlannedSlide
from .templates import (BODY_IDS, CATALOGUE, CLOSING_IDS, OPENING_IDS,
                        catalogue_prompt, get as get_template)

log = logging.getLogger("composer")

# Bitta so'rovda shuncha slayd — undan ko'pi javobni uzaytirib, chala
# kelishiga olib keladi.
CHUNK = 4

_LANGUAGE = {
    "ru": "русском языке",
    "en": "in English",
    "uz": "o'zbek tilida",
}


def _system_prompt(language: str) -> str:
    target = _LANGUAGE.get(language, _LANGUAGE["uz"])
    return f"""Sen professional taqdimot muallifisan. Slayd chizmaysan —
joylashuv tayyor qoliplarda belgilangan. Sen faqat QAYSI QOLIP va
o'rinlarga NIMA YOZILISHINI aytasan.

QOLIPLAR RO'YXATI:
{catalogue_prompt()}

QOIDALAR:
- Har slayd uchun ro'yxatdagi qolip nomini aynan yoz.
- Ketma-ket ikki slaydda bir xil qolip bo'lmasin; butun taqdimotda
  kamida oltita turli qolip ishlatilsin.
- Har o'rin uchun berilgan belgi chegarasidan oshma — oshsa matn
  qirqiladi.
- Matn {target} bo'lsin. Rasm tavsifi ("image") esa INGLIZ tilida va
  ichida yozuv bo'lmasin.
- "icon" maydoniga faqat shu ro'yxatdan nom yoz: {llm_client.ICON_NAMES}
- Diagramma ("chart") da raqamlar mavzuga oid va ishonarli bo'lsin.
- Mazmun aniq bo'lsin: raqam, misol, sana. Umumiy gaplardan qoch.

{timeframe.year_rule(language)}

JAVOB FORMATI — faqat JSON:
{{"slides": [{{"layout": "qolip_nomi", "content": {{"title": "...", "body": "..."}}}}]}}
"""


def _user_prompt(topic: str, start: int, count: int, total: int,
                 outline: List[str], done: List[str], level: int,
                 source: str, preferences: str) -> str:
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
    ]
    if outline:
        parts.append("Taqdimot rejasi:\n" + "\n".join(
            f"  {i}. {line}" for i, line in enumerate(outline, 1)))
    if done:
        parts.append("Oldingi slaydlarda ishlatilgan qoliplar (takrorlama): "
                     + ", ".join(done[-6:]))
    if preferences:
        parts.append(f"Mijoz istagi: {preferences}")
    if source:
        parts.append("Mijoz bergan material (shundan foydalanib yoz):\n"
                     + source[:4000])

    if start == 1:
        parts.append('Birinchi slayd "cover" qolipida bo'"'"'lsin.')
    if start + count > total:
        parts.append('Oxirgi slayd "closing" qolipida bo'"'"'lsin.')

    return "\n\n".join(parts)


def _outline(topic: str, count: int, language: str) -> List[str]:
    """Taqdimot rejasi — slaydlar bir-birini takrorlamasligi uchun.

    Bo'laklab so'ralganda har bo'lak avvalgisini ko'rmaydi. Reja oldindan
    tuzilsa, har bo'lak o'z o'rnini biladi.
    """
    prompt = (
        f'Mavzu: "{topic}"\n\n'
        f"Shu mavzudagi {count} slaydli taqdimot uchun har slaydning "
        "bir qatorli mazmunini yoz. Birinchisi — muqova, oxirgisi — "
        "yakun. Slaydlar bir-birini takrorlamasin, mavzuni bosqichma-"
        "bosqich ochsin.\n\n"
        f"Matn {_LANGUAGE.get(language, _LANGUAGE['uz'])}.\n"
        'Faqat JSON: {"outline": ["1-slayd mazmuni", "2-slayd mazmuni"]}'
    )
    try:
        data = llm_client._call_openrouter(
            "Sen taqdimot rejasini tuzasan. Faqat JSON qaytar.",
            prompt, temperature=0.6, max_tokens=180 + 60 * count)
        lines = [str(x).strip() for x in (data.get("outline") or []) if str(x).strip()]
        return lines[:count]
    except Exception as exc:
        log.warning("Reja olinmadi, slaydlar rejasiz yoziladi: %s", exc)
        return []


def _clean_layout(raw: str, previous: str, index: int, total: int) -> str:
    """Qolip nomini tekshiradi va takrorlanishdan saqlaydi."""
    name = (raw or "").strip().lower()
    if index == 1:
        return "cover"
    if index == total:
        return "closing"

    if name not in CATALOGUE or name in OPENING_IDS or name == "closing":
        log.info("Noma'lum qolip '%s' — o'rniga matnli qolip", raw)
        name = "text_block"
    if name == previous:
        # Ketma-ket bir xil qolip taqdimotni bir xil qilib qo'yadi.
        alternatives = [key for key in BODY_IDS if key != previous]
        name = alternatives[index % len(alternatives)]
    return name


def _slides_from(data: Dict, start: int, count: int, total: int,
                 previous: str) -> List[PlannedSlide]:
    planned: List[PlannedSlide] = []
    raw_slides = data.get("slides") or []
    for offset in range(count):
        index = start + offset
        raw = raw_slides[offset] if offset < len(raw_slides) else {}
        content = raw.get("content") if isinstance(raw, dict) else None
        layout = _clean_layout(
            raw.get("layout") if isinstance(raw, dict) else "",
            previous, index, total)
        if not isinstance(content, dict) or not content:
            log.warning("Slayd %s mazmunsiz keldi", index)
            content = {"title": "", "body": ""}
        planned.append(PlannedSlide(layout=layout, content=content))
        previous = layout
    return planned


def plan_deck(topic: str, slide_count: int, language: str = "uz",
              level: int = 2, preferences: str = "", source_text: str = "",
              progress_cb: Optional[Callable] = None) -> List[PlannedSlide]:
    """Butun taqdimotni rejalashtiradi va slaydlar ro'yxatini qaytaradi."""
    slide_count = max(4, int(slide_count or 8))
    outline = _outline(topic, slide_count, language)

    system = _system_prompt(language)
    slides: List[PlannedSlide] = []
    used: List[str] = []
    previous = ""

    start = 1
    while start <= slide_count:
        count = min(CHUNK, slide_count - start + 1)
        if progress_cb:
            try:
                progress_cb(start - 1, slide_count)
            except Exception:
                pass

        user = _user_prompt(topic, start, count, slide_count,
                            outline, used, level, source_text, preferences)
        try:
            data = llm_client._call_openrouter(
                system, user, temperature=0.65, max_tokens=900 + 700 * count)
        except Exception as exc:
            log.error("Slayd bo'lagi olinmadi (%s-%s): %s",
                      start, start + count - 1, exc)
            data = {}

        chunk = _slides_from(data, start, count, slide_count, previous)
        slides.extend(chunk)
        used.extend(item.layout for item in chunk)
        previous = chunk[-1].layout if chunk else previous
        start += count

    log.info("Taqdimot rejasi tayyor: %s slayd, %s xil qolip",
             len(slides), len({s.layout for s in slides}))
    return slides
