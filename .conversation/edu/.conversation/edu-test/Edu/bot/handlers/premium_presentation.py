"""
Premium taqdimot handleri — Ustalar loyihasidan olingan yangi taqdimot tizimi.
Mavjud hujjat xizmatlariga halaqit qilmaydi, to'liq mustaqil modul.
"""
import asyncio
import contextlib
import logging
import os

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, BufferedInputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.states import PremiumPresentationStates
from database.database import Database
from translations import get_text
from config import som_to_stars, STARS_RATE
from bot.keyboards import get_doc_language_keyboard

router = Router()
logger = logging.getLogger(__name__)

MIN_SLIDES = 5
MAX_SLIDES = 30

# Narx (so'm) — slide soni bo'yicha
def _get_price(slide_count: int) -> int:
    if slide_count <= 10:
        return 15000
    elif slide_count <= 20:
        return 25000
    else:
        return 35000


def _back_text(lang: str) -> str:
    if lang == "ru": return "🔙 Назад"
    if lang == "en": return "🔙 Back"
    return "🔙 Orqaga"


LEVEL_LABELS = {
    1: {"uz": "🏫 Maktab darsligi", "ru": "🏫 Школьный уровень", "en": "🏫 School level"},
    2: {"uz": "🎓 Student", "ru": "🎓 Студент", "en": "🎓 Student"},
    3: {"uz": "📚 Akademik", "ru": "📚 Академический", "en": "📚 Academic"},
}


def _client_name_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if lang == "ru":
        builder.button(text="⏭ Пропустить", callback_data="prem_ppt_skip_name")
        builder.button(text="🔙 Назад", callback_data="prem_ppt_back")
    elif lang == "en":
        builder.button(text="⏭ Skip", callback_data="prem_ppt_skip_name")
        builder.button(text="🔙 Back", callback_data="prem_ppt_back")
    else:
        builder.button(text="⏭ Tashlab ketish", callback_data="prem_ppt_skip_name")
        builder.button(text="🔙 Orqaga", callback_data="prem_ppt_back")
    builder.adjust(2)
    return builder.as_markup()


def _preferences_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    labels = {
        "uz": ("⏭ O‘tkazib yuborish", "🔙 Orqaga"),
        "ru": ("⏭ Пропустить", "🔙 Назад"),
        "en": ("⏭ Skip", "🔙 Back"),
    }
    skip, back = labels.get(lang, labels["uz"])
    builder.button(text=skip, callback_data="prem_ppt_skip_preferences")
    builder.button(text=back, callback_data="prem_ppt_back_to_name")
    builder.adjust(2)
    return builder.as_markup()


def _level_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if lang == "ru":
        builder.button(text="🏫 1. Школьный уровень", callback_data="prem_ppt_level:1")
        builder.button(text="🎓 2. Студент", callback_data="prem_ppt_level:2")
        builder.button(text="📚 3. Академический", callback_data="prem_ppt_level:3")
        builder.button(text="🔙 Назад", callback_data="prem_ppt_back_to_name")
    elif lang == "en":
        builder.button(text="🏫 1. School level", callback_data="prem_ppt_level:1")
        builder.button(text="🎓 2. Student", callback_data="prem_ppt_level:2")
        builder.button(text="📚 3. Academic", callback_data="prem_ppt_level:3")
        builder.button(text="🔙 Back", callback_data="prem_ppt_back_to_name")
    else:
        builder.button(text="🏫 1. Maktab darsligi", callback_data="prem_ppt_level:1")
        builder.button(text="🎓 2. Student", callback_data="prem_ppt_level:2")
        builder.button(text="📚 3. Akademik", callback_data="prem_ppt_level:3")
        builder.button(text="🔙 Orqaga", callback_data="prem_ppt_back_to_name")
    builder.adjust(1)
    return builder.as_markup()


def _slide_count_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for n in [5, 8, 10, 12, 15, 20, 25, 30]:
        price = _get_price(n)
        builder.button(text=f"{n} ta | {price:,} so'm", callback_data=f"prem_ppt_count:{n}")
    builder.button(text=_back_text(lang), callback_data="prem_ppt_back_to_level")
    builder.adjust(2)
    return builder.as_markup()


