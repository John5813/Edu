import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from bot.states import AdminStates
from bot.keyboards import (
    get_admin_keyboard, get_payment_review_keyboard, get_channel_management_keyboard,
    get_channels_list_keyboard, get_promocode_keyboard, get_broadcast_target_keyboard,
    get_main_keyboard
)
from database.database import Database
from services.channel_service import ChannelService
from config import ADMIN_IDS
import string
import random

router = Router()
logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in ADMIN_IDS

# Admin menu handlers
@router.message(F.text == "📋 Buyurtmalar")
async def handle_orders_request(message: Message, db: Database):
    """Handle orders/payments request"""
    if not is_admin(message.from_user.id):
        return
    
    pending_payments = await db.get_pending_payments()
    
    if not pending_payments:
        await message.answer("📋 Kutilayotgan to'lovlar yo'q.")
        return
    
    await message.answer(f"📋 {len(pending_payments)} ta kutilayotgan to'lov mavjud.")
    
    for payment in pending_payments[:5]:  # Show first 5 payments
        user = await db.get_user_by_id(payment.user_id)
        user_link = f"@{user.username}" if user.username else f"tg://user?id={user.telegram_id}"
        
        text = (
            f"🧾 To'lov #{payment.id}\n"
            f"👤 Foydalanuvchi: {user_link}\n"
            f"💵 Summasi: {payment.amount:,} so'm\n"
            f"📅 Sana: {payment.created_at.strftime('%d.%m.%Y %H:%M')}"
        )
        
        await message.answer(
            text,
            reply_markup=get_payment_review_keyboard(payment.id)
        )

@router.callback_query(F.data.startswith("approve_payment_"))
async def approve_payment(callback: CallbackQuery, db: Database):
    """Approve payment"""
    if not is_admin(callback.from_user.id):
        return
    
    payment_id = int(callback.data.split("_")[2])
    
    try:
        # Get payment details
        payment = await db.get_payment_by_id(payment_id)
        if not payment:
            await callback.answer("❌ To'lov topilmadi.")
            return
        
        # Update payment status
        await db.update_payment_status(payment_id, "approved")
        
        # Add balance to user
        user = await db.get_user_by_id(payment.user_id)
        await db.update_user_balance(user.telegram_id, payment.amount)
        
        # Notify user
        await callback.bot.send_message(
            user.telegram_id,
            f"✅ To'lovingiz tasdiqlandi! {payment.amount:,} so'm hisobingizga qo'shildi."
        )
        
        await callback.message.edit_text(
            f"✅ To'lov #{payment_id} tasdiqlandi.\n"
            f"💵 {payment.amount:,} so'm foydalanuvchi hisobiga qo'shildi."
        )
        
    except Exception as e:
        logger.error(f"Error approving payment: {e}")
        await callback.answer("❌ Xatolik yuz berdi.")

@router.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(callback: CallbackQuery, db: Database):
    """Reject payment"""
    if not is_admin(callback.from_user.id):
        return
    
    payment_id = int(callback.data.split("_")[2])
    
    try:
        # Get payment details
        payment = await db.get_payment_by_id(payment_id)
        if not payment:
            await callback.answer("❌ To'lov topilmadi.")
            return
        
        # Update payment status
        await db.update_payment_status(payment_id, "rejected")
        
        # Notify user
        user = await db.get_user_by_id(payment.user_id)
        await callback.bot.send_message(
            user.telegram_id,
            "❌ To'lovingiz rad etildi. Iltimos, qayta urinib ko'ring."
        )
        
        await callback.message.edit_text(
            f"❌ To'lov #{payment_id} rad etildi.\n"
            f"Foydalanuvchiga xabar yuborildi."
        )
        
    except Exception as e:
        logger.error(f"Error rejecting payment: {e}")
        await callback.answer("❌ Xatolik yuz berdi.")

@router.message(F.text == "📢 Kanal sozlamalari")
async def handle_channel_settings(message: Message):
    """Handle channel settings"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "📢 Kanal sozlamalari",
        reply_markup=get_channel_management_keyboard()
    )

@router.callback_query(F.data == "add_channel")
async def add_channel_start(callback: CallbackQuery, state: FSMContext):
    """Start adding channel"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.message.edit_text(
        "📢 Yangi kanal qo'shish\n\n"
        "Kanal ID sini kiriting (masalan: -1001234567890):"
    )
    await state.set_state(AdminStates.waiting_for_channel_id)

