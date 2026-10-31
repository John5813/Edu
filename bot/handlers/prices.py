"""«💵 Narxlar» — botdagi hamma xizmatlar narxi va dizayn uslublari.

Narxlar qo'lda yozilmaydi: buyurtma paytida hisoblanadigan o'sha jadval va funksiyalardan olinadi
(`config.py`, `_count_options`, `kat3d.price_for` ...). Narx o'zgarsa bu sahifa ham o'zi yangilanadi.
Ilgari narxlar «Yordam» matniga qo'lda yozilgan edi va eskirib qolardi.
"""
import logging
from typing import Iterable, List, Tuple

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import InputMediaPhoto, Message

from bot import previews
from translations import get_text, label_variants

router = Router()
logger = logging.getLogger(__name__)

PRICES_TEXTS = label_variants("main_menu.prices")

_T = {
    "uz": {
        "title": "💵 <b>Barcha xizmatlar narxi</b> (so'mda)",
        "ppt": "📊 <b>Taqdimot</b>", "info_modern": "🎨 Infografik va 📝 Zamonaviy",
        "classic": "📄 Klassik (tayyor shablonlar)", "slides": "slayd",
        "three_d": "🧊 <b>3D taqdimot Pro</b>", "full": "🧊 To'liq 3D", "mix": "🧩 Aralash 3D (40% arzon)",
        "med3d": "🫀 3D Anatomiya (tana tuzilishi)",
        "docs": "📚 <b>Ilmiy va o'quv ishlar</b>", "pages": "varoq", "chapters": "bob",
        "extras_free": "qo'shimchalar bepul", "extras": "➕ Referat qo'shimchalari",
        "other": "🛠 <b>Boshqa xizmatlar</b>", "pdf_pages": "bet",
        "test": "har savol", "test_file": "tayyor testni fayldan — bepul", "free": "🆓 Bepul",
        "styles": "🎨 <b>Dizayn uslublari</b> — namunalari pastdagi rasmlarda",
        "modern_styles": "Zamonaviy", "classic_styles": "Klassik: {n} ta tayyor fon",
        "info_styles": "Infografik: dizaynni tizim mazmunga qarab o'zi chizadi",
        "kat3d_styles": "3D taqdimot Pro ({n} uslub, fanga qarab avtomatik)",
        "med3d_styles": "3D Anatomiya ({n} uslub, o'zingiz tanlaysiz yoki avtomatik)",
        "captions": {"turlar": "📊 Taqdimot turlari: Infografik, Zamonaviy, Klassik",
                     "uslublar": "📝 Zamonaviy taqdimot uslublari",
                     "klassik": "📄 Klassik taqdimot shablonlari",
                     "kat3d": "🧊 3D taqdimot Pro uslublari",
                     "med3d": "🫀 3D Anatomiya uslublari"},
    },
    "ru": {
        "title": "💵 <b>Цены на все услуги</b> (в сумах)",
        "ppt": "📊 <b>Презентация</b>", "info_modern": "🎨 Инфографика и 📝 Современная",
        "classic": "📄 Классическая (готовые шаблоны)", "slides": "слайдов",
        "three_d": "🧊 <b>3D-презентация Pro</b>", "full": "🧊 Полное 3D", "mix": "🧩 Смешанное 3D (на 40% дешевле)",
        "med3d": "🫀 3D Анатомия (строение тела)",
        "docs": "📚 <b>Научные и учебные работы</b>", "pages": "стр.", "chapters": "главы",
        "extras_free": "дополнения бесплатно", "extras": "➕ Дополнения к реферату",
        "other": "🛠 <b>Другие услуги</b>", "pdf_pages": "стр.",
        "test": "за вопрос", "test_file": "готовый тест из файла — бесплатно", "free": "🆓 Бесплатно",
        "styles": "🎨 <b>Стили дизайна</b> — образцы на картинках ниже",
        "modern_styles": "Современная", "classic_styles": "Классическая: {n} готовых фонов",
        "info_styles": "Инфографика: дизайн система рисует сама под содержание",
        "kat3d_styles": "3D-презентация Pro ({n} стилей, автоматически по предмету)",
        "med3d_styles": "3D Анатомия ({n} стилей, выбираете сами или автоматически)",
        "captions": {"turlar": "📊 Типы презентаций: Инфографика, Современная, Классическая",
                     "uslublar": "📝 Стили современной презентации",
                     "klassik": "📄 Шаблоны классической презентации",
                     "kat3d": "🧊 Стили 3D-презентации Pro",
                     "med3d": "🫀 Стили 3D Анатомии"},
    },
    "en": {
        "title": "💵 <b>Prices for all services</b> (in soʻm)",
        "ppt": "📊 <b>Presentation</b>", "info_modern": "🎨 Infographic and 📝 Modern",
        "classic": "📄 Classic (ready templates)", "slides": "slides",
        "three_d": "🧊 <b>3D presentation Pro</b>", "full": "🧊 Full 3D", "mix": "🧩 Mixed 3D (40% cheaper)",
        "med3d": "🫀 3D Anatomy (human body)",
        "docs": "📚 <b>Academic papers</b>", "pages": "pages", "chapters": "chapters",
        "extras_free": "extras free", "extras": "➕ Research paper extras",
        "other": "🛠 <b>Other services</b>", "pdf_pages": "pages",
        "test": "per question", "test_file": "ready test from a file — free", "free": "🆓 Free",
        "styles": "🎨 <b>Design styles</b> — samples in the pictures below",
        "modern_styles": "Modern", "classic_styles": "Classic: {n} ready backgrounds",
        "info_styles": "Infographic: the system draws the design to fit the content",
        "kat3d_styles": "3D presentation Pro ({n} styles, picked by subject)",
        "med3d_styles": "3D Anatomy ({n} styles, choose yourself or automatic)",
        "captions": {"turlar": "📊 Presentation types: Infographic, Modern, Classic",
                     "uslublar": "📝 Modern presentation styles",
                     "klassik": "📄 Classic presentation templates",
                     "kat3d": "🧊 3D presentation Pro styles",
                     "med3d": "🫀 3D Anatomy styles"},
    },
}
_KAT3D_EXTRA_NAMES = {"tungi": {"uz": "Tungi ko'k", "ru": "Ночной синий", "en": "Night blue"}}
CLASSIC_TEMPLATES = 20


