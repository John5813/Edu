import logging
import json
import asyncio
import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from bot.states import DocumentStates
from bot.keyboards import get_slide_count_keyboard, get_page_count_keyboard, get_main_keyboard, get_template_keyboard
from database.database import Database
from services.ai_service_new import AIService
from services.document_service_new import DocumentService
from services.template_service import TemplateService
from services.channel_service import ChannelService
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
    "📄 Referat": "referat"
}

@router.message(F.text.in_(list(DOCUMENT_TYPES.keys())))
async def handle_document_type_selection(message: Message, state: FSMContext, user_lang: str, db: Database, user):
    """Handle document type selection from main menu"""
    try:
        # Check channel subscription
        channels = await db.get_active_channels()
        if channels:
            channel_service = ChannelService(message.bot)
            is_subscribed = await channel_service.check_user_subscription(user.telegram_id, channels)

            if not is_subscribed:
                from bot.keyboards import get_subscription_check_keyboard
                await message.answer(
                    get_text(user_lang, "subscription_required"),
                    reply_markup=get_subscription_check_keyboard(user_lang, channels)
                )
                return

        doc_type = DOCUMENT_TYPES[message.text]
        await state.update_data(document_type=doc_type)

        # Ask for topic
        topic_text = get_text(user_lang, "enter_topic")
        await message.answer(topic_text)
        await state.set_state(DocumentStates.waiting_for_topic)

    except Exception as e:
        logger.error(f"Error in document type selection: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

@router.message(DocumentStates.waiting_for_topic)
async def handle_topic_input(message: Message, state: FSMContext, user_lang: str, db: Database, user):
    """Handle topic input from user"""
    try:
        topic = message.text.strip()

        if not topic or len(topic) < 3:
            await message.answer(get_text(user_lang, "topic_too_short"))
            return

        await state.update_data(topic=topic)

        # Get document type from state
        data = await state.get_data()
        doc_type = data.get('document_type')

        # Ask for slide/page count based on document type
        if doc_type == "presentation":
            await message.answer(
                get_text(user_lang, "select_slide_count"),
                reply_markup=get_slide_count_keyboard(user_lang)
            )
            await state.set_state(DocumentStates.waiting_for_slide_count)
        else:  # referat or independent_work
            await message.answer(
                get_text(user_lang, "select_page_count"),
                reply_markup=get_page_count_keyboard(user_lang)
            )
            await state.set_state(DocumentStates.waiting_for_page_count)

    except Exception as e:
        logger.error(f"Error handling topic input: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

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

# Subscription check helper function
async def check_user_subscription_required(message: Message, user, db: Database, user_lang: str) -> bool:
    """Check if user is subscribed to required channels"""
    channels = await db.get_active_channels()

    if not channels:
        return True  # No channels required

    channel_service = ChannelService(message.bot)
    is_subscribed = await channel_service.check_user_subscription(user.telegram_id, channels)

    if not is_subscribed:
        # Show subscription requirement
        from bot.keyboards import get_subscription_check_keyboard

        if user_lang == "uz":
            text = "❌ Hujjat yaratish uchun avval kanallarga a'zo bo'lishingiz shart!\n\n👇 Kanalga o'tish uchun tugmani bosing:"
        elif user_lang == "ru":
            text = "❌ Для создания документа сначала подпишитесь на каналы!\n\n👇 Нажмите кнопку для перехода в канал:"
        else:  # en
            text = "❌ To create document, you must subscribe to channels first!\n\n👇 Click the button to go to the channel:"

        await message.answer(
            text,
            reply_markup=get_subscription_check_keyboard(user_lang, channels)
        )
        return False

    return True

@router.message(F.text.in_(DOCUMENT_TYPES.keys()))
async def handle_document_request(message: Message, state: FSMContext, db: Database, user_lang: str, user):
    """Handle document creation request"""
    if not user:
        await message.answer("❌ Сначала выполните команду /start")
        return

    # Check subscription before allowing document creation
    if not await check_user_subscription_required(message, user, db, user_lang):
        return

    document_type = DOCUMENT_TYPES[message.text]
    await state.update_data(document_type=document_type)

    # Proceed directly to topic input
    await message.answer(get_text(user_lang, "enter_topic"))
    await state.set_state(DocumentStates.waiting_for_topic)

@router.message(DocumentStates.waiting_for_topic)
async def handle_topic_input(message: Message, state: FSMContext, user_lang: str):
    """Handle topic input"""
    topic = message.text.strip()

    # Simple check - only handle actual topics (not system buttons)
    # System buttons will be handled by their specific routers first due to order
    if topic.startswith(("⚙️", "💳", "💰", "📞", "📊", "🎓", "📄")):
        return  # Let other handlers process system buttons

    if len(topic) < 3:
        await message.answer("❌ Mavzu juda qisqa. Iltimos, to'liqroq kiriting.")
        return

    await state.update_data(topic=topic)
    data = await state.get_data()
    document_type = data['document_type']

    if document_type == "presentation":
        # Show slide count selection for paid service
        await message.answer(
            get_text(user_lang, "select_slide_count"),
            reply_markup=get_slide_count_keyboard(user_lang)
        )
        await state.set_state(DocumentStates.waiting_for_slide_count)
    else:
        await message.answer(
            get_text(user_lang, "select_page_count"),
            reply_markup=get_page_count_keyboard(document_type, user_lang)
        )
        await state.set_state(DocumentStates.waiting_for_page_count)

async def show_template_selection(message: Message, state: FSMContext, user_lang: str, group: int = 1, edit_message: bool = False):
    """Show all 20 templates in one overview image with numbered buttons"""
    try:
        from aiogram.types import FSInputFile

        # Send the overview image showing all 20 templates
        overview_image_path = "attached_assets/IMG_20250823_093040_1755924327080.jpg"

        if os.path.exists(overview_image_path):
            # Use translated text
            title_text = get_text(user_lang, "template_selection_title")
            description_text = get_text(user_lang, "template_selection_description")
            text = f"{title_text}\n\n{description_text}"

            await message.answer_photo(
                photo=FSInputFile(overview_image_path),
                caption=text,
                parse_mode="Markdown"
            )
        else:
            # Fallback if overview image not found - use translated fallback text
            text = get_text(user_lang, "template_selection_fallback")
            await message.answer(text, parse_mode="Markdown")

        # Send compact numbered keyboard with all 20 options
        from bot.keyboards import get_all_templates_keyboard
        keyboard = get_all_templates_keyboard()
        await message.answer(
            get_text(user_lang, "template_select_number"), 
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error in show_template_selection: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

@router.callback_query(F.data.startswith("template_group_"))
async def handle_template_group_navigation(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Handle template group navigation"""
    try:
        group = int(callback.data.split('_')[-1])
        await callback.answer()
        # Send new template selection as fresh message instead of editing
        await show_template_selection(callback.message, state, user_lang, group, edit_message=False)
    except Exception as e:
        logger.error(f"Error in template group navigation: {e}")
        await callback.answer("❌ Xatolik yuz berdi")

@router.callback_query(F.data.startswith("template_template_"))
async def handle_template_selection(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Handle template selection and start generation"""
    try:
        # Extract template number from callback data (template_template_X)
        template_num = callback.data.split("_")[-1]
        template_id = f"template_{template_num}"
        await callback.answer()

        # Save selected template
        await state.update_data(selected_template=template_id)

        # Clear template selection message
        # Start presentation generation
        await callback.message.edit_text("⏳ Taqdimot yaratilmoqda...")
        await generate_presentation_with_template(callback, state, db, user_lang, user)

    except Exception as e:
        logger.error(f"Error in template selection: {e}")
        await callback.message.answer("❌ Xatolik yuz berdi")

async def generate_presentation_with_template(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Generate presentation with selected template"""
    try:
        data = await state.get_data()
        topic = data['topic']
        slide_count = data['slide_count']
        template_id = data.get('selected_template', 'template_20')
        price = data.get('price', 0)

        # Create order record
        specifications = json.dumps({
            "slide_count": slide_count,
            "template": template_id
        })
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
            content = {
                'slides': [
                    {'title': topic, 'content': f"Bu taqdimot {topic} mavzusida tayyorlangan.", 'layout_type': 'bullet_points', 'slide_number': 1},
                    {'title': 'Kirish', 'content': f"{topic} haqida batafsil ma'lumot va asosiy nuqtalar.", 'layout_type': 'bullet_points', 'slide_number': 2}
                ]
            }

        # Create presentation with selected template background
        doc_service = DocumentService()
        template_service = TemplateService()

        # Apply template to presentation
        file_path = await doc_service.create_presentation_with_template_background(
            topic, content, user.first_name or "", template_id, template_service, user_lang
        )

        # Update order
        await db.update_document_order(order_id, "completed", file_path)

        # Deduct from balance
        await db.update_user_balance(user.telegram_id, -price)
        await callback.message.answer(get_text(user_lang, "document_ready"))

        # Get template name for caption
        template_service = TemplateService()
        template_name = template_service.get_template_name(template_id, user_lang)

        # Send file
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=get_text(user_lang, "document_ready_caption", 
                topic=topic,
                slide_count=slide_count,
                template=template_name
            ),
            reply_markup=get_main_keyboard(user_lang)
        )

        # Send gentle reminder about content review
        await callback.message.answer(get_text(user_lang, "document_reminder"), parse_mode="Markdown")

        await state.clear()

    except Exception as e:
        logger.error(f"Error generating presentation with template: {e}")
        await callback.message.answer(
            "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",
            reply_markup=get_main_keyboard(user_lang)
        )
        try:
            if 'order_id' in locals():
                await db.update_document_order(order_id, "failed")
        except:
            pass
        await state.clear()

@router.callback_query(F.data.startswith("slides_"), DocumentStates.waiting_for_slide_count)
async def handle_slide_count(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Handle slide count selection"""
    slide_count = int(callback.data.split("_")[1])
    await state.update_data(slide_count=slide_count)

    # Calculate price based on slide count
    price = get_document_price("presentation", {"slide_count": slide_count})

    # Check if user has sufficient balance
    if user.balance >= price:
        await state.update_data(price=price)
    else:
        # Insufficient balance
        await callback.message.answer(
            get_text(user_lang, "insufficient_balance", price=price),
            reply_markup=get_main_keyboard(user_lang)
        )
        await state.clear()
        return

    # Show template selection instead of generating directly
    await callback.answer()
    await show_template_selection(callback.message, state, user_lang, group=1, edit_message=False)
    await state.set_state(DocumentStates.waiting_for_template)

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

    # Check if user has sufficient balance
    if user.balance >= price:
        await state.update_data(price=price)
    else:
        # Insufficient balance
        await callback.message.answer(
            get_text(user_lang, "insufficient_balance", price=price),
            reply_markup=get_main_keyboard(user_lang)
        )
        await state.clear()
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
        price = data.get('price', 0)

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
        file_path = await doc_service.create_new_presentation_system(topic, content, user.first_name or "", user_lang)

        # Update order
        await db.update_document_order(order_id, "completed", file_path)

        # Deduct from balance
        await db.update_user_balance(user.telegram_id, -price)
        await callback.message.edit_text(get_text(user_lang, "document_ready"))

        # Send file
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"📊 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )

        # Send gentle reminder about content review
        await callback.message.answer(get_text(user_lang, "document_reminder"), parse_mode="Markdown")

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

        # Deduct from balance
        price = data.get('price', 0)
        await db.update_user_balance(user.telegram_id, -price)

        await callback.message.edit_text(get_text(user_lang, "document_ready"))

        # Send file
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"🎓 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )

        # Send gentle reminder about content review
        await callback.message.answer(get_text(user_lang, "document_reminder"), parse_mode="Markdown")

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

        # Deduct from balance
        price = data.get('price', 0)
        await db.update_user_balance(user.telegram_id, -price)

        await callback.message.edit_text(get_text(user_lang, "document_ready"))

        # Send file
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"📄 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )

        # Send gentle reminder about content review
        await callback.message.answer(get_text(user_lang, "document_reminder"), parse_mode="Markdown")

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
    await message.answer(
        get_text(user_lang, "my_account_info", 
            name=user.first_name,
            balance=user.balance
        ),
        reply_markup=get_main_keyboard(user_lang)
    )

# Help button texts in different languages
HELP_BUTTON_TEXTS = ["📞 Yordam", "📞 Помощь", "📞 Help"]

@router.message(F.text.in_(HELP_BUTTON_TEXTS))
async def help_handler(message: Message, state: FSMContext, user_lang: str):
    """Handles the 'Help' button click."""
    await state.clear()  # Clear any active state

    # Use translation system for help text
    help_text = get_text(user_lang, "help_text")

    await message.answer(
        help_text,
        reply_markup=get_main_keyboard(user_lang),
        parse_mode="Markdown"
    )