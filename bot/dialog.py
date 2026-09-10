"""Javob berilgan savol suhbatda osilib qolmasin.

Har qadamning savoli tugmalari bilan chatda qolsa, mijoz oxirida o'nlab
eski savolni ko'radi va allaqachon bosilgan tugmani yana bosishi mumkin.
Shuning uchun savol javob olinishi bilan bir qatorlik tasdiqqa aylanadi:
tugmalari ham, uzun izohi ham ketadi, lekin javob nimaga tegishli ekani
ko'rinib turadi.
"""

import logging
from typing import Optional

from aiogram.types import InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)

_PROMPT_KEY = "_prompt_message_id"


async def ask(
    target: Message,
    state,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = None,
) -> Message:
    """Qadam savolini yuboradi va uni keyin tozalash uchun eslab qoladi."""
    sent = await target.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    await state.update_data(**{_PROMPT_KEY: sent.message_id})
    return sent


def remember(state_data: dict, message: Message) -> dict:
    """Callback bilan o'rniga yozilgan savolni ham eslab qo'yish uchun."""
    return {**state_data, _PROMPT_KEY: message.message_id}


async def resolve(message: Message, state, summary: str) -> None:
    """Oxirgi savolni qisqa tasdiqqa aylantiradi va tugmalarini oladi.

    Savolni butunlay o'chirib yuborish mijozning javobini kontekstsiz
    qoldiradi ("Javlonbek" — nimaga?), shuning uchun matn o'chirilmaydi,
    bir qatorga qisqaradi.
    """
    data = await state.get_data()
    message_id = data.get(_PROMPT_KEY)
    if not message_id:
        return

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message_id,
            text=summary,
            parse_mode="HTML",
        )
    except Exception as e:
        # Xabar o'chirilgan yoki matni aynan shu bo'lsa — muhim emas.
        logger.debug("Savolni tasdiqqa aylantirib bo'lmadi: %s", e)
    finally:
        await state.update_data(**{_PROMPT_KEY: None})


async def drop(message: Message, state) -> None:
    """Savolni butunlay o'chiradi — bekor qilishda ishlatiladi."""
    data = await state.get_data()
    message_id = data.get(_PROMPT_KEY)
    if not message_id:
        return
    try:
        await message.bot.delete_message(chat_id=message.chat.id, message_id=message_id)
    except Exception:
        pass
    await state.update_data(**{_PROMPT_KEY: None})
