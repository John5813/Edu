"""
# bot/handlers/documents.py
# Qo'shimcha: fayl yuborilganda "Tahrirlash" tugmasi bilan web-app ochish va 1 soat keyin tugmani olib tashlash

import os
import json
import asyncio
import logging
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, FSInputFile, CallbackQuery
from aiogram.fsm.context import FSMContext

from services.document_service import DocumentService
from services.ai_service import AIService  # yoki mavjud AIService import qiling
from utils import get_text, get_main_keyboard  # mavjud yordamchi funksiyalar
from db import Database  # loyihadagi DB wrapper
from bot.handlers.documents import generate_course_work  # agar mavjud bo'lsa, mos joydan import qiling

logger = logging.getLogger(__name__)
DOC_SVC = DocumentService()

async def send_course_work_with_edit_button(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user, file_path: str, topic: str, min_pages: int, max_pages: int, chapters: int, order_id: int, price: int):
    """
    Send the generated course work file with an inline "Edit" webapp button.
    The button opens a web-editor (EDITOR_BASE_URL) with params: user_id, order_id, file.
    After 1 hour the button is automatically removed.
    """
    try:
        # Build web app URL
        editor_base = os.getenv("EDITOR_BASE_URL", "").rstrip("/")
        if not editor_base:
            logger.warning("EDITOR_BASE_URL not set - sending without edit button")
            kb = None
        else:
            edit_url = f"{editor_base}/edit?user_id={user.telegram_id}&order_id={order_id}&file={os.path.basename(file_path)}"
            kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton(
                    text=get_text(user_lang, "edit_document"),
                    web_app=WebAppInfo(url=edit_url)
                )
            )

        document = FSInputFile(file_path)
        sent_msg = await callback.message.answer_document(
            document=document,
            caption=f"📚 {topic}\n📄 {min_pages}-{max_pages} varoq | {chapters} bo'lim",
            reply_markup=kb
        )

        # Schedule removal of the edit button after 1 hour (3600 seconds)
        async def _remove_edit_button(chat_id: int, message_id: int, delay: int = 3600):
            await asyncio.sleep(delay)
            try:
                await callback.bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
                logger.info("Removed edit button for message %s:%s", chat_id, message_id)
            except Exception as e:
                logger.warning("Failed to remove edit button: %s", e)

        # Run background task (best-effort; persistent scheduler recommended for production)
        asyncio.create_task(_remove_edit_button(sent_msg.chat.id, sent_msg.message_id, delay=3600))

        # Update DB and user balance handled by caller (if needed)
    except Exception as e:
        logger.exception("Failed to send course work with edit button: %s", e)
        await callback.message.answer(get_text(user_lang, "document_send_error"), reply_markup=get_main_keyboard(user_lang))
"""