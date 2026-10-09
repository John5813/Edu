"""Qayta jalb xabarlari tugmalari va sovg'a — 5 slaydli bepul taqdimot (botda).

Tugma `nz:<xabar>:<maqsad>`: bosilgani yoziladi (hisobot uchun), so'ng mijoz kerakli joyga tushadi —
"gift" bo'lsa sovg'a oqimi, aks holda botning bo'limi (taqdimot, mustaqil ish, to'lov, pul ishlash ...).

Sovg'a saytdagi bepul sinov bilan bitta: har akkauntga bir marta (`database.free_trial`), arzon model, rasmsiz,
5 slayd. Taqdimot tayyorlanmay qolsa imkoniyat qaytariladi.
"""
import asyncio
import contextlib
import html
import logging
import os
import uuid

from aiogram import Dispatcher, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import ad_buttons
from bot.states import GiftStates
from database.database import Database
from services import reengage
from services.reengage_texts import GIFT

logger = logging.getLogger(__name__)
router = Router()

# Bir vaqtda ko'pi bilan shuncha sovg'a taqdimoti tayyorlanadi (pullik buyurtmalarga joy qolsin).
_SLOTS = asyncio.Semaphore(2)
_RUNNING: set = set()


async def _language(db: Database, telegram_id: int) -> str:
    user = await db.get_user(telegram_id)
    if not user:
        return "uz"
    return "kk" if getattr(user, "kazakh", False) else reengage.language_of(user.language)


def _t(key: str, language: str) -> str:
    return GIFT[key].get(language) or GIFT[key]["uz"]


def _offer_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t("full", language), callback_data="ad:taqdimot")],
        [InlineKeyboardButton(text=_t("topup", language), callback_data="ad:tolov")],
    ])


@router.callback_query(F.data.startswith("nz:"))
async def nudge_button(callback: CallbackQuery, state: FSMContext, db: Database, dispatcher: Dispatcher):
    """Qayta jalb xabaridagi tugma."""
    parts = callback.data.split(":", 2)
    target = parts[2] if len(parts) == 3 else ""
    with contextlib.suppress(Exception):
        await reengage.clicked(int(parts[1]))
    await callback.answer()
    if target == "gift":
        await start_gift(callback.message, state, db, callback.from_user.id)
        return
    language = await _language(db, callback.from_user.id)
    if target in ad_buttons.TARGETS:
        await ad_buttons.open_section(callback, state, dispatcher, target, "ru" if language == "kk" else language)


@router.callback_query(F.data == "gift:start")
async def gift_again(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    await start_gift(callback.message, state, db, callback.from_user.id)


@router.callback_query(F.data == "gift:cancel")
async def gift_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    with contextlib.suppress(Exception):
        await callback.message.delete()


async def _subscribed(message: Message, db: Database, telegram_id: int, language: str) -> bool:
    """Kanalga obuna talabi (zamonaviy taqdimotdagidek)."""
    try:
        channels = await db.get_active_channels()
        if not channels:
            return True
        from bot.keyboards import get_subscription_check_keyboard
        from services.channel_service import ChannelService
        from translations import get_text
        if await ChannelService(message.bot).check_user_subscription(telegram_id, channels):
            return True
        ui = "ru" if language == "kk" else language
        await message.answer(get_text(ui, "subscription_required"),
                             reply_markup=get_subscription_check_keyboard(ui, channels))
        return False
    except Exception as exc:
        logger.warning("Obuna tekshiruvi o'tmadi: %s", exc)
        return True


async def start_gift(message: Message, state: FSMContext, db: Database, telegram_id: int) -> None:
    """Sovg'a oqimi: imkoniyat bo'lsa mavzu so'raladi, aks holda to'liq taqdimot taklif qilinadi."""
    from database import free_trial

    language = await _language(db, telegram_id)
    if telegram_id in _RUNNING:
        await message.answer(_t("busy", language))
        return
    if not await free_trial.available(telegram_id):
        await message.answer(_t("used", language), reply_markup=_offer_keyboard(language))
        return
    if not await _subscribed(message, db, telegram_id, language):
        return
    await state.clear()
    await state.set_state(GiftStates.waiting_for_topic)
    await message.answer(_t("ask", language), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_t("cancel", language), callback_data="gift:cancel")]]))


@router.message(GiftStates.waiting_for_topic, F.text)
async def gift_topic(message: Message, state: FSMContext, db: Database):
    from database import free_trial

    telegram_id = message.from_user.id
    language = await _language(db, telegram_id)
    topic = (message.text or "").strip()[:300]
    if len(topic) < 3:
        await message.answer(_t("short", language))
        return
    if telegram_id in _RUNNING:
        await message.answer(_t("busy", language))
        return
    job_id = "bot-" + uuid.uuid4().hex
    if not await free_trial.claim(telegram_id, job_id):
        await state.clear()
        await message.answer(_t("used", language), reply_markup=_offer_keyboard(language))
        return
    await state.set_state(GiftStates.generating)
    _RUNNING.add(telegram_id)
    status = await message.answer(_t("working", language).replace("{topic}", html.escape(topic)), parse_mode="HTML")
    path = ""
    try:
        path = await _build(topic)
        from aiogram.types import FSInputFile

        stem = "".join(ch if ch.isalnum() else "_" for ch in topic)[:30].strip("_") or "Taqdimot"
        await message.answer_document(FSInputFile(path, filename=f"Taqdimot_{stem}.pptx"))
        with contextlib.suppress(Exception):
            await status.delete()
        await message.answer(_t("done", language), parse_mode="HTML", reply_markup=_offer_keyboard(language))
        logger.info("Sovg'a taqdimoti yuborildi: %s", telegram_id)
    except Exception as exc:
        logger.exception("Sovg'a taqdimoti tayyorlanmadi (%s): %s", telegram_id, exc)
        await free_trial.release(telegram_id, job_id)
        retry = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text=_t("retry", language), callback_data="gift:start")]])
        with contextlib.suppress(Exception):
            await status.edit_text(_t("failed", language), reply_markup=retry)
    finally:
        _RUNNING.discard(telegram_id)
        await state.clear()
        if path:
            with contextlib.suppress(OSError):
                os.remove(path)


async def _build(topic: str) -> str:
    """5 slaydli bepul taqdimot (saytdagi bepul sinov bilan bir xil: arzon model, rasmsiz)."""
    from bot.handlers.premium_presentation import _detect_language
    from database import free_trial
    from services import workload
    from services.premium_presentation import llm_client, pipeline

    async with _SLOTS:
        work_id = workload.begin("sovg'a taqdimot")
        try:
            with llm_client.text_model(free_trial.MODEL):
                path, _slides, _photos = await pipeline.build_deck(
                    topic, free_trial.SLIDES, language=_detect_language(topic), style="toza", volume="kop",
                    photos=False)
            return path
        finally:
            workload.end(work_id)
