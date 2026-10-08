"""Zamonaviy taqdimot promptlari — mijoz tanlagan TILDA.

Ilgari hamma prompt o'zbekcha edi va oxirida "matnni ruscha yoz" deyilardi. Model o'zbekcha
ko'rsatma va o'zbekcha namunalarni ko'rib, ruscha taqdimotga o'zbekcha (ba'zan kirill harfidagi)
sarlavha va jumlalarni aralashtirib yuborardi. Endi prompt — ko'rsatma ham, namuna ham —
butunlay taqdimot tilida: `uz.py`, `ru.py`, `en.py`, `kk.py`. Mazmuni bir xil, faqat tili boshqa.

Har modulda bir xil nomlar bor (`test_prompt_tillari.py` tekshiradi). O'zgaruvchi joylar
⟨nom⟩ ko'rinishida yoziladi va `fill()` bilan to'ldiriladi (JSON namunalaridagi {} ga tegmaydi).
Kirill yozuvidagi o'zbekcha (uz-cyrl) — o'zbekcha prompt, matn esa kirillda yozilsin degan qoida
bilan (texnik kalitlar — kategoriya va sinf nomlari — lotinda qolishi kerak).
"""
import contextlib
import contextvars
import importlib

_MODULES = {"uz": "uz", "uz-cyrl": "uz", "ru": "ru", "en": "en", "kk": "kk"}

# Shu oqimdagi taqdimot tili (bugungi sana qoidasi va boshqa umumiy qo'shimchalar shu tilda bo'lsin).
_CURRENT: contextvars.ContextVar = contextvars.ContextVar("premium_prompt_language", default="uz")


def get(language: str):
    """Til moduli (noma'lum til — o'zbekcha)."""
    return importlib.import_module(f"{__name__}.{_MODULES.get(language or 'uz', 'uz')}")


def target(language: str) -> str:
    """"Matnni ... yozasan" dagi til ifodasi — shu tilning o'z so'zlari bilan."""
    value = get(language).TARGET
    return value.get(language, value.get("uz", "")) if isinstance(value, dict) else value


def fill(template: str, /, **values) -> str:
    for key, value in values.items():
        template = template.replace(f"⟨{key}⟩", str(value))
    return template


def current() -> str:
    return _CURRENT.get()


@contextlib.contextmanager
def use(language: str):
    """`with prompts.use("ru"):` — ichidagi so'rovlarga qo'shiladigan umumiy qoidalar ruscha bo'ladi."""
    token = _CURRENT.set(language or "uz")
    try:
        yield
    finally:
        _CURRENT.reset(token)


def year_rule(language: str) -> str:
    """Bugungi sana va yillar qoidasi — taqdimot tilida (qozoqchasi shu yerda, qolgani `timeframe` da)."""
    from services import timeframe

    rule = getattr(get(language), "YEAR_RULE", None)
    if callable(rule):
        return rule()
    return timeframe.year_rule("uz" if language in ("uz", "uz-cyrl") else language)
