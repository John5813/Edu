from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from typing import List
from translations import get_text
# No longer importing PAYMENT_AMOUNTS - now using local values

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

def get_slide_count_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Slide count selection keyboard with prices (multilingual)"""
    keyboard = InlineKeyboardBuilder()
    
    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="10 slayd - 5000 so'm", callback_data="slides_10"))
        keyboard.add(InlineKeyboardButton(text="15 slayd - 7000 so'm", callback_data="slides_15")) 
        keyboard.add(InlineKeyboardButton(text="20 slayd - 10000 so'm", callback_data="slides_20"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="10 слайдов - 5000 сум", callback_data="slides_10"))
        keyboard.add(InlineKeyboardButton(text="15 слайдов - 7000 сум", callback_data="slides_15"))
        keyboard.add(InlineKeyboardButton(text="20 слайдов - 10000 сум", callback_data="slides_20"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="10 slides - 5000 som", callback_data="slides_10"))
        keyboard.add(InlineKeyboardButton(text="15 slides - 7000 som", callback_data="slides_15"))
        keyboard.add(InlineKeyboardButton(text="20 slides - 10000 som", callback_data="slides_20"))
    
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_all_templates_keyboard() -> InlineKeyboardMarkup:
    """Create compact keyboard with all 20 template numbers"""
    keyboard = InlineKeyboardBuilder()
    
    # Add all 20 template buttons in compact format
    for i in range(1, 21):
        keyboard.add(InlineKeyboardButton(
            text=str(i),
            callback_data=f"template_template_{i}"
        ))
    
    # Arrange in 5 rows of 4 buttons each to match the image layout
    keyboard.adjust(4)  # 4 buttons per row
    
    return keyboard.as_markup()

def get_template_keyboard(group: int, total_groups: int) -> InlineKeyboardMarkup:
    """Legacy template keyboard - now uses single overview approach"""
    return get_all_templates_keyboard()

def get_page_count_keyboard(document_type: str, language: str = "uz") -> InlineKeyboardMarkup:
    """Page count selection keyboard with prices (multilingual)"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="10-15 varoq - 5000 so'm", callback_data="pages_10_15"))
        keyboard.add(InlineKeyboardButton(text="15-20 varoq - 7000 so'm", callback_data="pages_15_20"))
        keyboard.add(InlineKeyboardButton(text="20-25 varoq - 10000 so'm", callback_data="pages_20_25"))
        keyboard.add(InlineKeyboardButton(text="25-30 varoq - 12000 so'm", callback_data="pages_25_30"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="10-15 страниц - 5000 сум", callback_data="pages_10_15"))
        keyboard.add(InlineKeyboardButton(text="15-20 страниц - 7000 сум", callback_data="pages_15_20"))
        keyboard.add(InlineKeyboardButton(text="20-25 страниц - 10000 сум", callback_data="pages_20_25"))
        keyboard.add(InlineKeyboardButton(text="25-30 страниц - 12000 сум", callback_data="pages_25_30"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="10-15 pages - 5000 som", callback_data="pages_10_15"))
        keyboard.add(InlineKeyboardButton(text="15-20 pages - 7000 som", callback_data="pages_15_20"))
        keyboard.add(InlineKeyboardButton(text="20-25 pages - 10000 som", callback_data="pages_20_25"))
        keyboard.add(InlineKeyboardButton(text="25-30 pages - 12000 som", callback_data="pages_25_30"))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_payment_amount_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Payment amount selection keyboard with explanations (multilingual)"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        payment_options = [
            (15000, "15,000 so'm - 1-2 ta hujjat uchun"),
            (25000, "25,000 so'm - 3-4 ta hujjat uchun"), 
            (50000, "50,000 so'm - 7-10 ta hujjat uchun"),
            (100000, "100,000 so'm - Chegirmali to'plov")
        ]
    elif language == "ru":
        payment_options = [
            (15000, "15,000 сум - для 1-2 документов"),
            (25000, "25,000 сум - для 3-4 документов"), 
            (50000, "50,000 сум - для 7-10 документов"),
            (100000, "100,000 сум - Скидочная оплата")
        ]
    else:  # en
        payment_options = [
            (15000, "15,000 som - for 1-2 documents"),
            (25000, "25,000 som - for 3-4 documents"), 
            (50000, "50,000 som - for 7-10 documents"),
            (100000, "100,000 som - Discount payment")
        ]

    for amount, description in payment_options:
        keyboard.add(InlineKeyboardButton(
            text=description, 
            callback_data=f"pay_{amount}"
        ))

    keyboard.adjust(1)
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
    """Admin panel keyboard - with channel management"""
    keyboard = ReplyKeyboardBuilder()

    # Statistika va reklama
    keyboard.add(KeyboardButton(text="📊 Statistika"))
    keyboard.add(KeyboardButton(text="📤 Reklama yuborish"))

    # Kunlik statistika va to'lovlar
    keyboard.add(KeyboardButton(text="📈 Kunlik statistika"))
    keyboard.add(KeyboardButton(text="💳 To'lovlar"))

    # Kanallar boshqaruvi
    keyboard.add(KeyboardButton(text="📢 Kanallar"))

    # Orqaga qaytish
    keyboard.add(KeyboardButton(text="👤 Foydalanuvchi rejimi"))

    keyboard.adjust(2, 2, 1, 1)
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