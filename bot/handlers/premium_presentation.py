"""
Premium taqdimot handleri — Ustalar loyihasidan olingan yangi taqdimot tizimi.
Mavjud hujjat xizmatlariga halaqit qilmaydi, to'liq mustaqil modul.
"""
import asyncio
import contextlib
import html
import logging
import os
import re

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import checkout as pay
from bot import checkout as pay
from bot.states import PremiumPresentationStates
from database.database import Database
from translations import get_text, label_variants
from config import som_to_stars, STARS_RATE
from bot import uploads
from bot.keyboards import get_project_source_keyboard
from services import workload
from services import uz_script

# Har bosqich uchun vaqt chegarasi (soniya). Chegarasiz bosqich tashqi
# xizmat javob bermay qolganda cheksiz osilib qolardi: mijoz "tayyorlanmoqda"
# animatsiyasini soatlab ko'rar, admin panelda esa "hozir ish bajarilmoqda"
# yozuvi abadiy turib, yangilash tugmasini bloklab qo'yardi. Endi bosqich
# chegaradan oshsa xato ko'tariladi — pul qaytariladi, ro'yxat tozalanadi.
_STEP_TIMEOUTS = {
    "brief": 15 * 60,
    "canvas": 12 * 60,
    "render": 8 * 60,
    "qa": 12 * 60,
}


async def _run_step(loop, func, *, step: str, label: str):
    """Og'ir bosqichni chegaralangan vaqt ichida bajaradi."""
    timeout = _STEP_TIMEOUTS[step]
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, func), timeout)
    except (asyncio.TimeoutError, TimeoutError):
        raise RuntimeError(
            f"{label} {int(timeout // 60)} daqiqada tugamadi — "
            f"tashqi xizmat javob bermadi"
        ) from None
from services.project_work import source as source_module

router = Router()
logger = logging.getLogger(__name__)

MIN_SLIDES = 5
MAX_SLIDES = 30

# Narx oddiy taqdimot bilan BIR XIL: 10 varaq — 5 000, 15 — 7 000, 20 — 10 000
# (config.PRESENTATION_PRICES). Oraliq sonlar shu nuqtalar orasida chiziqli
# hisoblanib 500 so'mgacha yaxlitlanadi (12 varaq — 6 000), 10 dan kamida
# birinchi qadam narxi (500 so'm/varaq), 20 dan keyin oxirgi qadam narxi
# (600 so'm/varaq) ishlaydi.
MIN_PRICE = 3000


def _get_price(slide_count: int) -> int:
    """Varaq soniga qarab narx (so'm) — oddiy taqdimot narxlari bilan mos (sayt bilan umumiy)."""
    from services.premium_presentation import pipeline

    return pipeline.price_for(slide_count)


