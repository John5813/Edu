"""Sayt orqali balansni to'ldirish: chek yuklash (bot bilan bir xil tekshiruv qoidalari).

To'lov tizimlari (Click, Payme, Uzum) keyinroq ulanadi: shu uchun usullar ro'yxati (`methods`) alohida
turadi va har biri `enabled` bayrog'i bilan keladi. Telegram orqali to'lash shart emas: chek
saytdan yuklanadi, admin kartochkasi esa avvalgidek adminga boradi.
"""
import logging
from datetime import datetime
from types import SimpleNamespace
from typing import Dict, List, Optional

import config
from database.database import Database
from . import flow, rules, texts

log = logging.getLogger(__name__)

MIN_AMOUNT = 1000
MAX_AMOUNT = 5_000_000
MAX_FILE = 12 * 1024 * 1024
PRESETS = (10_000, 15_000, 20_000, 25_000, 30_000, 50_000)


def card_view(number: str) -> str:
    number = "".join(ch for ch in str(number or "") if ch.isdigit())
    return " ".join(number[i:i + 4] for i in range(0, len(number), 4))


def methods() -> List[Dict]:
    """Balansni to'ldirish usullari. `enabled=False` — tez orada (Click, Payme, Uzum)."""
    cards = [card_view(c) for c in (config.PAYMENT_CARD, config.PAYMENT_CARD_2) if c]
    return [
        {"key": "receipt", "label": "Kartaga o'tkazma (chek yuklash)", "enabled": True,
         "cards": cards, "owner": config.PAYMENT_CARD_OWNER,
         "note": "Pulni kartalardan biriga o'tkazing, so'ng to'lov chekini yuklang."},
        {"key": "click", "label": "Click", "enabled": False},
        {"key": "payme", "label": "Payme", "enabled": False},
        {"key": "uzum", "label": "Uzum", "enabled": False},
    ]


class WebMessage:
    """Telegram xabari o'rnini bosuvchi: `flow._process` faqat shu ko'rinishdan foydalanadi."""

    def __init__(self, bot, telegram_id: int, data: bytes, filename: str, mime: str):
        self.bot = bot
        self.chat = SimpleNamespace(id=telegram_id)
        self.message_id = 0
        self.web_data = data
        self.web_name = filename or ""
        self.web_mime = mime or ""
        self.replies: List[str] = []

    async def answer(self, text: str, reply_markup=None, parse_mode=None, **_):
        # Telegram belgilari (Markdown yulduzchalari) saytda ko'rinmasin.
        self.replies.append(str(text).replace("*", "").replace("`", ""))
        return SimpleNamespace(delete=_noop)

    async def send_copy(self, bot, admin_id: int, silent: bool = False) -> Optional[str]:
        """Chek faylini adminga yuboradi va Telegram `file_id` ni qaytaradi."""
        from aiogram.types import BufferedInputFile

        is_image = self.web_mime.startswith("image/") or self.web_name.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        file = BufferedInputFile(self.web_data, filename=self.web_name or ("chek.jpg" if is_image else "chek"))
        if is_image:
            sent = await bot.send_photo(admin_id, file, disable_notification=silent)
            return sent.photo[-1].file_id if sent.photo else None
        sent = await bot.send_document(admin_id, file, disable_notification=silent)
        return sent.document.file_id if sent.document else None


async def _noop(*_, **__):
    return None


def _validate(amount, size: int) -> int:
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise ValueError("Summani raqam bilan kiriting.")
    if amount < MIN_AMOUNT:
        raise ValueError(f"Minimal to'lov miqdori {MIN_AMOUNT:,} so'm.".replace(",", " "))
    if amount > MAX_AMOUNT:
        raise ValueError(f"Bir martalik to'lov {MAX_AMOUNT:,} so'mdan oshmasin.".replace(",", " "))
    if size <= 0:
        raise ValueError("Chek fayli bo'sh.")
    if size > MAX_FILE:
        raise ValueError("Fayl 12 MB dan katta.")
    return amount


async def submit(bot, telegram_id: int, amount, started_iso: str, data: bytes, filename: str, mime: str) -> Dict:
    """Chekni tekshiradi. Qaytadi: {verdict, message, retry, credited}. `ValueError` — noto'g'ri kiritish."""
    amount = _validate(amount, len(data))
    user = await Database.get_user(telegram_id)
    if not user:
        raise ValueError("Avval botda /start bosing.")
    lang = user.language if user.language in ("uz", "ru", "en") else "uz"
    try:
        datetime.fromisoformat(started_iso)
    except (TypeError, ValueError):
        started_iso = rules.now_tashkent().isoformat()

    web = WebMessage(bot, telegram_id, data, filename, mime)
    state = {"payment_amount": amount, "payment_started_at": started_iso}
    outcome = await flow.process_web(web, state, Database, user, lang)
    if outcome is None:
        return await _manual(web, bot, user, amount, lang)

    credited = None
    if outcome.payment_id:
        payment = await Database.get_payment_by_id(outcome.payment_id)
        if payment and str(getattr(payment, "status", "")) == "approved":
            credited = int(payment.amount)
    return {"verdict": outcome.verdict, "message": "\n\n".join(web.replies), "retry": not outcome.clear_state,
            "credited": credited, "pending": outcome.payment_id is not None and credited is None}


async def _manual(web: WebMessage, bot, user, amount: int, lang: str) -> Dict:
    """AI o'chiq yoki ishlamadi: chek odam tekshiruviga yuboriladi (botdagi avvalgi qo'lda yo'l)."""
    from bot.keyboards import get_payment_review_keyboard

    payment_id = await Database.create_payment(user.id, amount, "", "web")
    link = f"@{user.username}" if user.username else f"tg://user?id={user.telegram_id}"
    text = (f"🧾 Yangi to'lov (sayt):\n👤 Foydalanuvchi: {link}\n💵 Summasi: {amount:,} so'm\n"
            f"📅 To'lov ID: {payment_id}\n\n⬆️ Yuqoridagi chekni tekshiring va to'lovni tasdiqlang:")
    sent_any = False
    for admin_id in config.ADMIN_IDS:
        try:
            file_id = await web.send_copy(bot, admin_id)
            if file_id:
                await Database.set_payment_screenshot(payment_id, file_id)
            sent = await bot.send_message(admin_id, text, reply_markup=get_payment_review_keyboard(payment_id))
            await Database.add_payment_admin_message(payment_id, sent.chat.id, sent.message_id, text=text)
            sent_any = True
        except Exception as exc:
            log.error("Admin %s ga sayt cheki yuborilmadi: %s", admin_id, exc)
    message = texts.user_text(lang, "review")
    if not sent_any:
        message = "❌ Chekni adminga yuborib bo'lmadi. Birozdan keyin qayta urinib ko'ring."
    return {"verdict": "review", "message": message.replace("*", ""), "retry": not sent_any,
            "credited": None, "pending": sent_any}
