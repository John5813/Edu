"""«Sayt rejimi» yoqilganda botning kirish nuqtalari (services/site_mode.py).

Faqat `site_mode.ON` bo'lganda ishlaydi — aks holda bu router hech narsani ushlamaydi va bot avvalgidek
o'z oqimlari bilan ishlaydi (buyurtma, to'lov, Stars). Router admin routeridan keyin, qolganlardan oldin
ulanadi: asosiy menyu tugmasi va «Boshqa xizmatlar» bosilganda xizmat saytda ochiladigan tugma beriladi.
"""
import logging

import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
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


PRICE_LABELS = set(label_variants(site_mode.PRICES_KEY))


@router.message(_on, F.text.in_(PRICE_LABELS))
async def menu_prices(message: Message, state: FSMContext, user_lang: str):
    """Sayt rejimi: botda so'mdagi narxlar ro'yxati ko'rsatilmaydi — xizmatlar saytda (eski menyudan bosilganda)."""
    await state.clear()
    try:
        keyboard = await site_keyboard(message.from_user.id, "home", get_text(user_lang, "site_mode_open_btn"))
    except Exception as exc:
        log.warning("Sayt havolasi yaratilmadi (%s): %s", message.from_user.id, exc)
        await message.answer(get_text(user_lang, "site_mode_link_failed"))
        return
    from bot.keyboards import get_main_keyboard
    await message.answer(get_text(user_lang, "site_mode_prices"), reply_markup=keyboard)
    await message.answer("↩️", reply_markup=get_main_keyboard(user_lang))


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


def _off(_event=None) -> bool:
    return not site_mode.ON


@router.message(_off, F.text.in_(set(_flat("site_mode_cabinet_btn"))))
async def cabinet_after_off(message: Message, state, db, user_lang: str, user):
    """Rejim o'chirilgach, eski menyusida «🌐 Kabinetim» qolgan mijoz: «Mening hisobim» javobi va hozirgi to'liq
    menyu («To'lov qilish» bilan) qayta yuboriladi — bot avvalgi holiga to'liq qaytadi."""
    from bot.handlers.payments import handle_account_info
    await handle_account_info(message, state, db, user_lang, user)


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


@router.callback_query(F.data.startswith("golink:"))
async def fresh_link(callback: CallbackQuery, user_lang: str):
    """Eski xabardagi «Saytda ochish»: har bosishda yangi bir martalik kirish havolasi (rejimdan qat'i nazar)."""
    to = callback.data.split(":", 1)[1]
    if to not in ("docs", "profile", "home"):
        to = "docs"
    try:
        await callback.answer()
    except Exception:
        pass
    try:
        keyboard = await site_keyboard(callback.from_user.id, to, get_text(user_lang, "site_mode_open_btn"))
    except Exception as exc:
        log.warning("Sayt havolasi yaratilmadi (%s): %s", callback.from_user.id, exc)
        await callback.message.answer(get_text(user_lang, "site_mode_link_failed"))
        return
    await callback.message.answer(get_text(user_lang, "site_mode_cabinet"), reply_markup=keyboard)


# ── Sayt rejimi: botda qolgan pullik kirish yo'llari ham saytga ──────────────────────────────────────────────

def _old_payment_button(data: str) -> bool:
    """Rejim yoqilishidan oldingi xabarlardagi to'lov tugmalari (to'ldirish, karta, Stars, balansdan to'lash)."""
    from bot import checkout
    data = data or ""
    if data in ("pay_card_start", "pay_custom", "pay_custom_cancel", "show_referral") or re.fullmatch(r"pay_\d+", data):
        return True
    if data.startswith(("pay_by_card:", "pay_stars_", "rcpt_resend:")):
        return True
    return any(data == f"{s}_{x}" for s in checkout._SERVICE_PREFIXES for x in ("pay", "stars", "recheck", "other", "payback"))