def _confirm_keyboard(lang: str, slide_count: int, price: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if lang == "ru":
        builder.button(text="✅ Подтвердить заказ", callback_data="prem_ppt_confirm")
        builder.button(text="🔙 Назад", callback_data="prem_ppt_recount")
    elif lang == "en":
        builder.button(text="✅ Confirm order", callback_data="prem_ppt_confirm")
        builder.button(text="🔙 Back", callback_data="prem_ppt_recount")
    else:
        builder.button(text="✅ Buyurtmani tasdiqlash", callback_data="prem_ppt_confirm")
        builder.button(text="🔙 Orqaga", callback_data="prem_ppt_recount")
    builder.adjust(1)
    return builder.as_markup()


def _payment_keyboard(lang: str, price: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    stars = som_to_stars(price)
    if lang == "ru":
        builder.button(text=f"💰 С баланса · {price:,} сум", callback_data="prem_ppt_pay_balance")
        builder.button(text=f"⭐ Оплатить {stars} Stars", callback_data="prem_ppt_pay_stars")
        builder.button(text="🔙 Назад", callback_data="prem_ppt_back_to_confirm")
    elif lang == "en":
        builder.button(text=f"💰 From balance · {price:,} soʻm", callback_data="prem_ppt_pay_balance")
        builder.button(text=f"⭐ Pay {stars} Stars", callback_data="prem_ppt_pay_stars")
        builder.button(text="🔙 Back", callback_data="prem_ppt_back_to_confirm")
    else:
        builder.button(text=f"💰 Balansdan · {price:,} so'm", callback_data="prem_ppt_pay_balance")
        builder.button(text=f"⭐ {stars} Stars bilan to‘lash", callback_data="prem_ppt_pay_stars")
        builder.button(text="🔙 Orqaga", callback_data="prem_ppt_back_to_confirm")
    builder.adjust(1)
    return builder.as_markup()


def _code_feedback_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    labels = {
        "uz": ("❗ Xato chiqdi — tuzatish", "✅ Muvaffaqiyatli ishladi"),
        "ru": ("❗ Возникла ошибка — исправить", "✅ Успешно работает"),
        "en": ("❗ An error occurred — fix it", "✅ It works successfully"),
    }
    report, success = labels.get(lang, labels["uz"])
    builder.button(text=report, callback_data="prem_ppt_report_error")
    builder.button(text=success, callback_data="prem_ppt_code_success")
    builder.adjust(1)
    return builder.as_markup()


class _MessageCallbackAdapter:
    """Successful Stars paymentni mavjud generatsiya oqimiga ulaydi."""

    def __init__(self, message: Message, data: str = ""):
        self.message = message
        self.from_user = message.from_user
        self.data = data

    async def answer(self, *args, **kwargs):
        return None


# ──────────────────────────────────────────────────────────────── ENTRY POINT

@router.message(F.text.in_(["⭐ Premium taqdimot", "⭐ Премиум презентация", "⭐ Premium presentation"]))
async def premium_presentation_start(message: Message, state: FSMContext, db: Database):
    """Premium taqdimot tugmasi bosilganda"""
    await state.clear()
    user = await db.get_user(message.from_user.id)
    lang = user.language if user else "uz"

    msgs = {
        "uz": (
            "⭐ <b>Premium Taqdimot</b>\n\n"
            "OpenAI yordamida professional taqdimot uchun Python kodini yaratadi:\n\n"
            "✅ Faqat toza .txt source code\n"
            "✅ python-pptx va 16:9 o‘lcham\n"
            "✅ Har slayd uchun alohida premium tuzilma\n"
            "✅ Xato bo‘lsa, shu kod qayta tuzatiladi\n\n"
            "🌍 <b>Taqdimot tilini tanlang:</b>"
        ),
        "ru": (
            "⭐ <b>Премиум Презентация</b>\n\n"
            "Создаёт Python-код профессиональной презентации через OpenAI:\n\n"
            "✅ Только чистый исходный код в .txt\n"
            "✅ python-pptx и формат 16:9\n"
            "✅ Уникальная структура каждого слайда\n"
            "✅ Ошибки можно отправить на исправление\n\n"
            "🌍 <b>Выберите язык презентации:</b>"
        ),
        "en": (
            "⭐ <b>Premium Presentation</b>\n\n"
            "Creates professional presentation Python code with OpenAI:\n\n"
            "✅ Clean .txt source code only\n"
            "✅ python-pptx and 16:9 format\n"
            "✅ A distinct structure for every slide\n"
            "✅ Send any error back for a fix\n\n"
            "🌍 <b>Choose the presentation language:</b>"
        ),
    }

    await state.set_state(PremiumPresentationStates.waiting_for_topic)
    await message.answer(
        msgs.get(lang, msgs["uz"]),
        parse_mode="HTML",
        reply_markup=get_doc_language_keyboard(lang, back_callback="prem_ppt_back"),
    )


@router.callback_query(
    F.data.startswith("doc_lang_"),
    PremiumPresentationStates.waiting_for_topic,
)
async def premium_ppt_language_selected(
    callback: CallbackQuery, state: FSMContext, db: Database
):
    """Professional taqdimot uchun natija tilini tanlash."""
    await callback.answer()
    presentation_language = callback.data.split("_")[-1]
    await state.update_data(presentation_language=presentation_language)

    try:
        await callback.message.delete()
    except Exception:
        pass

    user = await db.get_user(callback.from_user.id)
    ui_lang = user.language if user else "uz"
    topic_prompts = {
        "uz": "📝 Taqdimot mavzusini kiriting:",
        "ru": "📝 Введите тему презентации:",
        "en": "📝 Enter the presentation topic:",
    }
    await callback.message.answer(
        topic_prompts.get(ui_lang, topic_prompts["uz"]),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text=_back_text(ui_lang), callback_data="prem_ppt_back"
                )
            ]]
        ),
    )
    await state.set_state(PremiumPresentationStates.waiting_for_topic_text)


# ──────────────────────────────────────────────────────────────── TOPIC

@router.message(PremiumPresentationStates.waiting_for_topic_text)
async def premium_ppt_got_topic(message: Message, state: FSMContext, db: Database):
    user = await db.get_user(message.from_user.id)
    lang = user.language if user else "uz"
    topic = (message.text or "").strip()

    if len(topic) < 3:
        short_msg = {
            "uz": "❌ Mavzu juda qisqa. Kamida 3 ta belgi kiriting.",
            "ru": "❌ Тема слишком короткая. Введите минимум 3 символа.",
            "en": "❌ Topic too short. Enter at least 3 characters.",
        }
        await message.answer(short_msg.get(lang, short_msg["uz"]))
        return

    await state.update_data(topic=topic)
    await state.set_state(PremiumPresentationStates.waiting_for_client_name)

    msgs = {
        "uz": (
            f"📋 Mavzu: <b>{topic}</b>\n\n"
            "👤 <b>Mijozning ism-familiyasini kiriting</b>\n"
            "<i>(Taqdimotning sarlavha sahifasiga yoziladi)</i>"
        ),
        "ru": (
            f"📋 Тема: <b>{topic}</b>\n\n"
            "👤 <b>Введите имя и фамилию клиента</b>\n"
            "<i>(Будет указано на титульном слайде)</i>"
        ),
        "en": (
            f"📋 Topic: <b>{topic}</b>\n\n"
            "👤 <b>Enter client's full name</b>\n"
            "<i>(Will appear on the title slide)</i>"
        ),
    }
    await message.answer(msgs.get(lang, msgs["uz"]), parse_mode="HTML",
                         reply_markup=_client_name_keyboard(lang))


