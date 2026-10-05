from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.database import Database
from bot.keyboards import get_help_keyboard, get_sample_management_keyboard, get_samples_list_keyboard
from translations import get_text
from config import ADMIN_IDS
import asyncio
import logging
import re
import time

logger = logging.getLogger(__name__)

router = Router()

class SampleStates(StatesGroup):
    waiting_for_file = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

SAMPLES_TEXTS = ["📁 Namunalar", "📁 Образцы", "📁 Samples"]

@router.message(F.text.in_(SAMPLES_TEXTS))
async def handle_samples_from_main_menu(message: Message, db: Database, user_lang: str):
    """Handle samples button click from main menu"""
    from bot.keyboards import get_main_keyboard
    
    samples = await db.get_all_sample_files()
    
    if not samples:
        await message.answer(
            get_text(user_lang, "samples_title") + "\n\n" + get_text(user_lang, "no_samples"),
            reply_markup=get_main_keyboard(user_lang)
        )
        return
    
    # Send title message
    await message.answer(get_text(user_lang, "samples_title"))
    
    # Send each sample file
    for sample in samples:
        caption = f"📁 {sample['title']}"
        if sample.get('description'):
            caption += f"\n\n{sample['description']}"
        
        try:
            if sample['file_type'] == 'document':
                await message.answer_document(document=sample['file_id'], caption=caption)
            elif sample['file_type'] == 'photo':
                await message.answer_photo(photo=sample['file_id'], caption=caption)
            elif sample['file_type'] == 'video':
                await message.answer_video(video=sample['file_id'], caption=caption)
        except Exception as e:
            logger.error(f"Error sending sample file: {e}")

@router.callback_query(F.data == "view_samples")
async def handle_view_samples(callback: CallbackQuery, db: Database):
    """Handle view samples button click from help section"""
    await callback.answer()
    
    user = await db.get_user(callback.from_user.id)
    language = user.language if user else "uz"
    
    samples = await db.get_all_sample_files()
    
    if not samples:
        await callback.message.edit_text(
            get_text(language, "samples_title") + "\n\n" + get_text(language, "no_samples"),
            reply_markup=get_help_keyboard(language)
        )
        return
    
    # Send title message
    await callback.message.answer(
        get_text(language, "samples_title")
    )
    
    # Send each sample file
    for sample in samples:
        caption = f"📁 {sample['title']}"
        if sample.get('description'):
            caption += f"\n\n{sample['description']}"
        
        try:
            if sample['file_type'] == 'document':
                await callback.message.answer_document(
                    document=sample['file_id'],
                    caption=caption
                )
            elif sample['file_type'] == 'photo':
                await callback.message.answer_photo(
                    photo=sample['file_id'],
                    caption=caption
                )
            elif sample['file_type'] == 'video':
                await callback.message.answer_video(
                    video=sample['file_id'],
                    caption=caption
                )
        except Exception as e:
            logger.error(f"Error sending sample file: {e}")
    
    # Answer the callback to remove loading state
    await callback.answer()

@router.message(F.text == "📁 Namunalar boshqaruvi")
async def handle_samples_management(message: Message):
    """Handle samples management button for admin"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "📁 Namunalar boshqaruvi\n\nTanlang:",
        reply_markup=get_sample_management_keyboard()
    )

@router.callback_query(F.data == "add_sample")
async def handle_add_sample(callback: CallbackQuery, state: FSMContext):
    """Namuna qo'shishni boshlaydi: fayllar ketma-ket (albom bilan ham) yuboriladi."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(
        "📎 Namuna fayllarini yuboring — bittadan ham, bir nechtasini birdaniga (albom) ham bo'ladi.\n\n"
        "Nom so'ralmaydi: fayl nomi yoki izohi nom bo'lib yoziladi. "
        "Hammasini yuborib bo'lgach «✅ Tayyor» ni bosing.",
        reply_markup=_done_keyboard(),
    )
    await state.set_state(SampleStates.waiting_for_file)
    _BATCH[callback.from_user.id] = _Batch()


def _done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tayyor", callback_data="sample_batch_done")]])


class _Batch:
    """Admin yuborayotgan namunalar hisobi (bir vaqtda kelgan albom fayllari uchun)."""

    def __init__(self) -> None:
        self.count = 0
        self.failed = 0
        self.lock = asyncio.Lock()
        self.status_mid = None
        self.last_edit = 0.0
        self.refresh_scheduled = False


_BATCH: dict = {}


def sample_title(message: Message) -> str:
    """Namuna nomi: izoh, bo'lmasa fayl nomi (kengaytmasiz), bo'lmasa "Namuna"."""
    caption = (message.caption or "").strip().splitlines()
    if caption and caption[0].strip():
        return caption[0].strip()[:120]
    name = ""
    if message.document and message.document.file_name:
        name = message.document.file_name
    elif message.video and message.video.file_name:
        name = message.video.file_name
    name = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name)
    name = re.sub(r"[_]+", " ", name).strip()
    return name[:120] or "Namuna"


@router.message(SampleStates.waiting_for_file, F.document | F.photo | F.video)
async def handle_sample_file(message: Message, state: FSMContext, db: Database):
    """Yuborilgan fayl darhol saqlanadi; holat keyingi fayl uchun ochiq qoladi."""
    if not is_admin(message.from_user.id):
        return

    if message.document:
        file_id, file_type = message.document.file_id, 'document'
    elif message.photo:
        file_id, file_type = message.photo[-1].file_id, 'photo'
    else:
        file_id, file_type = message.video.file_id, 'video'

    batch = _BATCH.setdefault(message.from_user.id, _Batch())
    async with batch.lock:
        ok = await db.add_sample_file(title=sample_title(message), description="",
                                      file_id=file_id, file_type=file_type)
        if ok:
            batch.count += 1
        else:
            batch.failed += 1
        await _show_progress(message, batch)


