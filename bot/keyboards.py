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

def get_doc_language_keyboard() -> InlineKeyboardMarkup:
    """Document language selection keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="doc_lang_uz"))
    keyboard.add(InlineKeyboardButton(text="🇷🇺 Русский", callback_data="doc_lang_ru"))
    keyboard.add(InlineKeyboardButton(text="🇬🇧 English", callback_data="doc_lang_en"))
    keyboard.adjust(3)
    return keyboard.as_markup()

def get_plan_slide_keyboard(language: str) -> InlineKeyboardMarkup:
    """Plan slide choice keyboard"""
    keyboard = InlineKeyboardBuilder()
    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="✅ Ha", callback_data="plan_slide_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ Yo'q", callback_data="plan_slide_no"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="✅ Да", callback_data="plan_slide_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ Нет", callback_data="plan_slide_no"))
    else:
        keyboard.add(InlineKeyboardButton(text="✅ Yes", callback_data="plan_slide_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ No", callback_data="plan_slide_no"))
    keyboard.adjust(2)
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

def get_main_keyboard(language: str, presentation_enabled: bool = True, independent_work_enabled: bool = True, referat_enabled: bool = True, course_work_enabled: bool = True) -> ReplyKeyboardMarkup:
    """Main reply keyboard with feature toggles"""
    keyboard = ReplyKeyboardBuilder()

    buttons = []

    # First row - document types
    if presentation_enabled:
        buttons.append(KeyboardButton(text=get_text(language, "main_menu.presentation")))
    if independent_work_enabled:
        buttons.append(KeyboardButton(text=get_text(language, "main_menu.independent_work")))
    if referat_enabled:
        buttons.append(KeyboardButton(text=get_text(language, "main_menu.referat")))
    if course_work_enabled:
        buttons.append(KeyboardButton(text=get_text(language, "main_menu.course_work")))

    # Add document type buttons
    for btn in buttons:
        keyboard.add(btn)

    # Second row - always visible
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.my_account")))
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.payment")))
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.samples")))

    # Third row - always visible
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.help")))
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.settings")))

    # Adjust layout - all layouts use 2 columns
    keyboard.adjust(2)

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
    """Create compact keyboard with all 20 template numbers (4 columns, 5 rows)"""
    keyboard = InlineKeyboardBuilder()

    # Sequential order 1-20
    for i in range(1, 21):
        keyboard.add(InlineKeyboardButton(
            text=str(i),
            callback_data=f"template_{i}"
        ))

    # 4 buttons per row = 5 rows
    keyboard.adjust(4)

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

def get_course_work_page_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Course work page count selection keyboard with chapters (multilingual)"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="15-20 varoq (2 bo'lim) - 15000 so'm", callback_data="cw_pages_15_20_2"))
        keyboard.add(InlineKeyboardButton(text="20-25 varoq (2 bo'lim) - 20000 so'm", callback_data="cw_pages_20_25_2"))
        keyboard.add(InlineKeyboardButton(text="25-30 varoq (3 bo'lim) - 25000 so'm", callback_data="cw_pages_25_30_3"))
        keyboard.add(InlineKeyboardButton(text="30-35 varoq (3 bo'lim) - 30000 so'm", callback_data="cw_pages_30_35_3"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="15-20 стр (2 главы) - 15000 сум", callback_data="cw_pages_15_20_2"))
        keyboard.add(InlineKeyboardButton(text="20-25 стр (2 главы) - 20000 сум", callback_data="cw_pages_20_25_2"))
        keyboard.add(InlineKeyboardButton(text="25-30 стр (3 главы) - 25000 сум", callback_data="cw_pages_25_30_3"))
        keyboard.add(InlineKeyboardButton(text="30-35 стр (3 главы) - 30000 сум", callback_data="cw_pages_30_35_3"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="15-20 pages (2 chapters) - 15000 som", callback_data="cw_pages_15_20_2"))
        keyboard.add(InlineKeyboardButton(text="20-25 pages (2 chapters) - 20000 som", callback_data="cw_pages_20_25_2"))
        keyboard.add(InlineKeyboardButton(text="25-30 pages (3 chapters) - 25000 som", callback_data="cw_pages_25_30_3"))
        keyboard.add(InlineKeyboardButton(text="30-35 pages (3 chapters) - 30000 som", callback_data="cw_pages_30_35_3"))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_payment_amount_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Payment amount selection keyboard with explanations (multilingual)"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        payment_options = [
            (10000, "10,000 so'm"),
            (15000, "15,000 so'm"),
            (20000, "20,000 so'm"),
            (25000, "25,000 so'm")
        ]
    elif language == "ru":
        payment_options = [
            (10000, "10,000 сум"),
            (15000, "15,000 сум"),
            (20000, "20,000 сум"),
            (25000, "25,000 сум")
        ]
    else:  # en
        payment_options = [
            (10000, "10,000 som"),
            (15000, "15,000 som"),
            (20000, "20,000 som"),
            (25000, "25,000 som")
        ]

    for amount, description in payment_options:
        keyboard.add(InlineKeyboardButton(
            text=description, 
            callback_data=f"pay_{amount}"
        ))

    # Add referral button
    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="💰 Pul ishlab topish", callback_data="show_referral"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="👥 Реферальная программа", callback_data="show_referral"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="👥 Referral Program", callback_data="show_referral"))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_subscription_check_keyboard(language: str, channels=None) -> InlineKeyboardMarkup:
    """Subscription check keyboard with channel links"""
    keyboard = InlineKeyboardBuilder()

    # Add buttons for each channel
    if channels:
        for channel in channels:
            # Create channel button text
            if language == "uz":
                button_text = f"📢 {channel.title}"
            elif language == "ru":
                button_text = f"📢 {channel.title}"
            else:  # en
                button_text = f"📢 {channel.title}"

            # Create channel link
            if channel.channel_username:
                channel_url = f"https://t.me/{channel.channel_username}"
            else:
                # If no username, try to create a link from channel_id (won't work for private channels)
                channel_url = f"https://t.me/c/{str(channel.channel_id)[4:]}"

            keyboard.add(InlineKeyboardButton(
                text=button_text,
                url=channel_url
            ))

    # Add check subscription button
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "check_subscription"), 
        callback_data="check_subscription"
    ))

    keyboard.adjust(1)  # One button per row
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

    # Kanallar va promokod boshqaruvi
    keyboard.add(KeyboardButton(text="📢 Kanallar"))
    keyboard.add(KeyboardButton(text="🎟 Promokod boshqaruvi"))

    # Feature management and sample management
    keyboard.add(KeyboardButton(text="🎛 Funksiyalar boshqaruvi"))
    keyboard.add(KeyboardButton(text="📁 Namunalar boshqaruvi"))

    # Block user management
    keyboard.add(KeyboardButton(text="🚫 Foydalanuvchilarni bloklash"))
    
    # AI model selection
    keyboard.add(KeyboardButton(text="🤖 AI modelni almashtirish"))

    # Orqaga qaytish
    keyboard.add(KeyboardButton(text="👤 Foydalanuvchi rejimi"))

    keyboard.adjust(2)
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
    keyboard.add(InlineKeyboardButton(
        text="💰 Summani o'zgartirish",
        callback_data=f"adjust_amount_{payment_id}"
    ))
    keyboard.adjust(2, 1)
    return keyboard.as_markup()

def get_amount_adjustment_keyboard(payment_id: int, current_amount: int) -> InlineKeyboardMarkup:
    """Amount adjustment keyboard for admin"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text="➖ -1000", 
        callback_data=f"decrease_amount_{payment_id}"
    ))
    keyboard.add(InlineKeyboardButton(
        text=f"💵 {current_amount:,} so'm", 
        callback_data=f"amount_display_{payment_id}"
    ))
    keyboard.add(InlineKeyboardButton(
        text="➕ +1000", 
        callback_data=f"increase_amount_{payment_id}"
    ))
    keyboard.add(InlineKeyboardButton(
        text="✅ Tasdiqlash (yangi summa bilan)", 
        callback_data=f"confirm_adjusted_{payment_id}"
    ))
    keyboard.add(InlineKeyboardButton(
        text="🔙 Bekor qilish", 
        callback_data=f"cancel_adjustment_{payment_id}"
    ))
    keyboard.adjust(3, 1, 1)
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
    keyboard.add(InlineKeyboardButton(text="📋 Barcha promokodlar", callback_data="list_promocodes"))
    keyboard.add(InlineKeyboardButton(text="📊 Statistika", callback_data="promocode_stats"))
    keyboard.adjust(1)
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

