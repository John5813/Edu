import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.keyboards import get_language_keyboard, get_main_keyboard, get_settings_keyboard
from bot.states import SettingsStates
from database.database import Database
from translations import get_text
from datetime import datetime

router = Router()
logger = logging.getLogger(__name__)

# Settings menu items in different languages
SETTINGS_TEXTS = ["⚙️ Sozlamalar", "⚙️ Настройки", "⚙️ Settings"]

@router.message(F.text.in_(SETTINGS_TEXTS))
async def handle_settings_request(message: Message, user_lang: str):
    """Handle settings request"""
    await message.answer(
        get_text(user_lang, "settings_menu"),
        reply_markup=get_settings_keyboard(user_lang)
    )

# Handle individual settings options
@router.callback_query(F.data == "change_language")
async def handle_change_language_option(callback: CallbackQuery, user_lang: str):
    """Handle change language option"""
    await callback.message.edit_text(
        get_text(user_lang, "choose_language"),
        reply_markup=get_language_keyboard()
    )

@router.callback_query(F.data == "enter_promocode")
async def handle_enter_promocode_option(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Handle enter promocode option"""
    await callback.message.edit_text("🎟 Promokodni kiriting:")
    await state.set_state(SettingsStates.waiting_for_promocode)

@router.callback_query(F.data.startswith("lang_"))
async def handle_language_change(callback: CallbackQuery, db: Database):
    """Handle language change from settings"""
    new_language = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    # Update user language
    await db.update_user_language(user_id, new_language)
    
    await callback.message.edit_text(
        get_text(new_language, "language_changed"),
        reply_markup=None
    )
    
    await callback.message.answer(
        "🎓 Bot ishga tayyor!",
        reply_markup=get_main_keyboard(new_language)
    )

@router.message(SettingsStates.waiting_for_promocode)
async def handle_settings_promocode_input(message: Message, state: FSMContext, db: Database, user_lang: str, user):
    """Handle promocode input from settings"""
    promocode_text = message.text.strip().upper()
    
    # Get promocode from database
    promocode = await db.get_promocode(promocode_text)
    
    if not promocode:
        await message.answer("❌ Noto'g'ri promokod. Qayta kiriting yoki /cancel buyrug'ini yuboring.")
        return
    
    # Check if promocode is expired
    if promocode.expires_at < datetime.now():
        await message.answer("❌ Promokodning amal qilish muddati tugagan. Qayta kiriting yoki /cancel buyrug'ini yuboring.")
        return
    
    # Check if user already used this promocode
    is_used = await db.is_promocode_used(user.id, promocode.id)
    if is_used:
        await message.answer("❌ Siz bu promokodni allaqachon ishlatgansiz. Qayta kiriting yoki /cancel buyrug'ini yuboring.")
        return
    
    # Apply promocode immediately - give one free document
    await db.mark_promocode_used(user.id, promocode.id)
    
    # Reset free service for this user if already used
    await db.reset_free_service(user.telegram_id)
    
    # Give user one free service of choice
    await message.answer(
        "✅ Promokod qabul qilindi! Sizga bepul bitta hujjat yaratish imkoniyati berildi.\n\n"
        "Asosiy menyudan kerakli hujjat turini tanlang.",
        reply_markup=get_main_keyboard(user_lang)
    )
    
    await state.clear()
