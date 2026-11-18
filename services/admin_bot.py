"""Alohida admin-bot: sayt rejimida to'lov va chek xabarlari adminlarga shu bot orqali boradi.

Maqsad — asosiy (mijozlar) bot pul ishlariga umuman aralashmasin. Ixtiyoriy: serverda `ADMIN_BOT_TOKEN`
(BotFather'da ochilgan alohida bot) bo'lsa va «🌐 Sayt rejimi» yoqilgan bo'lsa ishlaydi; aks holda hammasi
avvalgidek asosiy bot orqali. Har bir admin admin-botda bir marta /start bosishi kerak (bot birinchi bo'lib
yozolmaydi).

Admin-bot ham asosiy bot bilan bitta dispatcher'da ishlaydi (tasdiqlash/rad etish tugmalari o'sha
handler'larga keladi). Mijozga yoziladigan xabarlar esa doim asosiy bot orqali (`user_bot`): mijoz
admin-botni ochmagan.
"""
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

TOKEN = os.getenv("ADMIN_BOT_TOKEN", "").strip()
BOT = None                     # aiogram Bot (main.py ishga tushishda yaratadi)


def make(**session_kwargs):
    """Admin-bot obyekti (token bo'lmasa — None)."""
    global BOT
    if not TOKEN:
        return None
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    BOT = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML), **session_kwargs)
    return BOT


def active() -> bool:
    from services import site_mode
    return BOT is not None and site_mode.ON


def for_admins(bot):
    """Adminlarga to'lov/chek xabarini yuboradigan bot: sayt rejimida — admin-bot, aks holda — o'sha bot."""
    return BOT if active() else bot


def is_admin_bot(bot) -> bool:
    return BOT is not None and bot is not None and getattr(bot, "id", None) == BOT.id


def user_bot(bot):
    """Mijozga yoziladigan bot: admin-bot tugmasidan kelgan bo'lsa ham — asosiy bot."""
    if is_admin_bot(bot):
        import webapp
        return webapp.BOT or bot
    return bot


async def gate(handler, event, data):
    """Dispatcher middleware: admin-botga faqat adminlar yoza oladi; /start — qisqa izoh."""
    bot = data.get("bot")
    if not is_admin_bot(bot):
        return await handler(event, data)
    from config import ADMIN_IDS
    user = data.get("event_from_user")
    if not user or user.id not in ADMIN_IDS:
        return None
    message = getattr(event, "message", None)
    if message is not None and (message.text or "").startswith("/start"):
        await message.answer("🛡 Admin-bot: sayt rejimida to'lov va chek xabarlari shu yerga keladi. "
                             "Tasdiqlash tugmalari avvalgidek ishlaydi.")
        return None
    return await handler(event, data)