def _price_of(data: dict, slide_count: int) -> int:
    """Buyurtma narxi, shu jumladan 3D Anatomiya promokod chegirmasi."""
    price = _base_price_of(data, slide_count)
    percent = int(data.get("med3d_promo_percent") or 0)
    if data.get("standalone_med3d") and data.get("kind") in (KIND_MED3D, KIND_KAT3D) and 10 <= percent <= 100:
        return price - (price * percent // 100)
    return price


def _base_price_of(data: dict, slide_count: int) -> int:
    if data.get("kind") == KIND_PRO3D:
        import services.pro3d as pro3d

        return pro3d.price_for(slide_count)
    if data.get("kind") == KIND_MED3D:      # 3D Anatomiya — haqiqiy 3D modellar: o'z narxi
        from services.med3d import auto as med3d_auto

        return med3d_auto.price_for(slide_count)
    if data.get("kind") == KIND_KAT3D:      # 3D taqdimot (katalog) — 3D Anatomiya bilan bir narx
        import services.kat3d as kat3d

        return kat3d.price_for(slide_count)
    return _get_price(slide_count)


def _back_text(lang: str) -> str:
    if lang == "ru": return "🔙 Назад"
    if lang == "en": return "🔙 Back"
    return "🔙 Orqaga"


LEVEL_LABELS = {
    1: {"uz": "🏫 Maktab darsligi", "ru": "🏫 Школьный уровень", "en": "🏫 School level"},
    2: {"uz": "🎓 Student", "ru": "🎓 Студент", "en": "🎓 Student"},
    3: {"uz": "📚 Akademik", "ru": "📚 Академический", "en": "📚 Academic"},
}


# Premium ham boshqa xizmatlar bilan bir xil to'lov oqimidan foydalanadi:
# balans yetmasa buyurtma saqlanib qoladi, Stars esa «boshqa to'lov usuli»
# ortida turadi. Ilgari bu yerda o'z klaviaturasi bor edi va mablag'
# yetmaganda oqim shu yerda tugardi.
CHECKOUT = pay.Checkout(service="prem", back_callback="prem_ppt_back_to_confirm")


@pay.describes(CHECKOUT.service)
def _order_summary(data: dict, language: str) -> str:
    """Balans to'lgach mijozga ko'rsatiladigan buyurtma tafsiloti."""
    import html as _html

    def clean(value, limit=120):
        # quote=False: matn element ichida turadi, apostrof qochirilsa
        # o'zbekcha jumla "Ko&#x27;proq" bo'lib ko'rinardi.
        return _html.escape(str(value or "").strip(), quote=False)[:limit]

    lines = ["📊 <b>Taqdimot</b>"]
    if data.get("kind") in KINDS:                 # to'lovdan keyin eslatmada turi ham ko'rinsin (3D Anatomiya va b.)
        lines.append(f"🎨 Turi: {clean(_kind_name(data['kind'], 'uz'))}")
    topic = clean(data.get("topic"), 200)
    if topic:
        lines.append(f"📝 Mavzu: <b>{topic}</b>")
    if data.get("slide_count"):
        lines.append(f"📄 Slaydlar: {int(data['slide_count'])} ta")
    if data.get("med3d_promo_code") and data.get("med3d_promo_percent"):
        lines.append(
            f"🎟 3D promokod: {clean(data.get('med3d_promo_code'), 32)} "
            f"(-{int(data['med3d_promo_percent'])}%)"
        )
    name = clean(data.get("client_name"))
    lines.append(f"👤 Ism: {name}" if name else "👤 Ism: ko'rsatilmagan")
    lines.append(f"🌐 Til: {clean(_language_label(data.get('presentation_language', 'uz')))}")
    if data.get("style"):
        lines.append(f"🖌 Uslub: {clean(data.get('style'))}")
    wishes = clean(data.get("preferences"), 150)
    if wishes:
        lines.append(f"✍️ Istaklar: {wishes}")
    return "\n".join(lines)


def _payment_keyboard(lang: str, price: int) -> InlineKeyboardMarkup:
    return pay.payment_keyboard(CHECKOUT, lang, price)


async def _reserve_med3d_promo(db: Database, data: dict, user_id: int) -> bool:
    code = data.get("med3d_promo_code")
    if not code:
        return True
    promo, reason = await db.reserve_med3d_promocode(code, user_id)
    return bool(promo and reason == "ok")


async def _coupon_unavailable(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    texts = {
        "uz": "⚠️ Promokod endi faol emas yoki foydalanish limiti tugagan. Buyurtma chegirmasiz qayta hisoblandi.",
        "ru": "⚠️ Промокод больше не действует или лимит исчерпан. Заказ пересчитан без скидки.",
        "en": "⚠️ The promo code is no longer active or its limit was reached. The order was repriced without it.",
        "kk": "⚠️ Промокод енді белсенді емес немесе лимиті аяқталды. Тапсырыс жеңілдіксіз қайта есептелді.",
    }
    await state.update_data(
        med3d_promo_code="", med3d_promo_percent=0, med3d_promo_id=None,
        coupon_redeemed=False, payment_method=None,
    )
    await callback.message.answer(texts.get(lang) or texts["uz"])
    await _step_summary(callback.message, state, lang)


class _MessageCallbackAdapter:
    """Successful Stars paymentni mavjud generatsiya oqimiga ulaydi."""

    def __init__(self, message: Message, data: str = ""):
        self.message = message
        self.from_user = message.from_user
        self.data = data

    async def answer(self, *args, **kwargs):
        return None


# ──────────────────────────────────────────────────────────────── QADAMLAR
#
# Bitta "Taqdimot" katalogi. Tartib:
#   1 mavzu → 2 ism → 3 AI ga tushuntirish → 4 manba → 5 hajm → 6 uslub
#   → (zamonaviy uslub: rang → buyurtma) yoki ("Chiroyli orqa fonlar":
#   hozirgi oddiy oqim — to'lov, 20 ta shablon, yaratish).
#
# Har qadam bitta "so'rov" xabari: javob kelishi bilan u o'chadi (ilgari
# eski savollar suhbatda qolib ketardi). `prompt_mid` — shu xabar raqami.

ENTRY_TEXTS = [
    "🌟 Taqdimot", "🌟 Презентация", "🌟 Presentation",
    "✨ Zamonaviy taqdimot", "✨ Современная презентация", "✨ Modern presentation",
    "⭐ Premium taqdimot", "⭐ Премиум презентация", "⭐ Premium presentation",
]
for _key in ("main_menu.presentation", "main_menu.premium_presentation"):
    ENTRY_TEXTS += [text for text in label_variants(_key) if text not in ENTRY_TEXTS]
MED3D_ENTRY_TEXTS = label_variants("main_menu.presentation_3d") + [
    "🫀 3D taqdimot — tana tuzilishi", "🫀 3D презентация — строение тела", "🫀 3D presentation — human body",
    "🫀 3D Анатомия — дене құрылысы"]

SIMPLE_STYLE = "fon"
_STYLE_ORDER = ["toza", "jurnal", "blok", "kontur", "qorongu", SIMPLE_STYLE]

# Tugma: nom + qisqa tavsif. Tavsif tugmaning o'zida, shuning uchun alohida
# rasm yoki ro'yxat kerak emas.
_STYLE_BUTTONS = {
    "toza": {"uz": "🤍 Toza — yengil va ixcham", "ru": "🤍 Чистый — лёгкий и компактный",
             "en": "🤍 Clean — light and compact"},
    "jurnal": {"uz": "📖 Jurnal — klassik va nafis", "ru": "📖 Журнал — классика и изящество",
               "en": "📖 Journal — classic and elegant"},
    "blok": {"uz": "🟪 Blok — yorqin va kuchli", "ru": "🟪 Блок — яркий и сильный",
             "en": "🟪 Block — bold and vivid"},
    "kontur": {"uz": "📐 Kontur — aniq va texnik", "ru": "📐 Контур — чёткий и технический",
               "en": "📐 Outline — precise and technical"},
    "qorongu": {"uz": "🌙 Qorong'u — zamonaviy va jasur", "ru": "🌙 Тёмный — современный и смелый",
                "en": "🌙 Dark — modern and bold"},
    SIMPLE_STYLE: {"uz": "🖼 Chiroyli orqa fonlar — tayyor rasmli shablonlar",
                   "ru": "🖼 Красивые фоны — готовые шаблоны с рисунками",
                   "en": "🖼 Beautiful backgrounds — ready picture templates"},
}
_STYLE_NAMES = {
    "toza": {"uz": "Toza", "ru": "Чистый", "en": "Clean"},
    "jurnal": {"uz": "Jurnal", "ru": "Журнал", "en": "Journal"},
    "blok": {"uz": "Blok", "ru": "Блок", "en": "Block"},
    "kontur": {"uz": "Kontur", "ru": "Контур", "en": "Outline"},
    "qorongu": {"uz": "Qorong'u", "ru": "Тёмный", "en": "Dark"},
    SIMPLE_STYLE: {"uz": "Chiroyli orqa fonlar", "ru": "Красивые фоны",
                   "en": "Beautiful backgrounds"},
}
_LANG_BUTTONS = {"uz": "🇺🇿 O'zbek (lotin)", uz_script.UZ_CYRILLIC_LANG: "🇺🇿 Ўзбек (кирилл)",
                 uz_script.UZ_NEW_LANG: "🇺🇿 Özbek (yangi alifbo)",
                 "ru": "🇷🇺 Русский", "en": "🇬🇧 English", "kk": "🇰🇿 Қазақша"}


def _language_label(code: str) -> str:
    """Buyurtma xulosasidagi til yozuvi."""
    if code == uz_script.UZ_CYRILLIC_LANG:
        return "UZ (кирилл)"
    if code == uz_script.UZ_NEW_LANG:
        return "UZ (yangi alifbo)"
    return "UZ (lotin)" if code == "uz" else str(code or "uz").upper()

_TXT = {
    "ask_topic": {
        "uz": "📝 <b>Taqdimot mavzusini kiriting:</b>",
        "ru": "📝 <b>Введите тему презентации:</b>",
        "en": "📝 <b>Enter the presentation topic:</b>"},
    "ask_script": {
        "uz": ("🔤 <b>Taqdimot qaysi yozuvda bo‘lsin?</b>\n"
               "<i>Matnning hammasi (sarlavhalar ham) tanlangan yozuvda chiqadi, ikki yozuv aralashmaydi.</i>"),
        "ru": ("🔤 <b>Каким алфавитом написать презентацию?</b>\n"
               "<i>Весь текст (включая заголовки) будет в выбранном алфавите, без смешения.</i>"),
        "en": ("🔤 <b>Which script should the presentation use?</b>\n"
               "<i>All text, headings included, will use the chosen script without mixing.</i>")},
    "script_latin": {"uz": "🇺🇿 Lotin (O‘zbek)", "ru": "🇺🇿 Латиница (узб.)", "en": "🇺🇿 Latin (Uzbek)"},
    "script_cyrillic": {"uz": "🇺🇿 Кирилл (Ўзбек)", "ru": "🇺🇿 Кириллица (узб.)", "en": "🇺🇿 Cyrillic (Uzbek)"},
    "script_latin_new": {"uz": "🇺🇿 Yangi alifbo (Özbek)", "ru": "🇺🇿 Новая латиница (узб.)",
                         "en": "🇺🇿 New Latin (Uzbek)"},
    "topic_short": {
        "uz": "❌ Mavzu juda qisqa. Kamida 3 ta belgi kiriting.",
        "ru": "❌ Тема слишком короткая. Введите минимум 3 символа.",
        "en": "❌ Topic too short. Enter at least 3 characters."},
    "ask_name": {
        "uz": "👤 <b>Ism-familiyani kiriting</b>\n<i>(Taqdimotning sarlavha sahifasiga yoziladi)</i>",
        "ru": "👤 <b>Введите имя и фамилию</b>\n<i>(Будет указано на титульном слайде)</i>",
        "en": "👤 <b>Enter your full name</b>\n<i>(Will appear on the title slide)</i>"},
    "ask_prefs": {
        "uz": ("🎨 <b>Taqdimot qanday bo‘lishini xohlaysiz?</b>\n\n"
               "Istaklaringizni erkin yozing: auditoriya, maqsad, ohang, misollar yoki "
               "alohida talablar. Hech qanday qat’iy shakl shart emas.\n\n"
               "<i>Masalan: investorlar uchun ishonchli, ko‘proq vizual, qisqa va ta’sirli.</i>"),
        "ru": ("🎨 <b>Каким вы хотите видеть презентацию?</b>\n\n"
               "Напишите пожелания свободно: аудитория, цель, тон, примеры или любые "
               "требования. Жёсткий формат не нужен.\n\n"
               "<i>Например: убедительная для инвесторов, больше визуала, коротко.</i>"),
        "en": ("🎨 <b>How should the presentation feel?</b>\n\n"
               "Describe anything freely: audience, goal, tone, examples or special "
               "requirements. No rigid format is needed.\n\n"
               "<i>For example: confident for investors, visual, concise.</i>")},
    "ask_count": {
        "uz": "📊 <b>Nechta slayd kerak?</b>",
        "ru": "📊 <b>Сколько слайдов нужно?</b>",
        "en": "📊 <b>How many slides do you need?</b>"},
    "ask_style": {
        "uz": "🖌 <b>Ko‘rinish uslubini tanlang</b>",
        "ru": "🖌 <b>Выберите стиль оформления</b>",
        "en": "🖌 <b>Choose a visual style</b>"},
    "count_style": {
        "uz": "🖌 Uslub: <b>{style}</b>", "ru": "🖌 Стиль: <b>{style}</b>",
        "en": "🖌 Style: <b>{style}</b>"},
    "count_balance": {
        "uz": "💳 Balansingiz: <b>{balance} so'm</b>",
        "ru": "💳 Ваш баланс: <b>{balance} сум</b>",
        "en": "💳 Your balance: <b>{balance} soʻm</b>"},
    "count_hint": {
        "uz": ("<i>Narx slaydlar soniga qarab. Muqova va reja slaydi bu songa kirmaydi "
               "(kirish va xulosa kiradi). Tanlagach xulosa ko‘rsatiladi.</i>"),
        "ru": ("<i>Цена зависит от числа слайдов. Титульный слайд и план в число не входят "
               "(введение и заключение входят). После выбора покажем итог.</i>"),
        "en": ("<i>Price depends on the slide count. The cover and agenda are not counted "
               "(the introduction and conclusion are). A summary follows.</i>")},
    "count_hint_fon": {
        "uz": ("<i>Tayyor rasmli shablonlar 10, 15 yoki 20 slaydda tayyorlanadi. "
               "Muqova va reja slaydi bu songa kirmaydi (kirish va xulosa kiradi).</i>"),
        "ru": ("<i>Шаблоны с рисунками делаются на 10, 15 или 20 слайдов. Титульный слайд "
               "и план в число не входят (введение и заключение входят).</i>"),
        "en": ("<i>Picture templates come in 10, 15 or 20 slides. The cover and agenda "
               "are not counted (the introduction and conclusion are).</i>")},
    "style_hint": {
        "uz": "<i>Zamonaviy uslubda keyingi qadamda rang tanlanadi, orqa fonlarda — 20 ta shablon. Narx keyingi qadamda hajm bilan ko‘rsatiladi.</i>",
        "ru": "<i>В современных стилях дальше выбирается цвет, в красивых фонах — 20 шаблонов. Цена — на следующем шаге вместе с объёмом.</i>",
        "en": "<i>Modern styles ask for a colour next; backgrounds offer 20 templates. Prices come with the size.</i>"},
    "skip": {"uz": "⏭ O‘tkazib yuborish", "ru": "⏭ Пропустить", "en": "⏭ Skip"},
    "confirm": {"uz": "✅ Buyurtmani tasdiqlash", "ru": "✅ Подтвердить заказ", "en": "✅ Confirm order"},
    "source_input_back": {"uz": "🔙 Orqaga", "ru": "🔙 Назад", "en": "🔙 Back"},
}


def _t(lang: str, key: str, **kwargs) -> str:
    table = _TXT[key]
    text = table.get(lang) or table["uz"]
    return text.format(**kwargs) if kwargs else text


def _style_name(key: str, lang: str) -> str:
    names = _STYLE_NAMES.get(key) or {}
    return names.get(lang) or names.get("uz") or key


def _topic_line(data: dict, lang: str) -> str:
    label = {"uz": "Mavzu", "ru": "Тема", "en": "Topic"}.get(lang, "Mavzu")
    topic = (data.get("topic") or "").strip()
    return f"📋 {label}: <b>{topic}</b>\n\n" if topic else ""


# Orqaga: har qadamning oldingisi. Birinchi qadamdan (taqdimot turi) — bosh menyu.
# Tartib: tur → mavzu → (yozuv) → ism → istaklar → manba → (zamonaviyda uslub) → slaydlar soni → xulosa.
_PREVIOUS = {"topic": "kind", "script": "topic", "name": "topic", "prefs": "name", "source": "prefs",
             "source_input": "source", "style": "source", "volume": "style", "summary": "count",
             "photos": "count", "m3dstyle": "prefs", "med3d_promo": "topic"}  # 3D promo orqaga — mavzuga


def _previous_step(data: dict):
    """Orqaga qadam: slaydlar sonidan oldin — uslub (zamonaviy) yoki manba (qolgan turlar)."""
    step = data.get("step") or ""
    if step == "name" and data.get("script_asked"):
        return "script"
    if step == "topic" and data.get("standalone_med3d") and _kind_of(data) in (KIND_MED3D, KIND_KAT3D):
        return None                               # 3D bo'limi mavzudan boshlanadi
    if step == "count":
        kind = _kind_of(data)
        if kind == KIND_KAT3D:
            return "prefs"
        return "style" if kind == KIND_MODERN else ("m3dstyle" if kind == KIND_MED3D else "source")
    # Slaydlar sonidan keyin: rasm manbasi → yozuv animatsiyasi → xulosa (taklif qilinmaganlari o'tkazib yuboriladi).
    photos = "photos" if _photo_source(data) is not None else "count"
    if step == "anim":
        return photos
    if step == "summary":
        return "anim" if data.get("text_anim_offer") else photos
    return _PREVIOUS.get(step)


def _markup(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _back_row(lang: str, callback: str = "prem_ppt_prev"):
    return [InlineKeyboardButton(text=_back_text(lang), callback_data=callback)]


async def _drop_prompt(bot, chat_id: int, state: FSMContext) -> None:
    """Joriy so'rov xabarini o'chiradi (javob olingach u suhbatda qolmasin)."""
    data = await state.get_data()
    message_id = data.get("prompt_mid")
    if message_id:
        with contextlib.suppress(Exception):
            await bot.delete_message(chat_id, message_id)
        await state.update_data(prompt_mid=None)


async def _prompt(message: Message, state: FSMContext, text: str, markup,
                  step: str, fsm_state=None) -> None:
    """Yangi so'rovni yuboradi; oldingisi o'chiriladi."""
    await _drop_prompt(message.bot, message.chat.id, state)
    if fsm_state is not None:
        await state.set_state(fsm_state)
    sent = await message.answer(text, parse_mode="HTML", reply_markup=markup)
    await state.update_data(prompt_mid=sent.message_id, step=step)


async def _lang_of(user_id: int, db: Database) -> str:
    user = await db.get_user(user_id)
    return user.language if user else "uz"


_ENGLISH_WORDS = {"the", "of", "and", "in", "for", "to", "on", "with", "is", "are", "how",
                  "what", "why", "impact", "analysis", "theory", "history", "development",
                  "introduction", "role", "its", "an", "a", "by", "from", "as", "or"}


def _detect_language(topic: str) -> str:
    """Mavzuning tilidan taqdimot tili: ruscha, inglizcha yoki o'zbekcha.

    Til alohida so'ralmaydi (qadam kamaysin); noto'g'ri chiqsa, buyurtma
    xulosasida o'zgartiriladi.
    """
    from bot.handlers import documents as _documents

    written = _documents._topic_language(topic)
    if written:
        return written
    words = re.findall(r"[a-z']+", (topic or "").lower())
    if words and all(ord(ch) < 128 for ch in topic) and \
            sum(1 for word in words if word in _ENGLISH_WORDS) >= 1:
        return "en"
    return "uz"


# ── 1. Mavzu

THREE_D_INTRO = {
    "uz": ("🧊 <b>3D taqdimot</b> — har slaydda haqiqiy 3D model: Morph bilan aylanadi, suzib o'tadi, "
           "uchib kiradi.\n\nMavzu yozing: <b>tana tuzilishi</b> (organlar, suyaklar) yoki <b>tarix, tabiat, "
           "hayvonlar, texnika, transport, koinot, san'at</b>... Katalogdan mos 3D modellarni topib, "
           "to'lovdan oldin ko'rsatamiz.\n<i>Taqdimot kompyuterdagi PowerPoint (2019, 2021, 365) uchun.</i>"),
    "ru": ("🧊 <b>3D-презентация</b> — на каждом слайде настоящая 3D-модель: вращается, перелетает и "
           "появляется с эффектом Morph.\n\nНапишите тему: <b>строение тела</b> (органы, кости) или <b>история, "
           "природа, животные, техника, транспорт, космос, искусство</b>... Подберём 3D-модели из каталога и "
           "покажем их до оплаты.\n<i>Презентация для PowerPoint на компьютере (2019, 2021, 365).</i>"),
    "en": ("🧊 <b>3D presentation</b> — a real 3D model on every slide: it turns, flies and enters with Morph."
           "\n\nWrite a topic: <b>the human body</b> (organs, bones) or <b>history, nature, animals, machines, "
           "transport, space, art</b>... We find matching 3D models in our catalog and show them before you "
           "pay.\n<i>The deck is for PowerPoint on a computer (2019, 2021, 365).</i>"),
    "kk": ("🧊 <b>3D презентация</b> — әр слайдта нақты 3D модель: Morph арқылы айналады, ұшып өтеді."
           "\n\nТақырып жазыңыз: <b>дене құрылысы</b> немесе <b>тарих, табиғат, жануарлар, техника, ғарыш, "
           "өнер</b>... Каталогтан сай 3D модельдерді тауып, төлемге дейін көрсетеміз.\n"
           "<i>Презентация компьютердегі PowerPoint үшін (2019, 2021, 365).</i>"),
}


async def _step_topic(message: Message, state: FSMContext, lang: str) -> None:
    # Mavzudan oldin tur tanlangan: so'rov ustida tur nomi, "Orqaga" — tur tanloviga.
    data = await state.get_data()
    if data.get("standalone_med3d") and _kind_of(data) in (KIND_MED3D, KIND_KAT3D):   # 3D bo'limi: tur mavzudan
        await _prompt(message, state, (THREE_D_INTRO.get(lang) or THREE_D_INTRO["uz"]),
                      _markup([_back_row(lang)]), "topic", PremiumPresentationStates.waiting_for_topic_text)
        return
    head = ""
    if data.get("kind") in KINDS:
        label = {"uz": "Turi", "ru": "Тип", "en": "Type", "kk": "Түрі"}.get(lang, "Turi")
        head = f"🎨 {label}: <b>{_kind_name(data['kind'], lang)}</b>\n\n"
    await _prompt(message, state, head + _t(lang, "ask_topic"),
                  _markup([_back_row(lang)]), "topic",
                  PremiumPresentationStates.waiting_for_topic_text)


@router.message(F.text.in_((*ENTRY_TEXTS, *MED3D_ENTRY_TEXTS)))
async def premium_presentation_start(message: Message, state: FSMContext, db: Database):
    """Start either the presentation catalog or the standalone 3D anatomy flow."""
    med3d_entry = message.text in MED3D_ENTRY_TEXTS
    await state.clear()
    # Buyurtma boshlangan vaqti — bir soatdan keyin eskirishini hisoblash uchun.
    await state.set_data(pay.start({}))
    lang = await _lang_of(message.from_user.id, db)

    # Kanalga obuna talabi oddiy oqimda ham shunday edi.
    try:
        channels = await db.get_active_channels()
        if channels:
            from services.channel_service import ChannelService
            from bot.keyboards import get_subscription_check_keyboard
            if not await ChannelService(message.bot).check_user_subscription(
                    message.from_user.id, channels):
                await message.answer(get_text(lang, "subscription_required"),
                                     reply_markup=get_subscription_check_keyboard(lang, channels))
                return
    except Exception as e:
        logger.warning("Obuna tekshiruvi o'tmadi: %s", e)

    if med3d_entry:
        if not _med3d_open(message.from_user.id):
            await message.answer(_MED3D_SOON_BUTTON.get(lang) or _MED3D_SOON_BUTTON["uz"])
            await state.clear()
            return
        await state.update_data(standalone_med3d=True, kind=KIND_MED3D, style="", volume="")
        await _step_topic(message, state, lang)
    else:
        await _step_kind(message, state, lang)


@router.message(PremiumPresentationStates.waiting_for_topic_text)
async def premium_ppt_got_topic(message: Message, state: FSMContext, db: Database):
    lang = await _lang_of(message.from_user.id, db)
    topic = (message.text or "").strip()
    if len(topic) < 3:
        await message.answer(_t(lang, "topic_short"))
        return
    await _drop_prompt(message.bot, message.chat.id, state)
    language = _detect_language(topic)
    await state.update_data(topic=topic, presentation_language=language, script_asked=False)
    # O'zbekcha mavzu kirillda yozilgan bo'lsa yozuv mijozdan so'raladi:
    # ilgari sarlavhalar lotinda, qolgani kirillda chiqib aralashib ketardi.
    if language == "uz" and uz_script.has_cyrillic(topic):
        await _step_script(message, state, lang)
        return
    await _after_topic(message, state, lang)


async def _after_topic(message: Message, state: FSMContext, lang: str) -> None:
    """Mavzu yozildi. 3D Anatomiyada — darhol (to'lovdan oldin) tekshiriladi: mos bo'lmasa shu zahoti aytiladi."""
    data = await state.get_data()
    if _kind_of(data) in (KIND_MED3D, KIND_KAT3D):
        if data.get("standalone_med3d"):
            if not await _three_d_topic_gate(message, state, lang):
                return
            await _step_med3d_promocode(message, state, lang)
            return
        if not await _med3d_topic_gate(message, state, lang):
            return
    await _step_name(message, state, lang)


_MED3D_PROMO_TEXT = {
    "uz": "🎟 3D taqdimot promokodingiz bo'lsa, kiriting:",
    "ru": "🎟 Если у вас есть промокод на 3D-презентацию, введите его:",
    "en": "🎟 Enter your 3D presentation promo code, if you have one:",
    "kk": "🎟 3D презентация промокоды болса, енгізіңіз:",
}
_MED3D_PROMO_BUTTONS = {
    "uz": ("⏭ O'tkazib yuborish", "🔙 Orqaga"),
    "ru": ("⏭ Пропустить", "🔙 Назад"),
    "en": ("⏭ Skip", "🔙 Back"),
    "kk": ("⏭ Өткізіп жіберу", "🔙 Артқа"),
}
_MED3D_PROMO_ERRORS = {
    "not_found": {
        "uz": "❌ Promokod topilmadi yoki o'chirilgan.",
        "ru": "❌ Промокод не найден или отключён.",
        "en": "❌ Promo code not found or deactivated.",
        "kk": "❌ Промокод табылмады немесе өшірілген.",
    },
    "already_used": {
        "uz": "❌ Bu promokoddan avval foydalangansiz.",
        "ru": "❌ Вы уже использовали этот промокод.",
        "en": "❌ You have already used this promo code.",
        "kk": "❌ Бұл промокодты бұрын пайдаланғансыз.",
    },
    "limit_reached": {
        "uz": "❌ Bu promokodning foydalanish limiti tugagan.",
        "ru": "❌ Лимит использований этого промокода исчерпан.",
        "en": "❌ This promo code has reached its usage limit.",
        "kk": "❌ Бұл промокодтың пайдалану шегі аяқталды.",
    },
}


async def _step_med3d_promocode(message: Message, state: FSMContext, lang: str) -> None:
    skip, back = _MED3D_PROMO_BUTTONS.get(lang) or _MED3D_PROMO_BUTTONS["uz"]
    markup = _markup([
        [InlineKeyboardButton(text=skip, callback_data="prem_m3d_promo:skip")],
        [InlineKeyboardButton(text=back, callback_data="prem_m3d_promo:back")],
    ])
    data = await state.get_data()
    await _prompt(message, state, _topic_line(data, lang) + (
        _MED3D_PROMO_TEXT.get(lang) or _MED3D_PROMO_TEXT["uz"]
    ), markup, "med3d_promo", PremiumPresentationStates.waiting_for_med3d_promocode)


@router.message(PremiumPresentationStates.waiting_for_med3d_promocode, F.text)
async def premium_med3d_promocode_input(message: Message, state: FSMContext, db: Database):
    lang = await _lang_of(message.from_user.id, db)
    try:
        promo, reason = await db.get_med3d_promocode(message.text.strip(), message.from_user.id)
    except Exception:
        logger.exception("3D Anatomiya promokodi tekshirilmadi")
        await message.answer(
            "❌ Promokodni tekshirib bo'lmadi. Iltimos, qayta urinib ko'ring:",
            reply_markup=_med3d_promo_keyboard(lang),
        )
        return
    if not promo:
        error = _MED3D_PROMO_ERRORS.get(reason, _MED3D_PROMO_ERRORS["not_found"])
        await message.answer(
            (error.get(lang) or error["uz"]) + "\n\n" +
            (_MED3D_PROMO_TEXT.get(lang) or _MED3D_PROMO_TEXT["uz"]),
            reply_markup=_med3d_promo_keyboard(lang),
        )
        return
    await _drop_prompt(message.bot, message.chat.id, state)
    await state.update_data(
        med3d_promo_code=promo["code"],
        med3d_promo_percent=promo["discount_percent"],
        med3d_promo_id=promo["id"],
    )
    accepted = {
        "uz": f"✅ Promokod qabul qilindi: {promo['discount_percent']}% chegirma.",
        "ru": f"✅ Промокод принят: скидка {promo['discount_percent']}%.",
        "en": f"✅ Promo code accepted: {promo['discount_percent']}% discount.",
        "kk": f"✅ Промокод қабылданды: {promo['discount_percent']}% жеңілдік.",
    }
    await message.answer(accepted.get(lang) or accepted["uz"])
    await _step_name(message, state, lang)


def _med3d_promo_keyboard(lang: str) -> InlineKeyboardMarkup:
    skip, back = _MED3D_PROMO_BUTTONS.get(lang) or _MED3D_PROMO_BUTTONS["uz"]
    return _markup([
        [InlineKeyboardButton(text=skip, callback_data="prem_m3d_promo:skip")],
        [InlineKeyboardButton(text=back, callback_data="prem_m3d_promo:back")],
    ])


@router.callback_query(
    F.data == "prem_m3d_promo:skip",
    PremiumPresentationStates.waiting_for_med3d_promocode,
)
async def premium_med3d_promocode_skip(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    await _drop_prompt(callback.bot, callback.message.chat.id, state)
    await _step_name(callback.message, state, lang)


@router.callback_query(
    F.data == "prem_m3d_promo:back",
    PremiumPresentationStates.waiting_for_med3d_promocode,
)
async def premium_med3d_promocode_back(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    await _drop_prompt(callback.bot, callback.message.chat.id, state)
    await _step_topic(callback.message, state, lang)


MED3D_CHECKING = {"uz": "⏳ Mavzu 3D atlas bo'yicha tekshirilmoqda...", "ru": "⏳ Проверяем тему по 3D-атласу...",
                  "en": "⏳ Checking the topic against the 3D atlas...", "kk": "⏳ Тақырып 3D атлас бойынша тексерілуде..."}
MED3D_TOPIC_NO = {
    "uz": "🫀 Bu mavzuni 3D Anatomiya taqdimotida ko'rsatib bo'lmaydi.",
    "ru": "🫀 Эту тему нельзя показать в презентации 3D Анатомия.",
    "en": "🫀 This topic cannot be shown in a 3D Anatomy presentation.",
    "kk": "🫀 Бұл тақырыпты 3D Анатомия презентациясында көрсету мүмкін емес.",
}
MED3D_TOPIC_OK = {
    "uz": "✅ Mavzu 3D uchun mos.", "ru": "✅ Тема подходит для 3D.", "en": "✅ The topic fits 3D.",
    "kk": "✅ Тақырып 3D үшін жарайды.",
}
MED3D_TOPIC_DISEASE = {
    "uz": "🩺 Kasallik mavzusida AI mavzu va istaklaringizga mos foydali bo'limlarni tanlaydi. Kerakli joylarda "
        "zararlangan 3D a'zo qizil ko'rsatiladi va AI rasmi qo'shiladi; rasm bo'lmasa, taqdimot matn va 3D bilan davom etadi.",
    "ru": "🩺 Для темы о болезни ИИ подберёт полезные разделы с учётом темы и пожеланий. При необходимости "
        "поражённый орган будет выделен красным, а ИИ добавит иллюстрацию; если изображение не создастся, презентация "
        "продолжится с текстом и 3D.",
    "en": "🩺 For disease topics, AI chooses useful sections based on the topic and your wishes. When relevant, the "
        "affected organ is highlighted in red and an AI illustration is added; if image generation fails, the deck "
        "continues with text and 3D.",
    "kk": "🩺 Ауру тақырыбында ЖИ тақырып пен қалауыңызға сай бөлімдерді таңдайды. Қажет болса, зақымданған мүше "
        "қызылмен белгіленіп, ЖИ суреті қосылады; сурет жасалмаса, презентация мәтін және 3D арқылы жалғасады.",
}


ALT_KINDS = ("info", "modern", "classic")             # 3D bo'lmasa taklif qilinadigan turlar (KIND_*)


def _med3d_choice_keyboard(lang: str, cancel: bool = False) -> InlineKeyboardMarkup:
    """3D qilib bo'lmaydigan mavzu: boshqa turlar (Infografik, Zamonaviy, Klassik), boshqa mavzu, [bekor qilish]."""
    other = {"uz": "✏️ Boshqa mavzu yozish", "ru": "✏️ Написать другую тему", "en": "✏️ Enter another topic",
             "kk": "✏️ Басқа тақырып жазу"}
    rows = [[InlineKeyboardButton(text=_KIND_BUTTONS[k].get(lang) or _KIND_BUTTONS[k]["uz"],
                                  callback_data=f"prem_m3d_alt:kind:{k}")] for k in ALT_KINDS]
    rows.append([InlineKeyboardButton(text=other.get(lang) or other["uz"], callback_data="prem_m3d_alt:mavzu")])
    if cancel:
        no = {"uz": "❌ Kerak emas", "ru": "❌ Не нужно", "en": "❌ No, thanks", "kk": "❌ Керек емес"}
        rows.append([InlineKeyboardButton(text=no.get(lang) or no["uz"], callback_data="prem_m3d_alt:yoq")])
    return _markup(rows)


async def _med3d_topic_gate(message: Message, state: FSMContext, lang: str) -> bool:
    """3D Anatomiya mavzusini darhol tekshiradi. False — davom etilmaydi (mijozga sababi va tugmalar chiqdi)."""
    from services.med3d import auto as med3d_auto

    data = await state.get_data()
    note = await message.answer(MED3D_CHECKING.get(lang) or MED3D_CHECKING["uz"])
    loop = asyncio.get_running_loop()
    try:
        verdict = await asyncio.wait_for(loop.run_in_executor(
            None, med3d_auto.check_topic, data.get("topic", ""),
            uz_script.base_language(data.get("presentation_language") or "uz")), 60)
    except Exception as exc:                          # noqa: BLE001
        logger.warning("3D mavzu tekshiruvi: %s", exc)
        verdict = {"ok": True, "kind": "anatomy", "reason": ""}
    await state.update_data(m3d_topic_kind=verdict.get("kind", "anatomy"))
    if not verdict.get("ok"):
        reason = verdict.get("reason") or ""
        text = (MED3D_TOPIC_NO.get(lang) or MED3D_TOPIC_NO["uz"]) + (f"\n<i>{reason}</i>" if reason else "")
        text += "\n\n" + (MED3D_ALT_ASK.get(lang) or MED3D_ALT_ASK["uz"])
        with contextlib.suppress(Exception):
            await note.edit_text(text, parse_mode="HTML", reply_markup=_med3d_choice_keyboard(lang))
        return False
    if verdict.get("kind") == "disease":
        text = (MED3D_TOPIC_OK.get(lang) or MED3D_TOPIC_OK["uz"]) + "\n" + \
            (MED3D_TOPIC_DISEASE.get(lang) or MED3D_TOPIC_DISEASE["uz"])
    else:
        text = MED3D_TOPIC_OK.get(lang) or MED3D_TOPIC_OK["uz"]
    with contextlib.suppress(Exception):
        await note.edit_text(text)
    return True


THREE_D_CHECKING = {"uz": "⏳ Mavzuga mos 3D modellar qidirilmoqda...", "ru": "⏳ Ищем 3D-модели по теме...",
                    "en": "⏳ Looking for 3D models for the topic...", "kk": "⏳ Тақырыпқа сай 3D модельдер ізделуде..."}
THREE_D_FOUND = {
    "uz": "✅ Mavzuga mos <b>{n} ta 3D model</b> topildi — taqdimot shular bilan yasaladi:",
    "ru": "✅ Найдено <b>{n} 3D-моделей</b> по теме — презентация будет сделана с ними:",
    "en": "✅ Found <b>{n} 3D models</b> for the topic — the deck will be built with them:",
    "kk": "✅ Тақырыпқа сай <b>{n} 3D модель</b> табылды — презентация солармен жасалады:",
}
THREE_D_NONE = {
    "uz": "😔 Bu mavzu bo'yicha katalogimizda mos 3D model topilmadi.",
    "ru": "😔 По этой теме в нашем каталоге нет подходящих 3D-моделей.",
    "en": "😔 Our catalog has no matching 3D models for this topic.",
    "kk": "😔 Бұл тақырып бойынша каталогымызда сай 3D модель табылмады.",
}


async def _three_d_topic_gate(message: Message, state: FSMContext, lang: str) -> bool:
    """3D bo'limi: mavzu yozilishi bilan (to'lovdan oldin) — tana tuzilishimi (3D Anatomiya) yoki katalogda
    mos 3D modellar bormi (3D taqdimot). Topilgan modellar mijozga ko'rsatiladi va buyurtmada saqlanadi —
    taqdimot aynan shular bilan yasaladi. Hech narsa topilmasa — False (boshqa tur taklif qilinadi)."""
    from services.kat3d import qidiruv
    from services.med3d import auto as med3d_auto

    data = await state.get_data()
    topic = data.get("topic", "")
    language = uz_script.base_language(data.get("presentation_language") or "uz")
    note = await message.answer(THREE_D_CHECKING.get(lang) or THREE_D_CHECKING["uz"])
    loop = asyncio.get_running_loop()
    med_job = loop.run_in_executor(None, med3d_auto.check_topic, topic, language)
    kat_job = loop.run_in_executor(None, qidiruv.top, topic, language)
    try:
        med = await asyncio.wait_for(med_job, 60)
    except Exception as exc:                          # noqa: BLE001
        logger.warning("3D anatomiya tekshiruvi: %s", exc)
        med = {"ok": False, "checked": False}
    try:
        kat = await asyncio.wait_for(kat_job, 90)
    except Exception as exc:                          # noqa: BLE001
        logger.warning("3D katalog qidiruvi: %s", exc)
        kat = {"ok": False, "ids": []}

    anatomy = med.get("ok") and med.get("checked", True)
    if anatomy or (med.get("ok") and not kat.get("ok")):      # AI javob bermasa — avvalgidek 3D Anatomiya
        await state.update_data(kind=KIND_MED3D, kat3d_ids=[], m3d_topic_kind=med.get("kind", "anatomy"))
        text = MED3D_TOPIC_OK.get(lang) or MED3D_TOPIC_OK["uz"]
        if med.get("kind") == "disease":
            text += "\n" + (MED3D_TOPIC_DISEASE.get(lang) or MED3D_TOPIC_DISEASE["uz"])
        with contextlib.suppress(Exception):
            await note.edit_text(text)
        return True
    if kat.get("ok") and kat.get("ids"):
        from services import katalog3d

        ids = list(kat["ids"])
        await state.update_data(kind=KIND_KAT3D, kat3d_ids=ids, m3d_style="", m3d_topic_kind=None)
        with contextlib.suppress(Exception):          # serverda yo'qlari fonda yuklana boshlaydi — to'lovgacha tayyor
            from services.kat3d import yukla

            yukla.oldindan(ids)
        cat = katalog3d.katalog()
        names = [cat[i]["nom_uz"] if lang == "uz" else cat[i]["nom"] for i in ids[:8]]
        lines = "\n".join(f"• {html.escape(n)}" for n in names)
        more = f"\n• … +{len(ids) - 8}" if len(ids) > 8 else ""
        text = (THREE_D_FOUND.get(lang) or THREE_D_FOUND["uz"]).format(n=len(ids)) + f"\n{lines}{more}"
        with contextlib.suppress(Exception):
            await note.edit_text(text, parse_mode="HTML")
        with contextlib.suppress(Exception):
            from aiogram.types import BufferedInputFile

            picture = await loop.run_in_executor(None, qidiruv.collage, ids, lang)
            if picture:
                await message.answer_photo(BufferedInputFile(picture, filename="3d.jpg"))
        return True
    text = (THREE_D_NONE.get(lang) or THREE_D_NONE["uz"]) + "\n\n" + (MED3D_ALT_ASK.get(lang) or MED3D_ALT_ASK["uz"])
    with contextlib.suppress(Exception):
        await note.edit_text(text, parse_mode="HTML", reply_markup=_med3d_choice_keyboard(lang))
    return False


async def _step_script(message: Message, state: FSMContext, lang: str) -> None:
    markup = _markup([[InlineKeyboardButton(text=_t(lang, "script_latin"), callback_data="prem_ppt_script:latin"),
                       InlineKeyboardButton(text=_t(lang, "script_cyrillic"), callback_data="prem_ppt_script:cyrillic")],
                      [InlineKeyboardButton(text=_t(lang, "script_latin_new"),
                                            callback_data=f"prem_ppt_script:{uz_script.LATIN_NEW}")],
                      _back_row(lang)])
    data = await state.get_data()
    await _prompt(message, state, _topic_line(data, lang) + _t(lang, "ask_script"), markup,
                  "script", PremiumPresentationStates.waiting_for_script)


@router.callback_query(F.data.startswith("prem_ppt_script:"),
                       PremiumPresentationStates.waiting_for_script)
async def premium_ppt_got_script(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    choice = callback.data.split(":", 1)[1]
    data = await state.get_data()
    topic = data.get("topic", "")
    if choice == uz_script.LATIN:
        topic, language = uz_script.to_latin(topic), "uz"
    elif choice == uz_script.LATIN_NEW:
        # Mavzu modelga eski lotinda beriladi; tayyor fayl yangi alifboga o'giriladi.
        topic, language = uz_script.to_latin(topic), uz_script.UZ_NEW_LANG
    else:
        language = uz_script.UZ_CYRILLIC_LANG
    await _drop_prompt(callback.bot, callback.message.chat.id, state)
    await state.update_data(topic=topic, presentation_language=language, script_asked=True)
    await _after_topic(callback.message, state, lang)


# ── 2. Ism

async def _step_name(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    markup = _markup([[InlineKeyboardButton(text=_t(lang, "skip"),
                                            callback_data="prem_ppt_skip_name")],
                      _back_row(lang)])
    await _prompt(message, state, _topic_line(data, lang) + _t(lang, "ask_name"), markup,
                  "name", PremiumPresentationStates.waiting_for_client_name)


@router.message(PremiumPresentationStates.waiting_for_client_name)
async def premium_ppt_got_name(message: Message, state: FSMContext, db: Database):
    lang = await _lang_of(message.from_user.id, db)
    await _drop_prompt(message.bot, message.chat.id, state)
    await state.update_data(client_name=(message.text or "").strip())
    await _step_prefs(message, state, lang)


@router.callback_query(F.data == "prem_ppt_skip_name",
                       PremiumPresentationStates.waiting_for_client_name)
async def premium_ppt_skip_name(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    await _drop_prompt(callback.bot, callback.message.chat.id, state)
    await state.update_data(client_name="")
    await _step_prefs(callback.message, state, lang)


# ── 3. AI ga tushuntirish

async def _step_prefs(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    markup = _markup([[InlineKeyboardButton(text=_t(lang, "skip"),
                                            callback_data="prem_ppt_skip_preferences")],
                      _back_row(lang)])
    await _prompt(message, state, _topic_line(data, lang) + _t(lang, "ask_prefs"), markup,
                  "prefs", PremiumPresentationStates.waiting_for_preferences)


@router.message(PremiumPresentationStates.waiting_for_preferences)
async def premium_ppt_got_preferences(message: Message, state: FSMContext, db: Database):
    lang = await _lang_of(message.from_user.id, db)
    await _drop_prompt(message.bot, message.chat.id, state)
    await state.update_data(preferences=(message.text or "").strip())
    await _after_prefs(message, state, lang, db)


@router.callback_query(F.data == "prem_ppt_skip_preferences",
                       PremiumPresentationStates.waiting_for_preferences)
async def premium_ppt_skip_preferences(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    await _drop_prompt(callback.bot, callback.message.chat.id, state)
    await state.update_data(preferences="")
    await _after_prefs(callback.message, state, lang, db)


async def _after_prefs(message: Message, state: FSMContext, lang: str, db: Database) -> None:
    """Istaklardan keyin — manba; 3D Anatomiyada manba kerak emas (organlar atlasdan) — darhol slaydlar soni."""
    kind = _kind_of(await state.get_data())
    if kind == KIND_MED3D:
        await state.update_data(source_text="", source_label="")
        await _step_m3d_style(message, state, lang)
    elif kind == KIND_KAT3D:                      # modellar topilgan, uslubni AI mavzuga qarab tanlaydi
        await state.update_data(source_text="", source_label="")
        await _step_count(message, state, lang, db)
    else:
        await _step_source(message, state, lang)


# ── 4. Manba: AI o'zi, matn, fayl yoki sayt

async def _step_source(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    text = _topic_line(data, lang) + get_text(lang, "prem_ppt_ask_source")
    markup = get_project_source_keyboard(lang, prefix="prem_ppt", back="prem_ppt_prev")
    await _prompt(message, state, text, markup, "source",
                  PremiumPresentationStates.waiting_for_source_kind)


@router.callback_query(F.data.startswith("prem_ppt_source:"),
                       PremiumPresentationStates.waiting_for_source_kind)
async def premium_ppt_chose_source(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    kind = callback.data.split(":", 1)[1]

    if kind == source_module.KIND_AI:
        await state.update_data(source_kind=source_module.KIND_AI,
                                source_text="", source_label="")
        await _after_source(callback.message, state, lang, db)
        return

    prompts = {
        source_module.KIND_TEXT: ("prem_ppt_ask_instructions",
                                  PremiumPresentationStates.waiting_for_instructions),
        source_module.KIND_FILE: ("pw_ask_file",
                                  PremiumPresentationStates.waiting_for_source_file),
        source_module.KIND_URL: ("pw_ask_urls",
                                 PremiumPresentationStates.waiting_for_source_urls),
    }
    key, next_state = prompts[kind]
    await state.update_data(source_kind=kind)
    await _prompt(callback.message, state, get_text(lang, key),
                  _markup([_back_row(lang)]), "source_input", next_state)


@router.message(PremiumPresentationStates.waiting_for_instructions, F.text)
async def premium_ppt_got_instructions(message: Message, state: FSMContext, db: Database):
    lang = await _lang_of(message.from_user.id, db)
    material = source_module.from_instructions(message.text or "")
    if not material.has_content:
        await message.answer(get_text(lang, "prem_ppt_ask_instructions"), parse_mode="HTML")
        return
    await _store_source(message, state, lang, material, db)


@router.message(PremiumPresentationStates.waiting_for_source_file, F.document)
async def premium_ppt_got_source_file(message: Message, state: FSMContext, db: Database):
    lang = await _lang_of(message.from_user.id, db)
    upload = await uploads.receive(message, lang, accept=uploads.DOCUMENTS,
                                   prefix="prem_src")
    if upload is None:
        return

    await _drop_prompt(message.bot, message.chat.id, state)
    status = await message.answer(get_text(lang, "pw_source_reading"))
    try:
        material = source_module.from_extract(upload.extract, upload.file_name)
    except Exception as e:
        logger.error("Taqdimot manbasi o'qilmadi: %s", e)
        await status.edit_text(get_text(lang, "pw_source_failed"))
        await _step_source(message, state, lang)
        return
    finally:
        uploads.discard(upload)

    await status.delete()
    await _store_source(message, state, lang, material, db)


@router.message(PremiumPresentationStates.waiting_for_source_urls, F.text)
async def premium_ppt_got_source_urls(message: Message, state: FSMContext, db: Database):
    from services.url_book_service import extract_urls_from_text, validate_url

    lang = await _lang_of(message.from_user.id, db)
    urls = [url for url in extract_urls_from_text(message.text or "") if validate_url(url)[0]]
    if not urls:
        await message.answer(get_text(lang, "pw_ask_urls"), parse_mode="HTML")
        return

    await _drop_prompt(message.bot, message.chat.id, state)
    status = await message.answer(get_text(lang, "pw_source_reading"))
    try:
        material = await source_module.from_urls(urls[:5])
    except Exception as e:
        logger.error("Taqdimot uchun saytdan matn olinmadi: %s", e)
        await status.edit_text(get_text(lang, "pw_source_failed"))
        await _step_source(message, state, lang)
        return

    await status.delete()
    await _store_source(message, state, lang, material, db)


async def _store_source(message: Message, state: FSMContext, lang: str, material, db: Database):
    await _drop_prompt(message.bot, message.chat.id, state)
    await state.update_data(source_kind=material.kind, source_text=material.text,
                            source_label=material.label)
    if material.label:
        await message.answer(
            get_text(lang, "pw_source_ok", label=material.label,
                     words=len(material.text.split())),
            parse_mode="HTML")
    await _after_source(message, state, lang, db)


async def _after_source(message: Message, state: FSMContext, lang: str, db: Database) -> None:
    """Manbadan keyin: zamonaviyda — uslub, qolgan turlarda — darhol slaydlar soni (tur boshida tanlangan)."""
    if _kind_of(await state.get_data()) == KIND_MODERN:
        await _step_style(message, state, lang)
    else:
        await _step_count(message, state, lang, db)


# ── 4b. Taqdimot turi: infografik / zamonaviy / klassik
# Ilgari uch xil mahsulot bitta uslub ro'yxatida aralashgan edi: eng yangi infografik dizayn uslub va
# "matn hajmi" qadamlari ortida yashirinardi. Endi mijoz turini birinchi tanlaydi; tur keraksiz
# qadamlarni o'zi belgilaydi (infografik — uslub va hajm so'ralmaydi, klassik — shablonlarga o'tadi).
# Faqat tugmalar — namuna rasm yuborilmaydi.

KIND_INFO, KIND_MODERN, KIND_CLASSIC = "info", "modern", "classic"
# 3D Pro: har slaydda fonsiz 3D obyekt, yorliq-chiziqlar va PowerPoint Morph o'tishlari (`services.pro3d`).
KIND_PRO3D = "pro3d"
# 3D Anatomiya: inson tanasi tuzilishi — atlasdagi haqiqiy 3D organ modellari va Morph (`services.med3d`).
KIND_MED3D = "med3d"
# 3D taqdimot (katalog): tarix, tabiat, texnika... — katalogdagi haqiqiy 3D modellar va Morph (`services.kat3d`).
# Alohida tugmasi yo'q: 3D bo'limida mavzu tana tuzilishiga oid bo'lmasa va katalogda mos model topilsa.
KIND_KAT3D = "kat3d"
KINDS = (KIND_MED3D, KIND_KAT3D, KIND_PRO3D, KIND_INFO, KIND_MODERN, KIND_CLASSIC)
# 3D Anatomiya alohida asosiy menyu tugmasi; 3D Pro eski buyurtmalar uchun saqlanadi.
MENU_KINDS = (KIND_INFO, KIND_MODERN, KIND_CLASSIC)
# Infografik tur uchun uslub so'ralmaydi: vektor dizayner ko'rinishni o'zi tanlaydi.
INFO_STYLE = "toza"
_KIND_BUTTONS = {
    KIND_MED3D: {"uz": "🫀 3D taqdimot — tana tuzilishi", "ru": "🫀 3D презентация — строение тела",
                 "en": "🫀 3D presentation — human body", "kk": "🫀 3D презентация — дене құрылысы"},
    KIND_PRO3D: {"uz": "🧊 3D Pro — animatsiyali, yangi", "ru": "🧊 3D Pro — с анимацией, новинка",
                 "en": "🧊 3D Pro — animated, new", "kk": "🧊 3D Pro — анимациялы, жаңа"},
    KIND_INFO: {"uz": "🎨 Infografik — yangi", "ru": "🎨 Инфографика — новинка",
                "en": "🎨 Infographic — new", "kk": "🎨 Инфографика — жаңа"},
    KIND_MODERN: {"uz": "📝 Zamonaviy — batafsil matn", "ru": "📝 Современная — подробный текст",
                  "en": "📝 Modern — detailed text", "kk": "📝 Заманауи — толық мәтін"},
    KIND_CLASSIC: {"uz": "📄 Klassik — tayyor shablonlar", "ru": "📄 Классическая — готовые шаблоны",
                   "en": "📄 Classic — ready templates", "kk": "📄 Классикалық — дайын үлгілер"},
}
_KIND_NAMES = {
    KIND_MED3D: {"uz": "3D Anatomiya", "ru": "3D Анатомия", "en": "3D Anatomy", "kk": "3D Анатомия"},
    KIND_PRO3D: {"uz": "3D Pro", "ru": "3D Pro", "en": "3D Pro", "kk": "3D Pro"},
    KIND_KAT3D: {"uz": "3D taqdimot", "ru": "3D-презентация", "en": "3D presentation", "kk": "3D презентация"},
    KIND_INFO: {"uz": "Infografik", "ru": "Инфографика", "en": "Infographic", "kk": "Инфографика"},
    KIND_MODERN: {"uz": "Zamonaviy", "ru": "Современная", "en": "Modern", "kk": "Заманауи"},
    KIND_CLASSIC: {"uz": "Klassik", "ru": "Классическая", "en": "Classic", "kk": "Классикалық"},
}
_KIND_PROMPT = {
    "uz": "🖼 <b>Taqdimot turini tanlang</b>",
    "ru": "🖼 <b>Выберите тип презентации</b>",
    "en": "🖼 <b>Choose the presentation type</b>",
    "kk": "🖼 <b>Презентация түрін таңдаңыз</b>",
}


def _kind_name(key: str, lang: str) -> str:
    names = _KIND_NAMES.get(key) or _KIND_NAMES[KIND_MODERN]
    return names.get(lang) or names["uz"]


def _kind_of(data: dict) -> str:
    """Buyurtma turi (eski buyurtmalarda tur yo'q — uslub va hajmdan aniqlanadi)."""
    kind = data.get("kind")
    if kind in KINDS:
        return kind
    if data.get("style") == SIMPLE_STYLE:
        return KIND_CLASSIC
    return KIND_INFO if data.get("volume") == "kam" else KIND_MODERN


# 3D Pro hozircha faqat adminlar uchun: boshqalarga tugmada «tez orada» yoziladi va u ishlamaydi.
_PRO3D_SOON_BUTTON = {"uz": "🧊 3D Pro — ⏳ tez orada", "ru": "🧊 3D Pro — ⏳ скоро",
                      "en": "🧊 3D Pro — ⏳ coming soon", "kk": "🧊 3D Pro — ⏳ жақында"}
_PRO3D_SOON_ALERT = {"uz": "⏳ 3D Pro tez orada ishga tushadi!", "ru": "⏳ 3D Pro скоро будет доступен!",
                     "en": "⏳ 3D Pro is coming soon!", "kk": "⏳ 3D Pro жақында іске қосылады!"}


def _pro3d_open(user_id: int) -> bool:
    import config

    return user_id in config.ADMIN_IDS


# 3D Anatomiya: hammaga ochiq. Vaqtincha yopish (faqat adminlar) — serverda MED3D_OCHIQ=0.
_MED3D_SOON_BUTTON = {"uz": "🫀 3D Anatomiya — ⏳ tez orada", "ru": "🫀 3D Анатомия — ⏳ скоро",
                      "en": "🫀 3D Anatomy — ⏳ coming soon", "kk": "🫀 3D Анатомия — ⏳ жақында"}


def _med3d_open(user_id: int) -> bool:
    import config

    return os.getenv("MED3D_OCHIQ", "1") != "0" or user_id in config.ADMIN_IDS


# Tugma bosilganda BIRINCHI aytiladi: bu tur faqat tana tuzilishi uchun. Mijoz "Ha" bosmasa — davom etmaydi.
MED3D_WARNING = {
    "uz": ("🫀 <b>3D Anatomiya</b> — faqat <b>inson tanasi tuzilishi</b> mavzulari uchun: organlar, suyaklar, "
           "mushaklar, yurak, miya, hazm, nafas, siydik va jinsiy a'zolar tizimlari.\n\n"
           "Har slaydda haqiqiy 3D organ modeli bo'ladi: u aylanadi, qismlarga ajraladi, yorliqlar bilan "
           "ko'rsatiladi. Taqdimot <b>kompyuterdagi PowerPoint</b> (2019, 2021, 365) uchun — telefonda 3D "
           "ko'rinmaydi.\n\n<b>Mavzuingiz tana tuzilishiga oidmi?</b>"),
    "ru": ("🫀 <b>3D Анатомия</b> — только для тем о <b>строении тела человека</b>: органы, кости, мышцы, "
           "сердце, мозг, пищеварительная, дыхательная, мочевая и половая системы.\n\n"
           "На каждом слайде настоящая 3D-модель органа: вращается, разделяется на части, подписана. "
           "Презентация для <b>PowerPoint на компьютере</b> (2019, 2021, 365) — на телефоне 3D не видно.\n\n"
           "<b>Ваша тема о строении тела?</b>"),
    "en": ("🫀 <b>3D Anatomy</b> is only for topics about <b>the structure of the human body</b>: organs, bones, "
           "muscles, heart, brain, digestive, respiratory, urinary and reproductive systems.\n\n"
           "Every slide has a real 3D organ model that turns, splits into parts and is labelled. The "
           "presentation is for <b>PowerPoint on a computer</b> (2019, 2021, 365) — phones do not show 3D.\n\n"
           "<b>Is your topic about the human body?</b>"),
    "kk": ("🫀 <b>3D Анатомия</b> — тек <b>адам денесінің құрылысы</b> тақырыптарына арналған: мүшелер, "
           "сүйектер, бұлшықеттер, жүрек, ми, ас қорыту, тыныс алу, зәр шығару және жыныс жүйелері.\n\n"
           "Әр слайдта нақты 3D мүше моделі болады. Презентация <b>компьютердегі PowerPoint</b> үшін "
           "(2019, 2021, 365) — телефонда 3D көрінбейді.\n\n<b>Тақырыбыңыз дене құрылысына қатысты ма?</b>"),
}
_MED3D_YES_NO = {"uz": ("✅ Ha", "❌ Yo'q"), "ru": ("✅ Да", "❌ Нет"), "en": ("✅ Yes", "❌ No"),
                 "kk": ("✅ Иә", "❌ Жоқ")}
MED3D_NOT_FOR_YOU = {
    "uz": "🙂 Unda bu bo'lim siz uchun emas: 3D Anatomiya faqat inson tanasi tuzilishi mavzulari uchun. "
          "Boshqa turni tanlang.",
    "ru": "🙂 Тогда этот раздел не для вас: 3D Анатомия — только для тем о строении тела человека. "
          "Выберите другой тип.",
    "en": "🙂 Then this section is not for you: 3D Anatomy is only for topics about the human body. "
          "Please choose another type.",
    "kk": "🙂 Онда бұл бөлім сізге арналмаған: 3D Анатомия тек адам денесінің құрылысы тақырыптарына арналған. "
          "Басқа түрін таңдаңыз.",
}


# 3D Anatomiya: dizayn uslubi (namuna rasmi bilan). «Avtomatik» — mavzuga qarab tizim tanlaydi.
_M3D_STYLE_ASK = {
    "uz": "🎨 <b>Dizayn uslubini tanlang</b>\nRasmda 12 uslubning namunasi. «🎲 Avtomatik» — mavzuga mos uslubni "
          "tizim o'zi tanlaydi.",
    "ru": "🎨 <b>Выберите стиль оформления</b>\nНа картинке — 12 стилей. «🎲 Автоматически» — стиль под тему "
          "подберёт система.",
    "en": "🎨 <b>Choose a design style</b>\nThe picture shows all 12 styles. «🎲 Automatic» lets the system pick a "
          "style for the topic.",
    "kk": "🎨 <b>Дизайн стилін таңдаңыз</b>\nСуретте 12 стиль үлгісі. «🎲 Автоматты» — тақырыпқа сай стильді жүйе "
          "өзі таңдайды.",
}
_M3D_AUTO = {"uz": "🎲 Avtomatik", "ru": "🎲 Автоматически", "en": "🎲 Automatic", "kk": "🎲 Автоматты"}
M3D_STYLES_PREVIEW = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                  "assets", "med3d", "uslublar.jpg")


async def _step_m3d_style(message: Message, state: FSMContext, lang: str) -> None:
    from aiogram.types import FSInputFile
    from services.med3d import design

    rows, row = [], []
    for key in design.STYLE_ORDER:
        row.append(InlineKeyboardButton(text=f"{design.STYLE_EMOJI.get(key, '')} {design.style_name(key, lang)}",
                                        callback_data=f"prem_m3d_style:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=_M3D_AUTO.get(lang) or _M3D_AUTO["uz"], callback_data="prem_m3d_style:auto")])
    markup = _markup(rows + [_back_row(lang)])
    data = await state.get_data()
    text = _topic_line(data, lang) + (_M3D_STYLE_ASK.get(lang) or _M3D_STYLE_ASK["uz"])
    await _drop_prompt(message.bot, message.chat.id, state)
    await state.set_state(PremiumPresentationStates.waiting_for_style)
    sent = None
    if os.path.exists(M3D_STYLES_PREVIEW):
        try:
            sent = await message.answer_photo(FSInputFile(M3D_STYLES_PREVIEW), caption=text, parse_mode="HTML",
                                              reply_markup=markup)
        except Exception as exc:              # rasm ketmasa ham tanlov ishlasin
            logger.warning("3D uslublar rasmi yuborilmadi: %s", exc)
    if sent is None:
        sent = await message.answer(text, parse_mode="HTML", reply_markup=markup)
    await state.update_data(prompt_mid=sent.message_id, step="m3dstyle")


def _m3d_style_label(data: dict, lang: str) -> str:
    from services.med3d import design

    key = data.get("m3d_style") or ""
    if key in design.STYLES:
        return f"{design.STYLE_EMOJI.get(key, '')} {design.style_name(key, lang)}"
    return _M3D_AUTO.get(lang) or _M3D_AUTO["uz"]


def _kind_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key in MENU_KINDS:
        labels = _KIND_BUTTONS[key]
        builder.button(text=labels.get(lang) or labels["uz"], callback_data=f"prem_ppt_kind:{key}")
    builder.adjust(1)
    builder.row(*_back_row(lang))
    return builder.as_markup()


async def _step_kind(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    if data.get("standalone_med3d"):              # 3D bo'limi turdan emas, mavzudan boshlanadi
        await _step_topic(message, state, lang)
        return
    text = _topic_line(data, lang) + (_KIND_PROMPT.get(lang) or _KIND_PROMPT["uz"])
    # Shaxsiy chatda chat id = foydalanuvchi id (orqaga qaytishda xabar botniki bo'ladi).
    keyboard = _kind_keyboard(lang)
    await _prompt(message, state, text, keyboard, "kind", PremiumPresentationStates.waiting_for_kind)


async def _step_med3d_confirmation(message: Message, state: FSMContext, lang: str) -> None:
    yes, no = _MED3D_YES_NO.get(lang) or _MED3D_YES_NO["uz"]
    markup = _markup([[InlineKeyboardButton(text=yes, callback_data="prem_med3d:ha"),
                       InlineKeyboardButton(text=no, callback_data="prem_med3d:yoq")]])
    await _prompt(message, state, MED3D_WARNING.get(lang) or MED3D_WARNING["uz"], markup, "kind",
                  PremiumPresentationStates.waiting_for_kind)


async def _set_kind(state: FSMContext, kind: str) -> None:
    """Tur tanlanganda uning boshlang'ich sozlamalari (uslub, matn hajmi)."""
    await state.update_data(kind=kind)
    if kind == KIND_CLASSIC:
        await state.update_data(style=SIMPLE_STYLE, volume="")
    elif kind == KIND_PRO3D:
        # Uslub ham, matn hajmi ham so'ralmaydi: rang va ko'rinishni AI mavzuga qarab tanlaydi.
        await state.update_data(style="", volume="")
        with contextlib.suppress(Exception):     # fon olib tashlash modeli oldindan tayyorlansin
            from services.pro3d import cutout

            cutout.warm()
    elif kind == KIND_INFO:
        await state.update_data(style=INFO_STYLE, volume="kam")
    else:
        await state.update_data(style="", volume="kop")


@router.callback_query(F.data.startswith("prem_ppt_kind:"), PremiumPresentationStates.waiting_for_kind)
async def premium_ppt_kind_selected(callback: CallbackQuery, state: FSMContext, db: Database):
    """Tur tanlandi (birinchi qadam) — keyin mavzu. Tur keyingi qadamlarni belgilaydi: zamonaviyda manbadan
    keyin uslub so'raladi, infografik, 3D Pro va klassikda — darhol slaydlar soni."""
    lang = await _lang_of(callback.from_user.id, db)
    kind = callback.data.split(":", 1)[1]
    if kind == KIND_MED3D:  # old presentation prompts may still contain this choice
        if not _med3d_open(callback.from_user.id):
            await callback.answer(_MED3D_SOON_BUTTON.get(lang) or _MED3D_SOON_BUTTON["uz"],
                                  show_alert=True)
            return
        await callback.answer()
        await _step_med3d_confirmation(callback.message, state, lang)
        return
    if kind not in MENU_KINDS:                    # old 3D Pro prompts are no longer offered
        await callback.answer()
        await _step_kind(callback.message, state, lang)
        return
    await callback.answer()
    if kind not in KINDS:
        kind = KIND_INFO
    await _set_kind(state, kind)
    # Mavzu allaqachon yozilgan bo'lsa (orqaga qaytib turni almashtirgan) — u saqlanadi, so'rov qayta chiqadi.
    await _step_topic(callback.message, state, lang)


@router.callback_query(F.data.startswith("prem_m3d_style:"), PremiumPresentationStates.waiting_for_style)
async def premium_m3d_style(callback: CallbackQuery, state: FSMContext, db: Database):
    """3D Anatomiya uslubi tanlandi (yoki «Avtomatik») — keyin slaydlar soni."""
    from services.med3d import design

    await callback.answer()
    key = callback.data.split(":", 1)[1]
    await state.update_data(m3d_style=key if key in design.STYLES else "")
    await _step_count(callback.message, state, await _lang_of(callback.from_user.id, db), db)


@router.callback_query(F.data.startswith("prem_med3d:"), PremiumPresentationStates.waiting_for_kind)
async def premium_med3d_answer(callback: CallbackQuery, state: FSMContext, db: Database):
    """3D Anatomiya ogohlantirishiga javob: "Ha" — mavzu so'raladi, "Yo'q" — bu bo'lim siz uchun emas."""
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    if callback.data.endswith(":ha") and _med3d_open(callback.from_user.id):
        await state.update_data(kind=KIND_MED3D, style="", volume="")
        await _step_topic(callback.message, state, lang)
        return
    with contextlib.suppress(Exception):
        await callback.message.edit_text(MED3D_NOT_FOR_YOU.get(lang) or MED3D_NOT_FOR_YOU["uz"])
        await state.update_data(prompt_mid=None, standalone_med3d=False)  # "bu siz uchun emas" xabari qolsin
    await _step_kind(callback.message, state, lang)


# ── 5. Uslub

def _simple_price(count: int):
    from config import PRESENTATION_PRICES
    return PRESENTATION_PRICES.get(count)


def _style_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key in _STYLE_ORDER:
        if key == SIMPLE_STYLE:
            continue        # "Chiroyli orqa fonlar" endi alohida tur — "Klassik"
        builder.button(text=_STYLE_BUTTONS[key].get(lang) or _STYLE_BUTTONS[key]["uz"],
                       callback_data=f"ppt_style:{key}")
    builder.adjust(1)
    builder.row(*_back_row(lang))
    return builder.as_markup()


async def _step_style(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    text = _topic_line(data, lang) + _t(lang, "ask_style")
    await _prompt(message, state, text, _style_keyboard(lang), "style",
                  PremiumPresentationStates.waiting_for_style)


@router.callback_query(F.data.startswith("ppt_style:"),
                       PremiumPresentationStates.waiting_for_style)
async def premium_ppt_style_selected(callback: CallbackQuery, state: FSMContext, db: Database):
    """Uslub tanlandi: "Chiroyli orqa fonlar" — oddiy oqim, qolgani — zamonaviy."""
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    key = callback.data.split(":", 1)[1]

    if key == SIMPLE_STYLE:
        await state.update_data(style=SIMPLE_STYLE)
        await _step_count(callback.message, state, lang, db)
        return

    from services.premium_presentation import deck_styles
    if key not in deck_styles.STYLES:
        key = "toza"
    # Matn hajmi alohida so'ralmaydi: "Zamonaviy" turi — batafsil matn.
    await state.update_data(style=key, kind=KIND_MODERN, volume="kop")
    await _step_count(callback.message, state, lang, db)


# ── 6. Hajm — narxlar tanlangan uslubga qarab ko'rsatiladi

def _count_options(style: str, kind: str = ""):
    """[(slaydlar soni, narx)] — orqa fonlarda faqat 10/15/20, 3D Pro da 20 tagacha."""
    if style == SIMPLE_STYLE:
        from config import PRESENTATION_PRICES
        return sorted(PRESENTATION_PRICES.items())
    if kind == KIND_PRO3D:
        import services.pro3d as pro3d

        return [(n, pro3d.price_for(n)) for n in pro3d.SLIDE_OPTIONS]
    if kind == KIND_MED3D:
        from services.med3d import auto as med3d_auto

        return [(n, med3d_auto.price_for(n)) for n in med3d_auto.SLIDE_OPTIONS]
    if kind == KIND_KAT3D:
        import services.kat3d as kat3d

        return [(n, kat3d.price_for(n)) for n in kat3d.SLIDE_OPTIONS]
    return [(n, _get_price(n)) for n in (5, 8, 10, 12, 15, 20, 25, 30)]


def _count_keyboard(lang: str, style: str = "", kind: str = "") -> InlineKeyboardMarkup:
    word = {"uz": "ta slayd", "ru": "слайдов", "en": "slides"}.get(lang, "ta slayd")
    som = {"uz": "so'm", "ru": "сум", "en": "soʻm"}.get(lang, "so'm")
    prefix = "ppt_fon" if style == SIMPLE_STYLE else "prem_ppt_count"
    builder = InlineKeyboardBuilder()
    for count, price in _count_options(style, kind):
        builder.button(text=f"{count} {word} | {price:,} {som}",
                       callback_data=f"{prefix}:{count}")
    builder.adjust(2 if style != SIMPLE_STYLE else 1)
    builder.row(*_back_row(lang))
    return builder.as_markup()


async def _balance_of(db: Database, user_id: int) -> int:
    with contextlib.suppress(Exception):
        user = await db.get_user(user_id)
        return int(getattr(user, "balance", 0) or 0)
    return 0


async def _step_count(message: Message, state: FSMContext, lang: str, db: Database) -> None:
    data = await state.get_data()
    style = data.get("style") or ""
    balance = await _balance_of(db, message.chat.id)
    kind = _kind_of(data)
    style_name = _kind_name(kind, lang) + (f" · {_style_name(style or 'toza', lang)}" if kind == KIND_MODERN else "")
    lines = [_t(lang, "ask_count"), "", _t(lang, "count_style", style=style_name),
             _t(lang, "count_balance", balance=f"{balance:,}"), "",
             _t(lang, "count_hint_fon" if style == SIMPLE_STYLE else "count_hint")]
    await _prompt(message, state, _topic_line(data, lang) + "\n".join(lines),
                  _count_keyboard(lang, style, kind), "count",
                  PremiumPresentationStates.waiting_for_count)


@router.callback_query(F.data.startswith("prem_ppt_count:"),
                       PremiumPresentationStates.waiting_for_count)
async def premium_ppt_got_count(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    count = max(MIN_SLIDES, min(int(callback.data.split(":")[1]), MAX_SLIDES))
    await state.update_data(slide_count=count)
    await _after_count(callback.message, state, lang)


async def _after_count(message: Message, state: FSMContext, lang: str) -> None:
    """Slaydlar sonidan keyin: rasm manbasi (zamonaviy, infografika), so'ng yozuv animatsiyasi, so'ng xulosa."""
    if _photo_source(await state.get_data()) is not None:
        await _step_photos(message, state, lang)
    else:
        await _after_photos(message, state, lang)


_PHOTO_STEP = {
    "uz": ("🖼 <b>Taqdimotdagi rasmlar qayerdan olinsin?</b>",
           {"web": "internetdagi haqiqiy fotosuratlar (topilmagan joyda rasm o'rniga matn)",
            "ai": "rasmlarni sun'iy intellekt chizadi — har slaydga mos",
            "mix": "avval internetdan, topilmaganini AI chizadi (tavsiya)"}),
    "ru": ("🖼 <b>Откуда брать изображения?</b>",
           {"web": "настоящие фото из интернета (где не найдено — текст)",
            "ai": "изображения рисует ИИ — под каждый слайд",
            "mix": "сначала из интернета, недостающие рисует ИИ (рекомендуем)"}),
    "en": ("🖼 <b>Where should the images come from?</b>",
           {"web": "real photos from the web (text where none is found)",
            "ai": "AI draws the images to fit each slide",
            "mix": "web first, AI draws the rest (recommended)"}),
    "kk": ("🖼 <b>Суреттер қайдан алынсын?</b>",
           {"web": "интернеттегі нақты фотолар (табылмаса — мәтін)",
            "ai": "суреттерді ЖИ салады — әр слайдқа сай",
            "mix": "алдымен интернеттен, қалғанын ЖИ салады (ұсынамыз)"}),
}
_ANIM_STEP = {"uz": "✨ <b>Slaydlardagi yozuvlar animatsiya bilan chiqsinmi?</b>",
              "ru": "✨ <b>Добавить анимацию текста на слайдах?</b>",
              "en": "✨ <b>Animate the text on the slides?</b>",
              "kk": "✨ <b>Слайдтардағы мәтін анимациямен шықсын ба?</b>"}


async def _step_photos(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    head, notes = _PHOTO_STEP.get(lang) or _PHOTO_STEP["uz"]
    names = _PHOTO_SOURCE_BUTTONS.get(lang) or _PHOTO_SOURCE_BUTTONS["uz"]
    lines = [head, ""] + [f"{names[key]} — {notes[key]}" for key in ("mix", "web", "ai")]
    rows = [[InlineKeyboardButton(text=names[key], callback_data=f"prem_ppt_img:{key}")] for key in ("mix", "web", "ai")]
    await _prompt(message, state, _topic_line(data, lang) + "\n".join(lines), _markup(rows + [_back_row(lang)]),
                  "photos", PremiumPresentationStates.waiting_for_photo_source)


async def _anim_offer(data: dict) -> bool:
    """Yozuv animatsiyasi taklif qilinadimi: admin «🎛 Funksiyalar boshqaruvi» dan yoqqan va 3D Pro emas."""
    from services.premium_presentation import slide_anim

    if _kind_of(data) in (KIND_PRO3D, KIND_MED3D, KIND_KAT3D):   # o'z animatsiyasi bor (Morph)
        return False
    try:
        return bool(await Database().get_feature_status(slide_anim.FEATURE, default=False))
    except Exception as exc:  # baza o'qilmasa — tanlovsiz (animatsiyasiz) davom etadi
        logger.warning("Yozuv animatsiyasi holati o'qilmadi: %s", exc)
        return False


async def _after_photos(message: Message, state: FSMContext, lang: str) -> None:
    offer = await _anim_offer(await state.get_data())
    await state.update_data(text_anim_offer=offer)
    if offer:
        await _step_anim(message, state, lang)
    else:
        await _step_summary(message, state, lang)


async def _step_anim(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    _, yes, no = _TEXT_ANIM_LABEL.get(lang) or _TEXT_ANIM_LABEL["uz"]
    text = _topic_line(data, lang) + (_ANIM_STEP.get(lang) or _ANIM_STEP["uz"]) + "\n\n<i>" + anim_note(lang) + "</i>"
    rows = [[InlineKeyboardButton(text=yes, callback_data="prem_ppt_anim:1"),
             InlineKeyboardButton(text=no, callback_data="prem_ppt_anim:0")], _back_row(lang)]
    await _prompt(message, state, text, _markup(rows), "anim", PremiumPresentationStates.waiting_for_text_anim)


@router.callback_query(F.data.startswith("prem_ppt_img:"), PremiumPresentationStates.waiting_for_photo_source)
async def premium_ppt_photo_source(callback: CallbackQuery, state: FSMContext, db: Database):
    """Rasm manbasi bosqichi: internetdan / AI chizadi / aralash."""
    await callback.answer()
    value = callback.data.split(":", 1)[1]
    if value not in PHOTO_SOURCES:
        return
    await state.update_data(photo_source=value)
    lang = await _lang_of(callback.from_user.id, db)
    await _after_photos(callback.message, state, lang)


@router.callback_query(F.data.startswith("prem_ppt_anim:"), PremiumPresentationStates.waiting_for_text_anim)
async def premium_ppt_text_anim(callback: CallbackQuery, state: FSMContext, db: Database):
    """Yozuv animatsiyasi bosqichi: bor / yo'q."""
    await callback.answer()
    await state.update_data(text_anim=callback.data.endswith(":1"))
    lang = await _lang_of(callback.from_user.id, db)
    await _step_summary(callback.message, state, lang)


@router.callback_query(F.data.startswith("ppt_fon:"),
                       PremiumPresentationStates.waiting_for_count)
async def premium_ppt_fon_count(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    count = int(callback.data.split(":")[1])
    if not _simple_price(count):
        await _step_count(callback.message, state, lang, db)
        return
    await _handoff_simple(callback, state, db, lang, count)


async def _handoff_simple(callback: CallbackQuery, state: FSMContext, db: Database,
                          lang: str, count: int) -> None:
    """"Chiroyli orqa fonlar": yig'ilgan javoblar bilan hozirgi oddiy oqim ishlaydi.

    Oddiy oqim o'zgarishsiz davom etadi: to'lov, 20 ta shablon, ikonka
    tanlovi, yaratish.
    """
    from bot.handlers import documents as _documents

    data = await state.get_data()
    user = await db.get_user(callback.from_user.id)
    await _drop_prompt(callback.bot, callback.message.chat.id, state)

    name = (data.get("client_name") or "").strip() or (getattr(user, "first_name", "") or "")
    preferences = (data.get("preferences") or "").strip()
    language = data.get("presentation_language") or "uz"
    await state.clear()
    await state.set_data({
        "document_type": "presentation",
        "source_step_visited": True,
        "doc_language": "uz" if uz_script.script_of_language(language) else language,
        "uz_script": uz_script.script_of_language(language) or "",
        "uz_new": language == uz_script.UZ_NEW_LANG,
        "topic": uz_script.to_latin_old(data.get("topic", ""))
        if language in ("uz", uz_script.UZ_NEW_LANG) else data.get("topic", ""),
        "author_name": name,
        # Fayl yoki sayt matni va mijoz istagi oddiy oqimda ham ishlatiladi.
        "book_content": data.get("source_text") or "",
        "book_context": preferences or False,
        "book_urls": [],
    })
    await _documents.prompt_simple_payment(callback.message, state, lang, user, count)


# ── 5b. Matn hajmi — endi alohida so'ralmaydi (tur belgilaydi: zamonaviy — "kop", infografik — "kam").
# Qadam eski suhbatlar uchun qoldirildi: yangilanishdan oldin shu savolda turgan mijoz tugmani bossa ham
# buyurtma davom etadi.
# Rang alohida so'ralmaydi: uni mavzuga qarab tizim tanlaydi, uslub esa ko'rinishni belgilaydi.

VOLUMES = ("kop", "kam")
_VOLUME_BUTTONS = {
    "kop": {"uz": "📝 Matn hajmi: Ko'p", "ru": "📝 Объём текста: большой",
            "en": "📝 Amount of text: large", "kk": "📝 Мәтін көлемі: көп"},
    "kam": {"uz": "🖼 Matn hajmi: O'rtacha", "ru": "🖼 Объём текста: средний",
            "en": "🖼 Amount of text: medium", "kk": "🖼 Мәтін көлемі: орташа"},
}
# Xulosadagi "Matn hajmi: ..." qatori uchun. Ichki kalit "kam" o'zgarmaydi (saqlangan taqdimotlar, sayt).
_VOLUME_NAMES = {
    "kop": {"uz": "Ko'p", "ru": "Большой", "en": "Large", "kk": "Көп"},
    "kam": {"uz": "O'rtacha", "ru": "Средний", "en": "Medium", "kk": "Орташа"},
}


def _volume_name(key: str, lang: str) -> str:
    names = _VOLUME_NAMES.get(key) or _VOLUME_NAMES["kop"]
    return names.get(lang) or names["uz"]


def _volume_prompt(lang: str) -> str:
    msgs = {
        "uz": ("📏 <b>Matn hajmini belgilang</b>\n\n"
               "Ko'p — har slaydda fikr batafsil ochiladi.\n"
               "O'rtacha — aniq fikrlar, infografika va rasmlar ko'proq."),
        "ru": ("📏 <b>Укажите объём текста</b>\n\n"
               "Большой — мысль на каждом слайде раскрыта подробно.\n"
               "Средний — чёткие мысли, больше инфографики и фотографий."),
        "en": ("📏 <b>Set the amount of text</b>\n\n"
               "Large — each slide explains its idea in detail.\n"
               "Medium — sharp ideas, more infographics and photos."),
        "kk": ("📏 <b>Мәтін көлемін белгілеңіз</b>\n\n"
               "Көп — әр слайдта ой толық ашылады.\n"
               "Орташа — нақты ойлар, инфографика мен сурет көбірек."),
    }
    return msgs.get(lang, msgs["uz"])


def _volume_keyboard(lang: str):
    builder = InlineKeyboardBuilder()
    for key in VOLUMES:
        builder.add(InlineKeyboardButton(text=_VOLUME_BUTTONS[key].get(lang) or _VOLUME_BUTTONS[key]["uz"],
                                         callback_data=f"prem_ppt_vol:{key}"))
    builder.adjust(1)
    builder.row(*_back_row(lang))
    return builder.as_markup()


async def _step_volume(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    await _prompt(message, state, _topic_line(data, lang) + _volume_prompt(lang), _volume_keyboard(lang),
                  "volume", PremiumPresentationStates.waiting_for_volume)


@router.callback_query(F.data.startswith("prem_ppt_vol:"),
                       PremiumPresentationStates.waiting_for_volume)
async def premium_ppt_got_volume(callback: CallbackQuery, state: FSMContext, db: Database):
    """Matn hajmi tanlandi — slaydlar soni (narxlar bilan)."""
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    choice = callback.data.split(":", 1)[1]
    await state.update_data(volume=choice if choice in VOLUMES else "kop")
    await _step_count(callback.message, state, lang, db)


# ── Buyurtma xulosasi va tasdiqlash

# Rasm manbasi — mijoz tanlaydi (xulosa ekranida). Sukut: aralash (avval internet, topilmasa AI).
_PHOTO_SOURCE_BUTTONS = {
    "uz": {"web": "🌐 Internetdan", "ai": "🎨 AI chizadi", "mix": "🔀 Aralash"},
    "ru": {"web": "🌐 Из интернета", "ai": "🎨 Рисует ИИ", "mix": "🔀 Смешанно"},
    "en": {"web": "🌐 From the web", "ai": "🎨 AI-drawn", "mix": "🔀 Mixed"},
    "kk": {"web": "🌐 Интернеттен", "ai": "🎨 ЖИ салады", "mix": "🔀 Аралас"},
}
_PHOTO_SOURCE_LINE = {
    "uz": ("🖼 Rasmlar", {"web": "internetdagi haqiqiy fotosuratlar", "ai": "AI chizgan rasmlar",
                         "mix": "avval internetdan, topilmasa AI chizadi"}),
    "ru": ("🖼 Изображения", {"web": "настоящие фото из интернета", "ai": "рисует ИИ",
                             "mix": "сначала из интернета, если нет — рисует ИИ"}),
    "en": ("🖼 Images", {"web": "real photos from the web", "ai": "drawn by AI",
                        "mix": "from the web first, AI draws the rest"}),
    "kk": ("🖼 Суреттер", {"web": "интернеттегі нақты фотолар", "ai": "ЖИ салған суреттер",
                          "mix": "алдымен интернеттен, болмаса ЖИ салады"}),
}
PHOTO_SOURCES = ("web", "ai", "mix")

# Rang sxemasi — mijoz tanlaydi (xulosadagi «🎨 Rang» tugmasi). Faqat to'q, qat'iy ranglar (sariq va och qizil
# taklif qilinmaydi); "auto" — mavzuga qarab (`themes.suggest`).
COLOR_KEYS = ("auto", "ko'k", "to'q ko'k", "yashil", "zumrad", "binafsha", "kulrang")
_COLOR_NAMES = {
    "uz": ("✨ Avto (mavzuga qarab)", "🔵 Ko'k", "🔷 To'q ko'k", "🟢 Yashil", "💠 Zumrad", "🟣 Binafsha", "⚫ Kulrang"),
    "ru": ("✨ Авто (по теме)", "🔵 Синий", "🔷 Тёмно-синий", "🟢 Зелёный", "💠 Изумрудный", "🟣 Фиолетовый",
           "⚫ Графит"),
    "en": ("✨ Auto (by topic)", "🔵 Blue", "🔷 Navy", "🟢 Green", "💠 Emerald", "🟣 Purple", "⚫ Graphite"),
    "kk": ("✨ Авто (тақырыпқа қарай)", "🔵 Көк", "🔷 Қою көк", "🟢 Жасыл", "💠 Зүмірет", "🟣 Күлгін", "⚫ Сұр"),
}
_COLOR_LABEL = {"uz": ("🎨 Rang", "🎨 Rangni tanlang:"), "ru": ("🎨 Цвет", "🎨 Выберите цвет:"),
                "en": ("🎨 Colour", "🎨 Choose a colour:"), "kk": ("🎨 Түс", "🎨 Түсті таңдаңыз:")}


def _color(data: dict):
    """Rang tanlovi: None — taklif qilinmaydi (3D Pro, oddiy taqdimot); aks holda COLOR_KEYS dan biri."""
    if _kind_of(data) not in (KIND_MODERN, KIND_INFO):
        return None
    value = data.get("theme_key") or "auto"
    return value if value in COLOR_KEYS else "auto"


def _color_name(key: str, lang: str) -> str:
    names = _COLOR_NAMES.get(lang) or _COLOR_NAMES["uz"]
    return names[COLOR_KEYS.index(key)]


def _photo_source(data: dict):
    """Rasm manbasi: None — tanlov yo'q (3D Pro o'z obyektlarini chizadi); aks holda mijoz tanlovi."""
    if _kind_of(data) in (KIND_PRO3D, KIND_MED3D, KIND_KAT3D):
        return None
    value = data.get("photo_source") or "mix"
    return value if value in PHOTO_SOURCES else "mix"


_TEXT_ANIM_LABEL = {"uz": ("✨ Yozuv animatsiyasi", "✅ Bor", "❌ Yo'q"),
                    "ru": ("✨ Анимация текста", "✅ Есть", "❌ Нет"),
                    "en": ("✨ Text animation", "✅ On", "❌ Off"),
                    "kk": ("✨ Мәтін анимациясы", "✅ Бар", "❌ Жоқ")}


# Animatsiya tanlangan bo'lsa mijozga albatta aytiladi: u faqat PowerPoint slayd-shousida ko'rinadi.
ANIM_NOTE = {
    "uz": "ℹ️ Animatsiya PowerPoint'da «Slayd-shou» rejimida ko'rinadi. Telefon ilovalari va PDF'da sahifalar "
          "animatsiyasiz, to'liq holida chiqadi.",
    "ru": "ℹ️ Анимация видна в PowerPoint в режиме «Показ слайдов». В мобильных приложениях и PDF страницы "
          "показываются целиком, без анимации.",
    "en": "ℹ️ The animation plays in PowerPoint in Slide Show mode. Phone apps and PDF show the pages complete, "
          "without animation.",
    "kk": "ℹ️ Анимация PowerPoint-та «Слайд-шоу» режимінде көрінеді. Телефон қосымшалары мен PDF-те беттер "
          "анимациясыз, толық күйінде шығады.",
}


def anim_note(lang: str) -> str:
    return ANIM_NOTE.get(lang) or ANIM_NOTE["uz"]


PRO3D_NOTE = {
    "uz": "🧊 Har slaydda fonsiz 3D obyekt, unga yo'nalgan izohlar va «Morph» o'tishlari. Harakat PowerPoint "
          "2019/2021/365 da «Slayd-shou» rejimida ko'rinadi; eski versiyada va telefonda slaydlar oddiy almashadi.",
    "ru": "🧊 На каждом слайде 3D-объект без фона, подписи к его частям и переходы «Трансформация» (Morph). "
          "Движение видно в PowerPoint 2019/2021/365 в режиме «Показ слайдов»; в старых версиях и на телефоне "
          "слайды просто сменяются.",
    "en": "🧊 Every slide has a background-free 3D object, labels pointing to its parts and Morph transitions. "
          "The motion plays in PowerPoint 2019/2021/365 in Slide Show; older versions and phones simply switch slides.",
    "kk": "🧊 Әр слайдта фонсыз 3D нысан, оның бөліктеріне бағытталған жазбалар және «Morph» ауысулары. Қозғалыс "
          "PowerPoint 2019/2021/365-те «Слайд-шоу» режимінде көрінеді; ескі нұсқада және телефонда слайдтар жай ауысады.",
}


def pro3d_note(lang: str) -> str:
    return PRO3D_NOTE.get(lang) or PRO3D_NOTE["uz"]


MED3D_NOTE = {
    "uz": "🫀 Har slaydda haqiqiy 3D model: a'zolar bir-biriga to'g'ri birikkan, slaydlar orasida aylanadi, yangi "
          "a'zo o'z joyida asta paydo bo'ladi. Yorliqlarda o'zbekcha va lotincha nom. Faylni KOMPYUTERDAGI PowerPoint "
          "2019/2021/365 da «Slayd-shou» rejimida (F5) oching — telefonda va eski versiyalarda 3D ko'rinmaydi. "
          "Tahrirlash oynasidagi takrorlangandek slaydlar silliq o'tish uchun — ularni o'chirmang.",
    "ru": "🫀 На каждом слайде настоящая 3D-модель: органы правильно соединены, между слайдами модель вращается, "
          "новый орган плавно появляется на своём месте. На подписях — узбекское и латинское название. Откройте "
          "файл в PowerPoint 2019/2021/365 НА КОМПЬЮТЕРЕ в режиме «Показ слайдов» (F5) — на телефоне и в старых "
          "версиях 3D не видно. Похожие повторяющиеся слайды в режиме редактирования нужны для плавных переходов — "
          "не удаляйте их.",
    "en": "🫀 Every slide has a real 3D model: organs are joined correctly, the model turns between slides and a new "
          "organ fades in at its place. Labels show the Uzbek and Latin names. Open the file in PowerPoint "
          "2019/2021/365 ON A COMPUTER in Slide Show (F5) — phones and older versions do not show 3D. The "
          "near-duplicate slides in the editor make the transitions smooth — do not delete them.",
    "kk": "🫀 Әр слайдта нақты 3D модель: мүшелер дұрыс біріккен, слайдтар арасында модель айналады, жаңа мүше "
          "өз орнында бірте-бірте пайда болады. Белгілерде өзбекше және латынша атау. Файлды КОМПЬЮТЕРДЕГІ "
          "PowerPoint 2019/2021/365-те «Слайд-шоу» режимінде (F5) ашыңыз — телефонда 3D көрінбейді. Өңдеу "
          "терезесіндегі қайталанған сияқты слайдтар тегіс өту үшін — оларды өшірмеңіз.",
}


def med3d_note(lang: str) -> str:
    return MED3D_NOTE.get(lang) or MED3D_NOTE["uz"]


# 3D taqdimot bilan birga yuboriladigan yo'riqnoma videosi: slayd-shou tugmasi, Morph qanday ko'rinishi va
# telefonda 3D ko'rinmasligi. Birinchi yuborishdan keyin Telegram file_id si eslab qolinadi (qayta yuklanmaydi).
MED3D_GUIDE_VIDEO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                 "assets", "med3d", "korish_yoriqnoma.mp4")
_med3d_guide_id = None                           # Telegram file_id (str)


async def _send_med3d_guide(message: Message, lang: str) -> None:
    """Yo'riqnoma videosi (izohi — `med3d_note`); video bo'lmasa yoki yuborilmasa — faqat matn."""
    global _med3d_guide_id
    from aiogram.types import FSInputFile

    caption = med3d_note(lang)
    video = _med3d_guide_id or (FSInputFile(MED3D_GUIDE_VIDEO) if os.path.exists(MED3D_GUIDE_VIDEO) else None)
    if video is not None:
        try:
            sent = await message.answer_video(video=video, caption=caption[:1024], width=1080, height=1920,
                                              supports_streaming=True)
            if sent and sent.video:
                _med3d_guide_id = sent.video.file_id
            return
        except Exception as exc:                      # noqa: BLE001
            logger.warning("3D yo'riqnoma videosi yuborilmadi: %s", exc)
            _med3d_guide_id = None
    await message.answer(caption)


# Mavzu tana tuzilishiga oid bo'lmasa (AI tekshiruvi) — pul qaytariladi va shu aytiladi.
MED3D_NOT_ANATOMY = {
    "uz": "🫀 Bu mavzu inson tanasi tuzilishiga oid emas, shuning uchun 3D Anatomiya taqdimoti qilinmadi.",
    "ru": "🫀 Эта тема не о строении тела человека, поэтому презентация 3D Анатомия не создана.",
    "en": "🫀 This topic is not about the structure of the human body, so no 3D Anatomy presentation was made.",
    "kk": "🫀 Бұл тақырып адам денесінің құрылысына қатысты емес, сондықтан 3D Анатомия презентациясы жасалмады.",
}


# 3D Anatomiya fayli nomida ko'rish sharti: Morph va 3D — PowerPoint 2019+, telefonda ko'rinmaydi, kompyuterda
# Slayd-shou rejimida ko'rish kerak. Taqdimot tilida (lotin/kirill o'zbekcha alohida).
_MED3D_FILE_NOTE = {
    "uz": "3D Morph - PowerPoint 2019+ kerak, telefonda ko'rinmaydi, kompyuterda Slayd-shou rejimida oching",
    "uz_cyrl": "3D Morph - PowerPoint 2019+ керак, телефонда кўринмайди, компьютерда Слайд-шоу режимида очинг",
    "ru": "3D Morph - нужен PowerPoint 2019+, на телефоне не виден, открыть на ПК в режиме слайд-шоу",
    "en": "3D Morph - needs PowerPoint 2019+, not shown on phones, open on a PC in Slide Show mode",
    "kk": "3D Morph - PowerPoint 2019+ керек, телефонда көрінбейді, компьютерде слайд-шоу режимінде ашыңыз",
}


def med3d_filename(topic: str, language: str) -> str:
    """3D Anatomiya fayli nomi: mavzu va ko'rish sharti (mijoz tanlagan tilda)."""
    key = "uz_cyrl" if language == uz_script.UZ_CYRILLIC_LANG else (language or "uz")
    note = _MED3D_FILE_NOTE.get(key) or _MED3D_FILE_NOTE["en"]
    name = re.sub(r'\s+', " ", re.sub(r'[\\/:*?"<>|]+', " ", topic or "")).strip()[:40].strip() or "3D"
    return f"{name} ({note}).pptx"


# 3D qilib bo'lmaydigan mavzu: shu mavzuda oddiy (zamonaviy) taqdimot taklif qilinadi.
MED3D_ALT_ASK = {
    "uz": "Bu mavzuda boshqa turdagi taqdimot qilib beraylikmi? Turini tanlang:",
    "ru": "Сделать по этой теме презентацию другого типа? Выберите тип:",
    "en": "Shall we make another type of presentation on this topic? Choose the type:",
    "kk": "Осы тақырыпта басқа түрдегі презентация жасайық па? Түрін таңдаңыз:",
}


def _med3d_alt_keyboard(lang: str) -> InlineKeyboardMarkup:
    return _med3d_choice_keyboard(lang, cancel=True)


@router.callback_query(F.data.startswith("prem_m3d_alt:"))
async def premium_med3d_alternative(callback: CallbackQuery, state: FSMContext, db: Database):
    """3D qilib bo'lmagan mavzu: tanlangan tur (Infografik / Zamonaviy / Klassik) o'z oqimi bilan BOSHIDAN
    boshlanadi — faqat mavzu qayta so'ralmaydi (keyingi qadam — ism, keyin istaklar, uslub, slaydlar soni)."""
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    data = await state.get_data()
    choice = callback.data.split(":", 1)[1]
    kind = choice.split(":", 1)[1] if choice.startswith("kind:") else (KIND_MODERN if choice == "ha" else "")
    if kind in ALT_KINDS and data.get("topic"):
        with contextlib.suppress(Exception):
            await callback.message.edit_reply_markup(reply_markup=None)
        await state.update_data(m3d_style="", m3d_topic_kind=None, prompt_mid=None, payment_method=None,
                                client_name="", preferences="", kat3d_ids=[], standalone_med3d=False)
        await _set_kind(state, kind)
        await _step_name(callback.message, state, lang)
        return
    if callback.data.endswith(":mavzu"):              # boshqa mavzu — 3D Anatomiya turida qoladi
        with contextlib.suppress(Exception):
            await callback.message.edit_reply_markup(reply_markup=None)
        await state.update_data(kind=KIND_MED3D, topic="", prompt_mid=None, payment_method=None)
        await _step_topic(callback.message, state, lang)
        return
    with contextlib.suppress(Exception):
        await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()


# 3D taqdimot (katalog) bosqichlari holat xabarida.
_KAT3D_STAGES = {
    "uz": {"download": "3D modellar tayyorlanmoqda...",
           "plan": "AI slaydlar rejasini yozmoqda va faktlarni tekshirmoqda...",
           "models": "3D modellar joylanmoqda, Morph harakatlari tayyorlanmoqda..."},
    "ru": {"download": "Готовим 3D-модели...",
           "plan": "ИИ пишет план слайдов и проверяет факты...",
           "models": "Размещаем 3D-модели и готовим Morph-движения..."},
    "en": {"download": "Preparing the 3D models...",
           "plan": "AI is writing the slide plan and checking the facts...",
           "models": "Placing the 3D models and preparing the Morph moves..."},
    "kk": {"download": "3D модельдер дайындалуда...",
           "plan": "ЖИ слайдтар жоспарын жазып, фактілерді тексеруде...",
           "models": "3D модельдер орналастырылып, Morph қозғалыстары дайындалуда..."},
}

# 3D Anatomiya bosqichlari holat xabarida.
_MED3D_STAGES = {
    "uz": {"plan": "AI mavzuni tekshirib, organlar va slaydlar rejasini tuzmoqda...",
           "pictures": "AI kasallik ko'rinishini chizmoqda...",
           "models": "3D organ modellari yig'ilmoqda va PowerPoint tayyorlanmoqda..."},
    "ru": {"plan": "AI проверяет тему и составляет план органов и слайдов...",
           "pictures": "ИИ рисует, как выглядит заболевание...",
           "models": "Собираем 3D-модели органов и PowerPoint..."},
    "en": {"plan": "AI is checking the topic and planning the organs and slides...",
           "pictures": "AI is drawing what the disease looks like...",
           "models": "Building the 3D organ models and the PowerPoint file..."},
    "kk": {"plan": "AI тақырыпты тексеріп, мүшелер мен слайдтар жоспарын құруда...",
           "pictures": "ЖИ аурудың көрінісін салуда...",
           "models": "3D мүше модельдері мен PowerPoint дайындалуда..."},
}

# 3D Pro bosqichlari holat xabarida.
_PRO3D_STAGES = {
    "uz": {"plan": "AI taqdimot rejasini tuzmoqda...", "images": "3D obyektlar chizilmoqda (0/{total})...",
           "image": "3D obyektlar chizilmoqda: {done}/{total}", "anchors": "Izoh chiziqlari joylashtirilmoqda...",
           "render": "PowerPoint yig'ilmoqda: {slides} slayd, {photos} ta 3D obyekt"},
    "ru": {"plan": "AI составляет план презентации...", "images": "Рисуем 3D-объекты (0/{total})...",
           "image": "Рисуем 3D-объекты: {done}/{total}", "anchors": "Размещаем подписи...",
           "render": "Собираем PowerPoint: {slides} слайдов, 3D-объектов: {photos}"},
    "en": {"plan": "AI is planning the presentation...", "images": "Drawing 3D objects (0/{total})...",
           "image": "Drawing 3D objects: {done}/{total}", "anchors": "Placing the labels...",
           "render": "Building the PowerPoint: {slides} slides, {photos} 3D objects"},
}


def _text_anim_label(lang: str, on: bool) -> str:
    name, yes, no = _TEXT_ANIM_LABEL.get(lang) or _TEXT_ANIM_LABEL["uz"]
    return f"{name}: {yes if on else no}"


def _confirm_keyboard(lang: str, current_language: str, color=None) -> InlineKeyboardMarkup:
    """Xulosa tugmalari: til, rang (None — taklif qilinmaydi), tasdiqlash va orqaga.
    Rasm manbasi va yozuv animatsiyasi o'z bosqichlarida tanlanadi — xulosada faqat yozuv bo'lib turadi."""
    builder = InlineKeyboardBuilder()
    for code in ("uz", uz_script.UZ_CYRILLIC_LANG, uz_script.UZ_NEW_LANG, "ru", "en", "kk"):
        mark = "✓ " if code == current_language else ""
        builder.button(text=f"{mark}{_LANG_BUTTONS[code]}", callback_data=f"prem_ppt_lang:{code}")
    builder.adjust(2)
    if color is not None:
        label = (_COLOR_LABEL.get(lang) or _COLOR_LABEL["uz"])[0]
        builder.row(InlineKeyboardButton(text=f"{label}: {_color_name(color, lang)}", callback_data="prem_ppt_color"))
    builder.row(InlineKeyboardButton(text=_t(lang, "confirm"), callback_data="prem_ppt_confirm"))
    builder.row(*_back_row(lang))
    return builder.as_markup()


def _summary(data: dict, lang: str):
    """(matn, klaviatura) — to'lovdan oldingi xulosa."""
    def esc(value, limit=160):
        import html as _html
        return _html.escape(str(value or "").strip(), quote=False)[:limit]

    slide_count = int(data.get("slide_count") or MIN_SLIDES)
    price = _price_of(data, slide_count)
    base_price = _base_price_of(data, slide_count)
    promo_percent = int(data.get("med3d_promo_percent") or 0)
    kind = _kind_of(data)
    volume = ""
    # Infografikda uslub so'ralmaydi — xulosada uslub o'rniga tur yoziladi.
    style = _style_name(data.get("style") or "toza", lang) if kind == KIND_MODERN else ""
    language = data.get("presentation_language") or "uz"
    none = {"uz": "ko‘rsatilmagan", "ru": "не указано", "en": "not provided"}.get(lang, "—")
    source = data.get("source_label") or ""
    if not source and data.get("source_text"):
        source = {"uz": "mijoz matni", "ru": "текст клиента", "en": "client text"}.get(lang, "")
    labels = {
        "uz": ("Taqdimot", "Mavzu", "Ism", "Istaklar", "Manba", "Uslub", "Matn hajmi", "Slaydlar", "Narx",
               "so'm", "Hisobingizdan yechiladi. Tasdiqlaysizmi?", "Til"),
        "ru": ("Презентация", "Тема", "Имя", "Пожелания", "Источник", "Стиль", "Объём текста", "Слайдов",
               "Цена", "сум", "Будет списано с вашего баланса. Подтверждаете?", "Язык"),
        "en": ("Presentation", "Topic", "Name", "Preferences", "Source", "Style", "Text amount", "Slides",
               "Price", "soʻm", "Will be deducted from your balance. Confirm?", "Language"),
        "kk": ("Презентация", "Тақырып", "Аты", "Тілектер", "Дереккөз", "Стиль", "Мәтін көлемі", "Слайдтар",
               "Бағасы", "сом", "Балансыңыздан шегеріледі. Растайсыз ба?", "Тіл"),
    }
    head, topic_l, name_l, pref_l, src_l, style_l, volume_l, slides_l, price_l, cur, ask, lang_l = \
        labels.get(lang) or labels["uz"]
    lines = [f"✨ <b>{head}</b>", "",
             f"📋 {topic_l}: <b>{esc(data.get('topic'), 200)}</b>",
             f"👤 {name_l}: {esc(data.get('client_name')) or none}"]
    if data.get("preferences"):
        lines.append(f"✍️ {pref_l}: <i>{esc(data.get('preferences'), 150)}</i>")
    if source:
        lines.append(f"📎 {src_l}: {esc(source, 80)}")
    kind_l = {"uz": "Turi", "ru": "Тип", "en": "Type", "kk": "Түрі"}.get(lang, "Turi")
    lines.append(f"🎨 {kind_l}: <b>{esc(_kind_name(kind, lang))}</b>")
    if style:
        lines.append(f"🖌 {style_l}: <b>{esc(style)}</b>")
    if volume:
        lines.append(f"📏 {volume_l}: <b>{esc(volume)}</b>")
    if kind == KIND_PRO3D:
        lines.append(f"<i>{esc(pro3d_note(lang), 400)}</i>")
    if kind == KIND_MED3D:
        lines.append(f"🖌 {style_l}: <b>{esc(_m3d_style_label(data, lang))}</b>")
        lines.append(f"<i>{esc(med3d_note(lang), 400)}</i>")
    if kind == KIND_KAT3D:
        models_l = {"uz": "3D modellar", "ru": "3D-модели", "en": "3D models", "kk": "3D модельдер"}.get(lang, "3D modellar")
        lines.append(f"🧊 {models_l}: <b>{len(data.get('kat3d_ids') or [])}</b>")
        lines.append(f"<i>{esc(med3d_note(lang), 400)}</i>")
    color = _color(data)
    if color is not None:
        lines.append(f"{(_COLOR_LABEL.get(lang) or _COLOR_LABEL['uz'])[0]}: <b>{esc(_color_name(color, lang))}</b>")
    photo_source = _photo_source(data)
    if photo_source is not None:
        name, kinds = _PHOTO_SOURCE_LINE.get(lang) or _PHOTO_SOURCE_LINE["uz"]
        lines.append(f"{name}: <b>{esc(kinds[photo_source])}</b>")
    text_anim = _text_anim_choice(data)
    if text_anim is not None:
        lines.append(_text_anim_label(lang, text_anim))
        if text_anim:
            lines.append(f"<i>{esc(anim_note(lang), 400)}</i>")
    lines += [f"📊 {slides_l}: <b>{slide_count}</b>"]
    if promo_percent:
        lines += [
            f"🎟 <code>{esc(data.get('med3d_promo_code'), 32)}</code> — {promo_percent}% chegirma",
            f"💸 Chegirma: <b>{base_price - price:,} {cur}</b>",
        ]
    lines += [f"💰 {price_l}: <b>{price:,} {cur}</b>", "", ask]
    return "\n".join(lines), _confirm_keyboard(lang, language, color)


def _text_anim_choice(data: dict):
    """Yozuv animatsiyasi: None — taklif qilinmaydi; aks holda mijoz tanlovi (sukut — bor)."""
    if not data.get("text_anim_offer"):
        return None
    return bool(data.get("text_anim", True))


async def _step_summary(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    price = _price_of(data, int(data.get("slide_count") or MIN_SLIDES))
    # Yozuv animatsiyasi taklifi o'z bosqichida aniqlangan (`_after_photos`); xulosaga to'g'ridan kelinsa — shu yerda.
    offer = data["text_anim_offer"] if "text_anim_offer" in data else await _anim_offer(data)
    await state.update_data(price=price, text_anim_offer=offer)
    data = await state.get_data()
    text, markup = _summary({**data, "price": price}, lang)
    await _prompt(message, state, text, markup, "summary",
                  PremiumPresentationStates.waiting_for_slide_count)


@router.callback_query(F.data.startswith("prem_ppt_lang:"),
                       PremiumPresentationStates.waiting_for_slide_count)
async def premium_ppt_change_language(callback: CallbackQuery, state: FSMContext, db: Database):
    """Til avtomatik aniqlanadi; noto'g'ri bo'lsa shu yerda almashtiriladi."""
    code = callback.data.split(":", 1)[1]
    if code not in _LANG_BUTTONS:
        await callback.answer()
        return
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    await state.update_data(presentation_language=code)
    text, markup = _summary(await state.get_data(), lang)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data == "prem_ppt_color", PremiumPresentationStates.waiting_for_slide_count)
async def premium_ppt_color_menu(callback: CallbackQuery, state: FSMContext, db: Database):
    """«🎨 Rang» — ranglar ro'yxati (tanlangani ✓); tanlangach xulosaga qaytadi."""
    await callback.answer()
    data = await state.get_data()
    current = _color(data)
    if current is None:
        return
    lang = await _lang_of(callback.from_user.id, db)
    builder = InlineKeyboardBuilder()
    for index, key in enumerate(COLOR_KEYS):
        builder.button(text=("✓ " if key == current else "") + _color_name(key, lang),
                       callback_data=f"prem_ppt_clr:{index}")
    builder.adjust(1, 2, 2, 2)
    with contextlib.suppress(Exception):
        await callback.message.edit_text((_COLOR_LABEL.get(lang) or _COLOR_LABEL["uz"])[1],
                                         reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("prem_ppt_clr:"), PremiumPresentationStates.waiting_for_slide_count)
async def premium_ppt_color_chosen(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    try:
        key = COLOR_KEYS[int(callback.data.split(":", 1)[1])]
    except (ValueError, IndexError):
        return
    if _color(await state.get_data()) is None:
        return
    await state.update_data(theme_key="" if key == "auto" else key)
    lang = await _lang_of(callback.from_user.id, db)
    text, markup = _summary(await state.get_data(), lang)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


# ── Orqaga

@router.callback_query(F.data == "prem_ppt_prev")
async def premium_ppt_previous(callback: CallbackQuery, state: FSMContext, db: Database):
    """Bitta qadam orqaga: joriy so'rov o'chadi, oldingisi qayta so'raladi."""
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    data = await state.get_data()
    previous = _previous_step(data)
    if previous is None:
        await premium_ppt_back(callback, state, db)
        return
    steps = {"topic": _step_topic, "script": _step_script, "name": _step_name, "prefs": _step_prefs,
             "source": _step_source, "count": _step_count, "style": _step_style,
             "volume": _step_volume, "kind": _step_kind, "photos": _step_photos, "anim": _step_anim,
             "m3dstyle": _step_m3d_style}
    if previous == "count":
        await _step_count(callback.message, state, lang, db)
        return
    await steps[previous](callback.message, state, lang)


# ──────────────────────────────────────────────────────────────── CONFIRM & GENERATE

async def _order(user_id: int, state: FSMContext) -> dict:
    """Buyurtmani FSM dan, u yo'q bo'lsa saqlangan nusxadan oladi."""
    data = await state.get_data()
    if data.get("topic") and not pay.is_expired(data):
        return data

    saved = pay.recall(user_id, CHECKOUT.service)
    if saved:
        await state.set_data(saved)
        await state.set_state(PremiumPresentationStates.waiting_for_payment)
    return saved


async def _report_expired(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await message.answer(get_text(lang, "pay_order_expired"), parse_mode="HTML")


@router.callback_query(F.data == CHECKOUT.pay_other)
async def premium_ppt_other_methods(callback: CallbackQuery, state: FSMContext, db: Database):
    """Stars va balansni to'ldirish — asosiy oynani chalg'itmasin deb shu yerda."""
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    data = await _order(callback.from_user.id, state)
    if not data:
        await _report_expired(callback.message, state, lang)
        return
    price = int(data.get("price", _get_price(MIN_SLIDES)))
    await callback.message.edit_text(
        get_text(lang, "pay_other_title", price=price),
        parse_mode="HTML",
        reply_markup=pay.other_methods_keyboard(CHECKOUT, lang, price),
    )


@router.callback_query(F.data == CHECKOUT.pay_back)
async def premium_ppt_payment_back(callback: CallbackQuery, state: FSMContext, db: Database):
    """«Boshqa usullar»dan asosiy to'lov oynasiga qaytish."""
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    data = await _order(callback.from_user.id, state)
    if not data:
        await _report_expired(callback.message, state, lang)
        return
    price = int(data.get("price", _get_price(MIN_SLIDES)))
    texts = {
        "uz": f"✅ <b>Buyurtma tasdiqlandi</b>\n\n💰 Narx: <b>{price:,} so'm</b>\nTo'lov usulini tanlang:",
        "ru": f"✅ <b>Заказ подтверждён</b>\n\n💰 Цена: <b>{price:,} сум</b>\nВыберите способ оплаты:",
        "en": f"✅ <b>Order confirmed</b>\n\n💰 Price: <b>{price:,} so'm</b>\nChoose a payment method:",
    }
    await state.set_state(PremiumPresentationStates.waiting_for_payment)
    await callback.message.edit_text(texts.get(lang, texts["uz"]), parse_mode="HTML",
                                     reply_markup=_payment_keyboard(lang, price))


@router.callback_query(F.data == CHECKOUT.recheck)
async def premium_ppt_recheck(callback: CallbackQuery, state: FSMContext, db: Database):
    """Balans to'ldirilgandan keyin — buyurtmani yo'qotmasdan davom etish."""
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    data = await _order(callback.from_user.id, state)
    if not data:
        await callback.answer()
        await _report_expired(callback.message, state, lang)
        return

    price = int(data.get("price", _get_price(MIN_SLIDES)))
    balance = user.balance if user else 0
    if balance < price:
        await callback.answer(
            get_text(lang, "pay_still_short", balance=balance, price=price),
            show_alert=True,
        )
        return

    await callback.answer()
    pay.forget(callback.from_user.id)
    await state.update_data(payment_method="balance")
    await state.set_state(PremiumPresentationStates.waiting_for_slide_count)
    await premium_ppt_confirm(callback, state, db)

@router.callback_query(
    F.data == CHECKOUT.pay_balance,
    PremiumPresentationStates.waiting_for_payment,
)
async def premium_ppt_pay_balance(callback: CallbackQuery, state: FSMContext, db: Database):
    # premium_ppt_confirm() callback'ni o'zi tasdiqlaydi. Bu yerda yana
    # callback.answer() chaqirish Telegram callback'ini ikki marta
    # tasdiqlashga urinish va keyingi bosqich ochilmasligiga olib keladi.
    await state.update_data(payment_method="balance")
    await state.set_state(PremiumPresentationStates.waiting_for_slide_count)
    await premium_ppt_confirm(callback, state, db)


@router.callback_query(
    F.data == CHECKOUT.pay_stars,
    PremiumPresentationStates.waiting_for_payment,
)
async def premium_ppt_pay_stars(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    data = await _order(callback.from_user.id, state)
    if not data:
        await _report_expired(callback.message, state, lang)
        return
    price = int(data.get("price", _get_price(MIN_SLIDES)))
    if not await _reserve_med3d_promo(db, data, callback.from_user.id):
        await _coupon_unavailable(callback, state, lang)
        return
    slide_count = int(data.get("slide_count", 10))
    kind_name = _kind_name(_kind_of(data), "uz")          # hisob-faktura: buyurtma turi bilan (3D ham)
    try:
        sent = await pay.send_invoice(
            callback.message, CHECKOUT, lang, price,
            title=f"Taqdimot — {kind_name}",
            description=f"{slide_count} ta slaydli taqdimot ({kind_name})",
        )
    except Exception:
        logger.exception("Taqdimot uchun Stars hisob-fakturasi yuborilmadi")
        sent = False
    if sent:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    elif data.get("med3d_promo_code"):
        await db.release_med3d_promocode(data["med3d_promo_code"], callback.from_user.id)


@router.message(
    PremiumPresentationStates.waiting_for_payment,
    F.successful_payment,
)
async def premium_ppt_successful_stars(
    message: Message, state: FSMContext, db: Database
):
    payment = message.successful_payment
    if not payment or not CHECKOUT.owns_payload(payment.invoice_payload):
        return

    data = await _order(message.chat.id, state)
    if not data:
        await _report_expired(message, state, "uz")
        return
    if data.get("med3d_promo_code"):
        try:
            completed = await db.complete_med3d_promocode(
                data["med3d_promo_code"], message.from_user.id
            )
        except Exception:
            logger.exception("3D Anatomiya promokodidan foydalanish qayd etilmadi")
            completed = False
        if not completed:
            refunded = False
            try:
                refunded = await message.bot.refund_star_payment(
                    user_id=message.from_user.id,
                    telegram_payment_charge_id=payment.telegram_payment_charge_id,
                )
            except Exception:
                logger.exception("Stars to'lovi qaytarilmadi: foydalanuvchi=%s", message.from_user.id)
            await message.answer(
                "❌ Promokod limiti tasdiqlanmadi. " + (
                    "Stars to'lovi qaytarildi."
                    if refunded else
                    "Stars to'lovini avtomatik qaytarib bo'lmadi; iltimos, adminga murojaat qiling."
                )
            )
            return
        await state.update_data(coupon_redeemed=True)
    pay.forget(message.chat.id)
    await state.update_data(payment_method="stars")
    await state.set_state(PremiumPresentationStates.waiting_for_slide_count)
    adapter = _MessageCallbackAdapter(
        message,
        data=f"prem_ppt_count:{data.get('slide_count', 10)}",
    )
    await premium_ppt_confirm(adapter, state, db)


@router.callback_query(
    F.data == "prem_ppt_back_to_confirm",
    PremiumPresentationStates.waiting_for_payment,
)
async def premium_ppt_back_to_confirm(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    await state.set_state(PremiumPresentationStates.waiting_for_slide_count)
    text, markup = _summary(await state.get_data(), lang)
    with contextlib.suppress(Exception):
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "prem_ppt_confirm", PremiumPresentationStates.waiting_for_slide_count)
async def premium_ppt_confirm(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    data = await state.get_data()

    # Tasdiqlash va to'lov tanlovi alohida ekranda bo'ladi.
    if not data.get("payment_method"):
        price = data.get("price", _get_price(MIN_SLIDES))
        if int(price) <= 0 and data.get("med3d_promo_code"):
            await state.update_data(payment_method="promo")
            data = await state.get_data()
        else:
            await state.set_state(PremiumPresentationStates.waiting_for_payment)
            payment_texts = {
                "uz": (
                    "✅ <b>Buyurtma tasdiqlandi</b>\n\n"
                    f"💰 Narx: <b>{price:,} so'm</b>\n"
                    "To‘lov usulini tanlang:"
                ),
                "ru": (
                    "✅ <b>Заказ подтверждён</b>\n\n"
                    f"💰 Цена: <b>{price:,} сум</b>\n"
                    "Выберите способ оплаты:"
                ),
                "en": (
                    "✅ <b>Order confirmed</b>\n\n"
                    f"💰 Price: <b>{price:,} soʻm</b>\n"
                    "Choose a payment method:"
                ),
            }
            # Buyurtma shu yerdayoq saqlanadi: mijoz to'lov usulini tanlashdan
            # oldin balansni to'ldirishga ketishi mumkin, u oqim esa FSM ni
            # tozalaydi.
            pay.remember(callback.from_user.id, CHECKOUT.service, await state.get_data())
            await callback.message.edit_text(
                payment_texts.get(lang, payment_texts["uz"]),
                parse_mode="HTML",
                reply_markup=_payment_keyboard(lang, price),
            )
            return

    topic = data.get("topic", "")
    preferences = data.get("preferences", "")
    source_text = data.get("source_text", "")
    presentation_language = data.get("presentation_language", "uz")
    slide_count = data.get("slide_count", 10)
    price = data.get("price", _get_price(MIN_SLIDES))
    level = data.get("level", 2)
    client_name = data.get("client_name", "")

    payment_method = data.get("payment_method", "balance")

    # Faqat balans orqali to'lovda balansni tekshiramiz va yechamiz.
    if payment_method == "balance" and user.balance < price:
        # Buyurtma FSM dan tashqarida saqlanadi: balansni to'ldirish oqimi
        # FSM ni tozalaydi, shuning uchun ilgari mijoz hamma narsani
        # qaytadan kiritishga majbur bo'lardi.
        await state.update_data(payment_method=None)
        pay.remember(callback.from_user.id, CHECKOUT.service, await state.get_data())
        await state.set_state(PremiumPresentationStates.waiting_for_payment)
        await pay.send_shortfall(callback.message, CHECKOUT, lang, price, user.balance)
        return

    if data.get("med3d_promo_code") and not data.get("coupon_redeemed"):
        try:
            reserved = await _reserve_med3d_promo(db, data, callback.from_user.id)
        except Exception:
            logger.exception("3D Anatomiya promokodini band qilishda xatolik")
            reserved = False
        if not reserved:
            await _coupon_unavailable(callback, state, lang)
            return

    if payment_method == "balance":
        await db.update_user_balance(callback.from_user.id, -price)
    if data.get("med3d_promo_code") and not data.get("coupon_redeemed"):
        try:
            completed = await db.complete_med3d_promocode(
                data["med3d_promo_code"], callback.from_user.id
            )
        except Exception:
            logger.exception("3D Anatomiya promokodidan foydalanish qayd etilmadi")
            completed = False
        if not completed:
            if payment_method == "balance":
                await db.update_user_balance(callback.from_user.id, price)
            await _coupon_unavailable(callback, state, lang)
            return
        await state.update_data(coupon_redeemed=True)
    await state.set_state(PremiumPresentationStates.generating)

    # Create a status message before the AI content and PPTX generation starts.
    initial_status_texts = {
        "uz": (
            f"⏳ <b>{topic}</b>\n"
            f"📄 {slide_count} ta slaydli PPTX tayyorlanmoqda..."
        ),
        "ru": (
            f"⏳ <b>{topic}</b>\n"
            f"📄 Готовим PPTX-презентацию на {slide_count} слайдов..."
        ),
        "en": (
            f"⏳ <b>{topic}</b>\n"
            f"📄 Preparing the {slide_count}-slide PPTX..."
        ),
    }
    try:
        status = await callback.message.edit_text(
            initial_status_texts.get(lang, initial_status_texts["uz"]),
            parse_mode="HTML",
        )
    except Exception:
        # Successful Stars payments arrive as a service message that may not
        # be editable, so use a new message in that case.
        status = await callback.message.answer(
            initial_status_texts.get(lang, initial_status_texts["uz"]),
            parse_mode="HTML",
        )

    total_chunks = max(1, (slide_count + 4) // 5)
    status_msgs = {
        "uz": (
            f"⚙️ <b>{topic}</b>\n"
            f"📄 {slide_count} ta slayd tayyorlanmoqda...\n\n"
            f"⏳ Kontent 1/{total_chunks} bo'lak..."
        ),
        "ru": (
            f"⚙️ <b>{topic}</b>\n"
            f"📄 Готовим {slide_count} слайдов...\n\n"
            f"⏳ Контент 1/{total_chunks} часть..."
        ),
        "en": (
            f"⚙️ <b>{topic}</b>\n"
            f"📄 Preparing {slide_count} slides...\n\n"
            f"⏳ Content 1/{total_chunks} chunk..."
        ),
    }

    # Edit the status message created above — after a Stars payment that message
    # is a fresh one, not `callback.message`.
    await status.edit_text(status_msgs.get(lang, status_msgs["uz"]), parse_mode="HTML")

    loop = asyncio.get_running_loop()
    rotating_facts = {
        "uz": [
            "Quyosh nuri Yerga taxminan 8 daqiqa 20 soniyada yetib keladi.",
            "Ahtapotning uchta yuragi bor, qoni esa ko‘kimtir rangda bo‘ladi.",
            "Asalarilar raqs orqali oziq manzilini bir-biriga bildiradi.",
            "Odam miyasi tanadagi energiyaning taxminan 20 foizini sarflaydi.",
            "Venerada bir kun bir yildan uzunroq davom etadi.",
            "AI endi o‘rgangan ma’lumotlar asosida slaydlarni tekshirmoqda.",
        ],
        "ru": [
            "Солнечный свет достигает Земли примерно за 8 минут 20 секунд.",
            "У осьминога три сердца, а его кровь имеет голубоватый цвет.",
            "Пчёлы сообщают друг другу о местоположении пищи с помощью танца.",
            "Мозг человека расходует около 20 процентов энергии организма.",
            "На Венере один день длится дольше, чем один год.",
            "AI проверяет слайды на основе изученных материалов.",
        ],
        "en": [
            "Sunlight takes about 8 minutes and 20 seconds to reach Earth.",
            "An octopus has three hearts, and its blood is bluish.",
            "Bees use a dance to tell each other where food can be found.",
            "The human brain uses about 20 percent of the body's energy.",
            "A day on Venus lasts longer than one Venusian year.",
            "AI is checking the slides against the material it has learned.",
        ],
    }
    preparing_labels = {
        "uz": ("Tayyorlash jarayonida...", "Tayyorlanmoqda..."),
        "ru": ("Подготовка...", "Готовим презентацию..."),
        "en": ("Preparing...", "Creating your presentation..."),
    }
    fact_index = 0
    animation_task = None
    # 3D Pro: joriy bosqich ("3D obyektlar chizilmoqda: 4/9") — aylanuvchi holat xabarida ham ko'rinadi.
    stage_line = {"text": ""}

    async def rotate_status():
        nonlocal fact_index
        facts = rotating_facts.get(lang, rotating_facts["uz"])
        while True:
            await asyncio.sleep(6.5)
            fact_index = (fact_index + 1) % len(facts)
            try:
                await status.edit_text(
                    f"⚙️ <b>{topic}</b>\n"
                    f"📄 {slide_count} "
                    f"{'ta slayd' if lang == 'uz' else 'слайдов' if lang == 'ru' else 'slides'} "
                    f"{preparing_labels.get(lang, preparing_labels['uz'])[1]}\n\n"
                    f"⏳ <b>{stage_line['text'] or preparing_labels.get(lang, preparing_labels['uz'])[0]}</b>\n"
                    f"💡 {facts[fact_index]}",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    animation_task = asyncio.create_task(rotate_status())

    def progress_cb(done_chunk: int, total: int):
        async def _edit():
            try:
                msgs2 = {
                    "uz": (
                        f"⚙️ <b>{topic}</b>\n"
                        f"📄 {slide_count} ta slayd\n\n"
                        f"⏳ Kontent: {done_chunk}/{total} bo'lak tayyor..."
                    ),
                    "ru": (
                        f"⚙️ <b>{topic}</b>\n"
                        f"📄 {slide_count} слайдов\n\n"
                        f"⏳ Контент: {done_chunk}/{total} частей готово..."
                    ),
                    "en": (
                        f"⚙️ <b>{topic}</b>\n"
                        f"📄 {slide_count} slides\n\n"
                        f"⏳ Content: {done_chunk}/{total} chunks done..."
                    ),
                }
                fact = rotating_facts.get(lang, rotating_facts["uz"])[fact_index % len(rotating_facts.get(lang, rotating_facts["uz"]))]
                await status.edit_text(
                    msgs2.get(lang, msgs2["uz"]) + f"\n💡 {fact}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        asyncio.run_coroutine_threadsafe(_edit(), loop)

    # Admin paneldagi yangilash tugmasi shu ro'yxatga qaraydi: taqdimot
    # navbatdan tashqarida yaratiladi, sanalmasa "hech narsa bajarilmayapti"
    # deb ko'rinardi va qayta ishga tushirish uni uzib qo'yardi.
    work_id = workload.begin("zamonaviy taqdimot")
    html_pages: list = []
    # Yangi o'zbek alifbosi: ichkarida oddiy "uz" (model eski lotinda yozadi), slayd HTML'i va
    # tayyor PPTX esa yangi alifboga o'giriladi (uz_script.py).
    build_language = uz_script.base_language(presentation_language)
    new_alphabet = presentation_language == uz_script.UZ_NEW_LANG
    script_token = uz_script.use(uz_script.LATIN_NEW) if new_alphabet else None

    async def to_new_alphabet(path: str) -> None:
        if new_alphabet and path:
            await asyncio.to_thread(uz_script.normalize_pptx, path, uz_script.LATIN_NEW)

    try:
        # Premium taqdimot modeli admin panelda alohida tanlanadi.
        # Generatsiya sinxron oqimda ishlaydi va u yerdan bazaga murojaat
        # qilib bo'lmaydi, shuning uchun tanlov shu yerda o'qiladi.
        try:
            from config import AI_MODELS
            from services.premium_presentation import llm_client as _llm

            premium_key = await db.get_premium_ai_model()
            if premium_key in AI_MODELS:
                _llm.set_text_model(AI_MODELS[premium_key]["id"])
        except Exception as e:
            logger.error("Premium model tanlovini o'qib bo'lmadi: %s", e)

        from services.premium_presentation import llm_client, pipeline

        # Token hisobi shu taqdimot uchun noldan boshlansin.
        llm_client.reset_usage()

        def on_stage(name: str, info: dict) -> None:
            # Slaydlar yozilib bo'lgach holat xabari yangilanadi.
            if name != "render":
                return
            photos_now = info.get("photos", 0)
            step2 = {
                "uz": (f"⚙️ <b>{topic}</b>\n"
                       f"✅ Slaydlar: {info.get('slides', 0)} ta, rasm: {photos_now} ta\n"
                       f"⏳ PowerPointga o'tkazilmoqda..."),
                "ru": (f"⚙️ <b>{topic}</b>\n"
                       f"✅ Слайдов: {info.get('slides', 0)}, изображений: {photos_now}\n"
                       f"⏳ Переносим в PowerPoint..."),
                "en": (f"⚙️ <b>{topic}</b>\n"
                       f"✅ Slides: {info.get('slides', 0)}, images: {photos_now}\n"
                       f"⏳ Building the PowerPoint file..."),
            }
            asyncio.ensure_future(status.edit_text(step2.get(lang, step2["uz"]), parse_mode="HTML"))

        if _kind_of(data) == KIND_PRO3D:
            import services.pro3d as pro3d

            labels = _PRO3D_STAGES.get(lang) or _PRO3D_STAGES["uz"]

            def on_pro_stage(name: str, info: dict) -> None:
                if name == "image":
                    stage_line["text"] = labels["image"].format(done=info.get("done", 0), total=info.get("total", 0))
                elif name in labels:
                    stage_line["text"] = labels[name].format(**{k: info.get(k, "") for k in ("total", "slides", "photos")})
                else:
                    return

                async def _show():
                    with contextlib.suppress(Exception):
                        await status.edit_text(f"⚙️ <b>{topic}</b>\n📄 {slide_count}\n\n⏳ <b>{stage_line['text']}</b>",
                                               parse_mode="HTML")
                asyncio.run_coroutine_threadsafe(_show(), loop)

            final_path, ready_slides, _photos = await pro3d.build_deck(
                topic, slide_count, language=build_language, level=level,
                preferences=preferences, source_text=source_text, author=client_name, stage_cb=on_pro_stage)
            await to_new_alphabet(final_path)
            html_pages = [None] * ready_slides
        elif _kind_of(data) == KIND_KAT3D:
            import services.kat3d as kat3d

            kat_labels = _KAT3D_STAGES.get(lang) or _KAT3D_STAGES["uz"]

            def on_kat_stage(name: str, info: dict) -> None:
                if name not in kat_labels:
                    return
                stage_line["text"] = kat_labels[name]

                async def _show():
                    with contextlib.suppress(Exception):
                        await status.edit_text(f"⚙️ <b>{topic}</b>\n📄 {slide_count}\n\n⏳ <b>{stage_line['text']}</b>",
                                               parse_mode="HTML")
                asyncio.run_coroutine_threadsafe(_show(), loop)

            final_path, ready_slides = await kat3d.build_deck(
                topic, slide_count, list(data.get("kat3d_ids") or []), language=build_language, level=level,
                preferences=preferences, stage_cb=on_kat_stage)
            await to_new_alphabet(final_path)
            html_pages = [None] * ready_slides
        elif _kind_of(data) == KIND_MED3D:
            from services.med3d import auto as med3d_auto

            med_labels = _MED3D_STAGES.get(lang) or _MED3D_STAGES["uz"]

            def on_med_stage(name: str, info: dict) -> None:
                if name not in med_labels:
                    return
                stage_line["text"] = med_labels[name]

                async def _show():
                    with contextlib.suppress(Exception):
                        await status.edit_text(f"⚙️ <b>{topic}</b>\n📄 {slide_count}\n\n⏳ <b>{stage_line['text']}</b>",
                                               parse_mode="HTML")
                asyncio.run_coroutine_threadsafe(_show(), loop)

            final_path, ready_slides = await med3d_auto.build_deck(
                topic, slide_count, language=build_language, level=level, preferences=preferences,
                stage_cb=on_med_stage, style=data.get("m3d_style") or None)
            await to_new_alphabet(final_path)
            html_pages = [None] * ready_slides
        else:
            # AI slaydlarni HTML/CSS/SVG qilib chizadi, brauzer 1920×1080 joylashtiradi va PPTX
            # ga yig'adi: brauzer nima ko'rsatsa, PowerPointda ham aynan o'sha turadi.
            final_path, ready_slides, _photos = await pipeline.build_deck(
                topic, slide_count, language=build_language, level=level,
                preferences=preferences, source_text=source_text, author=client_name,
                style=data.get("style", ""), volume=data.get("volume", "kop"),
                photo_source=_photo_source(data) or "mix",
                theme_key=data.get("theme_key", "") if _color(data) not in (None, "auto") else "",
                progress_cb=progress_cb, stage_cb=on_stage)
            html_pages = [None] * ready_slides
            await to_new_alphabet(final_path)
            if _text_anim_choice(data):
                await _animate(final_path)

    except Exception as e:
        uz_script.reset(script_token)
        logger.exception("Premium taqdimot generatsiyasida xato: %s", e)
        workload.end(work_id)
        if animation_task:
            animation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await animation_task
        # Balansni qaytarish
        await db.update_user_balance(callback.from_user.id, price)
        from services.premium_presentation.llm_client import NoCredits

        if _kind_of(data) == KIND_MED3D:
            from services.med3d.auto import NotAnatomy

            if isinstance(e, NotAnatomy):        # xato emas — mavzu tana tuzilishiga oid emas
                reason = str(e).strip()
                text = (MED3D_NOT_ANATOMY.get(lang) or MED3D_NOT_ANATOMY["uz"]) + (f"\n<i>{reason[:300]}</i>" if reason else "")
                refund = {"uz": f"💰 {price:,} so'm hisobingizga qaytarildi.",
                          "ru": f"💰 {price:,} сум возвращены на баланс.",
                          "en": f"💰 {price:,} soʻm refunded to your balance."}.get(lang, f"💰 {price:,} so'm qaytarildi.")
                ask = MED3D_ALT_ASK.get(lang) or MED3D_ALT_ASK["uz"]
                with contextlib.suppress(Exception):
                    await status.edit_text(f"{text}\n\n{refund}\n\n{ask}", parse_mode="HTML",
                                           reply_markup=_med3d_alt_keyboard(lang))
                # Mavzu va slaydlar soni saqlanadi: mijoz oddiy taqdimotni tanlasa — qayta yozmaydi.
                await state.update_data(kind=KIND_MODERN, m3d_style="", prompt_mid=None)
                return
        if isinstance(e, NoCredits):
            await _warn_admins_no_credits(callback.bot, str(e))
            e = RuntimeError({
                "uz": "Xizmat vaqtincha ishlamayapti, admin xabardor qilindi.",
                "ru": "Сервис временно недоступен, администратор уведомлён.",
                "en": "The service is temporarily unavailable; the admin has been notified.",
            }.get(lang, "Xizmat vaqtincha ishlamayapti, admin xabardor qilindi."))
        err_msgs = {
            "uz": (
                f"❌ Xatolik yuz berdi:\n{str(e)[:300]}\n\n"
                f"💰 {price:,} so'm hisobingizga qaytarildi.\n"
                f"Qayta urinib ko'ring."
            ),
            "ru": (
                f"❌ Произошла ошибка:\n{str(e)[:300]}\n\n"
                f"💰 {price:,} сум возвращены на баланс.\n"
                f"Попробуйте снова."
            ),
            "en": (
                f"❌ An error occurred:\n{str(e)[:300]}\n\n"
                f"💰 {price:,} soʻm refunded to your balance.\n"
                f"Please try again."
            ),
        }
        try:
            await status.edit_text(err_msgs.get(lang, err_msgs["uz"]), parse_mode="HTML")
        except Exception:
            pass
        await state.clear()
        return
    uz_script.reset(script_token)

    if animation_task:
        animation_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await animation_task

    # Tayyor — yuborish
    ready = len(html_pages)
    done_msgs = {
        "uz": f"✅ <b>{topic}</b> — tayyor!\n📊 {ready} slayd | Yuborilmoqda...",
        "ru": f"✅ <b>{topic}</b> — готово!\n📊 {ready} слайдов | Отправляю...",
        "en": f"✅ <b>{topic}</b> — done!\n📊 {ready} slides | Sending...",
    }
    try:
        await status.edit_text(done_msgs.get(lang, done_msgs["uz"]), parse_mode="HTML")
    except Exception:
        pass

    filename = f"Taqdimot_{topic[:30].replace(' ', '_')}.pptx"
    if _kind_of(data) in (KIND_MED3D, KIND_KAT3D):   # ko'rish sharti fayl nomining o'zida — mijoz tanlagan tilda
        filename = med3d_filename(topic, build_language)
    try:
        from aiogram.types import FSInputFile
        document = FSInputFile(final_path, filename=filename)
        await callback.message.answer_document(document=document)
        if _text_anim_choice(data):          # ogohlantirish fayl izohida emas, alohida xabar
            with contextlib.suppress(Exception):
                await callback.message.answer(anim_note(lang))
        if _kind_of(data) == KIND_PRO3D:
            with contextlib.suppress(Exception):
                await callback.message.answer(pro3d_note(lang))
        if _kind_of(data) in (KIND_MED3D, KIND_KAT3D):   # telefonda 3D ko'rinmaydi — yo'riqnoma videosi bilan
            with contextlib.suppress(Exception):
                await _send_med3d_guide(callback.message, lang)
            with contextlib.suppress(Exception):     # telefonda Morph bilan ko'rish: serverda videoga o'giriladi
                from services import slide_player

                player_kb = slide_player.offer(final_path, user_id=callback.from_user.id,
                                               chat_id=callback.message.chat.id, user_lang=lang)
                if player_kb:
                    await callback.message.answer(slide_player.offer_text(lang), reply_markup=player_kb)
        logger.info("Premium taqdimot yuborildi: %s → %s", final_path, callback.from_user.id)
        if _kind_of(data) not in (KIND_PRO3D, KIND_MED3D, KIND_KAT3D):  # "Rahmat" animatsiyasi zamonaviyda
            await _offer_thanks_anim(callback, db, final_path, topic=topic, data=data,
                                     language=presentation_language, author=client_name, filename=filename,
                                     lang=lang)
        try:
            from services.store_publisher import schedule_publish

            schedule_publish(callback.bot, final_path, topic, "premium_taqdimot",
                             customer_name=client_name,
                             language="uz" if uz_script.script_of_language(presentation_language) else presentation_language)
        except Exception as store_err:
            logger.warning("Katalogga yo'naltirilmadi (premium): %s", store_err)
    except Exception as send_err:
        logger.exception("Premium taqdimot yuborishda xato: %s", send_err)
        # Balansni qaytarish
        await db.update_user_balance(callback.from_user.id, price)
        send_err_msgs = {
            "uz": (
                f"❌ Fayl yuborishda xato yuz berdi.\n\n"
                f"💰 {price:,} so'm hisobingizga qaytarildi.\n"
                f"Qayta urinib ko'ring yoki admin bilan bog'laning."
            ),
            "ru": (
                f"❌ Ошибка при отправке файла.\n\n"
                f"💰 {price:,} сум возвращены на баланс.\n"
                f"Попробуйте снова или обратитесь к администратору."
            ),
            "en": (
                f"❌ Error sending the file.\n\n"
                f"💰 {price:,} soʻm refunded to your balance.\n"
                f"Please try again or contact the administrator."
            ),
        }
        try:
            await callback.message.answer(
                send_err_msgs.get(lang, send_err_msgs["uz"]), parse_mode="HTML"
            )
        except Exception:
            pass
    finally:
        workload.end(work_id)
        # Temp faylni o'chirish
        try:
            os.remove(final_path)
        except Exception:
            pass

    await state.clear()


async def _animate(path: str) -> None:
    """Yozuv animatsiyasi: har sahifa ochilganda mazmuni o'zi navbat bilan chiqadi. Xato — animatsiyasiz qoladi."""
    from services.premium_presentation import slide_anim

    try:
        await asyncio.get_running_loop().run_in_executor(None, slide_anim.apply, path)
    except Exception as exc:
        logger.warning("Yozuv animatsiyasi qo'shilmadi: %s", exc)


async def _offer_thanks_anim(callback: CallbackQuery, db: Database, final_path: str, *, topic: str, data: dict,
                             language: str, author: str, filename: str, lang: str) -> None:
    """Admin yoqqan bo'lsa: taqdimot oxiriga "Rahmat" animatsiyasini qo'shish tugmasi (yaratish oqimidan tashqarida)."""
    from services import thanks_anim

    try:
        if not await db.get_feature_status(thanks_anim.FEATURE, default=False):
            return
        kb = thanks_anim.offer(final_path, topic=topic, style=data.get("style", ""), volume=data.get("volume", "kop"),
                               language=language, author=author, filename=filename,
                               user_id=callback.from_user.id, chat_id=callback.message.chat.id, user_lang=lang)
        if kb:
            await callback.message.answer(thanks_anim.offer_text(lang), reply_markup=kb)
    except Exception as exc:  # taklif chiqmasa ham taqdimot allaqachon yuborilgan
        logger.warning("Rahmat animatsiyasi tugmasi chiqmadi: %s", exc)


@router.callback_query(F.data.startswith("tanim_no:"))
async def premium_ppt_thanks_anim_decline(callback: CallbackQuery):
    """"❌ Kerak emas": taklif xabari o'chadi, saqlangan nusxa ham o'chiriladi."""
    from services import thanks_anim

    await callback.answer()
    thanks_anim.decline(callback.data.split(":", 1)[1], callback.from_user.id)
    with contextlib.suppress(Exception):
        await callback.message.delete()


_last_credit_warning = 0.0


async def _warn_admins_no_credits(bot, detail: str) -> None:
    """OpenRouter mablag'i tugaganini adminlarga aytadi (10 daqiqada bir marta)."""
    import time
    from config import ADMIN_IDS

    global _last_credit_warning
    if time.monotonic() - _last_credit_warning < 600:
        return
    _last_credit_warning = time.monotonic()
    text = ("⚠️ OpenRouter hisobida mablag' tugadi — zamonaviy taqdimot "
            "yaratilmayapti, mijozlarga pul qaytarilmoqda.\n"
            "To'ldirish: https://openrouter.ai/settings/credits\n\n"
            f"{detail[:200]}")
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:
            logger.warning("Adminga xabar yuborilmadi (%s): %s", admin_id, exc)


# ──────────────────────────────────────────────────────────────── BACK

@router.callback_query(F.data == "prem_ppt_back")
async def premium_ppt_back(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    await state.clear()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    from bot.keyboards import get_main_keyboard
    from database.database import Database as DB
    media_enabled = await db.get_feature_status("media")
    book_translate_enabled = await db.get_feature_status("book_translate")
    mahsus_ishlanma_enabled = await db.get_feature_status("mahsus_ishlanma")
    await callback.message.delete()
    await callback.message.answer(
        "🏠 Bosh menyu",
        reply_markup=get_main_keyboard(
            lang,
            media_enabled=media_enabled,
            book_translate_enabled=book_translate_enabled,
            mahsus_ishlanma_enabled=mahsus_ishlanma_enabled,
        )
    )
