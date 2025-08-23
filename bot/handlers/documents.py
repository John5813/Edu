import logging
import json
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from bot.states import DocumentStates
from bot.keyboards import get_slide_count_keyboard, get_page_count_keyboard, get_main_keyboard
from database.database import Database
from services.ai_service_new import AIService
from services.document_service_new import DocumentService
from translations import get_text
from config import PRESENTATION_PRICES, DOCUMENT_PRICES

router = Router()
logger = logging.getLogger(__name__)

# Promokod handlers moved to settings

# Document type mapping
DOCUMENT_TYPES = {
    "📊 Taqdimot": "presentation",
    "📊 Презентация": "presentation",
    "📊 Presentation": "presentation",
    "🎓 Mustaqil ish": "independent_work",
    "🎓 Самостоятельная работа": "independent_work",
    "🎓 Independent Work": "independent_work",
    "📄 Referat": "referat",
    "📄 Реферат": "referat",
    "📄 Research Paper": "referat"
}

# Dynamic pricing helper function
def get_document_price(document_type: str, count_data: dict) -> int:
    """Get price based on document type and count"""
    if document_type == "presentation":
        slide_count = count_data.get('slide_count', 10)
        return PRESENTATION_PRICES.get(slide_count, 5000)
    else:  # independent_work or referat
        min_pages = count_data.get('min_pages', 10)
        max_pages = count_data.get('max_pages', 15)
        page_key = f"{min_pages}_{max_pages}"
        return DOCUMENT_PRICES.get(page_key, 5000)

@router.message(F.text.in_(DOCUMENT_TYPES.keys()))
async def handle_document_request(message: Message, state: FSMContext, db: Database, user_lang: str, user):
    """Handle document creation request"""
    if not user:
        await message.answer("❌ Сначала выполните команду /start")
        return

    document_type = DOCUMENT_TYPES[message.text]
    await state.update_data(document_type=document_type)

    # Free service check only for presentations, and only if not used yet  
    if not user.free_service_used and document_type == "presentation":
        await state.update_data(use_free_service=True)

    # Proceed directly to topic input
    await message.answer(get_text(user_lang, "enter_topic"))
    await state.set_state(DocumentStates.waiting_for_topic)

@router.message(DocumentStates.waiting_for_topic)
async def handle_topic_input(message: Message, state: FSMContext, user_lang: str):
    """Handle topic input"""
    topic = message.text.strip()

    if len(topic) < 3:
        await message.answer("❌ Mavzu juda qisqa. Iltimos, to'liqroq kiriting.")
        return

    await state.update_data(topic=topic)
    data = await state.get_data()
    document_type = data['document_type']

    if document_type == "presentation":
        await message.answer(
            get_text(user_lang, "select_slide_count"),
            reply_markup=get_slide_count_keyboard()
        )
        await state.set_state(DocumentStates.waiting_for_slide_count)
    else:
        await message.answer(
            get_text(user_lang, "select_page_count"),
            reply_markup=get_page_count_keyboard(document_type)
        )
        await state.set_state(DocumentStates.waiting_for_page_count)

