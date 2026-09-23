"""AI matnining chala kelib qolishidan himoya.

Model javobi `max_tokens` ga urilsa, matn so'z o'rtasida uziladi va hujjatga
shundayligicha tushadi ("...global iqtisodiyotga yan"). Ikki tomondan
yopiladi: byudjet tilга yetarli qilib beriladi, va shunga qaramay chala
kelgan matn oxirgi tugagan gapgacha qirqiladi.
"""

import re

# Tokenizerlar ingliz tiliga sozlangan. O'zbek va rus so'zlari — ayniqsa
# "iqtisodiyotning", "transformatsiyaning" kabilar — bir necha bo'lakka
# bo'linadi, shuning uchun so'ziga ketadigan token ancha ko'p.
_TOKENS_PER_WORD = {"uz": 4.0, "ru": 3.5, "en": 2.0}
_DEFAULT_TOKENS_PER_WORD = 4.0

# Model ko'pincha so'ralgan hajmdan sal ko'proq yozadi; shuning uchun zaxira.
_HEADROOM_TOKENS = 300
_MAX_TOKENS = 8000

_SENTENCE_END = re.compile(r"[.!?…](?=[\s\"'»)\]]|$)")
_ENDS_CLEANLY = re.compile(r"[.!?…][\s\"'»)\]]*$")

# Qirqimdan keyin shundan kam qolsa, javobning o'zi buzuq — bunday matnni
# qirqish yordam bermaydi, shuning uchun chaqiruvchiga o'z holicha qaytadi.
_MIN_KEPT_CHARS = 150


def token_budget(word_target: str, language: str) -> int:
    """`"280-380"` kabi hajm ko'rsatkichidan xavfsiz max_tokens hisoblaydi."""
    try:
        upper = int(word_target.split("-")[-1].strip())
    except (AttributeError, ValueError):
        upper = 500
    per_word = _TOKENS_PER_WORD.get(language, _DEFAULT_TOKENS_PER_WORD)
    return min(int(upper * per_word) + _HEADROOM_TOKENS, _MAX_TOKENS)


def ends_cleanly(text: str) -> bool:
    return bool(_ENDS_CLEANLY.search((text or "").rstrip()))


def trim_to_last_sentence(text: str) -> str:
    """Chala qolgan oxirgi gapni olib tashlaydi.

    Matn tinish belgisi bilan tugasa — tegilmaydi. Aks holda oxirgi tugagan
    gapgacha qirqiladi, shunda o'quvchi hech qachon yarim so'z ko'rmaydi.
    """
    cleaned = (text or "").rstrip()
    if not cleaned or ends_cleanly(cleaned):
        return cleaned

    matches = list(_SENTENCE_END.finditer(cleaned))
    if not matches:
        return cleaned

    trimmed = cleaned[: matches[-1].end()].rstrip()
    if len(trimmed) < _MIN_KEPT_CHARS:
        return cleaned
    return trimmed
