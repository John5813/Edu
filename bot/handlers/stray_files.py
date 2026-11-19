"""Jarayondan tashqari botga tashlangan rasm, fayl yoki video.

Mijozlar ko'pincha to'lov chekini (skrinshot yoki PDF) adashib botga tashlab qo'yadi. Ilgari bunday rasm
stikerga aylantirilardi (eski «rasm → stiker» xizmati olib tashlandi). Endi mijozning tilida tushuntiriladi:
to'lov cheki bo'lsa — sayt rejimida saytdagi «To'lov» sahifasi orqali (bir bosishda kirish tugmasi bilan),
aks holda botdagi «To'lov qilish» tugmasi orqali yuborilsin.

Faqat hech qanday jarayon (holat) bo'lmaganda ishlaydi: chek kutilayotgan, manba fayl so'ralgan va boshqa
holatlardagi fayllarni o'z handlerlari qabul qiladi.
"""
import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message

from translations import get_text

router = Router()
log = logging.getLogger(__name__)

FILES = F.photo | F.document | F.video | F.animation


@router.message(StateFilter(None), FILES)
async def stray_file(message: Message, user_lang: str = "uz"):
    from services import site_mode

    if not site_mode.ON:
        await message.answer(get_text(user_lang, "stray_file_bot", button=get_text(user_lang, "main_menu.payment")),
                             parse_mode="HTML")
        return
    keyboard = None
    try:
        from bot.handlers.site_mode import site_keyboard
        keyboard = await site_keyboard(message.from_user.id, "wallet", get_text(user_lang, "stray_file_btn"))
    except Exception as exc:                  # havola chiqmasa ham tushuntirish yuboriladi
        log.warning("To'lov sahifasi havolasi yaratilmadi (%s): %s", message.from_user.id, exc)
    await message.answer(get_text(user_lang, "stray_file_site"), parse_mode="HTML", reply_markup=keyboard)
