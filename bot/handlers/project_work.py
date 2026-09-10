"""Loyiha ishi dialogi.

Mijoz mavzuni, manbani (AI o'zi / matn / fayl / sayt) va yo'nalishni o'zi
tanlaydi — shuning uchun bitta oqim har qanday institut talabiga moslashadi.
"""

import logging
import os

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.keyboards import (
    get_doc_language_keyboard,
    get_main_keyboard,
    get_project_artifacts_keyboard,
    get_project_depth_keyboard,
    get_project_field_keyboard,
    get_project_payment_keyboard,
    get_project_skip_keyboard,
    get_project_source_keyboard,
)
from bot.states import ProjectWorkStates
from config import PROJECT_WORK_DEPTH, PROJECT_WORK_PRICES, TEMP_DIR
from database.database import Database
from services.project_work import field_label, get_content_builder, get_document_builder
from services.project_work import source as source_module
from translations import get_text
from utils.security import sanitize_user_input, validate_topic_length

router = Router()
logger = logging.getLogger(__name__)

MENU_TEXTS = ["📐 Loyiha ishi", "📐 Проектная работа", "📐 Project Work"]

_SOURCE_NAMES = {
    source_module.KIND_AI: {"uz": "AI o'zi yozgan", "ru": "AI написал сам", "en": "Written by AI"},
    source_module.KIND_TEXT: {"uz": "Mijoz tushuntirgan", "ru": "Описание клиента", "en": "Client's brief"},
    source_module.KIND_FILE: {"uz": "Yuklangan fayl", "ru": "Загруженный файл", "en": "Uploaded file"},
    source_module.KIND_URL: {"uz": "Sayt", "ru": "Сайт", "en": "Website"},
}
_DEPTH_NAMES = {
    "standart": {"uz": "Standart", "ru": "Стандартный", "en": "Standard"},
    "keng": {"uz": "Kengaytirilgan", "ru": "Расширенный", "en": "Extended"},
}


def _label(table: dict, key: str, language: str) -> str:
    entry = table.get(key, {})
    return entry.get(language, entry.get("uz", key))


# ────────────────────────────────────────────────────────────────── boshlanish

@router.message(F.text.in_(MENU_TEXTS))
async def start_project_work(message: Message, state: FSMContext, user_lang: str):
    await state.clear()
    await state.set_state(ProjectWorkStates.waiting_for_language)
    await message.answer(
        get_text(user_lang, "pw_intro"),
        parse_mode="HTML",
        reply_markup=get_doc_language_keyboard(user_lang, back_callback="pw_cancel"),
    )


