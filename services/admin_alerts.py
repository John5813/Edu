"""Adminlarga xizmat muammosi haqida xabar (masalan, Together limiti tugadi).

Bir xil xabar `COOLDOWN` soniya ichida qayta yuborilmaydi — har rasm uchun
adminni xabarga ko'mib tashlamaslik uchun. Xabar yuborilmasa ham asosiy ish to'xtamaydi.
"""
import asyncio
import logging
import time
from typing import Dict

log = logging.getLogger(__name__)

COOLDOWN = 1800.0
_bot = None
_sent: Dict[str, float] = {}
_tasks: set = set()


def set_bot(bot) -> None:
    global _bot
    _bot = bot


async def _send(text: str) -> None:
    from config import ADMIN_IDS

    for admin in ADMIN_IDS:
        try:
            await _bot.send_message(admin, text, parse_mode=None)
        except Exception as exc:
            log.debug("Adminga xabar yuborilmadi (%s): %s", admin, exc)


def alert(key: str, text: str) -> None:
    """Xabarni fonda yuboradi; `key` bo'yicha takrorlanmaydi."""
    if _bot is None:
        return
    now = time.monotonic()
    if now - _sent.get(key, -COOLDOWN) < COOLDOWN:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _sent[key] = now
    task = loop.create_task(_send(text))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