def get_promocode_error_keyboard(language: str) -> InlineKeyboardMarkup:
    """Promocode error keyboard with retry and back options"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="🔄 Qayta kiritish", callback_data="retry_promocode"))
        keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_main"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="🔄 Повторить", callback_data="retry_promocode"))
        keyboard.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="🔄 Try again", callback_data="retry_promocode"))
        keyboard.add(InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main"))

    keyboard.adjust(2)
    return keyboard.as_markup()

def get_back_to_channels_keyboard() -> InlineKeyboardMarkup:
    """Back to channels keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_channels"))
    return keyboard.as_markup()

def get_outline_choice_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Outline choice keyboard - manual or automatic"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="✍️ Rejani qo'lda kiritish", callback_data="outline_manual"))
        keyboard.add(InlineKeyboardButton(text="🤖 Reja avtomatik yaratilsin", callback_data="outline_auto"))
        keyboard.add(InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_document"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="✍️ Ввести план вручную", callback_data="outline_manual"))
        keyboard.add(InlineKeyboardButton(text="🤖 Создать план автоматически", callback_data="outline_auto"))
        keyboard.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_document"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="✍️ Enter outline manually", callback_data="outline_manual"))
        keyboard.add(InlineKeyboardButton(text="🤖 Create outline automatically", callback_data="outline_auto"))
        keyboard.add(InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_document"))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_manual_input_keyboard(language: str = "uz") -> ReplyKeyboardMarkup:
    """Keyboard with back button for manual outline input"""
    keyboard = ReplyKeyboardBuilder()

    if language == "uz":
        keyboard.add(KeyboardButton(text="🔙 Ortga qaytish"))
    elif language == "ru":
        keyboard.add(KeyboardButton(text="🔙 Назад"))
    else:  # en
        keyboard.add(KeyboardButton(text="🔙 Back"))

    keyboard.adjust(1)
    return keyboard.as_markup(resize_keyboard=True)

def get_outline_review_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Keyboard for outline review - confirm or edit"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_outline"))
        keyboard.add(InlineKeyboardButton(text="✏️ Tahrirlash", callback_data="edit_outline"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_outline"))
        keyboard.add(InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_outline"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="✅ Confirm", callback_data="confirm_outline"))
        keyboard.add(InlineKeyboardButton(text="✏️ Edit", callback_data="edit_outline"))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_references_choice_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Keyboard for choosing whether to add references to presentation"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="✅ Ha", callback_data="add_references_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ Yo'q", callback_data="add_references_no"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="✅ Да", callback_data="add_references_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ Нет", callback_data="add_references_no"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="✅ Yes", callback_data="add_references_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ No", callback_data="add_references_no"))

    keyboard.adjust(2)
    return keyboard.as_markup()

def get_channel_error_keyboard() -> InlineKeyboardMarkup:
    """Channel error keyboard with retry and back options"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔄 Qayta kiritish", callback_data="retry_channel_id"))
    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_channels"))
    keyboard.adjust(2)
    return keyboard.as_markup()

def get_back_to_features_keyboard() -> InlineKeyboardMarkup:
    """Back to feature management keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_features"))
    return keyboard.as_markup()

def get_feature_management_keyboard(startup_bonus_enabled: bool) -> InlineKeyboardMarkup:
    """Feature management keyboard for admin - startup bonus toggle and mass gift"""
    keyboard = InlineKeyboardBuilder()

    # Startup bonus toggle (5000 for new users)
    bonus_status = "🟢 Yoqilgan" if startup_bonus_enabled else "🔴 O'chirilgan"
    bonus_action = "off" if startup_bonus_enabled else "on"
    keyboard.add(InlineKeyboardButton(
        text=f"🎁 Start bonus (5000): {bonus_status}",
        callback_data=f"toggle_startup_bonus_{bonus_action}"
    ))

    # Mass gift button
    keyboard.add(InlineKeyboardButton(
        text="💰 Barchaga sovg'a yuborish",
        callback_data="mass_gift_start"
    ))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_help_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Help section keyboard with view samples button"""
    keyboard = InlineKeyboardBuilder()
    
    # View samples button with proper translation
    samples_text = get_text(language, "view_samples")
    keyboard.add(InlineKeyboardButton(
        text=samples_text,
        callback_data="view_samples"
    ))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_sample_management_keyboard() -> InlineKeyboardMarkup:
    """Sample files management keyboard for admin"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="➕ Namuna qo'shish", callback_data="add_sample"))
    keyboard.add(InlineKeyboardButton(text="🗑 Namuna o'chirish", callback_data="delete_sample"))
    keyboard.add(InlineKeyboardButton(text="📋 Barcha namunalar", callback_data="list_samples"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_samples_list_keyboard(samples: list) -> InlineKeyboardMarkup:
    """Samples list keyboard for deletion"""
    keyboard = InlineKeyboardBuilder()

    for sample in samples:
        keyboard.add(InlineKeyboardButton(
            text=f"🗑 {sample['title']}",
            callback_data=f"delete_sample_{sample['id']}"
        ))

    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_sample_menu"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_block_user_keyboard() -> InlineKeyboardMarkup:
    """Block user management keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🚫 Foydalanuvchini bloklash", callback_data="block_user"))
    keyboard.add(InlineKeyboardButton(text="✅ Blokdan chiqarish", callback_data="unblock_user"))
    keyboard.add(InlineKeyboardButton(text="📋 Bloklangan foydalanuvchilar", callback_data="list_blocked"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_blocked_users_keyboard(blocked_users: list) -> InlineKeyboardMarkup:
    """Keyboard showing blocked users for unblocking"""
    keyboard = InlineKeyboardBuilder()
    
    for user in blocked_users:
        username_display = f"@{user['username']}" if user['username'] else f"ID: {user['telegram_id']}"
        keyboard.add(InlineKeyboardButton(
            text=f"✅ {username_display}",
            callback_data=f"unblock_{user['telegram_id']}"
        ))
    
    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_block_menu"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_ai_model_selection_keyboard(current_model: str) -> InlineKeyboardMarkup:
    """AI model selection keyboard for admin"""
    from config import AI_MODELS
    
    keyboard = InlineKeyboardBuilder()
    
    for model_key, model_info in AI_MODELS.items():
        is_current = "✅ " if model_key == current_model else ""
        button_text = f"{is_current}{model_info['name']} - {model_info['price']}"
        keyboard.add(InlineKeyboardButton(
            text=button_text,
            callback_data=f"select_ai_model_{model_key}"
        ))
    
    keyboard.adjust(1)
    return keyboard.as_markup()