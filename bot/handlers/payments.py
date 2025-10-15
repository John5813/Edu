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
REFERRAL_TEXTS = ["👥 Referral dastur", "👥 Реферальная программа", "👥 Referral Program"]

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
    amount = int(callback.data.split("_")[1])
    await state.update_data(payment_amount=amount)
    
    if user_lang == "uz":
        instructions = f"""💳 To'lov qilish uchun:

1. Quyidagi karta raqamiga pul o'tkazing:
{PAYMENT_CARD}
Karta egasi: {PAYMENT_CARD_OWNER}

2. Kartaga **{amount:,} so'm** o'tkazing va chek yuboring:"""
    elif user_lang == "ru":
        instructions = f"""💳 Для оплаты:

1. Переведите деньги на карту:
{PAYMENT_CARD}
Владелец карты: {PAYMENT_CARD_OWNER}

2. Переведите на карту **{amount:,} сум** и отправьте чек:"""
    else:  # en
        instructions = f"""💳 To pay:

1. Transfer money to the card:
{PAYMENT_CARD}
Card owner: {PAYMENT_CARD_OWNER}

2. Transfer **{amount:,} som** to the card and send receipt:"""
    
    await callback.message.edit_text(instructions)
    
    await state.set_state(PaymentStates.waiting_for_screenshot)

@router.message(PaymentStates.waiting_for_screenshot, F.content_type.in_([ContentType.PHOTO, ContentType.DOCUMENT]))
async def handle_payment_screenshot(message: Message, state: FSMContext, db: Database, user_lang: str, user):
    """Handle payment screenshot"""
    try:
        data = await state.get_data()
        amount = data['payment_amount']
        
        # Get file ID
        if message.photo:
            file_id = message.photo[-1].file_id
        else:
            file_id = message.document.file_id
        
        # Create payment record
        payment_id = await db.create_payment(user.id, amount, file_id)
        
        # Notify user
        await message.answer(
            get_text(user_lang, "payment_sent_to_admin"),
            reply_markup=get_main_keyboard(user_lang)
        )
        
        # Notify admins
        await notify_admins_about_payment(message.bot, user, amount, message.message_id, payment_id)
        
    except Exception as e:
        logger.error(f"Error processing payment: {e}")
        await message.answer(
            "❌ Xatolik yuz berdi. Qayta urinib ko'ring.",
            reply_markup=get_main_keyboard(user_lang)
        )
    
    finally:
        await state.clear()

@router.message(PaymentStates.waiting_for_screenshot)
async def handle_invalid_payment_screenshot(message: Message, user_lang: str):
    """Handle invalid payment screenshot"""
    await message.answer("❌ Iltimos, to'lov chekini rasm yoki fayl sifatida yuboring.")

async def notify_admins_about_payment(bot, user, amount, message_id, payment_id):
    """Notify admins about new payment"""
    from bot.keyboards import get_payment_review_keyboard
    
    user_link = f"@{user.username}" if user.username else f"tg://user?id={user.telegram_id}"
    
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
                f"📅 To'lov ID: {payment_id}\n\n"
                f"⬆️ Yuqoridagi chekni tekshiring va to'lovni tasdiqlang:"
            )
            
            await bot.send_message(
                admin_id,
                text,
                reply_markup=get_payment_review_keyboard(payment_id)
            )
            
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

@router.message(F.text.in_(REFERRAL_TEXTS))
async def handle_referral_info(message: Message, db: Database, user_lang: str, user):
    """Show referral information and statistics"""
    if not user:
        await message.answer("❌ Avval /start buyrug'ini bajaring")
        return
    
    try:
        # Ensure user has referral code (should be handled by get_user, but double-check)
        if not user.referral_code:
            # This shouldn't happen due to lazy backfill, but handle it gracefully
            logger.error(f"User {user.telegram_id} has no referral code after get_user")
            await message.answer("❌ Xatolik yuz berdi. Iltimos, /start buyrug'ini qayta bajaring.")
            return
        
        # Get referral statistics
        stats = await db.get_referral_stats(user.telegram_id)
        
        # Get bot username for referral link
        bot_info = await message.bot.get_me()
        bot_username = bot_info.username
        
        # Create referral link
        referral_link = f"https://t.me/{bot_username}?start=ref_{user.referral_code}"
        
        # Send referral info with statistics
        await message.answer(
            get_text(user_lang, "referral_info",
                    total_referrals=stats['total_referrals'],
                    paid_referrals=stats['paid_referrals'],
                    total_earned=stats['total_earned'],
                    referral_link=referral_link),
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_lang)
        )
    except Exception as e:
        logger.error(f"Error showing referral info: {e}")
        await message.answer("❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")
