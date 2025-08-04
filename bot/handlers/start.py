import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.keyboards import get_language_keyboard, get_main_keyboard, get_subscription_check_keyboard
from database.database import Database
from services.channel_service import ChannelService
from translations import get_text
from config import ADMIN_IDS

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def start_command(message: Message, state: FSMContext, db: Database):
    """Handle /start command"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        # New user - show language selection
        await message.answer(
            "🎓 EduBot.ai — Telegramda Akademik Hujjatlar Yaratish Bot\n\n"
            "🎓 EduBot.ai — Создание академических документов в Telegram\n\n"
            "🎓 EduBot.ai — Academic Document Creation in Telegram\n\n"
            "Tilni tanlang / Выберите язык / Choose language:",
            reply_markup=get_language_keyboard()
        )
    else:
        # Existing user - check channel subscription
        await check_subscription_and_show_menu(message, user, db)

@router.callback_query(F.data.startswith("lang_"))
async def language_selected(callback: CallbackQuery, state: FSMContext, db: Database):
    """Handle language selection"""
    language = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    # Create or update user
    user = await db.get_user(user_id)
    if not user:
        user = await db.create_user(
            telegram_id=user_id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            language=language
        )
    else:
        await db.update_user_language(user_id, language)
        user.language = language
    
    await callback.message.edit_text(
        get_text(language, "language_selected"),
        reply_markup=None
    )
    
    # Check channel subscription
    await check_subscription_and_show_menu(callback.message, user, db)

async def check_subscription_and_show_menu(message: Message, user, db: Database):
    """Check channel subscription and show main menu"""
    channels = await db.get_active_channels()
    
    if channels:
        # Check subscription to all required channels
        channel_service = ChannelService(message.bot)
        is_subscribed = await channel_service.check_user_subscription(user.telegram_id, channels)
        
        if not is_subscribed:
            # Show subscription requirement
            channel_links = []
            for channel in channels:
                if channel.channel_username:
                    channel_links.append(f"• @{channel.channel_username}")
                else:
                    channel_links.append(f"• {channel.title}")
            
            text = get_text(user.language, "channel_subscription_required") + "\n\n" + "\n".join(channel_links)
            await message.answer(
                text,
                reply_markup=get_subscription_check_keyboard(user.language)
            )
            return
    
    # Show main menu
    await message.answer(
        get_text(user.language, "language_selected") if hasattr(message, 'edit_text') else 
        "✅ " + get_text(user.language, "subscription_verified"),
        reply_markup=get_main_keyboard(user.language)
    )

@router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: CallbackQuery, db: Database, user_lang: str):
    """Handle subscription check"""
    user_id = callback.from_user.id
    channels = await db.get_active_channels()
    
    if channels:
        channel_service = ChannelService(callback.message.bot)
        is_subscribed = await channel_service.check_user_subscription(user_id, channels)
        
        if is_subscribed:
            await callback.message.edit_text(
                get_text(user_lang, "subscription_verified"),
                reply_markup=None
            )
            await callback.message.answer(
                "🎓 Bot ishga tayyor!",
                reply_markup=get_main_keyboard(user_lang)
            )
        else:
            await callback.answer(
                get_text(user_lang, "subscription_not_verified"),
                show_alert=True
            )
    else:
        # No channels required
        await callback.message.edit_text(
            get_text(user_lang, "subscription_verified"),
            reply_markup=None
        )
        await callback.message.answer(
            "🎓 Bot ishga tayyor!",
            reply_markup=get_main_keyboard(user_lang)
        )

@router.message(Command("admin"))
async def admin_command(message: Message):
    """Handle /admin command"""
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        from bot.keyboards import get_admin_keyboard
        await message.answer(
            "👨‍💼 Admin panel",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer("❌ Sizda admin huquqi yo'q.")
