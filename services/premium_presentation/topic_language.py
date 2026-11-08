"""Mavzu tili va mavzuni taqdimot tiliga moslash.

Mijoz mavzuni o'zbekcha yozib, xulosada «English» ni tanlasa, AI ga ko'rsatma inglizcha borardi, mavzu esa
o'zbekcha qolardi. Model rejani (sarlavhalarni) ko'pincha mavzu tilida yozardi, slaydlar esa reja sarlavhalarini
aynan ishlatadi — natijada taqdimot (ayniqsa matni kam infografik) o'zbekcha chiqardi, muqovada ham o'zbekcha
mavzu turardi. Hujjatlar oqimida mavzu allaqachon tarjima qilinardi; endi taqdimotlarda ham:

- `detect()` — mavzu qaysi tilda yozilgan (kirill: rus/qozoq/o'zbek; lotin: o'zbek yoki ingliz; aniq emas — None);
- `localize()` — mavzu taqdimot tilida bo'lmasa, AI uni shu tilga o'giradi (nomlar, qisqartmalar, raqamlar
  saqlanadi). Xato bo'lsa — asl mavzu.
"""
import json
import logging
import re
from typing import Optional

log = logging.getLogger(__name__)

_UZ_CYRILLIC = set("ўқғҳЎҚҒҲ")
_KK_CYRILLIC = set("әіңүұөһӘІҢҮҰӨҺ")
# O'zbek lotin belgilari: o'/g', «q» (inglizchada faqat «qu»), xos so'zlar va qo'shimchalar.
_UZ_LATIN = re.compile(
    r"[og][ʻ'`’‘]|q(?!u)|\b(?:va|uchun|bo'yicha|haqida|hamda|tahlili|ahamiyati|asoslari|xususiyatlari|"
    r"rivojlanishi|tarixi|o'rni|roli|turlari|usullari|muammolari)\b|"
    r"\w(?:lari|larning|lardagi|dagi|ligi|iyasi|iyati|chilik)\b", re.IGNORECASE)
_EN_WORDS = re.compile(r"\b(?:the|of|and|in|for|to|on|with|is|are|how|what|why|its|an|by|from|as|or|"
                       r"impact|analysis|theory|history|development|introduction|role)\b", re.IGNORECASE)
# O'zbek lotinida yo'q harf birikmalari: w, th, ph, ck va «c» («ch» dan tashqari), hamda inglizcha qo'shimchalar
# (o'zbekchada -siya, -logiya bo'ladi).
_EN_LETTERS = re.compile(r"w|th|ph|ck|c(?!h)|\w(?:tions?|ology|ness|ship)\b", re.IGNORECASE)

NAMES = {"uz": "Uzbek (Latin script)", "uz-cyrl": "Uzbek (Latin script)", "uz-yangi": "Uzbek (Latin script)",
         "ru": "Russian", "en": "English", "kk": "Kazakh"}


def base(language: str) -> str:
    """O'zbekchaning yozuvlari (lotin, kirill, yangi alifbo) — bitta til."""
    return "uz" if (language or "uz").startswith("uz") else language


def detect(topic: str) -> Optional[str]:
    """"uz", "ru", "kk", "en" yoki None (aniq emas)."""
    text = str(topic or "")
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 3:
        return None
    cyrillic = sum(1 for ch in letters if "Ѐ" <= ch <= "ӿ")
    if cyrillic / len(letters) > 0.6:
        if any(ch in _KK_CYRILLIC for ch in text):
            return "kk"
        return "uz" if any(ch in _UZ_CYRILLIC for ch in text) else "ru"
    if sum(1 for ch in letters if ch.isascii()) / len(letters) <= 0.6:
        return None
    if _UZ_LATIN.search(text):
        return "uz"
    if _EN_WORDS.search(text) or _EN_LETTERS.search(text):
        return "en"
    return None


SYSTEM = ("You translate presentation topics. Translate the topic into {name}. Keep proper names, abbreviations, "
          "formulas and numbers; keep it a natural, short title. If it is already in {name}, return it unchanged. "
          'Return ONLY JSON: {{"topic": "..."}}')


def localize(topic: str, language: str) -> str:
    """Mavzu taqdimot tilida bo'lmasa — shu tilga tarjimasi; aks holda (yoki xatoda) asl mavzu."""
    topic = (topic or "").strip()
    target = base(language)
    written = detect(topic)
    if not topic or written == target or (written is None and target == "uz"):
        return topic
    try:
        from . import llm_client

        data = llm_client._call_openrouter(SYSTEM.format(name=NAMES.get(target, "English")),
                                           json.dumps({"topic": topic}, ensure_ascii=False),
                                           temperature=0.2, max_tokens=300)
        fresh = re.sub(r"\s+", " ", str((data or {}).get("topic") or "")).strip().strip('"«»')
    except Exception as exc:                  # noqa: BLE001 — tarjima bo'lmasa ham taqdimot yoziladi
        log.warning("Mavzu %s tiliga o'girilmadi (%s) — asl mavzu bilan", target, exc)
        return topic
    if not fresh or len(fresh) > max(200, 3 * len(topic)):
        return topic
    if fresh != topic:
        log.info("Mavzu taqdimot tiliga (%s) o'girildi: %r → %r", target, topic, fresh)
    return fresh