async def _send_home(message: Message, telegram_id: int, user_lang: str, key: str, to: str = "home", **fmt) -> None:
    try:
        keyboard = await site_keyboard(telegram_id, to, get_text(user_lang, "site_mode_open_btn"))
    except Exception as exc:
        log.warning("Sayt havolasi yaratilmadi (%s): %s", telegram_id, exc)
        await message.answer(get_text(user_lang, "site_mode_link_failed"))
        return
    await message.answer(get_text(user_lang, key, **fmt), parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(_on, F.data.func(_old_payment_button))
async def old_payment_button(callback: CallbackQuery, state: FSMContext, user_lang: str):
    try:
        await callback.answer()
    except Exception:
        pass
    await state.clear()
    from bot import checkout
    checkout.forget(callback.from_user.id)
    await _send_home(callback.message, callback.from_user.id, user_lang, "site_mode_stale")


@router.message(_on, StateFilter("PaymentStates:waiting_for_screenshot", "PaymentStates:waiting_for_custom_amount"))
async def old_payment_state(message: Message, state: FSMContext, user_lang: str):
    """Rejim yoqilganda chek yoki summa kutib turgan mijoz: endi bot chek qabul qilmaydi."""
    await state.clear()
    from bot.keyboards import get_main_keyboard
    await _send_home(message, message.from_user.id, user_lang, "site_mode_stale")
    await message.answer("↩️", reply_markup=get_main_keyboard(user_lang))


@router.message(_on, CommandStart(deep_link=True, magic=F.args.startswith("buy_")))
async def store_link(message: Message, command: CommandObject, state: FSMContext, user_lang: str):
    """Saytdagi eski «Botda sotib olish» havolasi: xarid saytning o'zida (balansdan)."""
    from database.database import Database
    await state.clear()
    code = (command.args or "")[4:].strip().upper()
    item = await Database.get_store_item(code) if re.fullmatch(r"[A-Z0-9]{8}", code) else None
    if not item:
        await _send_home(message, message.from_user.id, user_lang, "site_mode_stale")
        return
    import html as _html
    await _send_home(message, message.from_user.id, user_lang, "site_mode_store", to=f"buy_{code}",
                     title=_html.escape(item["title"][:150], quote=False))


_EXTRA_PAID = set(label_variants("main_menu.book_translate") + label_variants("main_menu.pdf_convert")
                  + label_variants("main_menu.media") + label_variants("main_menu.test")
                  + ["📄 PDF → DOCX", "📚 Kitob tarjimasi", "📚 Перевод книги", "📚 Book Translation"])


@router.message(_on, F.text.in_(_EXTRA_PAID))
async def extra_paid_text(message: Message, state: FSMContext, user_lang: str):
    """Eski menyudagi pullik tugmalar (kitob tarjimasi, PDF → DOCX, media, test) — hali saytda yo'q."""
    await state.clear()
    await message.answer(get_text(user_lang, "site_mode_soon", label=message.text.strip()), parse_mode="HTML")


@router.message(_on, Command("book"))
async def book_command(message: Message, state: FSMContext, user_lang: str):
    await state.clear()
    await message.answer(get_text(user_lang, "site_mode_soon", label=get_text(user_lang, "main_menu.book_translate")),
                         parse_mode="HTML")


HELP_LABELS = set(label_variants("main_menu.help")) | {"💬 Yordam", "💬 Помощь", "💬 Help"}


@router.message(_on, F.text.in_(HELP_LABELS))
async def help_site(message: Message, state: FSMContext, user_lang: str):
    """Yordam: to'lov va narx haqidagi qatorlarsiz (xizmatlar saytda)."""
    await state.clear()
    from bot.keyboards import get_help_keyboard
    await message.answer(get_text(user_lang, "site_mode_help"), reply_markup=get_help_keyboard(user_lang),
                         parse_mode="Markdown")


def _referral_labels() -> set:
    from bot.handlers.payments import REFERRAL_TEXTS
    return set(REFERRAL_TEXTS)


@router.message(_on, F.text.func(lambda t: t in _referral_labels()))
async def referral_site(message: Message, state: FSMContext, user_lang: str, user):
    """Do'stlarni taklif qilish: havola qoladi, summa va «pul ishlab topish» so'zlari yo'q."""
    await state.clear()
    if not user or not user.referral_code:
        await message.answer(get_text(user_lang, "site_mode_link_failed"))
        return
    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user.referral_code}"
    await message.answer(get_text(user_lang, "site_mode_referral", referral_link=link), parse_mode="Markdown")
