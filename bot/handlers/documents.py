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
from config import PRESENTATION_PRICE, INDEPENDENT_WORK_PRICE, REFERAT_PRICE

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

DOCUMENT_PRICES = {
    "presentation": PRESENTATION_PRICE,
    "independent_work": INDEPENDENT_WORK_PRICE,
    "referat": REFERAT_PRICE
}

@router.message(F.text.in_(DOCUMENT_TYPES.keys()))
async def handle_document_request(message: Message, state: FSMContext, db: Database, user_lang: str, user):
    """Handle document creation request"""
    if not user:
        await message.answer("❌ Сначала выполните команду /start")
        return

    document_type = DOCUMENT_TYPES[message.text]
    await state.update_data(document_type=document_type)

    # Check balance and free service (no promocode interruption)
    price = DOCUMENT_PRICES[document_type]

    # Check if user has promocode credits from settings
    has_promocode_credit = user.promocode_credit > 0 if hasattr(user, 'promocode_credit') else False

    if has_promocode_credit:
        # User has promocode credit, use it
        await state.update_data(use_promocode_credit=True)
    elif not user.free_service_used:
        # User can use free service for presentation
        if document_type == "presentation":
            await state.update_data(use_free_service=True)
        else:
            if user.balance < price:
                await message.answer(get_text(user_lang, "insufficient_balance"))
                return
    else:
        if user.balance < price:
            await message.answer(get_text(user_lang, "insufficient_balance"))
            return

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

    await callback.message.edit_text("⏳ " + get_text(user_lang, "generating"))

    # Start document generation
    data = await state.get_data()
    document_type = data['document_type']

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
            await db.update_user_balance(user.telegram_id, -PRESENTATION_PRICE)
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

        # Generate content with AI
        ai_service = AIService()
        content = await ai_service.generate_document_content(
            topic, section_count, "independent_work", user_lang
        )

        # Create document file
        doc_service = DocumentService()
        file_path = await doc_service.create_independent_work(topic, content)

        # Update order
        await db.update_document_order(order_id, "completed", file_path)

        # Process payment - no promocode logic needed
        await db.update_user_balance(user.telegram_id, -INDEPENDENT_WORK_PRICE)
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

        # Determine section count (referats are typically shorter)
        if max_pages <= 10:
            section_count = 4
        elif max_pages <= 12:
            section_count = 5
        else:
            section_count = 6

        # Generate content with AI
        ai_service = AIService()
        content = await ai_service.generate_document_content(
            topic, section_count, "referat", user_lang
        )

        # Create document file
        doc_service = DocumentService()
        file_path = await doc_service.create_referat(topic, content)

        # Update order
        await db.update_document_order(order_id, "completed", file_path)

        # Process payment - no promocode logic needed
        await db.update_user_balance(user.telegram_id, -REFERAT_PRICE)
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
        await callback.message.edit_text(
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

@router.message(F.text == "Yordam")
async def help_handler(message: Message, user_lang: str):
    """Handles the 'Help' button click."""
    await message.answer(
        get_text(user_lang, "help_message"),
        reply_markup=get_main_keyboard(user_lang)
    )