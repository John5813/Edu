"""
Premium taqdimot handleri — Ustalar loyihasidan olingan yangi taqdimot tizimi.
Mavjud hujjat xizmatlariga halaqit qilmaydi, to'liq mustaqil modul.
"""
import asyncio
import contextlib
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
    topic = clean(data.get("topic"), 200)
    if topic:
        lines.append(f"📝 Mavzu: <b>{topic}</b>")
    if data.get("slide_count"):
        lines.append(f"📄 Slaydlar: {int(data['slide_count'])} ta")
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
                 "ru": "🇷🇺 Русский", "en": "🇬🇧 English", "kk": "🇰🇿 Қазақша"}


def _language_label(code: str) -> str:
    """Buyurtma xulosasidagi til yozuvi."""
    if code == uz_script.UZ_CYRILLIC_LANG:
        return "UZ (кирилл)"
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


# Orqaga: har qadamning oldingisi. Birinchi qadamdan — bosh menyu.
_PREVIOUS = {"script": "topic", "name": "topic", "prefs": "name", "source": "prefs",
             "source_input": "source", "kind": "source", "style": "kind", "volume": "style",
             "summary": "count"}


def _previous_step(data: dict):
    """Orqaga qadam: slaydlar sonidan oldin — matn hajmi (zamonaviy) yoki uslub (orqa fonlar)."""
    step = data.get("step") or ""
    if step == "name" and data.get("script_asked"):
        return "script"
    if step == "count":
        # Zamonaviy — uslubga, infografik va klassik — tur tanloviga qaytadi.
        return "style" if _kind_of(data) == KIND_MODERN else "kind"
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

async def _step_topic(message: Message, state: FSMContext, lang: str) -> None:
    await _prompt(message, state, _t(lang, "ask_topic"),
                  _markup([_back_row(lang, "prem_ppt_back")]), "topic",
                  PremiumPresentationStates.waiting_for_topic_text)


@router.message(F.text.in_(ENTRY_TEXTS))
async def premium_presentation_start(message: Message, state: FSMContext, db: Database):
    """"Taqdimot" tugmasi: birinchi savol — mavzu."""
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

    await _step_topic(message, state, lang)


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
    await _step_name(message, state, lang)


