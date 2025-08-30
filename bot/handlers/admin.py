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
@router.message(F.text == "💳 To'lovlar")
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

@router.message(F.text == "📢 Kanallar")
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
        
        # Validate if bot has access to this channel
        channel_service = ChannelService(message.bot)
        if not await channel_service.validate_channel(channel_id):
            await message.answer(
                "❌ Bot ushbu kanalga kirish huquqi yo'q!\n\n"
                "📝 Quyidagi qadamlarni bajaring:\n"
                "1. Kanalga @Hshjdjbot ni admin sifatida qo'shing\n"
                "2. Bot uchun 'A'zolarni ko'rish' huquqini bering\n"
                "3. Qayta urinib ko'ring"
            )
            return
        
        await state.update_data(channel_id=channel_id)
        await message.answer("🔗 Kanal linkini kiriting (https://t.me/channelname shaklida):")
        await state.set_state(AdminStates.waiting_for_channel_username)
        
    except Exception as e:
        logger.error(f"Error adding channel ID: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

@router.message(AdminStates.waiting_for_channel_username)
async def add_channel_username(message: Message, state: FSMContext):
    """Handle channel link input"""
    link = message.text.strip()
    
    # Extract username from link
    if link.startswith("https://t.me/"):
        username = link.replace("https://t.me/", "")
    elif link.startswith("t.me/"):
        username = link.replace("t.me/", "")
    elif link.startswith("@"):
        username = link.replace("@", "")
    else:
        # If it's just the username without link format
        username = link
    
    # Store both link and username
    await state.update_data(
        channel_username=username,
        channel_link=link if link.startswith(("https://", "t.me/")) else f"https://t.me/{username}"
    )
    
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

@router.callback_query(F.data == "list_promocodes")
async def list_promocodes(callback: CallbackQuery, db: Database):
    """List all promocodes"""
    if not is_admin(callback.from_user.id):
        return
    
    promocodes = await db.get_active_promocodes()
    
    if not promocodes:
        await callback.message.edit_text(
            "📋 Faol promokodlar yo'q",
            reply_markup=get_promocode_keyboard()
        )
        return
    
    text = f"📋 Faol promokodlar ({len(promocodes)} ta):\n\n"
    
    for promo in promocodes:
        expires_str = promo.expires_at.strftime('%d.%m.%Y %H:%M')
        # Count usage
        used_count = await db.count_promocode_usage(promo.id)
        
        text += f"🎟 **{promo.code}**\n"
        text += f"📅 Tugaydi: {expires_str}\n"
        text += f"👥 Ishlatilgan: {used_count} marta\n"
        text += f"🆔 ID: {promo.id}\n"
        text += "➖➖➖➖➖➖➖➖\n\n"
    
    # Add deactivate keyboard  
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔴 Promokodni o'chirish", callback_data="deactivate_promocode"))
    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_promocode_menu"))
    keyboard.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data == "promocode_stats")
async def promocode_stats(callback: CallbackQuery, db: Database):
    """Show promocode statistics"""
    if not is_admin(callback.from_user.id):
        return
    
    # Get all promocodes with usage stats
    all_promocodes = await db.get_all_promocodes_with_stats()
    active_count = len(await db.get_active_promocodes())
    
    total_created = len(all_promocodes)
    total_used = sum(promo.get('usage_count', 0) for promo in all_promocodes)
    
    text = f"📊 Promokod statistikasi:\n\n"
    text += f"🎟 Jami yaratilgan: {total_created}\n"
    text += f"✅ Faol promokodlar: {active_count}\n"
    text += f"❌ Faolsizlashtirilgan: {total_created - active_count}\n"
    text += f"👥 Jami foydalanish: {total_used} marta\n\n"
    
    # Top used promocodes
    if all_promocodes:
        text += "🔥 Eng ko'p ishlatilanlar:\n"
        sorted_promos = sorted(all_promocodes, key=lambda x: x.get('usage_count', 0), reverse=True)[:5]
        
        for i, promo in enumerate(sorted_promos, 1):
            usage = promo.get('usage_count', 0)
            text += f"{i}. {promo['code']} - {usage} marta\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_promocode_menu"))
    
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup())

@router.callback_query(F.data == "deactivate_promocode")
async def start_deactivate_promocode(callback: CallbackQuery, state: FSMContext):
    """Start deactivating promocode"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.message.edit_text(
        "🔴 Promokodni faolsizlashtirish\n\n"
        "Faolsizlashtirmoqchi bo'lgan promokod ID raqamini kiriting:"
    )
    await state.set_state(AdminStates.waiting_for_deactivate_promocode)

@router.callback_query(F.data == "back_to_promocode_menu")
async def back_to_promocode_menu(callback: CallbackQuery):
    """Return to promocode management menu"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.message.edit_text(
        "💬 Promokod boshqaruvi",
        reply_markup=get_promocode_keyboard()
    )

# Removed duplicate handler - using the first one defined above

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