# ──────────────────────────────────────────────────────────────── CLIENT NAME

@router.message(PremiumPresentationStates.waiting_for_client_name)
async def premium_ppt_got_name(message: Message, state: FSMContext, db: Database):
    user = await db.get_user(message.from_user.id)
    lang = user.language if user else "uz"
    client_name = (message.text or "").strip()
    await state.update_data(client_name=client_name)
    await _show_preferences_step(message, state, lang, is_callback=False)


@router.callback_query(F.data == "prem_ppt_skip_name")
async def premium_ppt_skip_name(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    await state.update_data(client_name="")
    await _show_preferences_step(callback, state, lang, is_callback=True)


async def _show_preferences_step(source, state: FSMContext, lang: str, is_callback: bool):
    """Foydalanuvchidan qat'iy forma emas, erkin ijodiy yo'nalish oladi."""
    await state.set_state(PremiumPresentationStates.waiting_for_preferences)
    data = await state.get_data()
    topic = data.get("topic", "")
    msgs = {
        "uz": (
            f"📋 Mavzu: <b>{topic}</b>\n\n"
            "🎨 <b>Taqdimot qanday bo‘lishini xohlaysiz?</b>\n\n"
            "Istaklaringizni erkin yozing: auditoriya, maqsad, ohang, ranglar, "
            "misollar, uslub yoki alohida talablar. Hech qanday qat’iy shakl shart emas — "
            "AI eng yaxshi tuzilma va dizaynni o‘zi tanlaydi.\n\n"
            "<i>Masalan: investorlar uchun ishonchli va zamonaviy, ko‘proq vizual, "
            "o‘zbek tilida, qisqa va ta’sirli.</i>"
        ),
        "ru": (
            f"📋 Тема: <b>{topic}</b>\n\n"
            "🎨 <b>Каким вы хотите видеть презентацию?</b>\n\n"
            "Напишите пожелания свободно: аудитория, цель, тон, цвета, примеры, "
            "стиль или любые требования. Жёсткий формат не нужен — AI сам выберет "
            "лучшую структуру и дизайн.\n\n"
            "<i>Например: современная презентация для инвесторов, больше визуала, "
            "коротко и убедительно.</i>"
        ),
        "en": (
            f"📋 Topic: <b>{topic}</b>\n\n"
            "🎨 <b>How should the presentation feel?</b>\n\n"
            "Describe anything freely: audience, goal, tone, colors, examples, "
            "style, or special requirements. No rigid format is needed — AI will "
            "choose the best structure and design.\n\n"
            "<i>For example: modern and confident for investors, visual, concise, "
            "and persuasive.</i>"
        ),
    }
    text = msgs.get(lang, msgs["uz"])
    kb = _preferences_keyboard(lang)
    if is_callback:
        await source.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await source.answer(text, parse_mode="HTML", reply_markup=kb)


async def _show_auto_confirm(source, state: FSMContext, lang: str, is_callback: bool):
    await state.set_state(PremiumPresentationStates.waiting_for_slide_count)
    data = await state.get_data()
    topic = data.get("topic", "")
    client_name = data.get("client_name", "")
    preferences = data.get("preferences", "")
    preference_line = {
        "uz": "AI daraja, tuzilma, vizual konsepsiya, ranglar, rasmlar va diagrammalarni "
               "mavzuga mos ravishda o‘zi tanlaydi.",
        "ru": "AI сам выберет уровень, структуру, визуальную концепцию, цвета, изображения "
               "и диаграммы по теме.",
        "en": "AI will choose the level, structure, visual concept, colors, images, and "
               "charts based on the topic.",
    }
    name_line = {
        "uz": f"\n👤 Ism-familiya: <b>{client_name or 'ko‘rsatilmagan — o‘tkazib yuborilgan'}</b>",
        "ru": f"\n👤 Имя: <b>{client_name or 'не указано — пропущено'}</b>",
        "en": f"\n👤 Name: <b>{client_name or 'not provided — skipped'}</b>",
    }
    preferences_line = {
        "uz": f"\n🎨 Istaklar: <i>{preferences or 'ko‘rsatilmagan — AI o‘zi tanlaydi'}</i>",
        "ru": f"\n🎨 Пожелания: <i>{preferences or 'не указаны — AI выберет сам'}</i>",
        "en": f"\n🎨 Preferences: <i>{preferences or 'not provided — AI will decide'}</i>",
    }
    msgs = {
        "uz": f"⭐ <b>AI erkin rejimi</b>\n\n📋 Mavzu: <b>{topic}</b>"
                f"{name_line['uz']}{preferences_line['uz']}\n\n{preference_line['uz']}\n\n"
               "📊 Endi slaydlar sonini tanlang:",
        "ru": f"⭐ <b>Свободный режим AI</b>\n\n📋 Тема: <b>{topic}</b>"
                f"{name_line['ru']}{preferences_line['ru']}\n\n{preference_line['ru']}\n\n"
               "📊 Теперь выберите количество слайдов:",
        "en": f"⭐ <b>AI free mode</b>\n\n📋 Topic: <b>{topic}</b>"
                f"{name_line['en']}{preferences_line['en']}\n\n{preference_line['en']}\n\n"
               "📊 Now choose the number of slides:",
    }
    kb = _slide_count_keyboard(lang)
    if is_callback:
        await source.message.edit_text(msgs.get(lang, msgs["uz"]), parse_mode="HTML", reply_markup=kb)
    else:
        await source.answer(msgs.get(lang, msgs["uz"]), parse_mode="HTML", reply_markup=kb)


@router.message(PremiumPresentationStates.waiting_for_preferences)
async def premium_ppt_got_preferences(message: Message, state: FSMContext, db: Database):
    user = await db.get_user(message.from_user.id)
    lang = user.language if user else "uz"
    preferences = (message.text or "").strip()
    await state.update_data(preferences=preferences)
    await _show_auto_confirm(message, state, lang, is_callback=False)


@router.callback_query(F.data == "prem_ppt_skip_preferences",
                       PremiumPresentationStates.waiting_for_preferences)
async def premium_ppt_skip_preferences(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    await state.update_data(preferences="")
    await _show_auto_confirm(callback, state, lang, is_callback=True)


async def _show_level_step(source, state: FSMContext, lang: str, is_callback: bool):
    await state.set_state(PremiumPresentationStates.waiting_for_level)
    data = await state.get_data()
    topic = data.get("topic", "")
    msgs = {
        "uz": (
            f"📋 Mavzu: <b>{topic}</b>\n\n"
            "📐 <b>Taqdimot qaysi daraja uchun?</b>\n\n"
            "🏫 <b>1. Maktab darsligi</b>\n"
            "   Bolalar uchun juda oddiy, hayotdan misollar\n\n"
            "🎓 <b>2. Student</b>\n"
            "   Tartibli, aniq ma'lumotlar, murakkablik o'rtacha\n\n"
            "📚 <b>3. Akademik</b>\n"
            "   Chuqur tahlil, ilmiy faktlar, professional til"
        ),
        "ru": (
            f"📋 Тема: <b>{topic}</b>\n\n"
            "📐 <b>Для какого уровня презентация?</b>\n\n"
            "🏫 <b>1. Школьный уровень</b>\n"
            "   Очень просто, примеры из жизни\n\n"
            "🎓 <b>2. Студент</b>\n"
            "   Структурировано, точные данные, средняя сложность\n\n"
            "📚 <b>3. Академический</b>\n"
            "   Глубокий анализ, научные факты, профессиональный язык"
        ),
        "en": (
            f"📋 Topic: <b>{topic}</b>\n\n"
            "📐 <b>What level is this presentation for?</b>\n\n"
            "🏫 <b>1. School level</b>\n"
            "   Very simple, real-life examples\n\n"
            "🎓 <b>2. Student</b>\n"
            "   Structured, accurate data, moderate complexity\n\n"
            "📚 <b>3. Academic</b>\n"
            "   Deep analysis, scientific facts, professional language"
        ),
    }
    text = msgs.get(lang, msgs["uz"])
    kb = _level_keyboard(lang)
    if is_callback:
        await source.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await source.answer(text, parse_mode="HTML", reply_markup=kb)


# ──────────────────────────────────────────────────────────────── LEVEL

@router.callback_query(F.data.startswith("prem_ppt_level:"))
async def premium_ppt_got_level(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    level = int(callback.data.split(":")[1])
    await state.update_data(level=level)
    await state.set_state(PremiumPresentationStates.waiting_for_slide_count)

    data = await state.get_data()
    topic = data.get("topic", "")
    level_label = LEVEL_LABELS.get(level, {}).get(lang, "")

    msgs = {
        "uz": f"📋 Mavzu: <b>{topic}</b>\n📐 Daraja: <b>{level_label}</b>\n\n📊 Necha slayd kerak?",
        "ru": f"📋 Тема: <b>{topic}</b>\n📐 Уровень: <b>{level_label}</b>\n\n📊 Сколько слайдов нужно?",
        "en": f"📋 Topic: <b>{topic}</b>\n📐 Level: <b>{level_label}</b>\n\n📊 How many slides do you need?",
    }
    await callback.message.edit_text(msgs.get(lang, msgs["uz"]), parse_mode="HTML",
                                     reply_markup=_slide_count_keyboard(lang))


@router.callback_query(F.data == "prem_ppt_back_to_name")
async def premium_ppt_back_to_name(callback: CallbackQuery, state: FSMContext, db: Database):
    """Daraja sahifasidan ism sahifasiga qaytish"""
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    await state.set_state(PremiumPresentationStates.waiting_for_client_name)
    data = await state.get_data()
    topic = data.get("topic", "")
    msgs = {
        "uz": (
            f"📋 Mavzu: <b>{topic}</b>\n\n"
            "👤 <b>Mijozning ism-familiyasini kiriting</b>\n"
            "<i>(Taqdimotning sarlavha sahifasiga yoziladi)</i>"
        ),
        "ru": (
            f"📋 Тема: <b>{topic}</b>\n\n"
            "👤 <b>Введите имя и фамилию клиента</b>\n"
            "<i>(Будет указано на титульном слайде)</i>"
        ),
        "en": (
            f"📋 Topic: <b>{topic}</b>\n\n"
            "👤 <b>Enter client's full name</b>\n"
            "<i>(Will appear on the title slide)</i>"
        ),
    }
    await callback.message.edit_text(msgs.get(lang, msgs["uz"]), parse_mode="HTML",
                                     reply_markup=_client_name_keyboard(lang))


@router.callback_query(F.data == "prem_ppt_back_to_level")
async def premium_ppt_back_to_level(callback: CallbackQuery, state: FSMContext, db: Database):
    """Slayd soni sahifasidan daraja sahifasiga qaytish"""
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    await _show_level_step(callback, state, lang, is_callback=True)


# ──────────────────────────────────────────────────────────────── SLIDE COUNT

@router.callback_query(F.data.startswith("prem_ppt_count:"), PremiumPresentationStates.waiting_for_slide_count)
async def premium_ppt_got_count(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"

    slide_count = int(callback.data.split(":")[1])
    price = _get_price(slide_count)
    data = await state.get_data()
    topic = data.get("topic", "")
    client_name = data.get("client_name", "")
    preferences = data.get("preferences", "")

    # Kod-only rejimda daraja uchun alohida AI chaqiruvi kerak emas.
    # OpenAI to‘liq source code promptida mavzu va foydalanuvchi istaklarini
    # bevosita hisobga oladi.
    level = 2
    level_label = LEVEL_LABELS.get(level, {}).get(lang, "")

    await state.update_data(slide_count=slide_count, price=price)

    name_line = {
        "uz": f"👤 Mijoz: <b>{client_name or 'ko‘rsatilmagan — o‘tkazib yuborilgan'}</b>\n",
        "ru": f"👤 Клиент: <b>{client_name or 'не указан — пропущено'}</b>\n",
        "en": f"👤 Client: <b>{client_name or 'not provided — skipped'}</b>\n",
    }
    preference_line = {
        "uz": f"🎨 Istaklar: <i>{preferences or 'ko‘rsatilmagan — AI o‘zi tanlaydi'}</i>\n",
        "ru": f"🎨 Пожелания: <i>{preferences or 'не указаны — AI выберет сам'}</i>\n",
        "en": f"🎨 Preferences: <i>{preferences or 'not provided — AI will decide'}</i>\n",
    }
    msgs = {
        "uz": (
            f"⭐ <b>Premium Taqdimot</b>\n\n"
            f"📋 Mavzu: <b>{topic}</b>\n"
            f"{name_line['uz']}"
            f"{preference_line['uz']}"
            f"📐 Daraja: <b>{level_label}</b>\n"
            f"📊 Slaydlar: <b>{slide_count} ta</b>\n"
            f"💰 Narx: <b>{price:,} so'm</b>\n\n"
            f"Hisobingizdan yechiladi. Tasdiqlaysizmi?"
        ),
        "ru": (
            f"⭐ <b>Премиум Презентация</b>\n\n"
            f"📋 Тема: <b>{topic}</b>\n"
            f"{name_line['ru']}"
            f"{preference_line['ru']}"
            f"📐 Уровень: <b>{level_label}</b>\n"
            f"📊 Слайдов: <b>{slide_count}</b>\n"
            f"💰 Цена: <b>{price:,} сум</b>\n\n"
            f"Будет списано с вашего баланса. Подтверждаете?"
        ),
        "en": (
            f"⭐ <b>Premium Presentation</b>\n\n"
            f"📋 Topic: <b>{topic}</b>\n"
            f"{name_line['en']}"
            f"{preference_line['en']}"
            f"📐 Level: <b>{level_label}</b>\n"
            f"📊 Slides: <b>{slide_count}</b>\n"
            f"💰 Price: <b>{price:,} soʻm</b>\n\n"
            f"Will be deducted from your balance. Confirm?"
        ),
    }
    await callback.message.edit_text(
        msgs.get(lang, msgs["uz"]),
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(lang, slide_count, price)
    )


@router.callback_query(F.data == "prem_ppt_recount", PremiumPresentationStates.waiting_for_slide_count)
async def premium_ppt_recount(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    data = await state.get_data()
    topic = data.get("topic", "")
    level = data.get("level", 2)
    level_label = LEVEL_LABELS.get(level, {}).get(lang, "")

    msgs = {
        "uz": f"📋 Mavzu: <b>{topic}</b>\n📐 Daraja: <b>{level_label}</b>\n\n📊 Necha slayd kerak?",
        "ru": f"📋 Тема: <b>{topic}</b>\n📐 Уровень: <b>{level_label}</b>\n\n📊 Сколько слайдов нужно?",
        "en": f"📋 Topic: <b>{topic}</b>\n📐 Level: <b>{level_label}</b>\n\n📊 How many slides do you need?",
    }
    await callback.message.edit_text(msgs.get(lang, msgs["uz"]), parse_mode="HTML",
                                     reply_markup=_slide_count_keyboard(lang))


# ──────────────────────────────────────────────────────────────── CONFIRM & GENERATE

@router.callback_query(
    F.data == "prem_ppt_pay_balance",
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
    F.data == "prem_ppt_pay_stars",
    PremiumPresentationStates.waiting_for_payment,
)
async def premium_ppt_pay_stars(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    data = await state.get_data()
    price = int(data.get("price", 15000))
    slide_count = int(data.get("slide_count", 10))
    stars = som_to_stars(price)
    title = "Premium taqdimot"
    description = f"{slide_count} ta slayd uchun premium taqdimot"

    try:
        await callback.message.answer_invoice(
            title=title,
            description=description,
            payload=f"premium_ppt_{callback.from_user.id}_{price}_{slide_count}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=stars)],
        )
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.exception("Premium presentation Stars invoice error: %s", e)
        await callback.answer("❌ Stars to‘lovini ochib bo‘lmadi", show_alert=True)


@router.message(
    PremiumPresentationStates.waiting_for_payment,
    F.successful_payment,
)
async def premium_ppt_successful_stars(
    message: Message, state: FSMContext, db: Database
):
    payment = message.successful_payment
    if not payment or not payment.invoice_payload.startswith("premium_ppt_"):
        return

    data = await state.get_data()
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
    data = await state.get_data()
    slide_count = int(data.get("slide_count", 10))
    adapter = _MessageCallbackAdapter(
        callback.message,
        data=f"prem_ppt_count:{slide_count}",
    )
    await state.set_state(PremiumPresentationStates.waiting_for_slide_count)
    await premium_ppt_got_count(adapter, state, db)

@router.callback_query(F.data == "prem_ppt_confirm", PremiumPresentationStates.waiting_for_slide_count)
async def premium_ppt_confirm(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    data = await state.get_data()

    # Tasdiqlash va to'lov tanlovi alohida ekranda bo'ladi.
    if not data.get("payment_method"):
        price = data.get("price", 15000)
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
        await callback.message.edit_text(
            payment_texts.get(lang, payment_texts["uz"]),
            parse_mode="HTML",
            reply_markup=_payment_keyboard(lang, price),
        )
        return

    topic = data.get("topic", "")
    preferences = data.get("preferences", "")
    presentation_language = data.get("presentation_language", "uz")
    slide_count = data.get("slide_count", 10)
    price = data.get("price", 15000)
    level = data.get("level", 2)
    client_name = data.get("client_name", "")

    payment_method = data.get("payment_method", "balance")

    # Faqat balans orqali to'lovda balansni tekshiramiz va yechamiz.
    if payment_method == "balance" and user.balance < price:
        shortage = price - user.balance
        msgs = {
            "uz": (
                f"❌ <b>Hisobingizda mablag' yetarli emas</b>\n\n"
                f"💰 Kerakli: {price:,} so'm\n"
                f"💳 Mavjud: {user.balance:,} so'm\n"
                f"📉 Yetishmaydi: {shortage:,} so'm\n\n"
                f"To'lov bo'limiga o'ting va hisobni to'ldiring."
            ),
            "ru": (
                f"❌ <b>Недостаточно средств</b>\n\n"
                f"💰 Нужно: {price:,} сум\n"
                f"💳 Доступно: {user.balance:,} сум\n"
                f"📉 Не хватает: {shortage:,} сум\n\n"
                f"Пополните баланс в разделе оплаты."
            ),
            "en": (
                f"❌ <b>Insufficient balance</b>\n\n"
                f"💰 Required: {price:,} soʻm\n"
                f"💳 Available: {user.balance:,} soʻm\n"
                f"📉 Shortfall: {shortage:,} soʻm\n\n"
                f"Please top up your balance in the payment section."
            ),
        }
        await state.update_data(payment_method=None)
        await state.set_state(PremiumPresentationStates.waiting_for_payment)
        await callback.message.edit_text(
            msgs.get(lang, msgs["uz"]),
            parse_mode="HTML",
            reply_markup=_payment_keyboard(lang, price),
        )
        return

    if payment_method == "balance":
        await db.update_user_balance(callback.from_user.id, -price)
    await state.set_state(PremiumPresentationStates.generating)

    # Create a status message before entering either generation branch.
    # The source-code branch below uses this message immediately; previously
    # `status` was only initialized later in the legacy PPTX branch, which
    # caused a NameError after a successful balance confirmation.
    initial_status_texts = {
        "uz": (
            f"⏳ <b>{topic}</b>\n"
            f"📄 {slide_count} ta slayd uchun tayyorgarlik boshlanmoqda..."
        ),
        "ru": (
            f"⏳ <b>{topic}</b>\n"
            f"📄 Подготовка презентации на {slide_count} слайдов начинается..."
        ),
        "en": (
            f"⏳ <b>{topic}</b>\n"
            f"📄 Preparing the {slide_count}-slide presentation..."
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

    # Yangi rejim: OpenAI faqat Python source code qaytaradi. Bu branch
    # eski PPTX render/QA oqimidan oldin ishlaydi va kodni hech qachon
    # ishga tushirmaydi.
    try:
        from services.premium_presentation.code_generator import (
            generate_presentation_code,
        )

        code = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: generate_presentation_code(
                topic=topic,
                slide_count=slide_count,
                presentation_language=presentation_language,
                client_name=client_name,
                preferences=preferences,
            ),
        )
        filename = f"Premium_{topic[:30].replace(' ', '_')}.txt"
        await status.edit_text(
            {
                "uz": (
                    f"✅ <b>{topic}</b> uchun kod tayyor.\n"
                    f"📄 {slide_count} ta slayd | Faqat .txt source code yuborilmoqda..."
                ),
                "ru": (
                    f"✅ Код для темы «{topic}» готов.\n"
                    f"📄 {slide_count} слайдов | Отправляю только .txt source code..."
                ),
                "en": (
                    f"✅ Code for <b>{topic}</b> is ready.\n"
                    f"📄 {slide_count} slides | Sending .txt source code only..."
                ),
            }.get(lang, "✅ Kod tayyor. Faqat .txt source code yuborilmoqda..."),
            parse_mode="HTML",
        )
        await callback.message.answer_document(
            document=BufferedInputFile(code.encode("utf-8"), filename=filename)
        )
        await state.update_data(last_code=code, error_history=[])
        await state.set_state(PremiumPresentationStates.waiting_for_code_feedback)
        await callback.message.answer(
            {
                "uz": (
                    "Kod ishga tushirilmaydi va PPTX faylga aylantirilmaydi. "
                    "Uni o‘zingiz ishga tushirib ko‘ring.\n\n"
                    "Agar xato chiqsa, xato matnini yuboring — OpenAI aynan shu "
                    "kodni xato konteksti bilan tuzatadi. Muvaffaqiyatli ishlasa, "
                    "tasdiqlang; shunda xato xotirasi o‘chiriladi."
                ),
                "ru": (
                    "Код не запускается и не конвертируется в PPTX. "
                    "Запустите его самостоятельно.\n\n"
                    "Если появится ошибка, отправьте её текст — OpenAI исправит "
                    "этот код с учётом контекста. После успешного запуска подтвердите "
                    "это, и память об ошибке будет удалена."
                ),
                "en": (
                    "The code is not run or converted to PPTX. Run it yourself.\n\n"
                    "If an error appears, send its text and OpenAI will fix this "
                    "code with the remembered context. Confirm after it works "
                    "successfully to delete the error memory."
                ),
            }.get(lang, "Kod ishga tushirilmaydi. Xato bo‘lsa, xato matnini yuboring."),
            parse_mode="HTML",
            reply_markup=_code_feedback_keyboard(lang),
        )
        logger.info(
            "Premium presentation source code sent: topic=%s -> %s",
            topic[:80],
            callback.from_user.id,
        )
        return
    except Exception as e:
        logger.exception("Premium source code generation failed: %s", e)
        await db.update_user_balance(callback.from_user.id, price)
        error_text = {
            "uz": (
                f"❌ Kod yaratishda xato: {str(e)[:300]}\n\n"
                f"💰 {price:,} so‘m hisobingizga qaytarildi."
            ),
            "ru": (
                f"❌ Ошибка создания кода: {str(e)[:300]}\n\n"
                f"💰 {price:,} сум возвращены на баланс."
            ),
            "en": (
                f"❌ Code generation failed: {str(e)[:300]}\n\n"
                f"💰 {price:,} soʻm refunded to your balance."
            ),
        }
        await status.edit_text(error_text.get(lang, error_text["uz"]), parse_mode="HTML")
        await state.clear()
        return

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

    status = await callback.message.edit_text(
        status_msgs.get(lang, status_msgs["uz"]), parse_mode="HTML"
    )

    loop = asyncio.get_event_loop()
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

    try:
        from services.premium_presentation.pipeline import (
            generate_brief_chunked,
            canvas_validation_and_fix,
            run_visual_qa_and_fix,
        )
        from services.premium_presentation.renderer import build_presentation

        # 1 — Brief yaratish (level va client_name uzatiladi)
        brief = await loop.run_in_executor(
            None,
            lambda: generate_brief_chunked(
                topic, slide_count, progress_cb, level=level,
                preferences=preferences,
                language=presentation_language,
            )
        )

        step2 = {
            "uz": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Kontent tayyor: {len(brief.slides)} slayd\n"
                f"⏳ Strukturaviy tekshiruv..."
            ),
            "ru": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Контент готов: {len(brief.slides)} слайдов\n"
                f"⏳ Структурная проверка..."
            ),
            "en": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Content ready: {len(brief.slides)} slides\n"
                f"⏳ Structural check..."
            ),
        }
        await status.edit_text(step2.get(lang, step2["uz"]), parse_mode="HTML")

        # 2 — Kanvas validatsiyasi
        brief = await loop.run_in_executor(
            None, canvas_validation_and_fix, brief, topic, 2, presentation_language
        )

        step3 = {
            "uz": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Kontent: {len(brief.slides)} slayd\n"
                f"✅ Strukturaviy tekshiruv o'tdi\n"
                f"⏳ Slaydlar chizilmoqda..."
            ),
            "ru": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Контент: {len(brief.slides)} слайдов\n"
                f"✅ Структурная проверка пройдена\n"
                f"⏳ Рисуем слайды..."
            ),
            "en": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Content: {len(brief.slides)} slides\n"
                f"✅ Structural check passed\n"
                f"⏳ Drawing slides..."
            ),
        }
        await status.edit_text(step3.get(lang, step3["uz"]), parse_mode="HTML")

        # 3 — Render
        pptx_path = await loop.run_in_executor(None, build_presentation, brief)

        step4 = {
            "uz": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Kontent: {len(brief.slides)} slayd\n"
                f"✅ Strukturaviy tekshiruv o'tdi\n"
                f"✅ Slaydlar chizildi\n"
                f"⏳ Vizual sifat nazorati..."
            ),
            "ru": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Контент: {len(brief.slides)} слайдов\n"
                f"✅ Структурная проверка пройдена\n"
                f"✅ Слайды нарисованы\n"
                f"⏳ Визуальный контроль качества..."
            ),
            "en": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Content: {len(brief.slides)} slides\n"
                f"✅ Structural check passed\n"
                f"✅ Slides drawn\n"
                f"⏳ Visual quality check..."
            ),
        }
        await status.edit_text(step4.get(lang, step4["uz"]), parse_mode="HTML")

        # 4 — Vizual QA
        final_path = await loop.run_in_executor(
            None, run_visual_qa_and_fix, pptx_path, brief, topic, presentation_language
        )

    except Exception as e:
        logger.exception("Premium taqdimot generatsiyasida xato: %s", e)
        if animation_task:
            animation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await animation_task
        # Balansni qaytarish
        await db.update_user_balance(callback.from_user.id, price)
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
    done_msgs = {
        "uz": f"✅ <b>{topic}</b> — tayyor!\n📊 {len(brief.slides)} slayd | Yuborilmoqda...",
        "ru": f"✅ <b>{topic}</b> — готово!\n📊 {len(brief.slides)} слайдов | Отправляю...",
        "en": f"✅ <b>{topic}</b> — done!\n📊 {len(brief.slides)} slides | Sending...",
    }
    try:
        await status.edit_text(done_msgs.get(lang, done_msgs["uz"]), parse_mode="HTML")
    except Exception:
        pass

    filename = f"Premium_{topic[:30].replace(' ', '_')}.pptx"
    try:
        from aiogram.types import FSInputFile
        document = FSInputFile(final_path, filename=filename)
        await callback.message.answer_document(document=document)
        logger.info("Premium taqdimot yuborildi: %s → %s", final_path, callback.from_user.id)
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
        # Temp faylni o'chirish
        try:
            os.remove(final_path)
        except Exception:
            pass

    await state.clear()


