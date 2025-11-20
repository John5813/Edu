import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.fsm.context import FSMContext

from bot.states import PaymentStates
from bot.keyboards import get_payment_amount_keyboard, get_main_keyboard
from database.database import Database
from translations import get_text
from config import PAYMENT_CARD, PAYMENT_CARD_OWNER, ADMIN_IDS

router = Router()
logger = logging.getLogger(__name__)

# Payment menu items in different languages
PAYMENT_TEXTS = ["💳 To'lov qilish", "💳 Оплата", "💳 Payment"]
ACCOUNT_TEXTS = ["💰 Mening hisobim", "💰 Мой счет", "💰 My Account"]
REFERRAL_TEXTS = ["💰 Pul ishlab topish", "👥 Реферальная программа", "👥 Referral Program"]

@router.message(F.text.in_(PAYMENT_TEXTS))
async def handle_payment_request(message: Message, state: FSMContext, user_lang: str):
    """Handle payment request"""
    await state.clear()  # Clear any active state
    
    if user_lang == "uz":
        explanation_text = "💳 Sizga kerakli to'lov miqdorini belgilang:"
    elif user_lang == "ru":
        explanation_text = "💳 Укажите необходимую сумму платежа:"
    else:  # en
        explanation_text = "💳 Specify the required payment amount:"
    
    await message.answer(
        explanation_text,
        reply_markup=get_payment_amount_keyboard(user_lang),
        parse_mode="Markdown"
    )

@router.message(F.text.in_(ACCOUNT_TEXTS))
async def handle_account_info(message: Message, state: FSMContext, db: Database, user_lang: str, user):
    """Show account information"""
    await state.clear()  # Clear any active state
    if not user:
        await message.answer("❌ Сначала выполните команду /start")
        return
    
    # Get referral statistics
    stats = await db.get_referral_stats(user.telegram_id)
    
    if user_lang == "uz":
        account_text = f"💰 Sizning hisobingiz:\n\n💵 Balans: {user.balance:,} so'm\n\n👥 Referral:\n• Taklif qilinganlar: {stats['total_referrals']}\n• To'lov qilganlar: {stats['paid_referrals']}\n• Jami daromad: {stats['total_earned']:,} so'm"
    elif user_lang == "ru":
        account_text = f"💰 Ваш счет:\n\n💵 Баланс: {user.balance:,} сум\n\n👥 Реферальная программа:\n• Приглашено: {stats['total_referrals']}\n• Оплатили: {stats['paid_referrals']}\n• Всего заработано: {stats['total_earned']:,} сум"
    else:  # en
        account_text = f"💰 Your Account:\n\n💵 Balance: {user.balance:,} som\n\n👥 Referral Program:\n• Invited: {stats['total_referrals']}\n• Paid: {stats['paid_referrals']}\n• Total Earned: {stats['total_earned']:,} som"
    
    await message.answer(
        account_text,
        reply_markup=get_main_keyboard(user_lang)
    )

@router.callback_query(F.data.startswith("pay_"))
async def handle_payment_amount_selection(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Handle payment amount selection"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    amount = int(callback.data.split("_")[1])
    await state.update_data(payment_amount=amount)
    
    if user_lang == "uz":
        instructions = f"""💳 **To'lov qilish uchun:**

1️⃣ Quyidagi karta raqamiga pul o'tkazing:
`{PAYMENT_CARD}`
Karta egasi: {PAYMENT_CARD_OWNER}

2️⃣ Kartaga **{amount:,} so'm** o'tkazing

3️⃣ "📤 To'lov chekini yuborish" tugmasini bosing va chekni yuboring

⚠️ **DIQQAT:** To'lov chekini faqat haqiqiy to'lov qilganingizdan keyin yuboring. Soxta chek yuborish taqiqlanadi va hisobingiz bloklanishi mumkin!"""
        upload_button_text = "📤 To'lov chekini yuborish"
    elif user_lang == "ru":
        instructions = f"""💳 **Для оплаты:**

1️⃣ Переведите деньги на карту:
`{PAYMENT_CARD}`
Владелец карты: {PAYMENT_CARD_OWNER}

2️⃣ Переведите на карту **{amount:,} сум**

3️⃣ Нажмите "📤 Отправить чек" и отправьте чек

⚠️ **ВНИМАНИЕ:** Отправляйте чек только после реального платежа. Отправка поддельных чеков запрещена и может привести к блокировке аккаунта!"""
        upload_button_text = "📤 Отправить чек"
    else:  # en
        instructions = f"""💳 **To pay:**

1️⃣ Transfer money to the card:
`{PAYMENT_CARD}`
Card owner: {PAYMENT_CARD_OWNER}

2️⃣ Transfer **{amount:,} som** to the card

3️⃣ Click "📤 Upload receipt" and send receipt

⚠️ **WARNING:** Send receipt only after real payment. Sending fake receipts is prohibited and may result in account blocking!"""
        upload_button_text = "📤 Upload receipt"
    
    # Create inline keyboard with upload button
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text=upload_button_text,
        callback_data=f"upload_receipt_{amount}"
    ))
    
    await callback.message.edit_text(
        instructions,
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )
    
    await state.update_data(payment_amount=amount)

