"""Mablag' yetmasa buyurtma o'chib ketmasin.

Ilgari balans yetmasa oqim shu yerda tugardi va mijoz hamma narsani —
mavzudan boshlab — qaytadan kiritishga majbur bo'lardi. Endi buyurtma
holatida qoladi: mijoz balansni to'ldiradi yoki Telegram Stars bilan
to'laydi, va to'lov qaysi yo'l bilan bo'lishidan qat'i nazar xizmat
o'sha buyurtma ustida davom etadi.

Buyurtma botda joy egallab turgani uchun bir soatdan keyin eskiradi.
"""

import logging
import time
from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import som_to_stars
from translations import get_text

logger = logging.getLogger(__name__)

ORDER_TTL_SECONDS = 3600

_STARTED_KEY = "_order_started_at"
_PAID_KEY = "_paid_with_stars"

# Kutayotgan buyurtmalar FSM dan tashqarida saqlanadi. Sabab: balansni
# to'ldirish oqimi (`pay_card_start`) FSM ni tozalaydi va o'z holatlarini
# yozadi — buyurtma FSM ichida qolsa, mijoz to'ldirishga o'tishi bilanoq
# yo'qolardi. Bu yerda esa u to'lov tugagunicha kutib turadi.
_PENDING: dict = {}


def remember(user_id: int, service: str, data: dict) -> None:
    """Buyurtmani to'lov tugagunicha saqlab qo'yadi."""
    _PENDING[user_id] = {"service": service, "data": dict(data), "at": time.time()}


def recall(user_id: int, service: str) -> dict:
    """Saqlangan buyurtmani qaytaradi; yo'q yoki eskirgan bo'lsa — bo'sh dict."""
    entry = _PENDING.get(user_id)
    if not entry or entry["service"] != service:
        return {}
    if time.time() - entry["at"] > ORDER_TTL_SECONDS:
        _PENDING.pop(user_id, None)
        return {}
    return entry["data"]


def forget(user_id: int) -> None:
    _PENDING.pop(user_id, None)


def purge_expired() -> int:
    """Eskirgan buyurtmalarni tozalaydi — bot xotirasida joy egallamasin."""
    now = time.time()
    stale = [uid for uid, e in _PENDING.items() if now - e["at"] > ORDER_TTL_SECONDS]
    for uid in stale:
        _PENDING.pop(uid, None)
    return len(stale)


# Xizmat uchun qilingan Stars to'lovi balansga yozilib ketmasligi uchun
# ro'yxatga olinadi: umumiy `successful_payment` handleri shu prefikslarni
# ko'rsa, to'lovni o'ziniki deb hisoblamaydi.
_SERVICE_PREFIXES: set = set()


def is_service_payload(payload: str) -> bool:
    return any((payload or "").startswith(f"{prefix}:") for prefix in _SERVICE_PREFIXES)


@dataclass(frozen=True)
class Checkout:
    """Bitta xizmatning to'lov sozlamalari."""
    service: str          # "pw", "doc", ... — Stars payload prefiksi
    back_callback: str    # "🔙 Orqaga" qaysi callbackka olib boradi

    def __post_init__(self):
        _SERVICE_PREFIXES.add(self.service)

    @property
    def pay_balance(self) -> str:
        return f"{self.service}_pay"

    @property
    def pay_stars(self) -> str:
        return f"{self.service}_stars"

    @property
    def recheck(self) -> str:
        return f"{self.service}_recheck"

    @property
    def pay_other(self) -> str:
        return f"{self.service}_other"

    def payload(self, user_id: int, price: int) -> str:
        return f"{self.service}:{user_id}:{price}"

    def owns_payload(self, payload: str) -> bool:
        return bool(payload) and payload.startswith(f"{self.service}:")


def start(state_data: dict) -> dict:
    """Buyurtma boshlangan vaqtini belgilaydi (eskirishni hisoblash uchun)."""
    return {**state_data, _STARTED_KEY: time.time()}


def is_expired(data: dict) -> bool:
    started = data.get(_STARTED_KEY)
    return bool(started) and (time.time() - started) > ORDER_TTL_SECONDS


def mark_paid_with_stars(data: dict) -> dict:
    return {**data, _PAID_KEY: True}


def paid_with_stars(data: dict) -> bool:
    return bool(data.get(_PAID_KEY))


def payment_keyboard(checkout: Checkout, language: str, price: int) -> InlineKeyboardMarkup:
    """Asosiy to'lov oynasi — balansdan to'lash va boshqa usullar.

    Stars tugmasi birinchi ekranda ko'rsatilmaydi: mijozlarning aksariyati
    balansdan to'laydi va yonma-yon turgan ikkita to'lov tugmasi chalg'itadi.
    Stars «boshqa to'lov usuli» ortida turadi.
    """
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "pay_from_balance", price=price),
        callback_data=checkout.pay_balance,
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "pay_other_method"),
        callback_data=checkout.pay_other,
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "pw_back"), callback_data=checkout.back_callback,
    ))
    keyboard.adjust(1)
    return keyboard.as_markup()


def other_methods_keyboard(checkout: Checkout, language: str, price: int) -> InlineKeyboardMarkup:
    """Boshqa to'lov usullari — Stars va balansni to'ldirish."""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "pay_with_stars", stars=som_to_stars(price)),
        callback_data=checkout.pay_stars,
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "pay_topup"), callback_data="pay_card_start",
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "pay_recheck"), callback_data=checkout.recheck,
    ))
    keyboard.adjust(1)
    return keyboard.as_markup()


def shortfall_keyboard(checkout: Checkout, language: str, price: int) -> InlineKeyboardMarkup:
    """Mablag' yetmaganda — to'ldirish, Stars, yoki qayta tekshirish."""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "pay_topup"), callback_data="pay_card_start",
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "pay_with_stars", stars=som_to_stars(price)),
        callback_data=checkout.pay_stars,
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "pay_recheck"), callback_data=checkout.recheck,
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "pw_back"), callback_data=checkout.back_callback,
    ))
    keyboard.adjust(1)
    return keyboard.as_markup()


async def send_shortfall(
    message: Message, checkout: Checkout, language: str, price: int, balance: int
) -> None:
    """Buyurtmani saqlab qolgan holda to'lov yo'llarini ko'rsatadi."""
    await message.answer(
        get_text(
            language, "pay_shortfall",
            price=price, balance=balance, shortage=max(price - balance, 0),
        ),
        parse_mode="HTML",
        reply_markup=shortfall_keyboard(checkout, language, price),
    )


async def send_invoice(
    message: Message, checkout: Checkout, language: str, price: int, title: str, description: str
) -> bool:
    """Stars hisob-fakturasini yuboradi. Muvaffaqiyatli bo'lsa True."""
    try:
        await message.answer_invoice(
            title=title[:32],
            description=description[:255],
            payload=checkout.payload(message.chat.id, price),
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=title[:32], amount=som_to_stars(price))],
        )
        return True
    except Exception as e:
        logger.exception("Stars hisob-fakturasi yuborilmadi (%s): %s", checkout.service, e)
        await message.answer(get_text(language, "pay_stars_failed"))
        return False