@router.callback_query(F.data.startswith("slides_"), DocumentStates.waiting_for_slide_count)
async def handle_slide_count(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Handle slide count selection"""
    slide_count = int(callback.data.split("_")[1])
    await state.update_data(slide_count=slide_count)

    # Calculate price based on slide count
    data = await state.get_data()
    price = get_document_price("presentation", {"slide_count": slide_count})
    use_free_service = data.get('use_free_service', False)

    # Check balance if not using free service
    if not use_free_service and user.balance < price:
        await callback.message.edit_text(get_text(user_lang, "insufficient_balance"))
        return

    await callback.message.edit_text("⏳ " + get_text(user_lang, "generating"))

    # Start document generation
    asyncio.create_task(generate_presentation(callback, state, db, user_lang, user))

@router.callback_query(F.data.startswith("pages_"), DocumentStates.waiting_for_page_count)
async def handle_page_count(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Handle page count selection"""
    page_range = callback.data.split("_")[1:]
    min_pages = int(page_range[0])
    max_pages = int(page_range[1])

    await state.update_data(min_pages=min_pages, max_pages=max_pages)

    # Calculate price based on page count
    data = await state.get_data()
    document_type = data['document_type']
    price = get_document_price(document_type, {"min_pages": min_pages, "max_pages": max_pages})

    # Check balance
    if user.balance < price:
        await callback.message.edit_text(get_text(user_lang, "insufficient_balance"))
        return

    await callback.message.edit_text("⏳ " + get_text(user_lang, "generating"))

    # Start document generation
    if document_type == "independent_work":
        asyncio.create_task(generate_independent_work(callback, state, db, user_lang, user))
    else:  # referat
        asyncio.create_task(generate_referat(callback, state, db, user_lang, user))

async def generate_presentation(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Generate presentation document"""
    try:
        data = await state.get_data()
        topic = data['topic']
        slide_count = data['slide_count']
        use_free_service = data.get('use_free_service', False)

        # Create order record
        specifications = json.dumps({"slide_count": slide_count})
        order_id = await db.create_document_order(
            user_id=user.id,
            document_type="presentation",
            topic=topic,
            specifications=specifications
        )

        # Generate content with NEW AI BATCH SYSTEM
        ai_service = AIService()
        content = await ai_service.generate_presentation_in_batches(topic, slide_count, user_lang)

        # Validate AI response
        if not content or 'slides' not in content:
            logger.error(f"Invalid AI response from batch generation: {content}")
            # Create fallback content with new layout system
            content = {
                'slides': [
                    {'title': topic, 'content': f"Bu taqdimot {topic} mavzusida tayyorlangan.", 'layout_type': 'bullet_points', 'slide_number': 1},
                    {'title': 'Kirish', 'content': f"{topic} haqida batafsil ma'lumot va asosiy nuqtalar.", 'layout_type': 'bullet_points', 'slide_number': 2},
                    {'title': 'Asosiy qism', 'content': f"{topic}ning asosiy jihatlari va muhim ma'lumotlar.", 'layout_type': 'text_with_image', 'slide_number': 3}
                ]
            }

        # Create presentation file with NEW SYSTEM (DALL-E + 3 layouts)
        doc_service = DocumentService()
        file_path = await doc_service.create_new_presentation_system(topic, content, user.first_name or "")

        # Update order
        await db.update_document_order(order_id, "completed", file_path)

        # Process payment
        data = await state.get_data()
        use_free_service = data.get('use_free_service', False)

        if use_free_service:
            await db.mark_free_service_used(user.telegram_id)
            await callback.message.edit_text(get_text(user_lang, "free_service_used"))
        else:
            price = get_document_price("presentation", {"slide_count": slide_count})
            await db.update_user_balance(user.telegram_id, -price)
            await callback.message.edit_text(get_text(user_lang, "document_ready"))

        # Send file
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"📊 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )

    except Exception as e:
        logger.error(f"Error generating presentation: {e}")
        await callback.message.edit_text("❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")
        await callback.message.answer("Asosiy menyu:", reply_markup=get_main_keyboard(user_lang))
        # Update order status
        if 'order_id' in locals():
            await db.update_document_order(order_id, "failed")

    finally:
        await state.clear()

async def generate_independent_work(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Generate independent work document"""
    try:
        data = await state.get_data()
        topic = data['topic']
        min_pages = data['min_pages']
        max_pages = data['max_pages']

        # Create order record
        specifications = json.dumps({"min_pages": min_pages, "max_pages": max_pages})
        order_id = await db.create_document_order(
            user_id=user.id,
            document_type="independent_work",
            topic=topic,
            specifications=specifications
        )

        # Determine section count based on page range
        if max_pages <= 15:
            section_count = 6
        elif max_pages <= 20:
            section_count = 9
        elif max_pages <= 25:
            section_count = 12
        else:
            section_count = 15

        # Generate content with AI using old professional service
        from services.ai_service import AIService as OldAIService
        ai_service = OldAIService()
        content = await ai_service.generate_document_content(
            topic, section_count, "independent_work", user_lang
        )

        # Add language info to content for template
        content['language'] = user_lang

        # Create document file using old professional service
        from services.document_service import DocumentService as OldDocumentService
        doc_service = OldDocumentService()
        file_path = await doc_service.create_independent_work(topic, content)

        # Update order
        await db.update_document_order(order_id, "completed", file_path)

        # Process payment with dynamic pricing
        price = get_document_price("independent_work", {"min_pages": min_pages, "max_pages": max_pages})
        await db.update_user_balance(user.telegram_id, -price)
        await callback.message.edit_text(get_text(user_lang, "document_ready"))

        # Send file
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"🎓 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )

    except Exception as e:
        logger.error(f"Error generating independent work: {e}")
        await callback.message.edit_text(
            "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",
            reply_markup=get_main_keyboard(user_lang)
        )
        if 'order_id' in locals():
            await db.update_document_order(order_id, "failed")

    finally:
        await state.clear()

async def generate_referat(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Generate referat document"""
    try:
        data = await state.get_data()
        topic = data['topic']
        min_pages = data['min_pages']
        max_pages = data['max_pages']

        # Create order record
        specifications = json.dumps({"min_pages": min_pages, "max_pages": max_pages})
        order_id = await db.create_document_order(
            user_id=user.id,
            document_type="referat",
            topic=topic,
            specifications=specifications
        )

        # Determine section count based on new page ranges
        if max_pages <= 15:
            section_count = 6
        elif max_pages <= 20:
            section_count = 9
        elif max_pages <= 25:
            section_count = 12
        else:
            section_count = 15

        # Generate content with AI using old professional service
        from services.ai_service import AIService as OldAIService
        ai_service = OldAIService()
        content = await ai_service.generate_document_content(
            topic, section_count, "referat", user_lang
        )

        # Add language info to content for template
        content['language'] = user_lang

        # Create document file using old professional service  
        from services.document_service import DocumentService as OldDocumentService
        doc_service = OldDocumentService()
        file_path = await doc_service.create_referat(topic, content)

        # Update order
        await db.update_document_order(order_id, "completed", file_path)

        # Process payment with dynamic pricing
        price = get_document_price("referat", {"min_pages": min_pages, "max_pages": max_pages})
        await db.update_user_balance(user.telegram_id, -price)
        await callback.message.edit_text(get_text(user_lang, "document_ready"))

        # Send file
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"📄 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )

    except Exception as e:
        logger.error(f"Error generating referat: {e}")
        await callback.message.answer(
            "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",
            reply_markup=get_main_keyboard(user_lang)
        )
        if 'order_id' in locals():
            await db.update_document_order(order_id, "failed")

    finally:
        await state.clear()



@router.message(F.text == "Mening hisobim")
async def my_account_handler(message: Message, db: Database, user_lang: str, user):
    """Handles the 'My Account' button click."""
    user_balance = await db.get_user_balance(user.telegram_id)
    await message.answer(
        get_text(user_lang, "my_account_info").format(
            name=user.first_name,
            balance=user_balance
        ),
        reply_markup=get_main_keyboard(user_lang)
    )

# Help button texts in different languages
HELP_BUTTON_TEXTS = ["📞 Yordam", "📞 Помощь", "📞 Help"]

@router.message(F.text.in_(HELP_BUTTON_TEXTS))
async def help_handler(message: Message, user_lang: str):
    """Handles the 'Help' button click."""
    if user_lang == "uz":
        help_text = """
🎓 **EduBot.ai - Yordam**

**📊 Taqdimot narxlari:**
• 10 slayd - 5,000 so'm
• 15 slayd - 7,000 so'm
• 20 slayd - 10,000 so'm

**🎓 Mustaqil ish va 📄 Referat narxlari:**
• 10-15 varoq - 5,000 so'm
• 15-20 varoq - 7,000 so'm
• 20-25 varoq - 10,000 so'm
• 25-30 varoq - 12,000 so'm

**🆓 Bepul xizmat:**
• Har bir foydalanuvchi bitta bepul taqdimot olishi mumkin

**💳 To'lov usullari:**
• Karta: 9860 6006 1234 5678 (Humo)
• Skrinshot yuborib, admin tasdiqlashini kuting

**🎟 Promokod:**
• Sozlamalar > Promokod kiritish
• Bepul hujjat yaratish imkoniyati

**📞 Yordam uchun:**
• @edubot_support - Texnik yordam
• Ish vaqti: 9:00-18:00

**🔧 Bot imkoniyatlari:**
• AI yordamida professional hujjatlar
• Zamonaviy dizayn va formatting
• Tez va sifatli natija
• Ko'p tillar qo'llab-quvvatlash

**❓ Tez-tez so'raladigan savollar:**
• Taqdimot necha daqiqada tayyor? - 2-5 daqiqa
• Hujjatlar qanday formatda? - PowerPoint/Word
• Mazmun o'zbekchami? - Ha, kerakli tilda
• Qayta ishlash mumkinmi? - Ha, bepul

**🔄 Foydalanish tartibi:**
1. Hujjat turini tanlang
2. Mavzuni kiriting  
3. Parametrlarni sozlang
4. To'lovni amalga oshiring
5. Tayyor hujjatni oling

Agar savol bo'lsa, @edubot_support ga murojaat qiling! 😊
"""
    elif user_lang == "ru":
        help_text = """
🎓 **EduBot.ai - Помощь**

**📊 Презентация цены:**
• 10 слайдов - 5,000 сум
• 15 слайдов - 7,000 сум
• 20 слайдов - 10,000 сум

**🎓 Самостоятельная работа и 📄 Реферат цены:**
• 10-15 страниц - 5,000 сум
• 15-20 страниц - 7,000 сум
• 20-25 страниц - 10,000 сум
• 25-30 страниц - 12,000 сум

**🆓 Бесплатная услуга:**
• Каждый пользователь может получить одну бесплатную презентацию

**💳 Способы оплаты:**
• Карта: 9860 6006 1234 5678 (Humo)
• Отправьте скриншот и ждите подтверждения админа

**🎟 Промокод:**
• Настройки > Ввести промокод
• Возможность создать бесплатный документ

**📞 Для помощи:**
• @edubot_support - Техническая поддержка
• Рабочее время: 9:00-18:00

**🔧 Возможности бота:**
• Профессиональные документы с помощью AI
• Современный дизайн и форматирование
• Быстрый и качественный результат
• Поддержка нескольких языков

**❓ Часто задаваемые вопросы:**
• Сколько времени готовится презентация? - 2-5 минут
• В каком формате документы? - PowerPoint/Word
• Контент на узбекском? - Да, на нужном языке
• Можно ли редактировать? - Да, бесплатно

**🔄 Порядок использования:**
1. Выберите тип документа
2. Введите тему  
3. Настройте параметры
4. Произведите оплату
5. Получите готовый документ

При вопросах обращайтесь к @edubot_support! 😊
"""
    else:  # English
        help_text = """
🎓 **EduBot.ai - Help**

**📊 Presentation prices:**
• 10 slides - 5,000 som
• 15 slides - 7,000 som
• 20 slides - 10,000 som

**🎓 Independent Work and 📄 Research Paper prices:**
• 10-15 pages - 5,000 som
• 15-20 pages - 7,000 som
• 20-25 pages - 10,000 som
• 25-30 pages - 12,000 som

**🆓 Free service:**
• Each user can get one free presentation

**💳 Payment methods:**
• Card: 9860 6006 1234 5678 (Humo)
• Send screenshot and wait for admin confirmation

**🎟 Promocode:**
• Settings > Enter promocode
• Free document creation opportunity

**📞 For help:**
• @edubot_support - Technical support
• Working hours: 9:00-18:00

**🔧 Bot capabilities:**
• AI-powered professional documents
• Modern design and formatting
• Fast and quality results
• Multi-language support

**❓ Frequently asked questions:**
• How long does presentation take? - 2-5 minutes
• What format are documents? - PowerPoint/Word
• Content in Uzbek? - Yes, in required language
• Can I edit? - Yes, for free

**🔄 Usage process:**
1. Choose document type
2. Enter topic  
3. Configure parameters
4. Make payment
5. Get ready document

If you have questions, contact @edubot_support! 😊
"""

    await message.answer(
        help_text,
        reply_markup=get_main_keyboard(user_lang),
        parse_mode="Markdown"
    )