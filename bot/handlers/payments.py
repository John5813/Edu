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
    
    free_service_status = "❌ Используется" if user.free_service_used else "✅ Доступна"
    
    await message.answer(
        get_text(user_lang, "balance_info", 
                balance=user.balance, 
                free_service=free_service_status),
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
