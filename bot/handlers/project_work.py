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
    get_project_blocks_keyboard,
    get_project_depth_keyboard,
    get_project_field_confirm_keyboard,
    get_project_field_keyboard,
    get_project_skip_keyboard,
    get_project_source_keyboard,
)
from bot import checkout as pay
from bot import dialog
from bot.states import ProjectWorkStates
from config import PROJECT_WORK_DEPTH, PROJECT_WORK_PRICES, TEMP_DIR
from database.database import Database
from services.project_work import field_label, get_content_builder, get_document_builder
from services.project_work.specs import (
    BLOCK_AUTO,
    BLOCK_SCHEME,
    GENERIC_FIELD_KEY,
    block_label,
)
from services import document_source
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


CHECKOUT = pay.Checkout(service="pw", back_callback="pw_back_to_depth")


def _label(table: dict, key: str, language: str) -> str:
    entry = table.get(key, {})
    return entry.get(language, entry.get("uz", key))


# ────────────────────────────────────────────────────────────────── boshlanish

@router.message(F.text.in_(MENU_TEXTS))
async def start_project_work(message: Message, state: FSMContext, user_lang: str):
    await state.clear()
    await state.set_data(pay.start({}))
    await state.set_state(ProjectWorkStates.waiting_for_language)
    await dialog.ask(
        message, state,
        get_text(user_lang, "pw_intro"),
        reply_markup=get_doc_language_keyboard(user_lang, back_callback="pw_cancel"),
        parse_mode="HTML",
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
    await dialog.resolve(message, state, get_text(user_lang, "pw_done_topic", topic=topic))
    await state.update_data(topic=topic)
    await _suggest_field(message, state, user_lang, topic)


# ─────────────────────────────────────────────────────────────── yo'nalish

async def _suggest_field(message: Message, state: FSMContext, user_lang: str, topic: str):
    """Mavzudan yo'nalishni taxmin qilib, tasdiqlashni so'raydi.

    Sakkizta tugmani mijozning o'zi ko'zdan kechirgandan ko'ra, taklifni
    tasdiqlash tezroq. Taxmin ishonchsiz bo'lsa — to'liq ro'yxat ochiladi.
    """
    try:
        field_key = await get_content_builder().suggest_field(topic)
    except Exception as e:
        logger.warning("Yo'nalish taxmini ishlamadi: %s", e)
        field_key = GENERIC_FIELD_KEY

    if field_key == GENERIC_FIELD_KEY:
        # Taxmin ishonchsiz — to'liq ro'yxat ochiladi.
        await _ask_field(message, state, user_lang)
        return

    await state.update_data(suggested_field=field_key)
    await state.set_state(ProjectWorkStates.waiting_for_field_confirm)
    await dialog.ask(
        message, state,
        get_text(user_lang, "pw_field_suggest", field=field_label(field_key, user_lang)),
        reply_markup=get_project_field_confirm_keyboard(user_lang, field_key),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "pw_field_change", ProjectWorkStates.waiting_for_field_confirm)
async def change_field(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    await _ask_field(callback.message, state, user_lang, edit=True)


async def _ask_source(message: Message, state: FSMContext, user_lang: str):
    await state.set_state(ProjectWorkStates.waiting_for_source_kind)
    await dialog.ask(
        message, state,
        get_text(user_lang, "pw_ask_source"),
        reply_markup=get_project_source_keyboard(user_lang),
        parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────────────── manba

@router.callback_query(F.data.startswith("pw_source:"), ProjectWorkStates.waiting_for_source_kind)
async def chose_source(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    kind = callback.data.split(":", 1)[1]
    await dialog.resolve(
        callback.message, state,
        get_text(user_lang, "pw_done_source", source=_label(_SOURCE_NAMES, kind, user_lang)),
    )

    if kind == source_module.KIND_AI:
        await state.update_data(source_kind=source_module.KIND_AI, source_text="", source_label="")
        await _ask_blocks(callback.message, state, user_lang)
        return

    prompts = {
        source_module.KIND_TEXT: ("pw_ask_instructions", ProjectWorkStates.waiting_for_instructions),
        source_module.KIND_FILE: ("pw_ask_file", ProjectWorkStates.waiting_for_source_file),
        source_module.KIND_URL: ("pw_ask_urls", ProjectWorkStates.waiting_for_source_urls),
    }
    key, next_state = prompts[kind]
    await state.update_data(source_kind=kind)
    await state.set_state(next_state)
    await dialog.ask(callback.message, state, get_text(user_lang, key))


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

    # Hajm xabar bilan birga keladi — bitta bayt yuklanmasdan oldin rad etamiz.
    try:
        document_source.check_size(document.file_size)
    except document_source.SourceTooLarge as e:
        await message.answer(
            get_text(user_lang, "source_too_large",
                     size=round(e.size_mb, 1),
                     limit=document_source.MAX_UPLOAD_BYTES // (1024 * 1024)),
            parse_mode="HTML",
        )
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
        await dialog.resolve(
            message, state,
            get_text(user_lang, "pw_source_ok", label=material.label, words=len(material.text.split())),
        )
    else:
        await dialog.resolve(message, state, get_text(user_lang, "pw_done_brief"))
    await _ask_blocks(message, state, user_lang)


# ─────────────────────────────────────────────────────────── yo'nalish va hajm

async def _ask_field(message: Message, state: FSMContext, user_lang: str, edit: bool = False):
    await state.set_state(ProjectWorkStates.waiting_for_field)
    text = get_text(user_lang, "pw_ask_field")
    markup = get_project_field_keyboard(user_lang)
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        return
    await dialog.ask(message, state, text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("pw_field:"),
                       ProjectWorkStates.waiting_for_field,
                       ProjectWorkStates.waiting_for_field_confirm)
async def chose_field(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    field_key = callback.data.split(":", 1)[1]
    await state.update_data(field_key=field_key)
    await dialog.resolve(
        callback.message, state,
        get_text(user_lang, "pw_done_field", field=field_label(field_key, user_lang)),
    )
    await _ask_source(callback.message, state, user_lang)


# ──────────────────────────────────────────────────────────── mazmun bloklari

async def _ask_blocks(message: Message, state: FSMContext, user_lang: str):
    data = await state.get_data()
    await state.set_state(ProjectWorkStates.waiting_for_blocks)
    await dialog.ask(
        message, state,
        get_text(user_lang, "pw_ask_blocks"),
        reply_markup=get_project_blocks_keyboard(user_lang, data.get("blocks") or []),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("pw_block:"), ProjectWorkStates.waiting_for_blocks)
async def toggle_block(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Bitta blokni yoqadi yoki o'chiradi va ro'yxatni joyida yangilaydi."""
    await callback.answer()
    key = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected = set(data.get("blocks") or [])

    if key == BLOCK_AUTO:
        # AI tanlovi qolgan belgilarni ma'nosiz qiladi, shuning uchun ular tozalanadi.
        selected = set() if BLOCK_AUTO in selected else {BLOCK_AUTO}
    else:
        selected.discard(BLOCK_AUTO)
        selected.symmetric_difference_update({key})

    await state.update_data(blocks=sorted(selected))
    try:
        await callback.message.edit_reply_markup(
            reply_markup=get_project_blocks_keyboard(user_lang, selected))
    except Exception:
        pass


@router.callback_query(F.data == "pw_blocks_done", ProjectWorkStates.waiting_for_blocks)
async def blocks_done(callback: CallbackQuery, state: FSMContext, user_lang: str):
    data = await state.get_data()
    selected = list(data.get("blocks") or [])
    if not selected:
        await callback.answer(get_text(user_lang, "pw_blocks_empty"), show_alert=True)
        return

    await callback.answer()
    names = ", ".join(block_label(key, user_lang) for key in selected)
    await dialog.resolve(callback.message, state,
                         get_text(user_lang, "pw_done_blocks", blocks=names))
    await state.update_data(with_scheme=BLOCK_SCHEME in selected)
    await state.set_state(ProjectWorkStates.waiting_for_depth)
    await dialog.ask(
        callback.message, state,
        get_text(user_lang, "pw_ask_depth"),
        reply_markup=get_project_depth_keyboard(user_lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("pw_depth:"), ProjectWorkStates.waiting_for_depth)
async def chose_depth(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    depth_key = callback.data.split(":", 1)[1]
    await state.update_data(depth_key=depth_key, price=PROJECT_WORK_PRICES[depth_key])
    await dialog.resolve(
        callback.message, state,
        get_text(user_lang, "pw_done_depth", depth=_label(_DEPTH_NAMES, depth_key, user_lang)),
    )
    # Muallif ismi faqat muqova uchun kerak, shuning uchun u eng oxirida so'raladi.
    await state.set_state(ProjectWorkStates.waiting_for_author)
    await dialog.ask(
        callback.message, state,
        get_text(user_lang, "pw_ask_author"),
        reply_markup=get_project_skip_keyboard(user_lang, "pw_skip_author"),
    )


@router.message(ProjectWorkStates.waiting_for_author, F.text)
async def got_author(message: Message, state: FSMContext, user_lang: str, user):
    author = sanitize_user_input(message.text or "")[:100]
    await dialog.resolve(message, state, get_text(user_lang, "pw_done_author", author=author))
    await state.update_data(author_name=author)
    await _show_summary(message, state, user_lang, user)


@router.callback_query(F.data == "pw_skip_author", ProjectWorkStates.waiting_for_author)
async def skip_author(callback: CallbackQuery, state: FSMContext, user_lang: str, user):
    await callback.answer()
    await dialog.resolve(callback.message, state, get_text(user_lang, "pw_done_author_skipped"))
    await state.update_data(author_name="")
    await _show_summary(callback.message, state, user_lang, user)


@router.callback_query(F.data == "pw_back_to_depth", ProjectWorkStates.waiting_for_payment)
async def back_to_depth(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Orqaga — hajm tanlash qaytadan ochiladi."""
    await callback.answer()
    await state.set_state(ProjectWorkStates.waiting_for_depth)
    await callback.message.edit_text(
        get_text(user_lang, "pw_ask_depth"),
        parse_mode="HTML",
        reply_markup=get_project_depth_keyboard(user_lang),
    )


async def _show_summary(message: Message, state: FSMContext, user_lang: str, user) -> None:
    await state.set_state(ProjectWorkStates.waiting_for_payment)
    data = await state.get_data()
    doc_language = data.get("doc_language", user_lang)
    price = data.get("price", 0)
    summary = get_text(
        user_lang, "pw_summary",
        topic=data.get("topic", ""),
        field=field_label(data.get("field_key", ""), doc_language),
        source=_label(_SOURCE_NAMES, data.get("source_kind", source_module.KIND_AI), user_lang),
        depth=_label(_DEPTH_NAMES, data.get("depth_key", "standart"), user_lang),
        blocks=", ".join(block_label(key, user_lang) for key in (data.get("blocks") or []))
               or block_label(BLOCK_AUTO, user_lang),
        price=price,
        balance=user.balance if user else 0,
    )
    markup = pay.payment_keyboard(CHECKOUT, user_lang, price)
    try:
        await message.edit_text(summary, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await message.answer(summary, parse_mode="HTML", reply_markup=markup)


# ─────────────────────────────────────────────────────────────────── to'lov

# Holat filtri yo'q: mijoz balansni to'ldirishga o'tib qaytgan bo'lishi
# mumkin, u oqim esa FSM ni tozalab yuboradi.
@router.callback_query(F.data == CHECKOUT.pay_stars)
async def pay_with_stars(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    data = await _order(callback.from_user.id, state)
    if not data:
        await _report_expired(callback.message, state, user_lang)
        return
    await pay.send_invoice(
        callback.message, CHECKOUT, user_lang, data.get("price", 0),
        title=get_text(user_lang, "main_menu.project_work"),
        description=data.get("topic", "")[:200],
    )


@router.message(F.successful_payment)
async def stars_paid(message: Message, state: FSMContext, user_lang: str, db: Database, user):
    """Stars to'landi — balans tekshirilmaydi, xizmat darhol yaratiladi."""
    payment = message.successful_payment
    if not payment or not CHECKOUT.owns_payload(payment.invoice_payload):
        return

    data = await _order(message.from_user.id, state)
    if not data:
        await _report_expired(message, state, user_lang)
        return

    await state.set_data(pay.mark_paid_with_stars(data))
    pay.forget(message.from_user.id)
    await message.answer(get_text(user_lang, "pay_stars_done"))
    await _generate(message, state, user_lang, db, user)


@router.callback_query(F.data == CHECKOUT.recheck)
async def recheck_balance(callback: CallbackQuery, state: FSMContext, user_lang: str, db: Database, user):
    """Mijoz balansni to'ldirgach — buyurtma o'sha joyidan davom etadi."""
    await callback.answer()
    data = await _order(callback.from_user.id, state)
    if not data:
        await _report_expired(callback.message, state, user_lang)
        return

    fresh = await db.get_user(callback.from_user.id)
    balance = fresh.balance if fresh else 0
    price = data.get("price", 0)
    if balance < price:
        await callback.answer(
            get_text(user_lang, "pay_still_short", balance=balance, price=price),
            show_alert=True,
        )
        return
    pay.forget(callback.from_user.id)
    await _generate(callback.message, state, user_lang, db, fresh)


async def _order(user_id: int, state: FSMContext) -> dict:
    """Buyurtmani FSM dan, u yo'q bo'lsa saqlangan nusxadan oladi."""
    data = await state.get_data()
    if data.get("topic") and not pay.is_expired(data):
        return data

    saved = pay.recall(user_id, CHECKOUT.service)
    if saved:
        await state.set_data(saved)
        await state.set_state(ProjectWorkStates.waiting_for_payment)
    return saved


async def _report_expired(message: Message, state: FSMContext, user_lang: str) -> None:
    await state.clear()
    pay.forget(message.chat.id)
    await message.answer(
        get_text(user_lang, "order_expired"), reply_markup=get_main_keyboard(user_lang)
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

@router.callback_query(F.data == CHECKOUT.pay_balance, ProjectWorkStates.waiting_for_payment)
async def pay_from_balance(callback: CallbackQuery, state: FSMContext, user_lang: str, db: Database, user):
    await callback.answer()
    data = await _order(callback.from_user.id, state)
    if not data:
        await _report_expired(callback.message, state, user_lang)
        return

    price = data.get("price", 0)
    balance = user.balance if user else 0
    if balance < price:
        # Buyurtma o'chmaydi. Balansni to'ldirish oqimi FSM ni tozalaydi,
        # shuning uchun buyurtma undan tashqarida saqlanadi.
        pay.remember(callback.from_user.id, CHECKOUT.service, data)
        await pay.send_shortfall(callback.message, CHECKOUT, user_lang, price, balance)
        return

    await _generate(callback.message, state, user_lang, db, user)


async def _generate(message: Message, state: FSMContext, user_lang: str, db: Database, user):
    data = await state.get_data()
    price = data.get("price", 0)

    await state.set_state(ProjectWorkStates.generating)
    topic = data.get("topic", "")
    doc_language = data.get("doc_language", user_lang)

    status = await message.answer(
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
            blocks=data.get("blocks") or None,
            user_id=message.chat.id,
            depth=PROJECT_WORK_DEPTH[data.get("depth_key", "standart")],
            source=material,
            progress_cb=progress,
        )
        content.author_name = data.get("author_name", "")

        await _safe_edit(status, get_text(user_lang, "pw_building", topic=topic))
        file_path = await get_document_builder().build(content)

        tables = sum(1 for section in content.sections if section.table)
        await message.answer_document(
            document=FSInputFile(file_path, filename=f"Loyiha_ishi_{topic[:30].replace(' ', '_')}.docx"),
            caption=get_text(user_lang, "pw_done", sections=len(content.sections), tables=tables),
        )
        # Stars bilan to'langan bo'lsa balansdan yechilmaydi.
        if not pay.paid_with_stars(data):
            await db.update_user_balance(user.telegram_id, -price)
        logger.info("Loyiha ishi yuborildi: %s → %s", topic[:60], user.telegram_id)

        try:
            await status.delete()
        except Exception:
            pass
        await message.answer(
            get_text(user_lang, "document_ready"), reply_markup=get_main_keyboard(user_lang)
        )
    except Exception as e:
        logger.exception("Loyiha ishi yaratishda xato: %s", e)
        await _safe_edit(status, get_text(user_lang, "pw_failed"))
        await message.answer(
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
