"""AI editing of a document the client uploads.

The client uploads a DOCX, says in free text what should change, gets a quote
built from the plan the AI produced, and pays from balance only once the
edited file is actually in hand.
"""

import logging
import os

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.keyboards import get_ai_edit_confirm_keyboard, get_main_keyboard
from bot.states import AIFileEditStates
from config import TEMP_DIR
from database.database import Database
from services.file_edit_service import get_file_edit_service
from translations import get_text

router = Router()
logger = logging.getLogger(__name__)

_MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _discard(*paths: str) -> None:
    for path in paths:
        if not path:
            continue
        try:
            os.remove(path)
        except OSError:
            pass


async def start_ai_edit(message: Message, state: FSMContext, user_lang: str) -> None:
    """Entry point from the "Faylni tahrirlash" menu."""
    await state.clear()
    await state.set_state(AIFileEditStates.waiting_for_file)
    await message.answer(get_text(user_lang, "ai_edit_send_file"))


@router.message(AIFileEditStates.waiting_for_file, F.document)
async def handle_upload(message: Message, state: FSMContext, user_lang: str):
    document = message.document
    name = (document.file_name or "").lower()

    if not name.endswith(".docx"):
        await message.answer(get_text(user_lang, "ai_edit_only_docx"))
        return

    if document.file_size and document.file_size > _MAX_UPLOAD_BYTES:
        await message.answer(get_text(user_lang, "edit_file_error"))
        return

    try:
        os.makedirs(TEMP_DIR, exist_ok=True)
        local_path = os.path.join(TEMP_DIR, f"ai_edit_{document.file_id[-12:]}.docx")
        await message.bot.download(document, destination=local_path)
    except Exception as e:
        logger.error(f"ai_edit download error: {e}")
        await message.answer(get_text(user_lang, "edit_file_error"))
        return

    await state.update_data(local_path=local_path, original_filename=document.file_name or "hujjat.docx")
    await state.set_state(AIFileEditStates.waiting_for_instructions)
    await message.answer(get_text(user_lang, "ai_edit_ask_changes"))


@router.message(AIFileEditStates.waiting_for_instructions, F.text)
async def handle_instructions(message: Message, state: FSMContext, user_lang: str, user):
    instruction = (message.text or "").strip()
    if len(instruction) < 5:
        await message.answer(get_text(user_lang, "ai_edit_ask_changes"))
        return

    data = await state.get_data()
    local_path = data.get("local_path")
    if not local_path or not os.path.exists(local_path):
        await state.clear()
        await message.answer(get_text(user_lang, "edit_file_error"), reply_markup=get_main_keyboard(user_lang))
        return

    status = await message.answer(get_text(user_lang, "ai_edit_analyzing"))
    try:
        plan = await get_file_edit_service().plan(local_path, instruction, user_lang)
    except Exception as e:
        logger.error(f"ai_edit planning failed: {e}")
        await status.edit_text(get_text(user_lang, "ai_edit_failed"))
        return

    if not plan.operations:
        await status.edit_text(
            get_text(user_lang, "ai_edit_nothing_to_do", summary=plan.summary or ""),
        )
        return

    await state.update_data(
        instruction=instruction,
        plan_operations=[operation.__dict__ for operation in plan.operations],
        plan_summary=plan.summary,
        plan_truncated=plan.truncated,
        price=plan.price,
    )
    await state.set_state(AIFileEditStates.waiting_for_confirmation)

    quote = get_text(
        user_lang,
        "ai_edit_quote",
        summary=plan.summary or "",
        ops=len(plan.operations),
        price=plan.price,
        balance=user.balance if user else 0,
    )
    if plan.truncated:
        quote += get_text(user_lang, "ai_edit_truncated_note")

    await status.edit_text(quote, parse_mode="HTML", reply_markup=get_ai_edit_confirm_keyboard(user_lang))


@router.callback_query(F.data == "ai_edit:retry", AIFileEditStates.waiting_for_confirmation)
async def handle_retry(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.set_state(AIFileEditStates.waiting_for_instructions)
    await callback.message.answer(get_text(user_lang, "ai_edit_ask_changes"))


@router.callback_query(F.data == "ai_edit:cancel", AIFileEditStates.waiting_for_confirmation)
async def handle_cancel(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    data = await state.get_data()
    _discard(data.get("local_path"))
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        get_text(user_lang, "ai_edit_cancelled"), reply_markup=get_main_keyboard(user_lang)
    )


@router.callback_query(F.data == "ai_edit:confirm", AIFileEditStates.waiting_for_confirmation)
async def handle_confirm(callback: CallbackQuery, state: FSMContext, user_lang: str, db: Database, user):
    await callback.answer()

    data = await state.get_data()
    price = data.get("price", 0)
    balance = user.balance if user else 0
    if balance < price:
        await callback.message.answer(get_text(user_lang, "insufficient_balance"))
        return

    local_path = data.get("local_path")
    if not local_path or not os.path.exists(local_path):
        await state.clear()
        await callback.message.answer(
            get_text(user_lang, "edit_file_error"), reply_markup=get_main_keyboard(user_lang)
        )
        return

    await state.set_state(AIFileEditStates.applying)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    status = await callback.message.answer(get_text(user_lang, "ai_edit_applying"))

    from services.file_edit_service import EditOperation, EditPlan

    plan = EditPlan(
        operations=[EditOperation(**item) for item in data.get("plan_operations", [])],
        summary=data.get("plan_summary", ""),
        price=price,
        truncated=data.get("plan_truncated", False),
    )

    out_path = None
    try:
        out_path = await get_file_edit_service().apply(local_path, plan, user_lang)

        original = data.get("original_filename", "hujjat.docx")
        base = os.path.splitext(original)[0]
        edited = FSInputFile(out_path, filename=f"{base}_tahrirlangan.docx")

        await callback.message.answer_document(
            document=edited, caption=get_text(user_lang, "ai_edit_done")
        )
        # Charged only after the file is delivered, so a failure costs nothing.
        await db.update_user_balance(user.telegram_id, -price)
        logger.info(
            "AI edit delivered to %s: %s operations, %s so'm",
            user.telegram_id, len(plan.operations), price,
        )
        await callback.message.answer(
            get_text(user_lang, "document_ready"), reply_markup=get_main_keyboard(user_lang)
        )
    except Exception as e:
        logger.error(f"ai_edit apply failed: {e}")
        await callback.message.answer(
            get_text(user_lang, "ai_edit_failed"), reply_markup=get_main_keyboard(user_lang)
        )
    finally:
        try:
            await status.delete()
        except Exception:
            pass
        _discard(local_path, out_path)
        await state.clear()
