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
        use_free_service = data.get('use_free_service', False)

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
            topic, content, user.first_name or "", template_id, template_service
        )

        # Update order
        await db.update_document_order(order_id, "completed", file_path)

        # Process payment
        price = get_document_price("presentation", {"slide_count": slide_count})
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

    # Check balance
    if user.balance < price:
        await callback.message.edit_text(get_text(user_lang, "insufficient_balance"))
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
        
        try:
            raw_content = await ai_service.generate_document_content(
                topic, section_count, "independent_work", user_lang
            )
            
            # Parse if string
            if isinstance(raw_content, str):
                try:
                    content = json.loads(raw_content)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse AI response as JSON: {raw_content[:100]}")
                    content = {'sections': [], 'references': []}
            else:
                content = raw_content
                
        except Exception as e:
            logger.error(f"Error getting AI content: {e}")
            content = {'sections': [], 'references': []}

        # Ensure content is dict
        if not isinstance(content, dict):
            logger.error(f"Content is not dict after parsing: {type(content)}")
            content = {'sections': [], 'references': []}
        
        # Add language
        content['language'] = user_lang
        
        # Validate sections
        if 'sections' not in content or not content['sections']:
            logger.error("No sections in content")
            content['sections'] = []
        else:
            validated_sections = []
            for idx, section in enumerate(content['sections']):
                if isinstance(section, dict) and 'title' in section and 'content' in section:
                    validated_sections.append(section)
                else:
                    logger.error(f"Invalid section {idx}: {section}")
            content['sections'] = validated_sections
        
        # Ensure references
        if 'references' not in content:
            content['references'] = []

        # Create document file using old professional service
        from services.document_service import DocumentService as OldDocumentService
        doc_service = OldDocumentService()
        file_path = await doc_service.create_independent_work(topic, content)

        # Update order
        await db.update_document_order(order_id, "completed", file_path)

        # Process payment with dynamic pricing
        price = get_document_price("independent_work", {"min_pages": min_pages, "max_pages": max_pages})
        await db.update_user_balance(user.telegram_id, -price)
        
        # Delete "generating" message
        try:
            await callback.message.delete()
        except:
            pass

        # Send file directly
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"✅ {get_text(user_lang, 'document_ready')}\n\n🎓 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )
        
        # Send gentle reminder about content review
        await callback.message.answer(get_text(user_lang, "document_reminder"), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error generating independent work: {e}")
        # Send new message instead of editing (can't use ReplyKeyboardMarkup with edit_text)
        await callback.message.answer(
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
        
        try:
            raw_content = await ai_service.generate_document_content(
                topic, section_count, "referat", user_lang
            )
            
            # Parse if string
            if isinstance(raw_content, str):
                try:
                    content = json.loads(raw_content)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse AI response as JSON: {raw_content[:100]}")
                    content = {'sections': [], 'references': []}
            else:
                content = raw_content
                
        except Exception as e:
            logger.error(f"Error getting AI content: {e}")
            content = {'sections': [], 'references': []}

        # Ensure content is dict
        if not isinstance(content, dict):
            logger.error(f"Content is not dict after parsing: {type(content)}")
            content = {'sections': [], 'references': []}
        
        # Add language
        content['language'] = user_lang
        
        # Validate sections
        if 'sections' not in content or not content['sections']:
            logger.error("No sections in content")
            content['sections'] = []
        else:
            validated_sections = []
            for idx, section in enumerate(content['sections']):
                if isinstance(section, dict) and 'title' in section and 'content' in section:
                    validated_sections.append(section)
                else:
                    logger.error(f"Invalid section {idx}: {section}")
            content['sections'] = validated_sections
        
        # Ensure references
        if 'references' not in content:
            content['references'] = []

        # Create document file using old professional service  
        from services.document_service import DocumentService as OldDocumentService
        doc_service = OldDocumentService()
        file_path = await doc_service.create_referat(topic, content)

        # Update order
        await db.update_document_order(order_id, "completed", file_path)

        # Process payment with dynamic pricing
        price = get_document_price("referat", {"min_pages": min_pages, "max_pages": max_pages})
        await db.update_user_balance(user.telegram_id, -price)
        
        # Delete "generating" message
        try:
            await callback.message.delete()
        except:
            pass

        # Send file directly
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"✅ {get_text(user_lang, 'document_ready')}\n\n📄 {topic}",
            reply_markup=get_main_keyboard(user_lang)
        )
        
        # Send gentle reminder about content review
        await callback.message.answer(get_text(user_lang, "document_reminder"), parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error generating referat: {e}")
        # Send new message (already using answer, not edit_text)
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
        get_text(user_lang, "my_account_info", 
            name=user.first_name,
            balance=user_balance
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