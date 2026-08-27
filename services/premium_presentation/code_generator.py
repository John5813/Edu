"""OpenRouter orqali tayyor PPTX yaratadigan Python source code generatori."""

from __future__ import annotations

import logging
import re

from openai import OpenAI

from . import config

logger = logging.getLogger("premium_presentation.code_generator")


BASE_PROMPT = """Sen professional PowerPoint dizayneri va Python dasturchisisan.
    Vazifa: foydalanuvchi bergan mavzu asosida python-pptx kutubxonasi bilan
    murakkab, zamonaviy va premium ko‘rinishdagi taqdimot yaratadigan
    to‘liq Python source code yozish.

QAT'IY TEXNIK TALABLAR:
- Faqat python-pptx ishlatilsin; tashqi framework yoki boshqa slayd kutubxonasi kerak emas.
- Slayd o‘lchami aynan 13.333 x 7.5 inch (16:9) bo‘lsin.
- Foydalanuvchi so‘ragan slayd soni aynan yaratilishi shart.
- Har bir slayd boshqa dizayn tuzilishiga ega bo‘lsin, lekin umumiy vizual til izchil qolsin.
- Oddiy oq professional fon, ko‘k va yashil ranglar palitrasi ishlatilsin.
- Juda ko‘p yoki ma’nosiz shakllar ishlatilmasin; har bir shakl kontentga xizmat qilsin.
- Chiroyli, takrorlanmaydigan nozik ramkalar, chiziqlar va aksentlar ishlatilsin.
- Matn o‘qiladigan bo‘lsin: sarlavhalar katta, tana matni yetarlicha yirik.
- Matn, rang, layout va vizuallar mavzuga mos bo‘lsin.
- Shakllar uchun faqat python-pptx tomonidan ishonchli qo‘llab-quvvatlanadigan
  rectangle, rounded_rectangle, ellipse va line turlaridan foydalan; ROOF,
  FREEFORM yoki noma’lum murakkab shape turlarini ishlatma.
- Kod bitta mustaqil .py fayl sifatida ishlashga tayyor bo‘lsin va serverda
  ishga tushirilganda haqiqiy PPTX fayl yaratsin.
- Faqat python-pptx va xavfsiz standart kutubxonalar ishlatilsin; internet,
  fayl yuklash, subprocess, shell buyruqlari, eval yoki exec ishlatilmasin.
- Rasm uchun tashqi URL yoki alohida fayl talab qilma; shakllar, ikonka
  o‘rnidagi geometrik elementlar va matn bilan premium dizayn yarat.
- Quyidagi output yo‘lini aynan ishlat:
  OUTPUT_PATH = os.environ.get("PPTX_OUTPUT_PATH", "presentation.pptx")
  va oxirida prs.save(OUTPUT_PATH) chaqir.
- MAVZU va SLIDE_COUNT o‘zgaruvchilari kodda aniq ko‘rinsin.

JAVOB FORMATI:
- Faqat sof Python source code qaytar. Bu kod foydalanuvchiga yuborilmaydi,
  server tomonidan PPTX yaratish uchun ishlatiladi.
- Markdown code fence (```), izohli kirish, xulosa yoki boshqa matn yozma.
- Kod to‘liq bo‘lsin; qisqartirma, pseudocode yoki TODO qoldirma.
"""


def _without_code_fences(text: str) -> str:
    """Model tasodifan fence qo‘shsa ham txt faylni toza saqlaydi."""
    cleaned = text.strip()
    cleaned = re.sub(r"^\s*```(?:python|py)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    return cleaned.strip()


def _history_text(error_history: list[str] | None) -> str:
    if not error_history:
        return "Hali xato qayd etilmagan."
    return "\n".join(
        f"{index}. {item}" for index, item in enumerate(error_history[-5:], start=1)
    )


def generate_presentation_code(
    topic: str,
    slide_count: int,
    presentation_language: str = "uz",
    client_name: str = "",
    preferences: str = "",
    previous_code: str = "",
    error_feedback: str = "",
    error_history: list[str] | None = None,
) -> str:
    """OpenRouter'dan to‘liq kod oladi yoki xato berilgan kodni qayta tuzatadi."""
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY topilmadi")

    language_names = {"uz": "o‘zbek", "ru": "rus", "en": "ingliz"}
    language = language_names.get(presentation_language, "o‘zbek")

    if previous_code and error_feedback:
        task = f"""Avvalgi kod quyidagi xatoga sabab bo‘ldi:

XATO:
{error_feedback}

Oldingi xatolar tarixi:
{_history_text(error_history)}

Quyidagi to‘liq kodni tahlil qil, xatoni tuzat va to‘liq yangilangan kodni
qaytar. Faqat source code qaytar, avvalgi koddan faqat kerakli joyni emas,
butun faylni qaytar:

{previous_code}
"""
    else:
        task = f"""Yangi taqdimot kodi kerak.
Mavzu: {topic}
Slaydlar soni: {slide_count}
Taqdimot tili: {language}
Taqdimot egasi: {client_name or "ko‘rsatilmagan"}
Qo‘shimcha istaklar: {preferences or "ko‘rsatilmagan; eng yaxshi premium variantni tanla"}
"""

    # OpenRouter OpenAI-compatible endpoint beradi, shuning uchun mavjud
    # OpenAI SDK klienti ishlatiladi, lekin so'rovlar OpenRouter'ga yuboriladi.
    client = OpenAI(
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
        default_headers={
            "X-Title": "Edu Premium Taqdimot",
        },
    )
    response = client.chat.completions.create(
        model=config.OPENROUTER_TEXT_MODEL,
        max_completion_tokens=16000,
        messages=[
            {"role": "system", "content": BASE_PROMPT},
            {"role": "user", "content": task},
        ],
    )
    content = response.choices[0].message.content or ""
    code = _without_code_fences(content)
    if not code:
        raise RuntimeError("OpenRouter bo‘sh kod qaytardi")

    logger.info(
        "Presentation source code generated: topic=%r slides=%s repaired=%s",
        topic[:80],
        slide_count,
        bool(previous_code and error_feedback),
    )
    return code