def _texts(lang: str) -> dict:
    return _T.get("ru" if lang == "kk" else lang) or _T["uz"]


def _som(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def _row(items: Iterable[Tuple[str, int]], unit: str = "") -> str:
    """«5 slayd — 3 000 · 8 — 4 000»: birlik faqat birinchisida (qator qisqa o'qiladi)."""
    parts = []
    for index, (label, price) in enumerate(items):
        label = f"{label} {unit}" if unit and index == 0 else label
        parts.append(f"{label} — {_som(price)}")
    return " · ".join(parts)


def _ranges(table: dict) -> List[Tuple[str, int]]:
    """{"15_20_3": narx} → [("15-20", narx)] — kalitning birinchi ikki soni oraliq."""
    out = []
    for key, price in table.items():
        parts = str(key).split("_")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            out.append((f"{parts[0]}-{parts[1]}", price))
    return out


def _slides(options) -> List[Tuple[str, int]]:
    return [(str(count), price) for count, price in options]


def _style_names(lang: str) -> Tuple[List[str], List[str], List[str]]:
    from bot.handlers import premium_presentation as pp
    from services.kat3d import uslub
    from services.med3d import design

    modern = [pp._style_name(key, lang) for key in pp._STYLE_ORDER if key != pp.SIMPLE_STYLE]
    kat3d = []
    for key, style in uslub.STYLES.items():
        names = design.STYLE_NAMES.get(lang, {})
        kat3d.append(names.get(key) or (_KAT3D_EXTRA_NAMES.get(key) or {}).get(lang) or style.uz)
    med3d = [design.style_name(key, lang) for key in design.STYLE_ORDER]
    return modern, kat3d, med3d


def prices_text(lang: str) -> str:
    import config
    import services.kat3d as kat3d
    from bot.handlers import premium_presentation as pp
    from bot.handlers.test import TEST_PRICE_PER_QUESTION
    from bot.keyboards import _EXTRAS_META

    t = _texts(lang)
    code = "ru" if lang == "kk" else lang
    menu = lambda key: get_text(lang, "main_menu." + key)       # noqa: E731 — tugmadagi nom bilan bir xil
    pages = t["pages"]

    lines = [t["title"], "", t["ppt"],
             f"{t['info_modern']}: {_row(_slides(pp._count_options('', pp.KIND_MODERN)), t['slides'])}",
             f"{t['classic']}: {_row(_slides(pp._count_options(pp.SIMPLE_STYLE)), t['slides'])}",
             "", t["three_d"],
             f"{t['full']}: {_row(_slides(pp._count_options('', pp.KIND_KAT3D, 'full')), t['slides'])}",
             f"{t['mix']}: {_row(_slides(pp._count_options('', pp.KIND_KAT3D, 'mix')), t['slides'])}",
             f"{t['med3d']}: {_row(_slides(pp._count_options('', pp.KIND_MED3D)), t['slides'])}"]

    docs = {k: v for k, v in config.DOCUMENT_PRICES.items() if k != "tezis"}
    extras = " · ".join(f"{(meta.get(code) or meta['uz'])} +{_som(config.EXTRAS_PRICES[key])}"
                        for key, meta in _EXTRAS_META.items() if key in config.EXTRAS_PRICES)
    project = [(f"{size['pages'][0]}-{size['pages'][1]}", size["price"])
               for size in config.PROJECT_WORK_SIZES.values()]
    lines += ["", t["docs"],
              f"{menu('independent_work')}: {_row(_ranges(docs), pages)} ({t['extras_free']})",
              f"{menu('referat')}: {_row(_ranges(docs), pages)}",
              f"   {t['extras']}: {extras}",
              f"{menu('course_work')} (3 {t['chapters']}): {_row(_ranges(config.COURSE_WORK_PRICES), pages)}",
              f"{menu('project_work')}: {_row(project, pages)}",
              f"{menu('diploma_work')}: {_row(_ranges(config.DIPLOMA_WORK_PRICES), pages)}",
              f"{menu('bitiruv_ishi')}: {_row(_ranges(config.GRADUATION_WORK_PRICES), pages)}",
              f"{menu('dissertatsiya')}: {_row(_ranges(config.DISSERTATION_PRICES), pages)}",
              f"{menu('tezis')}: {_som(config.DOCUMENT_PRICES.get('tezis', 3000))}",
              f"{menu('maqola')}: {_row(_ranges(config.ARTICLE_PRICES), pages)}"]

    pdf = config.PDF_CONVERT_PRICES
    pdf_rows = [("1-30", pdf["1_30"]), ("31-100", pdf["31_100"]), ("100+", pdf["101_plus"])]
    lines += ["", t["other"],
              f"{menu('pdf_convert')}: {_row(pdf_rows, t['pdf_pages'])}",
              f"{menu('test')}: {t['test']} — {_som(TEST_PRICE_PER_QUESTION)} ({t['test_file']})",
              f"{t['free']}: {menu('pptx_to_pdf')}, {menu('edit_file')}"]

    modern, kat3d_names, med3d = _style_names(code)
    lines += ["", t["styles"],
              f"• {t['modern_styles']}: {', '.join(modern)}",
              f"• {t['info_styles']}",
              f"• {t['classic_styles'].format(n=CLASSIC_TEMPLATES)}",
              f"• {t['kat3d_styles'].format(n=len(kat3d_names))}: {', '.join(kat3d_names)}",
              f"• {t['med3d_styles'].format(n=len(med3d))}: {', '.join(med3d)}"]
    return "\n".join(lines)


ALBUM = ("turlar", "uslublar", "klassik", "kat3d", "med3d")


async def send_style_album(message: Message, lang: str) -> None:
    """Hamma dizayn namunalari bitta albomda (har rasm ostida nomi)."""
    captions = _texts(lang)["captions"]
    keys = [key for key in ALBUM if previews.exists(key)]
    if not keys:
        return
    for attempt in range(2):
        album = [InputMediaPhoto(media=previews.media(key), caption=captions[key]) for key in keys]
        try:
            sent = await message.answer_media_group(album)
            break
        except Exception as exc:
            cached = [key for key in keys if key in previews._FILE_IDS]
            if attempt or not cached:
                logger.warning("Dizayn namunalari albomi yuborilmadi: %s", exc)
                return
            for key in cached:                   # eskirgan file_id — fayllardan qayta yuboriladi
                previews._FILE_IDS.pop(key, None)
    for key, item in zip(keys, sent or []):
        previews.remember(key, item)


@router.message(F.text.in_(PRICES_TEXTS))
async def prices_handler(message: Message, state: FSMContext, user_lang: str):
    await state.clear()
    await message.answer(prices_text(user_lang), parse_mode="HTML", disable_web_page_preview=True)
    await send_style_album(message, user_lang)