async def _show_progress(message: Message, batch: "_Batch") -> None:
    """Bitta holat xabari yangilanadi: albomdagi har fayl uchun alohida xabar chiqmaydi."""
    text = f"✅ Qo'shildi: {batch.count} ta namuna"
    if batch.failed:
        text += f"\n❌ Saqlanmadi: {batch.failed} ta"
    text += "\n\nYana fayl yuboring yoki «✅ Tayyor» ni bosing."
    now = time.monotonic()
    if batch.status_mid and now - batch.last_edit < 1.0:
        # Telegram tez-tez tahrirlashni cheklaydi: oxirgi son keyinroq yangilanadi.
        if not batch.refresh_scheduled:
            batch.refresh_scheduled = True
            asyncio.create_task(_refresh_later(message, batch))
        return
    try:
        if batch.status_mid:
            await message.bot.edit_message_text(text, chat_id=message.chat.id, message_id=batch.status_mid,
                                                reply_markup=_done_keyboard())
        else:
            sent = await message.answer(text, reply_markup=_done_keyboard())
            batch.status_mid = sent.message_id
        batch.last_edit = now
    except Exception as exc:
        logger.debug("Namuna holati yangilanmadi: %s", exc)


async def _refresh_later(message: Message, batch: "_Batch") -> None:
    await asyncio.sleep(1.2)
    batch.refresh_scheduled = False
    async with batch.lock:
        await _show_progress(message, batch)


@router.callback_query(F.data == "sample_batch_done", SampleStates.waiting_for_file)
async def handle_sample_batch_done(callback: CallbackQuery, state: FSMContext):
    """Yuborish tugadi: yakuniy son ko'rsatiladi."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    await callback.answer()
    batch = _BATCH.pop(callback.from_user.id, None)
    await state.clear()
    count = batch.count if batch else 0
    failed = batch.failed if batch else 0
    text = f"✅ Tayyor: {count} ta namuna qo'shildi." if count else "Hech narsa qo'shilmadi."
    if failed:
        text += f"\n❌ Saqlanmadi: {failed} ta."
    try:
        await callback.message.edit_text(text)
    except Exception:
        await callback.message.answer(text)
    await callback.message.answer("📁 Namunalar boshqaruvi\n\nTanlang:",
                                  reply_markup=get_sample_management_keyboard())


@router.callback_query(F.data == "delete_sample")
async def handle_delete_sample(callback: CallbackQuery, db: Database):
    """Show samples list for deletion"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    
    await callback.answer()
    
    samples = await db.get_all_sample_files()
    
    if not samples:
        await callback.message.edit_text(
            "Hozircha namunalar mavjud emas.",
            reply_markup=get_sample_management_keyboard()
        )
        return
    
    await callback.message.edit_text(
        "🗑 O'chirish uchun namunani tanlang:",
        reply_markup=get_samples_list_keyboard(samples)
    )

@router.callback_query(F.data.startswith("delete_sample_"))
async def handle_confirm_delete_sample(callback: CallbackQuery, db: Database):
    """Delete selected sample"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    
    sample_id = int(callback.data.split("_")[2])
    
    success = await db.delete_sample_file(sample_id)
    
    if success:
        await callback.answer("✅ Namuna o'chirildi!", show_alert=True)
        
        samples = await db.get_all_sample_files()
        if samples:
            await callback.message.edit_text(
                "🗑 O'chirish uchun namunani tanlang:",
                reply_markup=get_samples_list_keyboard(samples)
            )
        else:
            await callback.message.edit_text(
                "Barcha namunalar o'chirildi.",
                reply_markup=get_sample_management_keyboard()
            )
    else:
        await callback.answer("❌ Xatolik yuz berdi", show_alert=True)

@router.callback_query(F.data == "list_samples")
async def handle_list_samples(callback: CallbackQuery, db: Database):
    """Show all samples list"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    
    await callback.answer()
    
    samples = await db.get_all_sample_files()
    
    if not samples:
        await callback.message.edit_text(
            "Hozircha namunalar mavjud emas.",
            reply_markup=get_sample_management_keyboard()
        )
        return
    
    samples_text = "📋 Namunalar ro'yxati:\n\n"
    for i, sample in enumerate(samples, 1):
        samples_text += f"{i}. 📁 {sample['title']}"
        if sample.get('description'):
            samples_text += f"\n   {sample['description']}"
        
        created_at = sample.get('created_at', 'Noma\'lum')
        if isinstance(created_at, str):
            date_str = created_at[:10]
        else:
            date_str = created_at.strftime('%Y-%m-%d')
            
        samples_text += f"\n   📅 {date_str}\n\n"
    
    await callback.message.edit_text(
        samples_text,
        reply_markup=get_sample_management_keyboard()
    )

@router.callback_query(F.data == "back_to_sample_menu")
async def handle_back_to_sample_menu(callback: CallbackQuery):
    """Go back to sample management menu"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    
    await callback.answer()
    await callback.message.edit_text(
        "📁 Namunalar boshqaruvi\n\nTanlang:",
        reply_markup=get_sample_management_keyboard()
    )
