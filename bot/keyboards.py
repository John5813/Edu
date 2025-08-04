from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from typing import List
from translations import get_text
from config import PAYMENT_AMOUNTS

def get_language_keyboard() -> InlineKeyboardMarkup:
    """Language selection keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_uz"))
    keyboard.add(InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"))
    keyboard.add(InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_main_keyboard(language: str) -> ReplyKeyboardMarkup:
    """Main reply keyboard"""
    keyboard = ReplyKeyboardBuilder()
    
    # First row
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.presentation")))
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.independent_work")))
    
    # Second row
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.referat")))
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.my_account")))
    
    # Third row
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.payment")))
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.help")))
    
    # Fourth row
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.settings")))
    
    keyboard.adjust(2, 2, 2, 1)
    return keyboard.as_markup(resize_keyboard=True)

def get_slide_count_keyboard() -> InlineKeyboardMarkup:
    """Slide count selection keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="10 слайдов", callback_data="slides_10"))
    keyboard.add(InlineKeyboardButton(text="15 слайдов", callback_data="slides_15"))
    keyboard.add(InlineKeyboardButton(text="20 слайдов", callback_data="slides_20"))
    keyboard.adjust(3)
    return keyboard.as_markup()

def get_page_count_keyboard(document_type: str) -> InlineKeyboardMarkup:
    """Page count selection keyboard"""
    keyboard = InlineKeyboardBuilder()
    
    if document_type == "independent_work":
        keyboard.add(InlineKeyboardButton(text="10-15 листов", callback_data="pages_10_15"))
        keyboard.add(InlineKeyboardButton(text="15-20 листов", callback_data="pages_15_20"))
        keyboard.add(InlineKeyboardButton(text="20-25 листов", callback_data="pages_20_25"))
        keyboard.add(InlineKeyboardButton(text="25-30 листов", callback_data="pages_25_30"))
    else:  # referat
        keyboard.add(InlineKeyboardButton(text="8-10 листов", callback_data="pages_8_10"))
        keyboard.add(InlineKeyboardButton(text="10-12 листов", callback_data="pages_10_12"))
        keyboard.add(InlineKeyboardButton(text="12-15 листов", callback_data="pages_12_15"))
    
    keyboard.adjust(2)
    return keyboard.as_markup()

def get_payment_amount_keyboard() -> InlineKeyboardMarkup:
    """Payment amount selection keyboard"""
    keyboard = InlineKeyboardBuilder()
    
    for amount in PAYMENT_AMOUNTS:
        keyboard.add(InlineKeyboardButton(
            text=f"{amount:,} сум", 
            callback_data=f"pay_{amount}"
        ))
    
    keyboard.adjust(2)
    return keyboard.as_markup()

def get_subscription_check_keyboard(language: str) -> InlineKeyboardMarkup:
    """Subscription check keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "check_subscription"), 
        callback_data="check_subscription"
    ))
    return keyboard.as_markup()

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Admin panel keyboard"""
    keyboard = ReplyKeyboardBuilder()
    
    # To'lovlar va buyurtmalar
    keyboard.add(KeyboardButton(text="💳 To'lovlar"))
    keyboard.add(KeyboardButton(text="📋 Buyurtmalar"))
    
    # Kanallar va promokodlar  
    keyboard.add(KeyboardButton(text="📢 Kanal sozlamalari"))
    keyboard.add(KeyboardButton(text="🎟 Promokod boshqaruvi"))
    
    # Foydalanuvchilar va statistika
    keyboard.add(KeyboardButton(text="👥 Foydalanuvchilar"))
    keyboard.add(KeyboardButton(text="📊 Statistika"))
    
    # Xabar yuborish va sozlamalar
    keyboard.add(KeyboardButton(text="📤 Xabar yuborish"))
    keyboard.add(KeyboardButton(text="💰 Narxlar sozlamalari"))
    
    # Bot sozlamalari
    keyboard.add(KeyboardButton(text="🔧 Bot sozlamalari"))
    keyboard.add(KeyboardButton(text="🗄 Database boshqaruvi"))
    
    # Orqaga qaytish
    keyboard.add(KeyboardButton(text="👤 Foydalanuvchi rejimi"))
    
    keyboard.adjust(2, 2, 2, 2, 2, 1)
    return keyboard.as_markup(resize_keyboard=True)

def get_payment_review_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    """Payment review keyboard for admin"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text="✅ Tasdiqlash", 
        callback_data=f"approve_payment_{payment_id}"
    ))
    keyboard.add(InlineKeyboardButton(
        text="❌ Rad etish", 
        callback_data=f"reject_payment_{payment_id}"
    ))
    keyboard.adjust(2)
    return keyboard.as_markup()

def get_channel_management_keyboard() -> InlineKeyboardMarkup:
    """Channel management keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel"))
    keyboard.add(InlineKeyboardButton(text="🗑 Kanal o'chirish", callback_data="remove_channel"))
    keyboard.add(InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="list_channels"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_channels_list_keyboard(channels: List) -> InlineKeyboardMarkup:
    """Channels list keyboard for removal"""
    keyboard = InlineKeyboardBuilder()
    
    for channel in channels:
        keyboard.add(InlineKeyboardButton(
            text=f"🗑 {channel.title}",
            callback_data=f"delete_channel_{channel.channel_id}"
        ))
    
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_promocode_keyboard() -> InlineKeyboardMarkup:
    """Promocode management keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="📤 Promokod yaratish", callback_data="create_promocode"))
    return keyboard.as_markup()

def get_broadcast_target_keyboard() -> InlineKeyboardMarkup:
    """Broadcast target selection keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="👥 Hamma", callback_data="broadcast_all"))
    keyboard.add(InlineKeyboardButton(text="🟢 Faqat faollar", callback_data="broadcast_active"))
    keyboard.adjust(2)
    return keyboard.as_markup()