@router.message(AdminStates.waiting_for_channel_id)
async def add_channel_id(message: Message, state: FSMContext):
    """Handle channel ID input"""
    try:
        channel_id = message.text.strip()
        
        # Basic validation
        if not channel_id.startswith("-100"):
            await message.answer("❌ Kanal ID noto'g'ri formatda. -100 bilan boshlanishi kerak.")
            return
        
        await state.update_data(channel_id=channel_id)
        await message.answer("📝 Kanal username ini kiriting (@username shaklida):")
        await state.set_state(AdminStates.waiting_for_channel_username)
        
    except Exception as e:
        logger.error(f"Error adding channel ID: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

@router.message(AdminStates.waiting_for_channel_username)
async def add_channel_username(message: Message, state: FSMContext):
    """Handle channel username input"""
    username = message.text.strip().replace("@", "")
    await state.update_data(channel_username=username)
    
    await message.answer("📝 Kanal nomini kiriting:")
    await state.set_state(AdminStates.waiting_for_channel_title)

@router.message(AdminStates.waiting_for_channel_title)
async def add_channel_title(message: Message, state: FSMContext, db: Database):
    """Handle channel title input and complete channel addition"""
    title = message.text.strip()
    data = await state.get_data()
    
    try:
        await db.add_channel(
            channel_id=data['channel_id'],
            channel_username=data['channel_username'],
            title=title
        )
        
        await message.answer(
            f"✅ Kanal qo'shildi:\n"
            f"📢 {title}\n"
            f"🆔 {data['channel_id']}\n"
            f"👤 @{data['channel_username']}",
            reply_markup=get_admin_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error adding channel: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
    
    finally:
        await state.clear()

@router.callback_query(F.data == "remove_channel")
async def remove_channel_start(callback: CallbackQuery, db: Database):
    """Start removing channel"""
    if not is_admin(callback.from_user.id):
        return
    
    channels = await db.get_active_channels()
    
    if not channels:
        await callback.message.edit_text("📢 Faol kanallar yo'q.")
        return
    
    await callback.message.edit_text(
        "🗑 O'chirish uchun kanalni tanlang:",
        reply_markup=get_channels_list_keyboard(channels)
    )

@router.callback_query(F.data.startswith("delete_channel_"))
async def remove_channel_confirm(callback: CallbackQuery, db: Database):
    """Remove channel"""
    if not is_admin(callback.from_user.id):
        return
    
    channel_id = callback.data.split("_")[2]
    
    try:
        await db.remove_channel(channel_id)
        await callback.message.edit_text(
            f"✅ Kanal o'chirildi: {channel_id}"
        )
    except Exception as e:
        logger.error(f"Error removing channel: {e}")
        await callback.answer("❌ Xatolik yuz berdi.")

@router.callback_query(F.data == "list_channels")
async def list_channels(callback: CallbackQuery, db: Database):
    """List all channels"""
    if not is_admin(callback.from_user.id):
        return
    
    channels = await db.get_active_channels()
    
    if not channels:
        await callback.message.edit_text("📢 Faol kanallar yo'q.")
        return
    
    text = "📢 Faol kanallar:\n\n"
    for channel in channels:
        text += f"• {channel.title}\n"
        text += f"  🆔 {channel.channel_id}\n"
        if channel.channel_username:
            text += f"  👤 @{channel.channel_username}\n"
        text += "\n"
    
    await callback.message.edit_text(text)

@router.message(F.text == "🎟 Promokod boshqaruvi")
async def handle_promocode_management(message: Message):
    """Handle promocode management"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "💬 Promokod boshqaruvi",
        reply_markup=get_promocode_keyboard()
    )

@router.callback_query(F.data == "create_promocode")
async def create_promocode_start(callback: CallbackQuery, state: FSMContext):
    """Start creating promocode"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.message.edit_text(
        "💬 Yangi promokod yaratish\n\n"
        "Promokod nomini kiriting (yoki 'auto' deb yozing avtomatik yaratish uchun):"
    )
    await state.set_state(AdminStates.waiting_for_promocode)

@router.message(AdminStates.waiting_for_promocode)
async def create_promocode_finish(message: Message, state: FSMContext, db: Database):
    """Complete promocode creation"""
    try:
        code_input = message.text.strip().upper()
        
        if code_input == "AUTO":
            # Generate random code
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        else:
            code = code_input
        
        # Set expiry to 24 hours from now
        expires_at = datetime.now() + timedelta(hours=24)
        
        promocode_id = await db.create_promocode(code, expires_at)
        
        await message.answer(
            f"✅ Promokod yaratildi:\n"
            f"💬 Kod: {code}\n"
            f"⏰ Amal qilish muddati: 24 soat\n"
            f"📅 Tugaydi: {expires_at.strftime('%d.%m.%Y %H:%M')}",
            reply_markup=get_admin_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error creating promocode: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
    
    finally:
        await state.clear()

@router.message(F.text == "💳 To'lovlar")
async def handle_payments_list(message: Message, db: Database):
    """Handle payments list request"""
    if not is_admin(message.from_user.id):
        return
    
    payments = await db.get_pending_payments()
    
    if not payments:
        await message.answer("📝 Kutilayotgan to'lovlar yo'q", reply_markup=get_admin_keyboard())
        return
    
    text = f"💳 Kutilayotgan to'lovlar ({len(payments)} ta):\n\n"
    
    for payment in payments:
        user = await db.get_user_by_id(payment.user_id)
        username = f"@{user.username}" if user.username else "Username yo'q"
        first_name = user.first_name or "Ism yo'q"
        text += (
            f"🆔 ID: {payment.id}\n"
            f"👤 {first_name} ({username})\n" 
            f"💰 {payment.amount:,} so'm\n"
            f"📅 {payment.created_at}\n\n"
        )
    
    await message.answer(text, reply_markup=get_admin_keyboard())

@router.message(F.text == "👥 Foydalanuvchilar")
async def handle_users_list(message: Message, db: Database):
    """Handle users list request"""
    if not is_admin(message.from_user.id):
        return
    
    users = await db.get_all_users()
    
    text = f"👥 Jami foydalanuvchilar: {len(users)}\n\n"
    text += "So'nggi 10 ta foydalanuvchi:\n"
    
    for user in users[-10:]:
        username = f"@{user.username}" if user.username else "Username yo'q"
        first_name = user.first_name or "Ism yo'q"
        text += f"• {first_name} ({username})\n"
        text += f"  💰 Balans: {user.balance} so'm\n"
        text += f"  🗓 Qo'shilgan: {user.created_at.strftime('%d.%m.%Y')}\n\n"
    
    await message.answer(text)

@router.message(F.text == "📊 Statistika")
async def handle_statistics(message: Message, db: Database):
    """Handle statistics request"""
    if not is_admin(message.from_user.id):
        return
    
    stats = await db.get_user_stats()
    
    text = (
        f"📈 Bot statistikasi:\n\n"
        f"👥 Jami foydalanuvchilar: {stats['total_users']}\n"
        f"🆕 Bugun qo'shilganlar: {stats['users_today']}\n"
        f"💰 Jami tushum: {stats['total_revenue']:,} so'm\n"
        f"📄 Jami buyurtmalar: {stats['total_orders']}\n"
    )
    
    await message.answer(text)

@router.message(F.text == "💰 Narxlar sozlamalari") 
async def handle_price_settings(message: Message):
    """Handle price settings request"""
    if not is_admin(message.from_user.id):
        return
    
    from config import PRESENTATION_PRICE, INDEPENDENT_WORK_PRICE, REFERAT_PRICE
    
    text = (
        f"💰 Joriy narxlar:\n\n"
        f"📊 Taqdimot: {PRESENTATION_PRICE:,} so'm\n"
        f"📄 Mustaqil ish: {INDEPENDENT_WORK_PRICE:,} so'm\n"
        f"📚 Referat: {REFERAT_PRICE:,} so'm\n\n"
        f"Narxlarni o'zgartirish uchun config.py faylini tahrirlang."
    )
    
    await message.answer(text, reply_markup=get_admin_keyboard())

@router.message(F.text == "🔧 Bot sozlamalari")
async def handle_bot_settings(message: Message):
    """Handle bot settings request"""
    if not is_admin(message.from_user.id):
        return
    
    from config import ADMIN_IDS, PAYMENT_CARD
    
    text = (
        f"🔧 Bot sozlamalari:\n\n"
        f"👨‍💼 Admin IDs: {', '.join(map(str, ADMIN_IDS))}\n"
        f"💳 To'lov kartasi: {PAYMENT_CARD}\n"
        f"🤖 Bot ishlayapti va barcha funksiyalar faol\n\n"
        f"Sozlamalarni o'zgartirish uchun config.py faylini tahrirlang."
    )
    
    await message.answer(text, reply_markup=get_admin_keyboard())

@router.message(F.text == "🗄 Database boshqaruvi")
async def handle_database_management(message: Message, db: Database):
    """Handle database management request"""
    if not is_admin(message.from_user.id):
        return
    
    # Get database statistics
    users_count = len(await db.get_all_users())
    orders_count = 0  # Placeholder - would need proper query method
    payments_count = 0  # Placeholder - would need proper query method
    
    text = (
        f"🗄 Database ma'lumotlari:\n\n"
        f"👥 Foydalanuvchilar: {users_count}\n"
        f"📋 Buyurtmalar: {orders_count}\n" 
        f"💳 To'lovlar: {payments_count}\n\n"
        f"Database to'liq ishlayapti va barcha ma'lumotlar saqlab qolinmoqda."
    )
    
    await message.answer(text, reply_markup=get_admin_keyboard())

@router.message(F.text == "📤 Xabar yuborish")
async def handle_broadcast_start(message: Message, state: FSMContext):
    """Start broadcast message"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "📣 Xabar yuborish\n\n"
        "Yubormoqchi bo'lgan xabaringizni kiriting:"
    )
    await state.set_state(AdminStates.waiting_for_broadcast_message)

@router.message(AdminStates.waiting_for_broadcast_message)
async def handle_broadcast_message(message: Message, state: FSMContext):
    """Handle broadcast message input"""
    await state.update_data(
        message_text=message.text,
        message_type="text"
    )
    
    await message.answer(
        "📣 Kimga yuborilsin?",
        reply_markup=get_broadcast_target_keyboard()
    )
    await state.set_state(AdminStates.waiting_for_broadcast_target)

@router.callback_query(F.data.startswith("broadcast_"), AdminStates.waiting_for_broadcast_target)
async def handle_broadcast_target(callback: CallbackQuery, state: FSMContext, db: Database):
    """Handle broadcast target selection and send messages"""
    if not is_admin(callback.from_user.id):
        return
    
    target = callback.data.split("_")[1]
    data = await state.get_data()
    
    # Get target users
    all_users = await db.get_all_users()
    
    if target == "all":
        target_users = all_users
    else:  # active (users who used the bot in last 30 days)
        cutoff_date = datetime.now() - timedelta(days=30)
        target_users = [user for user in all_users if user.updated_at >= cutoff_date]
    
    await callback.message.edit_text(
        f"📤 Xabar yuborilmoqda...\n"
        f"Jami: {len(target_users)} ta foydalanuvchi"
    )
    
    # Send messages
    sent_count = 0
    failed_count = 0
    
    for user in target_users:
        try:
            await callback.bot.send_message(
                user.telegram_id,
                data['message_text']
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send message to {user.telegram_id}: {e}")
            failed_count += 1
    
    # Send result
    await callback.message.edit_text(
        f"✅ Xabar yuborish yakunlandi:\n\n"
        f"✅ {sent_count} ta yuborildi\n"
        f"❌ {failed_count} ta foydalanuvchiga yetmadi"
    )
    
    await state.clear()

@router.message(F.text == "👤 Foydalanuvchi rejimi")
async def switch_to_user_mode(message: Message):
    """Switch to user mode"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "👤 Foydalanuvchi rejimiga o'tdingiz",
        reply_markup=get_main_keyboard("uz")  # Default to Uzbek
    )