@router.message(PaymentStates.waiting_for_screenshot, F.content_type.in_([ContentType.PHOTO, ContentType.DOCUMENT]))
async def handle_payment_screenshot(message: Message, state: FSMContext, db: Database, user_lang: str, user=None):
    """Handle payment screenshot"""
    try:
        # Get user from database if not provided by middleware
        if not user:
            user = await db.get_user(message.from_user.id)
            if not user:
                if user_lang == "uz":
                    error_text = "❌ Xatolik yuz berdi. Iltimos, /start buyrug'ini bajaring."
                elif user_lang == "ru":
                    error_text = "❌ Произошла ошибка. Пожалуйста, выполните команду /start."
                else:
                    error_text = "❌ Error occurred. Please execute /start command."
                
                await message.answer(error_text, reply_markup=get_main_keyboard(user_lang))
                await state.clear()
                return
        
        # Get payment amount and source from state
        data = await state.get_data()
        amount = data.get('payment_amount')
        source = data.get('payment_source', "")  # Get source if from help section
        
        if not amount:
            if user_lang == "uz":
                error_text = "❌ To'lov miqdori topilmadi. Iltimos, qaytadan boshlang."
            elif user_lang == "ru":
                error_text = "❌ Сумма платежа не найдена. Пожалуйста, начните заново."
            else:
                error_text = "❌ Payment amount not found. Please start again."
            
            await message.answer(error_text, reply_markup=get_main_keyboard(user_lang))
            await state.clear()
            return
        
        # Get file ID
        if message.photo:
            file_id = message.photo[-1].file_id
        else:
            file_id = message.document.file_id
        
        # Create payment record with source
        payment_id = await db.create_payment(user.id, amount, file_id, source)
        
        if not payment_id:
            if user_lang == "uz":
                error_text = "❌ To'lovni saqlashda xatolik. Iltimos, qayta urinib ko'ring."
            elif user_lang == "ru":
                error_text = "❌ Ошибка при сохранении платежа. Пожалуйста, попробуйте снова."
            else:
                error_text = "❌ Error saving payment. Please try again."
            
            await message.answer(error_text, reply_markup=get_main_keyboard(user_lang))
            await state.clear()
            return
        
        # Check time and add reminder
        from datetime import datetime
        now = datetime.now()
        current_hour = now.hour
        is_daytime = 7 <= current_hour < 22
        
        # Notify user
        success_msg = get_text(user_lang, "payment_sent_to_admin")
        if is_daytime:
            success_msg += f"\n\n{get_text(user_lang, 'payment_reminder_daytime')}"
        else:
            success_msg += f"\n\n{get_text(user_lang, 'payment_reminder_nighttime')}"
        
        await message.answer(
            success_msg,
            reply_markup=get_main_keyboard(user_lang),
            parse_mode="Markdown"
        )
        
        # Notify admins with source info
        await notify_admins_about_payment(message.bot, user, amount, message.message_id, payment_id, source)
        
        logger.info(f"Payment {payment_id} created successfully for user {user.telegram_id}, amount {amount}, source: {source}")
        
    except Exception as e:
        logger.error(f"Error processing payment screenshot for user {message.from_user.id}: {e}", exc_info=True)
        
        if user_lang == "uz":
            error_text = "❌ Xatolik yuz berdi. Iltimos, /start buyrug'ini bajaring va qayta urinib ko'ring."
        elif user_lang == "ru":
            error_text = "❌ Произошла ошибка. Пожалуйста, выполните /start и попробуйте снова."
        else:
            error_text = "❌ Error occurred. Please execute /start and try again."
        
        await message.answer(error_text, reply_markup=get_main_keyboard(user_lang))
    
    finally:
        await state.clear()

@router.callback_query(F.data.startswith("upload_receipt_"))
async def handle_upload_receipt(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Handle upload receipt button - show back button and wait for receipt"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    
    amount = int(callback.data.split("_")[2])
    
    if user_lang == "uz":
        wait_text = f"""📸 **To'lov chekini yuboring**

Summa: **{amount:,} so'm**

📤 To'lov chekini rasm yoki fayl shaklida yuboring.

⚠️ **DIQQAT:** Agar to'lovni bekor qilmoqchi bo'lsangiz, "🔙 Orqaga qaytish" tugmasini bosing!

❗️ Faqat haqiqiy to'lov chekini yuboring!"""
        back_button_text = "🔙 Orqaga qaytish"
    elif user_lang == "ru":
        wait_text = f"""📸 **Отправьте чек об оплате**

Сумма: **{amount:,} сум**

📤 Отправьте чек как фото или файл.

⚠️ **ВНИМАНИЕ:** Если хотите отменить платеж, нажмите "🔙 Назад"!

❗️ Отправляйте только настоящий чек об оплате!"""
        back_button_text = "🔙 Назад"
    else:  # en
        wait_text = f"""📸 **Send payment receipt**

Amount: **{amount:,} som**

📤 Send receipt as photo or file.

⚠️ **WARNING:** If you want to cancel payment, press "🔙 Back"!

❗️ Send only real payment receipt!"""
        back_button_text = "🔙 Back"
    
    # Delete the inline keyboard message
    await callback.message.edit_text(
        wait_text,
        parse_mode="Markdown"
    )
    
    # Show back button
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=back_button_text)]],
        resize_keyboard=True
    )
    
    await callback.message.answer(
        "👇",
        reply_markup=keyboard
    )
    
    await state.update_data(payment_amount=amount)
    await state.set_state(PaymentStates.waiting_for_screenshot)
    await callback.answer()

