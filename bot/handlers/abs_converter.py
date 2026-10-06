"""Yashirin /abs xizmati: PPTX matnini lotin ↔ kirill (o'zbekcha) o'girib berish.

Menyu, yordam va buyruqlar ro'yxatida ko'rinmaydi — faqat /abs yozilganda ishlaydi.
Faqat matn o'giriladi; rasm, joylashuv va boshqa hamma narsa o'zgarmaydi.
"""
import asyncio
import logging
import os
import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from bot.states import AbsStates
from services import uz_script
from services.pptx_script import AbsError, convert_file

router = Router()
logger = logging.getLogger(__name__)

MAX_SIZE = 20 * 1024 * 1024

_TEXTS = {
    "uz": {
        "ask": "📄 PPTX (yoki PPT) faylni yuboring.\nLotincha bo'lsa — kirillchaga, kirillcha bo'lsa — lotinchaga o'giraman. "
               "Faqat matn o'zgaradi, qolgan hammasi joyida qoladi.",
        "not_pptx": "❌ Iltimos, faqat .pptx yoki .ppt fayl yuboring.",
        "too_big": "❌ Fayl juda katta (20 MB gacha).",
        "work": "⏳ O'girilmoqda...",
        "no_text": "❌ Faylda o'giriladigan matn topilmadi.",
        "russian": "❌ Bu taqdimot rus tilida ko'rinadi — faqat o'zbekcha matn o'giriladi.",
        "bad_file": "❌ Faylni ochib bo'lmadi. Buzilmagan .pptx yuboring.",
        "fail": "❌ O'girishda xatolik. Qayta urinib ko'ring: /abs",
        "to_cyr": "✅ Lotin → Кирилл",
        "to_lat": "✅ Кириллица → Латиница",
        "no_change": "ℹ️ O'zgargan matn yo'q.",
    },
    "ru": {
        "ask": "📄 Отправьте PPTX (или PPT) файл.\nЛатиницу переведу в кириллицу, кириллицу — в латиницу (узбекский). "
               "Меняется только текст, всё остальное остаётся как было.",
        "not_pptx": "❌ Отправьте файл .pptx или .ppt.",
        "too_big": "❌ Файл слишком большой (до 20 МБ).",
        "work": "⏳ Конвертирую...",
        "no_text": "❌ В файле не найден текст для конвертации.",
        "russian": "❌ Похоже, презентация на русском — конвертируется только узбекский текст.",
        "bad_file": "❌ Не удалось открыть файл. Отправьте целый .pptx.",
        "fail": "❌ Ошибка конвертации. Попробуйте снова: /abs",
        "to_cyr": "✅ Латиница → Кириллица",
        "to_lat": "✅ Кириллица → Латиница",
        "no_change": "ℹ️ Нечего менять.",
    },
    "en": {
        "ask": "📄 Send a PPTX (or PPT) file.\nLatin text becomes Cyrillic and Cyrillic becomes Latin (Uzbek). "
               "Only text changes; everything else stays as is.",
        "not_pptx": "❌ Please send a .pptx or .ppt file.",
        "too_big": "❌ File is too large (up to 20 MB).",
        "work": "⏳ Converting...",
        "no_text": "❌ No convertible text found in the file.",
        "russian": "❌ This deck looks Russian — only Uzbek text is converted.",
        "bad_file": "❌ Could not open the file. Send a valid .pptx.",
        "fail": "❌ Conversion failed. Try again: /abs",
        "to_cyr": "✅ Latin → Cyrillic",
        "to_lat": "✅ Cyrillic → Latin",
        "no_change": "ℹ️ Nothing to change.",
    },
}


def _t(lang: str, key: str) -> str:
    return _TEXTS.get(lang, _TEXTS["ru"])[key]


@router.message(Command("abs"))
async def abs_start(message: Message, state: FSMContext, user_lang: str):
    await state.clear()
    await state.set_state(AbsStates.waiting_for_file)
    await message.answer(_t(user_lang, "ask"))


@router.message(AbsStates.waiting_for_file)
async def abs_file(message: Message, state: FSMContext, user_lang: str):
    document = message.document
    if not document or not (document.file_name or "").lower().endswith((".pptx", ".ppt")):
        await message.answer(_t(user_lang, "not_pptx"))
        return
    if (document.file_size or 0) > MAX_SIZE:
        await message.answer(_t(user_lang, "too_big"))
        return

    status = await message.answer(_t(user_lang, "work"))
    os.makedirs("temp", exist_ok=True)
    uid = uuid.uuid4().hex[:8]
    ext = ".ppt" if document.file_name.lower().endswith(".ppt") else ".pptx"
    src, dst = f"temp/abs_{uid}{ext}", f"temp/abs_{uid}_out.pptx"
    try:
        file = await message.bot.get_file(document.file_id)
        await message.bot.download_file(file.file_path, src)
        result = await asyncio.get_running_loop().run_in_executor(None, convert_file, src, dst)

        if not result.runs:
            await message.answer(_t(user_lang, "no_change"))
        else:
            stem = os.path.splitext(document.file_name)[0]
            suffix = "_kirill" if result.script == uz_script.CYRILLIC else "_lotin"
            caption = _t(user_lang, "to_cyr" if result.script == uz_script.CYRILLIC else "to_lat")
            await message.answer_document(FSInputFile(dst, filename=f"{stem}{suffix}.pptx"), caption=caption)
        await state.clear()
    except AbsError as exc:
        await message.answer(_t(user_lang, exc.code))
        await state.clear()
    except Exception:
        logger.exception("/abs conversion failed")
        await message.answer(_t(user_lang, "fail"))
        await state.clear()
    finally:
        for path in (src, dst):
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            await status.delete()
        except Exception:
            pass
