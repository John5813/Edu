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
    row = None
    with contextlib.suppress(Exception):
        row = await reengage.clicked(int(parts[1]))
    await callback.answer()
    if target == "gift":
        await start_gift(callback.message, state, db, callback.from_user.id)
        return
    language = await _language(db, callback.from_user.id)
    flow = row[1] if row else ""
    # Bonus faqat shu tugma orqali: bosilganda taklif faollashadi, so'ng to'lov bo'limi ochiladi.
    # (Eski xabarlardagi «💳 Hisobni to'ldirish» ham bonusli guruhda xuddi shunday ishlaydi.)
    if target == "bonus" or (target == "tolov" and flow in ("trial", "weekly")):
        await _arm_bonus(callback, callback.from_user.id, flow, language)
        target = "tolov"
    if target in ad_buttons.TARGETS:
        await ad_buttons.open_section(callback, state, dispatcher, target, "ru" if language == "kk" else language)


async def _arm_bonus(callback: CallbackQuery, telegram_id: int, flow: str, language: str) -> None:
    from services.reengage_texts import BONUS_ARMED

    try:
        armed = await reengage.arm_offer(telegram_id, flow if flow in ("trial", "weekly") else "")
    except Exception as exc:
        logger.warning("Bonus faollashmadi (%s): %s", telegram_id, exc)
        return
    key = armed[0] if armed else "expired"
    text = BONUS_ARMED[key].get(language) or BONUS_ARMED[key]["uz"]
    if armed:
        text = text.replace("{date}", reengage._date(armed[1], language)).replace(
            "{bonus}", str(reengage.BONUS_PERCENT))
    with contextlib.suppress(Exception):
        await callback.message.answer(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("gift:start"))
async def gift_again(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    link = callback.data[len("gift:start:"):] if callback.data.startswith("gift:start:") else ""
    await start_gift(callback.message, state, db, callback.from_user.id, link=link)


@router.callback_query(F.data.startswith("gl:"))
async def gift_link_button(callback: CallbackQuery, state: FSMContext, db: Database):
    """Tekin taqdimot havolasidan kelgan mijoz «Tekin taqdimot olish» tugmasini bosdi."""
    await callback.answer()
    await start_gift(callback.message, state, db, callback.from_user.id, link=callback.data[3:])


async def offer_link_gift(message: Message, db: Database, code: str) -> None:
    """`/start g_<kod>`: havola yoziladi va mijozga tekin taqdimot tugmasi beriladi.

    Mijoz yangi bo'lsa ham, bazada avvaldan bo'lsa ham (bepul sinovni ishlatgan bo'lsa ham) — shu havoladan
    bir marta oladi.
    """
    from database import gift_links

    telegram_id = message.from_user.id
    language = await _language(db, telegram_id)
    with contextlib.suppress(Exception):
        await gift_links.record_click(code, telegram_id)
    if not await gift_links.is_active(code):
        await message.answer(_t("link_off", language), reply_markup=_offer_keyboard(language))
        return
    if not await gift_links.available(code, telegram_id):
        await message.answer(_t("link_used", language), reply_markup=_offer_keyboard(language))
        return
    await message.answer(_t("link_offer", language), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_t("link_button", language), callback_data=f"gl:{code}")]]))


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


async def start_gift(message: Message, state: FSMContext, db: Database, telegram_id: int, link: str = "") -> None:
    """Sovg'a oqimi: imkoniyat bo'lsa mavzu so'raladi, aks holda to'liq taqdimot taklif qilinadi.

    `link` — tekin taqdimot havolasi kodi: imkoniyat bepul sinovdan emas, shu havoladan olinadi.
    """
    from database import free_trial, gift_links

    language = await _language(db, telegram_id)
    if telegram_id in _RUNNING:
        await message.answer(_t("busy", language))
        return
    if link:
        if not await gift_links.available(link, telegram_id):
            key = "link_used" if await gift_links.is_active(link) else "link_off"
            await message.answer(_t(key, language), reply_markup=_offer_keyboard(language))
            return
    elif not await free_trial.available(telegram_id):
        await message.answer(_t("used", language), reply_markup=_offer_keyboard(language))
        return
    if not await _subscribed(message, db, telegram_id, language):
        return
    await state.clear()
    await state.set_state(GiftStates.waiting_for_topic)
    await state.update_data(gift_link=link)
    await message.answer(_t("link_ask" if link else "ask", language), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_t("cancel", language), callback_data="gift:cancel")]]))