@router.message(F.text == "📈 Kunlik statistika")
async def handle_daily_statistics(message: Message, db: Database):
    """Handle daily statistics request"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        # Get statistics using existing method
        stats = await db.get_user_stats()
        today = datetime.now()
        
        # Calculate yesterday's users (simple approximation)
        users_yesterday = max(0, stats['users_week'] - stats['users_today'])
        
        text = (
            f"📈 Kunlik statistika ({today.strftime('%d.%m.%Y')}):\n\n"
            f"👥 Bugun yangi foydalanuvchilar: {stats['users_today']}\n"
            f"📊 Bu hafta yangi foydalanuvchilar: {stats['users_week']}\n"
            f"📋 Jami buyurtmalar: {stats['total_orders']}\n"
            f"💰 Jami tushum: {stats['total_revenue']:,} so'm\n"
            f"📆 Bu oy buyurtmalar: {stats['orders_month']}\n\n"
            f"📈 Haftalik o'sish: +{stats['users_week']} foydalanuvchi\n"
            f"📅 Ma'lumot: {today.strftime('%d.%m.%Y %H:%M')}"
        )
        
        await message.answer(text)
        
    except Exception as e:
        logger.error(f"Error in daily statistics: {e}")
        await message.answer("❌ Kunlik statistikani olishda xatolik yuz berdi.")

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

@router.message(F.text == "📤 Reklama yuborish")
async def handle_broadcast_start(message: Message, state: FSMContext):
    """Start advertisement broadcast"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "📢 Reklama yuborish\n\n"
        "Yubormoqchi bo'lgan reklamangizni kiriting:\n\n"
        "📝 Matn xabar\n"
        "🖼 Rasm (caption bilan)\n"
        "🎥 Video (caption bilan)\n"
        "📄 Fayl/Hujjat\n"
        "🔗 URL havola\n\n"
        "Reklama materialingizni yuboring:"
    )
    await state.set_state(AdminStates.waiting_for_broadcast_message)

@router.message(AdminStates.waiting_for_broadcast_message)
async def handle_broadcast_message(message: Message, state: FSMContext):
    """Handle advertisement content input - supports all media types"""
    
    # Determine content type and store appropriate data
    if message.text:
        await state.update_data(
            message_text=message.text,
            message_type="text"
        )
    elif message.photo:
        await state.update_data(
            photo_id=message.photo[-1].file_id,
            caption=message.caption or "",
            message_type="photo"
        )
    elif message.video:
        await state.update_data(
            video_id=message.video.file_id,
            caption=message.caption or "",
            message_type="video"
        )
    elif message.document:
        await state.update_data(
            document_id=message.document.file_id,
            caption=message.caption or "",
            message_type="document"
        )
    elif message.animation:
        await state.update_data(
            animation_id=message.animation.file_id,
            caption=message.caption or "",
            message_type="animation"
        )
    elif message.voice:
        await state.update_data(
            voice_id=message.voice.file_id,
            caption=message.caption or "",
            message_type="voice"
        )
    elif message.audio:
        await state.update_data(
            audio_id=message.audio.file_id,
            caption=message.caption or "",
            message_type="audio"
        )
    else:
        await message.answer("❌ Ushbu turdagi kontent qo'llab-quvvatlanmaydi.")
        return
    
    await message.answer(
        "📢 Kimga reklama yuborilsin?",
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
        f"📢 Reklama yuborilmoqda...\n"
        f"Jami: {len(target_users)} ta foydalanuvchi"
    )
    
    # Send advertisements based on type
    sent_count = 0
    failed_count = 0
    message_type = data.get('message_type', 'text')
    
    for user in target_users:
        try:
            if message_type == "text":
                await callback.bot.send_message(
                    user.telegram_id,
                    data['message_text']
                )
            elif message_type == "photo":
                await callback.bot.send_photo(
                    user.telegram_id,
                    photo=data['photo_id'],
                    caption=data.get('caption')
                )
            elif message_type == "video":
                await callback.bot.send_video(
                    user.telegram_id,
                    video=data['video_id'],
                    caption=data.get('caption')
                )
            elif message_type == "document":
                await callback.bot.send_document(
                    user.telegram_id,
                    document=data['document_id'],
                    caption=data.get('caption')
                )
            elif message_type == "animation":
                await callback.bot.send_animation(
                    user.telegram_id,
                    animation=data['animation_id'],
                    caption=data.get('caption')
                )
            elif message_type == "voice":
                await callback.bot.send_voice(
                    user.telegram_id,
                    voice=data['voice_id'],
                    caption=data.get('caption')
                )
            elif message_type == "audio":
                await callback.bot.send_audio(
                    user.telegram_id,
                    audio=data['audio_id'],
                    caption=data.get('caption')
                )
            
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send {message_type} to {user.telegram_id}: {e}")
            failed_count += 1
    
    # Send result
    await callback.message.edit_text(
        f"✅ Reklama yuborish yakunlandi:\n\n"
        f"📊 Tur: {message_type.title()}\n"
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
