import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from bot.keyboards import get_language_keyboard, get_main_keyboard
from database.database import Database
from translations import get_text

router = Router()
logger = logging.getLogger(__name__)

# Settings menu items in different languages
SETTINGS_TEXTS = ["⚙️ Sozlamalar", "⚙️ Настройки", "⚙️ Settings"]

@router.message(F.text.in_(SETTINGS_TEXTS))
async def handle_settings_request(message: Message, user_lang: str):
    """Handle settings request"""
    await message.answer(
        get_text(user_lang, "settings_menu"),
        reply_markup=get_language_keyboard()
    )

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