@router.callback_query(F.data.startswith("doc_lang_"), ProjectWorkStates.waiting_for_language)
async def chose_language(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    await state.update_data(doc_language=callback.data.replace("doc_lang_", ""))
    await state.set_state(ProjectWorkStates.waiting_for_topic)
    await callback.message.edit_text(get_text(user_lang, "pw_ask_topic"))


@router.message(ProjectWorkStates.waiting_for_topic, F.text)
async def got_topic(message: Message, state: FSMContext, user_lang: str):
    topic = sanitize_user_input(message.text or "")
    if not validate_topic_length(topic):
        await message.answer(get_text(user_lang, "pw_ask_topic"))
        return
    await state.update_data(topic=topic)
    await state.set_state(ProjectWorkStates.waiting_for_author)
    await message.answer(
        get_text(user_lang, "pw_ask_author"),
        reply_markup=get_project_skip_keyboard(user_lang, "pw_skip_author"),
    )


@router.message(ProjectWorkStates.waiting_for_author, F.text)
async def got_author(message: Message, state: FSMContext, user_lang: str):
    await state.update_data(author_name=sanitize_user_input(message.text or "")[:100])
    await _ask_source(message, state, user_lang)


@router.callback_query(F.data == "pw_skip_author", ProjectWorkStates.waiting_for_author)
async def skip_author(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    await state.update_data(author_name="")
    await _ask_source(callback.message, state, user_lang)


async def _ask_source(message: Message, state: FSMContext, user_lang: str):
    await state.set_state(ProjectWorkStates.waiting_for_source_kind)
    await message.answer(
        get_text(user_lang, "pw_ask_source"),
        parse_mode="HTML",
        reply_markup=get_project_source_keyboard(user_lang),
    )


# ──────────────────────────────────────────────────────────────────── manba

@router.callback_query(F.data.startswith("pw_source:"), ProjectWorkStates.waiting_for_source_kind)
async def chose_source(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    kind = callback.data.split(":", 1)[1]
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if kind == source_module.KIND_AI:
        await state.update_data(source_kind=source_module.KIND_AI, source_text="", source_label="")
        await _ask_field(callback.message, state, user_lang)
        return

    prompts = {
        source_module.KIND_TEXT: ("pw_ask_instructions", ProjectWorkStates.waiting_for_instructions),
        source_module.KIND_FILE: ("pw_ask_file", ProjectWorkStates.waiting_for_source_file),
        source_module.KIND_URL: ("pw_ask_urls", ProjectWorkStates.waiting_for_source_urls),
    }
    key, next_state = prompts[kind]
    await state.update_data(source_kind=kind)
    await state.set_state(next_state)
    await callback.message.answer(get_text(user_lang, key))


@router.message(ProjectWorkStates.waiting_for_instructions, F.text)
async def got_instructions(message: Message, state: FSMContext, user_lang: str):
    material = source_module.from_instructions(message.text or "")
    if not material.has_content:
        await message.answer(get_text(user_lang, "pw_ask_instructions"))
        return
    await _store_source(message, state, user_lang, material)


@router.message(ProjectWorkStates.waiting_for_source_file, F.document)
async def got_source_file(message: Message, state: FSMContext, user_lang: str):
    document = message.document
    name = (document.file_name or "").lower()
    if not name.endswith((".pdf", ".docx", ".pptx")):
        await message.answer(get_text(user_lang, "pw_source_bad_file"))
        return

    status = await message.answer(get_text(user_lang, "pw_source_reading"))
    local_path = None
    try:
        os.makedirs(TEMP_DIR, exist_ok=True)
        extension = os.path.splitext(name)[1]
        local_path = os.path.join(TEMP_DIR, f"pw_src_{document.file_id[-12:]}{extension}")
        await message.bot.download(document, destination=local_path)
        material = await source_module.from_file(local_path, document.file_name or "manba")
    except Exception as e:
        logger.error("Loyiha ishi manbasi o'qilmadi: %s", e)
        await status.edit_text(get_text(user_lang, "pw_source_failed"))
        return
    finally:
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except OSError:
                pass

    await status.delete()
    await _store_source(message, state, user_lang, material)


@router.message(ProjectWorkStates.waiting_for_source_urls, F.text)
async def got_source_urls(message: Message, state: FSMContext, user_lang: str):
    from services.url_book_service import extract_urls_from_text, validate_url

    urls = [url for url in extract_urls_from_text(message.text or "") if validate_url(url)[0]]
    if not urls:
        await message.answer(get_text(user_lang, "pw_ask_urls"))
        return

    status = await message.answer(get_text(user_lang, "pw_source_reading"))
    try:
        material = await source_module.from_urls(urls[:5])
    except Exception as e:
        logger.error("Loyiha ishi uchun saytdan matn olinmadi: %s", e)
        await status.edit_text(get_text(user_lang, "pw_source_failed"))
        return

    await status.delete()
    await _store_source(message, state, user_lang, material)


async def _store_source(message: Message, state: FSMContext, user_lang: str, material):
    await state.update_data(
        source_kind=material.kind,
        source_text=material.text,
        source_label=material.label,
    )
    if material.label:
        await message.answer(
            get_text(user_lang, "pw_source_ok", label=material.label, words=len(material.text.split())),
            parse_mode="HTML",
        )
    await _ask_field(message, state, user_lang)


# ─────────────────────────────────────────────────────────── yo'nalish va hajm

async def _ask_field(message: Message, state: FSMContext, user_lang: str):
    await state.set_state(ProjectWorkStates.waiting_for_field)
    await message.answer(
        get_text(user_lang, "pw_ask_field"),
        parse_mode="HTML",
        reply_markup=get_project_field_keyboard(user_lang),
    )


@router.callback_query(F.data.startswith("pw_field:"), ProjectWorkStates.waiting_for_field)
async def chose_field(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    await state.update_data(field_key=callback.data.split(":", 1)[1])
    await state.set_state(ProjectWorkStates.waiting_for_artifacts)
    await callback.message.edit_text(
        get_text(user_lang, "pw_ask_artifacts"),
        parse_mode="HTML",
        reply_markup=get_project_artifacts_keyboard(user_lang),
    )


@router.callback_query(F.data.startswith("pw_artifacts:"), ProjectWorkStates.waiting_for_artifacts)
async def chose_artifacts(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    await state.update_data(with_scheme=callback.data.endswith(":scheme"))
    await state.set_state(ProjectWorkStates.waiting_for_depth)
    await callback.message.edit_text(
        get_text(user_lang, "pw_ask_depth"),
        parse_mode="HTML",
        reply_markup=get_project_depth_keyboard(user_lang),
    )


@router.callback_query(F.data.startswith("pw_depth:"), ProjectWorkStates.waiting_for_depth)
async def chose_depth(callback: CallbackQuery, state: FSMContext, user_lang: str, user):
    await callback.answer()
    depth_key = callback.data.split(":", 1)[1]
    price = PROJECT_WORK_PRICES[depth_key]
    await state.update_data(depth_key=depth_key, price=price)
    await state.set_state(ProjectWorkStates.waiting_for_payment)

    data = await state.get_data()
    doc_language = data.get("doc_language", user_lang)
    await callback.message.edit_text(
        get_text(
            user_lang, "pw_summary",
            topic=data.get("topic", ""),
            field=field_label(data.get("field_key", ""), doc_language),
            source=_label(_SOURCE_NAMES, data.get("source_kind", source_module.KIND_AI), user_lang),
            depth=_label(_DEPTH_NAMES, depth_key, user_lang),
            price=price,
            balance=user.balance if user else 0,
        ),
        parse_mode="HTML",
        reply_markup=get_project_payment_keyboard(user_lang, price),
    )


@router.callback_query(F.data == "pw_cancel")
async def cancel(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        get_text(user_lang, "pw_cancelled"), reply_markup=get_main_keyboard(user_lang)
    )


# ────────────────────────────────────────────────────────────────── yaratish

@router.callback_query(F.data == "pw_pay", ProjectWorkStates.waiting_for_payment)
async def generate(callback: CallbackQuery, state: FSMContext, user_lang: str, db: Database, user):
    await callback.answer()
    data = await state.get_data()
    price = data.get("price", 0)

    if (user.balance if user else 0) < price:
        await callback.message.answer(get_text(user_lang, "insufficient_balance"))
        return

    await state.set_state(ProjectWorkStates.generating)
    topic = data.get("topic", "")
    doc_language = data.get("doc_language", user_lang)

    status = await callback.message.edit_text(
        get_text(user_lang, "pw_generating", topic=topic, done=0, total="?"),
        parse_mode="HTML",
    )

    import asyncio

    loop = asyncio.get_running_loop()

    def progress(done: int, total: int) -> None:
        asyncio.run_coroutine_threadsafe(
            _safe_edit(status, get_text(user_lang, "pw_generating", topic=topic, done=done, total=total)),
            loop,
        )

    material = source_module.SourceMaterial(
        kind=data.get("source_kind", source_module.KIND_AI),
        text=data.get("source_text", ""),
        label=data.get("source_label", ""),
    )

    file_path = None
    try:
        content = await get_content_builder().build(
            topic=topic,
            field_key=data.get("field_key", ""),
            language=doc_language,
            with_scheme=data.get("with_scheme", False),
            depth=PROJECT_WORK_DEPTH[data.get("depth_key", "standart")],
            source=material,
            progress_cb=progress,
        )
        content.author_name = data.get("author_name", "")

        await _safe_edit(status, get_text(user_lang, "pw_building", topic=topic))
        file_path = await get_document_builder().build(content)

        tables = sum(1 for section in content.sections if section.table)
        await callback.message.answer_document(
            document=FSInputFile(file_path, filename=f"Loyiha_ishi_{topic[:30].replace(' ', '_')}.docx"),
            caption=get_text(user_lang, "pw_done", sections=len(content.sections), tables=tables),
        )
        await db.update_user_balance(user.telegram_id, -price)
        logger.info("Loyiha ishi yuborildi: %s → %s", topic[:60], user.telegram_id)

        try:
            await status.delete()
        except Exception:
            pass
        await callback.message.answer(
            get_text(user_lang, "document_ready"), reply_markup=get_main_keyboard(user_lang)
        )
    except Exception as e:
        logger.exception("Loyiha ishi yaratishda xato: %s", e)
        await _safe_edit(status, get_text(user_lang, "pw_failed"))
        await callback.message.answer(
            get_text(user_lang, "pw_cancelled"), reply_markup=get_main_keyboard(user_lang)
        )
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        await state.clear()


async def _safe_edit(message: Message, text: str) -> None:
    try:
        await message.edit_text(text, parse_mode="HTML")
    except Exception:
        pass