async def _step_script(message: Message, state: FSMContext, lang: str) -> None:
    markup = _markup([[InlineKeyboardButton(text=_t(lang, "script_latin"), callback_data="prem_ppt_script:latin"),
                       InlineKeyboardButton(text=_t(lang, "script_cyrillic"), callback_data="prem_ppt_script:cyrillic")],
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
    else:
        language = uz_script.UZ_CYRILLIC_LANG
    await _drop_prompt(callback.bot, callback.message.chat.id, state)
    await state.update_data(topic=topic, presentation_language=language, script_asked=True)
    await _step_name(callback.message, state, lang)


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
    await _step_source(message, state, lang)


@router.callback_query(F.data == "prem_ppt_skip_preferences",
                       PremiumPresentationStates.waiting_for_preferences)
async def premium_ppt_skip_preferences(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    await _drop_prompt(callback.bot, callback.message.chat.id, state)
    await state.update_data(preferences="")
    await _step_source(callback.message, state, lang)


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
        await _step_kind(callback.message, state, lang)
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
    await _store_source(message, state, lang, material)


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
    await _store_source(message, state, lang, material)


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
    await _store_source(message, state, lang, material)


async def _store_source(message: Message, state: FSMContext, lang: str, material):
    await _drop_prompt(message.bot, message.chat.id, state)
    await state.update_data(source_kind=material.kind, source_text=material.text,
                            source_label=material.label)
    if material.label:
        await message.answer(
            get_text(lang, "pw_source_ok", label=material.label,
                     words=len(material.text.split())),
            parse_mode="HTML")
    await _step_kind(message, state, lang)


# ── 4b. Taqdimot turi: infografik / zamonaviy / klassik
# Ilgari uch xil mahsulot bitta uslub ro'yxatida aralashgan edi: eng yangi infografik dizayn uslub va
# "matn hajmi" qadamlari ortida yashirinardi. Endi mijoz turini birinchi tanlaydi; tur keraksiz
# qadamlarni o'zi belgilaydi (infografik — uslub va hajm so'ralmaydi, klassik — shablonlarga o'tadi).
# Faqat tugmalar — namuna rasm yuborilmaydi.

KIND_INFO, KIND_MODERN, KIND_CLASSIC = "info", "modern", "classic"
KINDS = (KIND_INFO, KIND_MODERN, KIND_CLASSIC)
# Infografik tur uchun uslub so'ralmaydi: vektor dizayner ko'rinishni o'zi tanlaydi.
INFO_STYLE = "toza"
_KIND_BUTTONS = {
    KIND_INFO: {"uz": "🎨 Infografik — yangi", "ru": "🎨 Инфографика — новинка",
                "en": "🎨 Infographic — new", "kk": "🎨 Инфографика — жаңа"},
    KIND_MODERN: {"uz": "📝 Zamonaviy — batafsil matn", "ru": "📝 Современная — подробный текст",
                  "en": "📝 Modern — detailed text", "kk": "📝 Заманауи — толық мәтін"},
    KIND_CLASSIC: {"uz": "📄 Klassik — tayyor shablonlar", "ru": "📄 Классическая — готовые шаблоны",
                   "en": "📄 Classic — ready templates", "kk": "📄 Классикалық — дайын үлгілер"},
}
_KIND_NAMES = {
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


def _kind_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key in KINDS:
        builder.button(text=_KIND_BUTTONS[key].get(lang) or _KIND_BUTTONS[key]["uz"],
                       callback_data=f"prem_ppt_kind:{key}")
    builder.adjust(1)
    builder.row(*_back_row(lang))
    return builder.as_markup()


async def _step_kind(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    text = _topic_line(data, lang) + (_KIND_PROMPT.get(lang) or _KIND_PROMPT["uz"])
    await _prompt(message, state, text, _kind_keyboard(lang), "kind", PremiumPresentationStates.waiting_for_kind)


@router.callback_query(F.data.startswith("prem_ppt_kind:"), PremiumPresentationStates.waiting_for_kind)
async def premium_ppt_kind_selected(callback: CallbackQuery, state: FSMContext, db: Database):
    """Tur tanlandi: infografik — darhol hajm (slaydlar soni), zamonaviy — uslub, klassik — shablonlar."""
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    kind = callback.data.split(":", 1)[1]
    if kind not in KINDS:
        kind = KIND_INFO
    await state.update_data(kind=kind)
    if kind == KIND_CLASSIC:
        await state.update_data(style=SIMPLE_STYLE, volume="")
        await _step_count(callback.message, state, lang, db)
    elif kind == KIND_INFO:
        await state.update_data(style=INFO_STYLE, volume="kam")
        await _step_count(callback.message, state, lang, db)
    else:
        await state.update_data(volume="kop")
        await _step_style(callback.message, state, lang)


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

def _count_options(style: str):
    """[(slaydlar soni, narx)] — orqa fonlarda faqat 10/15/20."""
    if style == SIMPLE_STYLE:
        from config import PRESENTATION_PRICES
        return sorted(PRESENTATION_PRICES.items())
    return [(n, _get_price(n)) for n in (5, 8, 10, 12, 15, 20, 25, 30)]


def _count_keyboard(lang: str, style: str = "") -> InlineKeyboardMarkup:
    word = {"uz": "ta slayd", "ru": "слайдов", "en": "slides"}.get(lang, "ta slayd")
    som = {"uz": "so'm", "ru": "сум", "en": "soʻm"}.get(lang, "so'm")
    prefix = "ppt_fon" if style == SIMPLE_STYLE else "prem_ppt_count"
    builder = InlineKeyboardBuilder()
    for count, price in _count_options(style):
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
                  _count_keyboard(lang, style), "count",
                  PremiumPresentationStates.waiting_for_count)


@router.callback_query(F.data.startswith("prem_ppt_count:"),
                       PremiumPresentationStates.waiting_for_count)
async def premium_ppt_got_count(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    lang = await _lang_of(callback.from_user.id, db)
    count = max(MIN_SLIDES, min(int(callback.data.split(":")[1]), MAX_SLIDES))
    await state.update_data(slide_count=count)
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
        "topic": uz_script.convert(data.get("topic", ""), uz_script.LATIN)
        if language == "uz" else data.get("topic", ""),
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

def _confirm_keyboard(lang: str, current_language: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code in ("uz", uz_script.UZ_CYRILLIC_LANG, "ru", "en", "kk"):
        mark = "✓ " if code == current_language else ""
        builder.button(text=f"{mark}{_LANG_BUTTONS[code]}", callback_data=f"prem_ppt_lang:{code}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text=_t(lang, "confirm"), callback_data="prem_ppt_confirm"))
    builder.row(*_back_row(lang))
    return builder.as_markup()


def _summary(data: dict, lang: str):
    """(matn, klaviatura) — to'lovdan oldingi xulosa."""
    def esc(value, limit=160):
        import html as _html
        return _html.escape(str(value or "").strip(), quote=False)[:limit]

    slide_count = int(data.get("slide_count") or MIN_SLIDES)
    price = _get_price(slide_count)
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
    lines += [f"📊 {slides_l}: <b>{slide_count}</b>",
              f"💰 {price_l}: <b>{price:,} {cur}</b>", "", ask]
    return "\n".join(lines), _confirm_keyboard(lang, language)


async def _step_summary(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    price = _get_price(int(data.get("slide_count") or MIN_SLIDES))
    await state.update_data(price=price)
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
             "volume": _step_volume, "kind": _step_kind}
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
    slide_count = int(data.get("slide_count", 10))
    sent = await pay.send_invoice(
        callback.message, CHECKOUT, lang, price,
        title="Zamonaviy taqdimot",
        description=f"{slide_count} ta slaydli zamonaviy taqdimot",
    )
    if sent:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass


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

    if payment_method == "balance":
        await db.update_user_balance(callback.from_user.id, -price)
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
                    f"⏳ <b>{preparing_labels.get(lang, preparing_labels['uz'])[0]}</b>\n"
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

        # AI slaydlarni HTML/CSS/SVG qilib chizadi, brauzer 1920×1080 joylashtiradi va PPTX
        # ga yig'adi: brauzer nima ko'rsatsa, PowerPointda ham aynan o'sha turadi.
        final_path, ready_slides, _photos = await pipeline.build_deck(
            topic, slide_count, language=presentation_language, level=level,
            preferences=preferences, source_text=source_text, author=client_name,
            style=data.get("style", ""), volume=data.get("volume", "kop"),
            progress_cb=progress_cb, stage_cb=on_stage)
        html_pages = [None] * ready_slides

    except Exception as e:
        logger.exception("Premium taqdimot generatsiyasida xato: %s", e)
        workload.end(work_id)
        if animation_task:
            animation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await animation_task
        # Balansni qaytarish
        await db.update_user_balance(callback.from_user.id, price)
        from services.premium_presentation.llm_client import NoCredits

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
    try:
        from aiogram.types import FSInputFile
        document = FSInputFile(final_path, filename=filename)
        await callback.message.answer_document(document=document)
        logger.info("Premium taqdimot yuborildi: %s → %s", final_path, callback.from_user.id)
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