@router.message(PaymentStates.waiting_for_screenshot)
async def handle_invalid_payment_screenshot(message: Message, state: FSMContext, user_lang: str):
    """Handle invalid payment screenshot or back button"""
    # Check if user pressed back button
    back_buttons = ["🔙 Orqaga qaytish", "🔙 Назад", "🔙 Back"]
    
    if message.text in back_buttons:
        await state.clear()
        
        if user_lang == "uz":
            cancel_text = "❌ To'lov bekor qilindi."
        elif user_lang == "ru":
            cancel_text = "❌ Платеж отменен."
        else:
            cancel_text = "❌ Payment cancelled."
        
        await message.answer(
            cancel_text,
            reply_markup=get_main_keyboard(user_lang)
        )
        logger.info(f"User {message.from_user.id} cancelled payment using back button")
        return
    
    # Handle invalid content
    if user_lang == "uz":
        error_text = "❌ Iltimos, to'lov chekini rasm yoki fayl sifatida yuboring.\n\nAgar to'lovni bekor qilmoqchi bo'lsangiz, \"🔙 Orqaga qaytish\" tugmasini bosing."
    elif user_lang == "ru":
        error_text = "❌ Пожалуйста, отправьте чек об оплате как фото или файл.\n\nЕсли хотите отменить платеж, нажмите \"🔙 Назад\"."
    else:
        error_text = "❌ Please send payment receipt as photo or file.\n\nIf you want to cancel payment, press \"🔙 Back\"."
    
    await message.answer(error_text)
    logger.warning(f"User {message.from_user.id} sent invalid content type during payment: {message.content_type}")

async def notify_admins_about_payment(bot, user, amount, message_id, payment_id, source=""):
    """Notify admins about new payment"""
    from bot.keyboards import get_payment_review_keyboard
    
    user_link = f"@{user.username}" if user.username else f"tg://user?id={user.telegram_id}"
    
    # Add source info if present
    source_text = ""
    if source == "help":
        source_text = "\n📍 Manba: 📞 Yordam bo'limi orqali"
    
    for admin_id in ADMIN_IDS:
        try:
            # First, forward the screenshot
            await bot.copy_message(
                chat_id=admin_id,
                from_chat_id=user.telegram_id,
                message_id=message_id
            )
            
            # Then send payment info with buttons below the image
            text = (
                f"🧾 Yangi to'lov:\n"
                f"👤 Foydalanuvchi: {user_link}\n"
                f"💵 Summasi: {amount:,} so'm\n"
                f"📅 To'lov ID: {payment_id}{source_text}\n\n"
                f"⬆️ Yuqoridagi chekni tekshiring va to'lovni tasdiqlang:"
            )
            
            await bot.send_message(
                admin_id,
                text,
                reply_markup=get_payment_review_keyboard(payment_id)
            )
            
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

@router.callback_query(F.data == "show_referral")
async def handle_referral_callback(callback: CallbackQuery, db: Database, user_lang: str, user):
    """Show referral information from payment menu"""
    if not user:
        await callback.answer("❌ Avval /start buyrug'ini bajaring", show_alert=True)
        return
    
    try:
        # Ensure user has referral code
        if not user.referral_code:
            logger.error(f"User {user.telegram_id} has no referral code after get_user")
            await callback.answer("❌ Xatolik yuz berdi. Iltimos, /start buyrug'ini qayta bajaring.", show_alert=True)
            return
        
        # Get referral statistics
        stats = await db.get_referral_stats(user.telegram_id)
        
        # Get bot username for referral link
        bot_info = await callback.bot.get_me()
        bot_username = bot_info.username
        
        # Create referral link
        referral_link = f"https://t.me/{bot_username}?start=ref_{user.referral_code}"
        
        # Edit message with referral info
        await callback.message.edit_text(
            get_text(user_lang, "referral_info",
                    total_referrals=stats['total_referrals'],
                    paid_referrals=stats['paid_referrals'],
                    total_earned=stats['total_earned'],
                    referral_link=referral_link),
            parse_mode="Markdown"
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing referral info: {e}")
        await callback.answer("❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.", show_alert=True)
