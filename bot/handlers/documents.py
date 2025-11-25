import logging
import json
import asyncio
import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from bot.states import DocumentStates
from bot.keyboards import get_slide_count_keyboard, get_page_count_keyboard, get_main_keyboard, get_template_keyboard, get_manual_input_keyboard, get_outline_review_keyboard, get_references_choice_keyboard
from database.database import Database
from utils.security import sanitize_user_input, validate_topic_length
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
        # Sanitize user input to prevent injection attacks
        topic = sanitize_user_input(message.text, max_length=200)

        if not validate_topic_length(topic, min_length=3, max_length=200):
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
    # Sanitize user input to prevent injection attacks
    topic = sanitize_user_input(message.text, max_length=200)
    
    # Remove problematic special characters that may break AI processing
    # Replace smart quotes and other special characters with standard ones
    topic = topic.replace('«', '"').replace('»', '"')
    topic = topic.replace('"', '"').replace('"', '"')
    topic = topic.replace(''', "'").replace(''', "'")
    # Normalize numbers: replace comma with period (3,5 -> 3.5)
    import re
    topic = re.sub(r'(\d),(\d)', r'\1.\2', topic)
    topic = topic.strip()

    # Simple check - only handle actual topics (not system buttons)
    # System buttons will be handled by their specific routers first due to order
    if topic.startswith(("⚙️", "💳", "💰", "📞", "📊", "🎓", "📄")):
        return  # Let other handlers process system buttons

    if not validate_topic_length(topic, min_length=3, max_length=200):
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

        photo_msg = None
        if os.path.exists(overview_image_path):
            # Use translated text - only title, no description
            title_text = get_text(user_lang, "template_selection_title")

            photo_msg = await message.answer_photo(
                photo=FSInputFile(overview_image_path),
                caption=title_text,
                parse_mode="Markdown"
            )
        else:
            # Fallback if overview image not found - use translated fallback text
            text = get_text(user_lang, "template_selection_fallback")
            photo_msg = await message.answer(text, parse_mode="Markdown")

        # Send compact numbered keyboard with all 20 options
        from bot.keyboards import get_all_templates_keyboard
        keyboard = get_all_templates_keyboard()
        keyboard_msg = await message.answer(
            get_text(user_lang, "template_select_number"), 
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # Save message IDs to state for later deletion
        await state.update_data(
            template_photo_msg_id=photo_msg.message_id if photo_msg else None,
            template_keyboard_msg_id=keyboard_msg.message_id
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
    """Handle template selection and ask about references"""
    try:
        # Extract template number from callback data (template_template_X)
        template_num = callback.data.split("_")[-1]
        template_id = f"template_{template_num}"
        await callback.answer()

        # Save selected template
        await state.update_data(selected_template=template_id)

        # Delete template selection messages (photo and keyboard)
        data = await state.get_data()
        photo_msg_id = data.get('template_photo_msg_id')
        keyboard_msg_id = data.get('template_keyboard_msg_id')
        
        try:
            if photo_msg_id:
                await callback.message.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=photo_msg_id
                )
            if keyboard_msg_id:
                await callback.message.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=keyboard_msg_id
                )
        except Exception as del_err:
            logger.warning(f"Could not delete template messages: {del_err}")
        
        # Ask if user wants to add references
        await callback.message.answer(
            get_text(user_lang, "add_references_question"),
            reply_markup=get_references_choice_keyboard(user_lang)
        )
        await state.set_state(DocumentStates.waiting_for_references_choice)

    except Exception as e:
        logger.error(f"Error in template selection: {e}")
        await callback.message.answer("❌ Xatolik yuz berdi")

