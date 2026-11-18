"""«Sayt rejimi» yoqilganda botning kirish nuqtalari (services/site_mode.py).

Faqat `site_mode.ON` bo'lganda ishlaydi — aks holda bu router hech narsani ushlamaydi va bot avvalgidek
o'z oqimlari bilan ishlaydi (buyurtma, to'lov, Stars). Router admin routeridan keyin, qolganlardan oldin
ulanadi: asosiy menyu tugmasi va «Boshqa xizmatlar» bosilganda xizmat saytda ochiladigan tugma beriladi.
"""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LoginUrl, Message

import webapp
from services import site_mode
from translations import get_text, label_variants

router = Router()
log = logging.getLogger(__name__)


def _labels(keys) -> dict:
    found = {}
    for key in keys:
        for text in label_variants(key):
            found[text] = key
    return found


MENU_LABELS = _labels(site_mode.MENU)
ACCOUNT_LABELS = _labels(site_mode.ACCOUNT_KEYS)


def _flat(key: str) -> list:
    """Jadval oxiridagi {"uz","ru","en","kk"} kalitlarining barcha yozuvlari."""
    from translations import TRANSLATIONS
    value = TRANSLATIONS.get(key)
    return list(value.values()) if isinstance(value, dict) else []


ACCOUNT_LABELS.update({text: "cabinet" for text in _flat("site_mode_cabinet_btn")})


def _on(_event=None) -> bool:
    return site_mode.ON


async def site_keyboard(telegram_id: int, to: str, text: str) -> InlineKeyboardMarkup:
    """Saytda kerakli joyni ochadigan tugma: bir martalik kirish havolasi yoki Telegram «Login URL»."""
    if site_mode.login_url_buttons():
        button = InlineKeyboardButton(text=text, login_url=LoginUrl(url=webapp.public_url(f"/go/tg?to={to}")))
    else:
        from database import web_store
        token = await web_store.start_go(telegram_id)
        button = InlineKeyboardButton(text=text, url=webapp.public_url(f"/go?t={token}&to={to}"))
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


async def send_site_link(message: Message, telegram_id: int, user_lang: str, label: str, kind) -> None:
    """Xizmat saytda bo'lsa — ochish tugmasi; hali bo'lmasa — «tez orada saytda»."""
    if kind is None:
        await message.answer(get_text(user_lang, "site_mode_soon", label=label), parse_mode="HTML")
        return
    try:
        keyboard = await site_keyboard(telegram_id, kind, get_text(user_lang, "site_mode_open_btn"))
    except Exception as exc:
        log.warning("Sayt havolasi yaratilmadi (%s): %s", telegram_id, exc)
        await message.answer(get_text(user_lang, "site_mode_link_failed"))
        return
    await message.answer(get_text(user_lang, "site_mode_open", label=label), parse_mode="HTML",
                         reply_markup=keyboard)


@router.message(_on, F.text.in_(set(MENU_LABELS)))
async def menu_service(message: Message, state: FSMContext, user_lang: str):
    await state.clear()
    kind = site_mode.MENU[MENU_LABELS[message.text]]
    await send_site_link(message, message.from_user.id, user_lang, message.text.strip(), kind)


@router.message(_on, F.text.in_(set(ACCOUNT_LABELS)))
async def menu_cabinet(message: Message, state: FSMContext, user_lang: str):
    await state.clear()
    try:
        keyboard = await site_keyboard(message.from_user.id, "profile",
                                       get_text(user_lang, "site_mode_cabinet_btn"))
    except Exception as exc:
        log.warning("Kabinet havolasi yaratilmadi (%s): %s", message.from_user.id, exc)
        await message.answer(get_text(user_lang, "site_mode_link_failed"))
        return
    await message.answer(get_text(user_lang, "site_mode_cabinet"), reply_markup=keyboard)


@router.callback_query(_on, F.data.func(lambda d: (d or "").startswith("os:") and d[3:] in site_mode.OTHER))
async def other_service(callback: CallbackQuery, state: FSMContext, user_lang: str):
    try:
        await callback.answer()
    except Exception:
        pass
    await state.clear()
    key = callback.data[3:]
    label = get_text(user_lang, f"main_menu.{key}")
    await send_site_link(callback.message, callback.from_user.id, user_lang, label, site_mode.OTHER[key])
