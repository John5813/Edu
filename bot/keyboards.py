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

def get_settings_keyboard(language: str) -> InlineKeyboardMarkup:
    """Settings menu keyboard"""
    keyboard = InlineKeyboardBuilder()
    
    # Language change
    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="🌍 Tilni o'zgartirish", callback_data="change_language"))
        keyboard.add(InlineKeyboardButton(text="🎟 Promokod kiritish", callback_data="enter_promocode"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="🌍 Изменить язык", callback_data="change_language"))
        keyboard.add(InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="enter_promocode"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="🌍 Change language", callback_data="change_language"))
        keyboard.add(InlineKeyboardButton(text="🎟 Enter promocode", callback_data="enter_promocode"))
    
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
    """Slide count selection keyboard with prices"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="10 slayd - 5000 som", callback_data="slides_10"))
    keyboard.add(InlineKeyboardButton(text="15 slayd - 7000 som", callback_data="slides_15"))
    keyboard.add(InlineKeyboardButton(text="20 slayd - 10000 som", callback_data="slides_20"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_template_keyboard(group: int, total_groups: int) -> InlineKeyboardMarkup:
    """Template selection keyboard with navigation"""
    from services.template_service import TemplateService
    
    template_service = TemplateService()
    groups = template_service.get_template_groups()
    
    if group < 1 or group > len(groups):
        group = 1
    
    current_group = groups[group - 1]
    keyboard = InlineKeyboardBuilder()
    
    # Add template selection buttons (5 per row)
    for template in current_group:
        template_num = int(template['id'].split('_')[1])
        keyboard.add(InlineKeyboardButton(
            text=f"{template_num}. {template['name']}",
            callback_data=f"template_{template['id']}"
        ))
    
    keyboard.adjust(1)  # One template per row for better readability
    
    # Add navigation buttons
    nav_row = []
    if group > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"template_group_{group-1}"))
    
    nav_row.append(InlineKeyboardButton(text=f"{group}/{total_groups}", callback_data="template_info"))
    
    if group < total_groups:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"template_group_{group+1}"))
    
    if nav_row:
        keyboard.row(*nav_row)
    
    return keyboard.as_markup()

def get_page_count_keyboard(document_type: str) -> InlineKeyboardMarkup:
    """Page count selection keyboard with prices"""
    keyboard = InlineKeyboardBuilder()

    # Both independent_work and referat now have same pricing structure
    keyboard.add(InlineKeyboardButton(text="10-15 varoq - 5000 som", callback_data="pages_10_15"))
    keyboard.add(InlineKeyboardButton(text="15-20 varoq - 7000 som", callback_data="pages_15_20"))
    keyboard.add(InlineKeyboardButton(text="20-25 varoq - 10000 som", callback_data="pages_20_25"))
    keyboard.add(InlineKeyboardButton(text="25-30 varoq - 12000 som", callback_data="pages_25_30"))

    keyboard.adjust(1)
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

def get_promocode_option_keyboard(language: str = 'en'):
    """Get promocode option keyboard"""
    keyboard = InlineKeyboardBuilder()

    keyboard.row(
        InlineKeyboardButton(text="✅ Ha, promokod ishlataman", callback_data="use_promocode"),
        InlineKeyboardButton(text="❌ Yo'q, o'tkazib yuboraman", callback_data="skip_promocode")
    )

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

def get_promocode_option_keyboard(language: str) -> InlineKeyboardMarkup:
    """Promocode option keyboard"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="🎟 Ha, promokod kiritaman", callback_data="use_promocode"))
        keyboard.add(InlineKeyboardButton(text="❌ Yo'q, davom etaman", callback_data="skip_promocode"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="🎟 Да, введу промокод", callback_data="use_promocode"))
        keyboard.add(InlineKeyboardButton(text="❌ Нет, продолжить", callback_data="skip_promocode"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="🎟 Yes, enter promocode", callback_data="use_promocode"))
        keyboard.add(InlineKeyboardButton(text="❌ No, continue", callback_data="skip_promocode"))

    keyboard.adjust(1)
    return keyboard.as_markup()