@router.message(GiftStates.waiting_for_topic, F.text)
async def gift_topic(message: Message, state: FSMContext, db: Database):
    from database import free_trial, gift_links

    telegram_id = message.from_user.id
    language = await _language(db, telegram_id)
    topic = (message.text or "").strip()[:300]
    if len(topic) < 3:
        await message.answer(_t("short", language))
        return
    if telegram_id in _RUNNING:
        await message.answer(_t("busy", language))
        return
    link = (await state.get_data()).get("gift_link") or ""
    job_id = free_trial.BOT_PENDING + uuid.uuid4().hex
    claimed = (await gift_links.claim(link, telegram_id, job_id) if link
               else await free_trial.claim(telegram_id, job_id))
    if not claimed:
        await state.clear()
        await message.answer(_t("link_used" if link else "used", language), reply_markup=_offer_keyboard(language))
        return
    await state.set_state(GiftStates.generating)
    _RUNNING.add(telegram_id)
    status = await message.answer(_t("link_working" if link else "working", language).replace(
        "{topic}", html.escape(topic)), parse_mode="HTML")
    path = ""
    try:
        path = (await _build(topic, gift_links.SLIDES, gift_links.PHOTOS) if link
                else await _build(topic))
        from aiogram.types import FSInputFile

        stem = "".join(ch if ch.isalnum() else "_" for ch in topic)[:30].strip("_") or "Taqdimot"
        await message.answer_document(FSInputFile(path, filename=f"Taqdimot_{stem}.pptx"))
        if link:
            await gift_links.mark_delivered(link, telegram_id, job_id)
        else:
            await free_trial.mark_delivered(telegram_id, job_id)
        with contextlib.suppress(Exception):
            await status.delete()
        await message.answer(_t("done", language), parse_mode="HTML", reply_markup=_offer_keyboard(language))
        logger.info("Sovg'a taqdimoti yuborildi: %s", telegram_id)
    except Exception as exc:
        logger.exception("Sovg'a taqdimoti tayyorlanmadi (%s): %s", telegram_id, exc)
        if link:
            await gift_links.release(link, telegram_id, job_id)
        else:
            await free_trial.release(telegram_id, job_id)
        retry = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text=_t("retry", language), callback_data=f"gift:start:{link}" if link else "gift:start")]])
        with contextlib.suppress(Exception):
            await status.edit_text(_t("failed", language), reply_markup=retry)
    finally:
        _RUNNING.discard(telegram_id)
        await state.clear()
        if path:
            with contextlib.suppress(OSError):
                os.remove(path)


async def _build(topic: str, slides: int = 0, photos: bool = False) -> str:
    """Bepul taqdimot: arzon model, sukut bo'yicha 5 slayd va rasmsiz (saytdagi bepul sinov bilan bir xil).

    Tekin taqdimot havolasi orqali — 10 slayd, rasmli (`database.gift_links`).
    """
    from bot.handlers.premium_presentation import _detect_language
    from database import free_trial
    from services import heavy_gate, workload
    from services.premium_presentation import llm_client, pipeline

    async with _SLOTS:
        work_id = workload.begin("sovg'a taqdimot")
        try:
            # Bepul sovg'a: server band bo'lsa pullik buyurtmalardan keyin chiziladi (og'ir ishlar navbatida — FON).
            with llm_client.text_model(free_trial.MODEL), heavy_gate.fon():
                path, _slides, _photos = await pipeline.build_deck(
                    topic, slides or free_trial.SLIDES, language=_detect_language(topic), style="toza",
                    volume="kop", photos=photos)
            return path
        finally:
            workload.end(work_id)