@router.callback_query(F.data == "add_references_yes", DocumentStates.waiting_for_references_choice)
async def handle_add_references_yes(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Handle user choosing to add references"""
    await callback.answer()
    
    # Delete references question message
    await callback.message.delete()
    
    # Save choice
    await state.update_data(add_references=True)
    
    # Start generation
    await callback.message.answer("⏳ " + get_text(user_lang, "generating"))
    await generate_presentation_with_template(callback, state, db, user_lang, user)

@router.callback_query(F.data == "add_references_no", DocumentStates.waiting_for_references_choice)
async def handle_add_references_no(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Handle user choosing not to add references"""
    await callback.answer()
    
    # Delete references question message
    await callback.message.delete()
    
    # Save choice
    await state.update_data(add_references=False)
    
    # Start generation
    await callback.message.answer("⏳ " + get_text(user_lang, "generating"))
    await generate_presentation_with_template(callback, state, db, user_lang, user)

async def generate_presentation_with_template(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Generate presentation with selected template"""
    try:
        data = await state.get_data()
        topic = data['topic']
        slide_count = data['slide_count']
        template_id = data.get('selected_template', 'template_20')
        price = data.get('price', 0)
        manual_outline = data.get('manual_outline', [])
        add_references = data.get('add_references', False)

        # Create order record
        specifications = json.dumps({
            "slide_count": slide_count,
            "template": template_id,
            "manual_outline": len(manual_outline) > 0
        })
        order_id = await db.create_document_order(
            user_id=user.id,
            document_type="presentation",
            topic=topic,
            specifications=specifications
        )

        # Generate content with NEW AI BATCH SYSTEM
        ai_service = AIService()

        # If manual outline provided, use it
        if manual_outline:
            content = await ai_service.generate_presentation_with_manual_titles(
                topic, manual_outline, user_lang
            )
        else:
            content = await ai_service.generate_presentation_in_batches(topic, slide_count, user_lang)
        
        # Generate references if requested
        references = []
        if add_references:
            references = await ai_service.generate_references(topic, user_lang)

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
            topic, content, user.first_name or "", template_id, template_service, user_lang, references
        )

        # Verify file was created
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Presentation file not created or not found: {file_path}")
            raise Exception(f"File not created: {file_path}")

        # Get template name for caption
        template_name = template_service.get_template_name(template_id, user_lang)

        # Send file FIRST - only proceed if successful
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

        # File sent successfully - NOW update database and balance
        await db.update_document_order(order_id, "completed", file_path)
        await db.update_user_balance(user.telegram_id, -price)

        # Send success message AFTER file is delivered
        await callback.message.answer(get_text(user_lang, "document_ready"))

        # Send gentle reminder about content review
        await callback.message.answer(get_text(user_lang, "document_reminder"), parse_mode="Markdown")

        logger.info(f"Presentation successfully generated and sent: {file_path} for user {user.telegram_id}")
        await state.clear()

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error generating presentation with template: {e}\n{error_details}")
        await callback.message.answer(
            "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.\n\nSabab: " + str(e)[:100],
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
    # Check if user exists
    if not user:
        await callback.message.answer(
            "❌ Xatolik yuz berdi. Iltimos, /start buyrug'ini bajaring.",
            reply_markup=get_main_keyboard(user_lang)
        )
        await state.clear()
        return
    
    slide_count = int(callback.data.split("_")[1])
    await state.update_data(slide_count=slide_count)

    # Calculate price based on slide count
    price = get_document_price("presentation", {"slide_count": slide_count})

    # Check if user has sufficient balance
    if user.balance >= price:
        await state.update_data(price=price)
    else:
        # Insufficient balance
        await callback.message.delete()
        await callback.message.answer(
            get_text(user_lang, "insufficient_balance", price=price),
            reply_markup=get_main_keyboard(user_lang)
        )
        await state.clear()
        return

    # Delete slide count selection message
    await callback.answer()
    await callback.message.delete()
    
    # Show outline choice before template selection
    from bot.keyboards import get_outline_choice_keyboard
    await callback.message.answer(
        get_text(user_lang, "outline_choice"),
        reply_markup=get_outline_choice_keyboard(user_lang)
    )
    await state.set_state(DocumentStates.waiting_for_outline_choice)

@router.callback_query(F.data.startswith("pages_"), DocumentStates.waiting_for_page_count)
async def handle_page_count(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Handle page count selection"""
    # Check if user exists
    if not user:
        await callback.message.answer(
            "❌ Xatolik yuz berdi. Iltimos, /start buyrug'ini bajaring.",
            reply_markup=get_main_keyboard(user_lang)
        )
        await state.clear()
        return
    
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
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            get_text(user_lang, "insufficient_balance", price=price),
            reply_markup=get_main_keyboard(user_lang)
        )
        await state.clear()
        return

    # Remove inline keyboard (buttons disappear)
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    
    # Show outline choice
    from bot.keyboards import get_outline_choice_keyboard
    await callback.message.answer(
        get_text(user_lang, "outline_choice"),
        reply_markup=get_outline_choice_keyboard(user_lang)
    )
    await state.set_state(DocumentStates.waiting_for_outline_choice)

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

        # Verify file was created
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Presentation file (legacy) not created: {file_path}")
            raise Exception(f"File not created: {file_path}")

        # Send file FIRST - only proceed if successful
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"📊 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )

        # File sent successfully - NOW update database and balance
        await db.update_document_order(order_id, "completed", file_path)
        await db.update_user_balance(user.telegram_id, -price)

        # Send success message AFTER file is delivered
        await callback.message.edit_text(get_text(user_lang, "document_ready"))

        # Send gentle reminder about content review
        await callback.message.answer(get_text(user_lang, "document_reminder"), parse_mode="Markdown")

        logger.info(f"Presentation (legacy) generated and sent: {file_path} for user {user.telegram_id}")

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error generating presentation: {e}\n{error_details}")
        await callback.message.edit_text("❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.\n\nSabab: " + str(e)[:100])
        await callback.message.answer("Asosiy menyu:", reply_markup=get_main_keyboard(user_lang))
        # Update order status
        if 'order_id' in locals():
            await db.update_document_order(order_id, "failed")

    finally:
        await state.clear()

async def generate_independent_work_manual(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Generate independent work with manual outline"""
    try:
        data = await state.get_data()
        topic = data['topic']
        min_pages = data['min_pages']
        max_pages = data['max_pages']
        manual_outline = data.get('manual_outline', [])

        # Create order record
        specifications = json.dumps({"min_pages": min_pages, "max_pages": max_pages, "manual_outline": True})
        order_id = await db.create_document_order(
            user_id=user.id,
            document_type="independent_work",
            topic=topic,
            specifications=specifications
        )

        # Use manual outline instead of AI-generated
        from services.ai_service import AIService as OldAIService
        ai_service = OldAIService()

        # Generate content for each manually entered section
        sections = []
        for i, section_title in enumerate(manual_outline):
            section_content = await ai_service._generate_section_content(
                topic, section_title, i + 1, len(manual_outline), "independent_work", user_lang
            )
            sections.append({
                "title": section_title,
                "content": section_content
            })

        # Generate references
        references = await ai_service._generate_references(topic, user_lang)

        content = {
            "title": topic,
            "sections": sections,
            "references": references,
            "language": user_lang
        }

        # Create document file
        from services.document_service import DocumentService as OldDocumentService
        doc_service = OldDocumentService()
        file_path = await doc_service.create_independent_work(topic, content)

        # Verify file was created
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Manual independent work file not created: {file_path}")
            raise Exception(f"File not created: {file_path}")

        # Send file FIRST - only proceed if successful
        from aiogram.types import FSInputFile
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"🎓 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )

        # File sent successfully - NOW update database and balance
        await db.update_document_order(order_id, "completed", file_path)
        price = data.get('price', 0)
        await db.update_user_balance(user.telegram_id, -price)

        # Send success message AFTER file is delivered
        await callback.message.answer(get_text(user_lang, "document_ready"))
        await callback.message.answer(get_text(user_lang, "document_reminder"), parse_mode="Markdown")

        logger.info(f"Manual independent work generated and sent: {file_path} for user {user.telegram_id}")
        await state.clear()

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error generating manual independent work: {e}\n{error_details}")
        await callback.message.answer(
            "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.\n\nSabab: " + str(e)[:100],
            reply_markup=get_main_keyboard(user_lang)
        )
        if 'order_id' in locals():
            await db.update_document_order(order_id, "failed")
        await state.clear()

async def generate_referat_manual(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Generate referat with manual outline"""
    try:
        data = await state.get_data()
        topic = data['topic']
        min_pages = data['min_pages']
        max_pages = data['max_pages']
        manual_outline = data.get('manual_outline', [])

        # Create order record
        specifications = json.dumps({"min_pages": min_pages, "max_pages": max_pages, "manual_outline": True})
        order_id = await db.create_document_order(
            user_id=user.id,
            document_type="referat",
            topic=topic,
            specifications=specifications
        )

        # Use manual outline instead of AI-generated
        from services.ai_service import AIService as OldAIService
        ai_service = OldAIService()

        # Generate content for each manually entered section
        sections = []
        for i, section_title in enumerate(manual_outline):
            section_content = await ai_service._generate_section_content(
                topic, section_title, i + 1, len(manual_outline), "referat", user_lang
            )
            sections.append({
                "title": section_title,
                "content": section_content
            })

        # Generate references
        references = await ai_service._generate_references(topic, user_lang)

        content = {
            "title": topic,
            "sections": sections,
            "references": references,
            "language": user_lang
        }

        # Create document file
        from services.document_service import DocumentService as OldDocumentService
        doc_service = OldDocumentService()
        file_path = await doc_service.create_referat(topic, content)

        # Verify file was created
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Manual referat file not created: {file_path}")
            raise Exception(f"File not created: {file_path}")

        # Send file FIRST - only proceed if successful
        from aiogram.types import FSInputFile
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"📄 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )

        # File sent successfully - NOW update database and balance
        await db.update_document_order(order_id, "completed", file_path)
        price = data.get('price', 0)
        await db.update_user_balance(user.telegram_id, -price)

        # Send success message AFTER file is delivered
        await callback.message.answer(get_text(user_lang, "document_ready"))
        await callback.message.answer(get_text(user_lang, "document_reminder"), parse_mode="Markdown")

        logger.info(f"Manual referat generated and sent: {file_path} for user {user.telegram_id}")
        await state.clear()

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error generating manual referat: {e}\n{error_details}")
        await callback.message.answer(
            "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.\n\nSabab: " + str(e)[:100],
            reply_markup=get_main_keyboard(user_lang)
        )
        if 'order_id' in locals():
            await db.update_document_order(order_id, "failed")
        await state.clear()

async def generate_presentation_duplicate(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Generate presentation document (DUPLICATE - REDIRECTS TO MAIN)"""
    await generate_presentation(callback, state, db, user_lang, user)

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

        # Verify file was created
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Independent work file not created: {file_path}")
            raise Exception(f"File not created: {file_path}")

        # Send file FIRST - only proceed if successful
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"🎓 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )

        # File sent successfully - NOW update database and balance
        await db.update_document_order(order_id, "completed", file_path)
        price = data.get('price', 0)
        await db.update_user_balance(user.telegram_id, -price)

        # Send success message AFTER file is delivered
        await callback.message.answer(get_text(user_lang, "document_ready"))

        # Send gentle reminder about content review
        await callback.message.answer(get_text(user_lang, "document_reminder"), parse_mode="Markdown")

        logger.info(f"Independent work generated and sent: {file_path} for user {user.telegram_id}")

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error generating independent work: {e}\n{error_details}")
        await callback.message.answer(
            "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.\n\nSabab: " + str(e)[:100],
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

        # Verify file was created
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Referat file not created: {file_path}")
            raise Exception(f"File not created: {file_path}")

        # Send file FIRST - only proceed if successful
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"📄 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )

        # File sent successfully - NOW update database and balance
        await db.update_document_order(order_id, "completed", file_path)
        price = data.get('price', 0)
        await db.update_user_balance(user.telegram_id, -price)

        # Send success message AFTER file is delivered
        await callback.message.answer(get_text(user_lang, "document_ready"))

        # Send gentle reminder about content review
        await callback.message.answer(get_text(user_lang, "document_reminder"), parse_mode="Markdown")

        logger.info(f"Referat generated and sent: {file_path} for user {user.telegram_id}")

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error generating referat: {e}\n{error_details}")
        await callback.message.answer(
            "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.\n\nSabab: " + str(e)[:100],
            reply_markup=get_main_keyboard(user_lang)
        )
        if 'order_id' in locals():
            await db.update_document_order(order_id, "failed")

    finally:
        await state.clear()



@router.callback_query(F.data == "outline_auto", DocumentStates.waiting_for_outline_choice)
async def handle_outline_auto(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Handle automatic outline generation"""
    await callback.answer()
    
    # Delete outline choice message
    await callback.message.delete()

    data = await state.get_data()
    document_type = data.get('document_type')

    if document_type == "presentation":
        # For presentation, show template selection
        await show_template_selection(callback.message, state, user_lang, group=1, edit_message=False)
        await state.set_state(DocumentStates.waiting_for_template)
    else:
        # For documents, start generation
        generation_msg = await callback.message.answer("⏳ " + get_text(user_lang, "generating"))

        if document_type == "independent_work":
            # Call with callback parameter
            await generate_independent_work(callback, state, db, user_lang, user)
        else:  # referat
            # Call with callback parameter
            await generate_referat(callback, state, db, user_lang, user)

@router.callback_query(F.data == "cancel_document")
async def handle_cancel_document(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Handle document creation cancellation"""
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    
    cancel_texts = {
        "uz": "❌ Hujjat yaratish bekor qilindi.",
        "ru": "❌ Создание документа отменено.",
        "en": "❌ Document creation cancelled."
    }
    
    await callback.message.answer(
        cancel_texts.get(user_lang, cancel_texts["uz"]),
        reply_markup=get_main_keyboard(user_lang)
    )
    await state.clear()

@router.callback_query(F.data == "outline_manual", DocumentStates.waiting_for_outline_choice)
async def handle_outline_manual(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Handle manual outline entry"""
    await callback.answer()
    
    # Delete outline choice message
    await callback.message.delete()

    data = await state.get_data()
    document_type = data.get('document_type')

    # Calculate how many sections/slides needed
    if document_type == "presentation":
        slide_count = data.get('slide_count', 10)
        await state.update_data(manual_outline=[], current_section=1, total_sections=slide_count)
        
        # Show instruction with total count
        await callback.message.answer(
            get_text(user_lang, "manual_outline_instruction_presentation", total_slides=slide_count)
        )
        await callback.message.answer(
            get_text(user_lang, "enter_slide_title", slide_num=1, total_slides=slide_count),
            reply_markup=get_manual_input_keyboard(user_lang)
        )
    else:
        # For documents, determine section count based on pages
        max_pages = data.get('max_pages', 15)
        if max_pages <= 15:
            section_count = 6
        elif max_pages <= 20:
            section_count = 9
        elif max_pages <= 25:
            section_count = 12
        else:
            section_count = 15

        await state.update_data(manual_outline=[], current_section=1, total_sections=section_count)
        
        # Show instruction with total count
        await callback.message.answer(
            get_text(user_lang, "manual_outline_instruction_document", total_sections=section_count)
        )
        await callback.message.answer(
            get_text(user_lang, "enter_section_title", section_num=1, total_sections=section_count),
            reply_markup=get_manual_input_keyboard(user_lang)
        )

    await state.set_state(DocumentStates.waiting_for_manual_outline)

@router.message(DocumentStates.waiting_for_manual_outline)
async def handle_manual_outline_input(message: Message, state: FSMContext, db: Database, user_lang: str, user):
    """Handle manual outline section/slide title input"""
    
    # Check if user wants to go back
    back_texts = ["🔙 Ortga qaytish", "🔙 Назад", "🔙 Back"]
    if message.text in back_texts:
        # Go back to outline choice
        from bot.keyboards import get_outline_choice_keyboard
        await message.answer(
            get_text(user_lang, "outline_choice"),
            reply_markup=get_outline_choice_keyboard(user_lang)
        )
        await state.set_state(DocumentStates.waiting_for_outline_choice)
        return
    
    data = await state.get_data()
    manual_outline = data.get('manual_outline', [])
    current_section = data.get('current_section', 1)
    total_sections = data.get('total_sections', 1)
    document_type = data.get('document_type')

    # Sanitize and validate outline input
    outline_text = sanitize_user_input(message.text, max_length=150)
    
    if not validate_topic_length(outline_text, min_length=2, max_length=150):
        await message.answer("❌ Mavzu juda qisqa yoki uzun. 2-150 belgi oralig'ida kiriting.")
        return

    # Add current title to outline
    manual_outline.append(outline_text)
    current_section += 1

    if current_section <= total_sections:
        # Ask for next section/slide
        await state.update_data(manual_outline=manual_outline, current_section=current_section)

        if document_type == "presentation":
            await message.answer(
                get_text(user_lang, "enter_slide_title", slide_num=current_section, total_slides=total_sections),
                reply_markup=get_manual_input_keyboard(user_lang)
            )
        else:
            await message.answer(
                get_text(user_lang, "enter_section_title", section_num=current_section, total_sections=total_sections),
                reply_markup=get_manual_input_keyboard(user_lang)
            )
    else:
        # All sections/slides collected - show review
        await state.update_data(manual_outline=manual_outline)
        
        # Format outline for display
        outline_text = ""
        for i, item in enumerate(manual_outline, 1):
            outline_text += f"{i}. {item}\n"
        
        # Show review with confirm/edit buttons
        await message.answer(
            get_text(user_lang, "outline_review", outline_list=outline_text),
            reply_markup=get_outline_review_keyboard(user_lang),
            parse_mode="Markdown"
        )
        await state.set_state(DocumentStates.waiting_for_outline_confirmation)

@router.callback_query(F.data == "confirm_outline", DocumentStates.waiting_for_outline_confirmation)
async def handle_confirm_outline(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Handle outline confirmation"""
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    
    data = await state.get_data()
    document_type = data.get('document_type')
    
    await callback.message.answer(get_text(user_lang, "outline_complete"), reply_markup=get_main_keyboard(user_lang))
    
    if document_type == "presentation":
        # Show template selection for presentation
        await show_template_selection(callback.message, state, user_lang, group=1, edit_message=False)
        await state.set_state(DocumentStates.waiting_for_template)
    else:
        # Start document generation
        await callback.message.answer("⏳ " + get_text(user_lang, "generating"))
        
        if document_type == "independent_work":
            # Call with callback parameter
            await generate_independent_work_manual(callback, state, db, user_lang, user)
        else:  # referat
            # Call with callback parameter
            await generate_referat_manual(callback, state, db, user_lang, user)

@router.callback_query(F.data == "edit_outline", DocumentStates.waiting_for_outline_confirmation)
async def handle_edit_outline(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Handle outline editing - restart from beginning"""
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    
    data = await state.get_data()
    document_type = data.get('document_type')
    
    # Reset outline and start over
    if document_type == "presentation":
        slide_count = data.get('slide_count', 10)
        total_sections = slide_count
        await state.update_data(manual_outline=[], current_section=1, total_sections=total_sections)
        
        await callback.message.answer(
            get_text(user_lang, "manual_outline_instruction_presentation", total_slides=slide_count)
        )
        await callback.message.answer(
            get_text(user_lang, "enter_slide_title", slide_num=1, total_slides=slide_count),
            reply_markup=get_manual_input_keyboard(user_lang)
        )
    else:
        max_pages = data.get('max_pages', 15)
        if max_pages <= 15:
            section_count = 6
        elif max_pages <= 20:
            section_count = 9
        elif max_pages <= 25:
            section_count = 12
        else:
            section_count = 15
            
        await state.update_data(manual_outline=[], current_section=1, total_sections=section_count)
        
        await callback.message.answer(
            get_text(user_lang, "manual_outline_instruction_document", total_sections=section_count)
        )
        await callback.message.answer(
            get_text(user_lang, "enter_section_title", section_num=1, total_sections=section_count),
            reply_markup=get_manual_input_keyboard(user_lang)
        )
    
    await state.set_state(DocumentStates.waiting_for_manual_outline)

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

    from bot.keyboards import get_help_keyboard
    await message.answer(
        help_text,
        reply_markup=get_help_keyboard(user_lang),
        parse_mode="Markdown"
    )