# ──────────────────────────────────────────────────────────────── CODE FEEDBACK

@router.callback_query(
    F.data == "prem_ppt_report_error",
    PremiumPresentationStates.waiting_for_code_feedback,
)
async def premium_ppt_report_error(callback: CallbackQuery, state: FSMContext, db: Database):
    """Foydalanuvchidan ishga tushirishda chiqqan xatoni qabul qiladi."""
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    await state.set_state(PremiumPresentationStates.waiting_for_error_text)
    prompts = {
        "uz": "❗ Iltimos, chiqqan xato matnini to‘liq yuboring:",
        "ru": "❗ Отправьте полный текст возникшей ошибки:",
        "en": "❗ Send the complete error message you received:",
    }
    await callback.message.answer(prompts.get(lang, prompts["uz"]))


@router.message(PremiumPresentationStates.waiting_for_error_text)
async def premium_ppt_fix_code(
    message: Message, state: FSMContext, db: Database
):
    """Oldingi kod va xato tarixi bilan OpenAI'dan to‘liq tuzatilgan kod oladi."""
    user = await db.get_user(message.from_user.id)
    lang = user.language if user else "uz"
    error_feedback = (message.text or "").strip()
    data = await state.get_data()
    previous_code = data.get("last_code", "")

    if len(error_feedback) < 3:
        prompts = {
            "uz": "❌ Xato matni juda qisqa. To‘liq xatoni yuboring.",
            "ru": "❌ Текст ошибки слишком короткий. Отправьте ошибку полностью.",
            "en": "❌ The error is too short. Send the complete error message.",
        }
        await message.answer(prompts.get(lang, prompts["uz"]))
        return

    if not previous_code:
        await state.clear()
        await message.answer(
            {
                "uz": "❌ Eski kod topilmadi. Iltimos, yangi premium taqdimot yarating.",
                "ru": "❌ Предыдущий код не найден. Создайте новую презентацию.",
                "en": "❌ The previous code was not found. Please create a new presentation.",
            }.get(lang)
        )
        return

    topic = data.get("topic", "")
    slide_count = int(data.get("slide_count", 10))
    presentation_language = data.get("presentation_language", "uz")
    client_name = data.get("client_name", "")
    preferences = data.get("preferences", "")
    history = list(data.get("error_history", []))
    history.append(error_feedback)

    status_messages = {
        "uz": "🔧 OpenAI xato kontekstini eslab, kodni tuzatmoqda...",
        "ru": "🔧 OpenAI исправляет код с учётом контекста ошибки...",
        "en": "🔧 OpenAI is fixing the code using the remembered error context...",
    }
    status = await message.answer(status_messages.get(lang, status_messages["uz"]))

    try:
        from services.premium_presentation.code_generator import (
            generate_presentation_code,
        )

        fixed_code = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: generate_presentation_code(
                topic=topic,
                slide_count=slide_count,
                presentation_language=presentation_language,
                client_name=client_name,
                preferences=preferences,
                previous_code=previous_code,
                error_feedback=error_feedback,
                error_history=history,
            ),
        )
        filename = f"Premium_{topic[:30].replace(' ', '_')}_fixed.txt"
        await message.answer_document(
            document=BufferedInputFile(fixed_code.encode("utf-8"), filename=filename)
        )
        await state.update_data(
            last_code=fixed_code,
            error_history=history[-5:],
        )
        await state.set_state(PremiumPresentationStates.waiting_for_code_feedback)
        await status.edit_text(
            {
                "uz": (
                    "✅ Kod xato ma’lumotlari asosida qayta tuzatildi.\n\n"
                    "Yana xato bo‘lsa, yana yuboring. Kod muvaffaqiyatli ishlasa, "
                    "pastdagi tasdiqlash tugmasini bosing."
                ),
                "ru": (
                    "✅ Код исправлен с учётом информации об ошибке.\n\n"
                    "Если ошибка повторится, отправьте её снова. После успешного "
                    "запуска нажмите кнопку подтверждения."
                ),
                "en": (
                    "✅ The code was fixed using the error information.\n\n"
                    "If another error appears, send it again. After a successful "
                    "run, press the confirmation button."
                ),
            }.get(lang, "✅ Kod xato ma’lumotlari asosida qayta tuzatildi."),
            reply_markup=_code_feedback_keyboard(lang),
        )
    except Exception as exc:
        logger.exception("Premium code repair failed: %s", exc)
        await state.set_state(PremiumPresentationStates.waiting_for_code_feedback)
        await status.edit_text(
            {
                "uz": f"❌ Tuzatishda xato: {str(exc)[:300]}\nXatoni yana yuborishingiz mumkin.",
                "ru": f"❌ Ошибка исправления: {str(exc)[:300]}\nМожно отправить ошибку ещё раз.",
                "en": f"❌ Repair failed: {str(exc)[:300]}\nYou can send the error again.",
            }.get(lang)
        )


@router.callback_query(
    F.data == "prem_ppt_code_success",
    PremiumPresentationStates.waiting_for_code_feedback,
)
async def premium_ppt_code_success(callback: CallbackQuery, state: FSMContext, db: Database):
    """Muvaffaqiyat tasdiqlanganda xato kontekstini ataylab o‘chiradi."""
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    await state.clear()
    await callback.message.edit_text(
        {
            "uz": "✅ Ajoyib! Taqdimot kodi muvaffaqiyatli ishladi. Xato xotirasi o‘chirildi.",
            "ru": "✅ Отлично! Код презентации работает. Память об ошибках удалена.",
            "en": "✅ Great! The presentation code works. The error memory was deleted.",
        }.get(lang, "✅ Ajoyib! Kod muvaffaqiyatli ishladi. Xato xotirasi o‘chirildi.")
    )


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
