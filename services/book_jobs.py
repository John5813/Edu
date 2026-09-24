"""Kitob tarjimasini fonda, qismlarga bo'lib bajarish — bot qotmaydi, uzilsa davom etadi.

Butun kitob bir yo'la ishlanganda 226 betlik darslik 2 GB xotirali serverni
to'ldirib, botni qotirib qo'ydi — mijoz esa 95% da turgan xabarga qarab
qolaverdi. Endi:

  * rasmlarga tegilmaydi: faqat matn olinadi va natija toza Word (DOCX);
  * kitob 20 betlik qismlarga bo'linadi, har qism tarjimasi darhol diskka
    yoziladi — bot qayta ishga tushsa (yangilash, xato), ish to'xtagan
    qismidan davom etadi;
  * mijoz kutib o'tirmaydi: holat xabari yangilanib turadi, u shu orada
    botning boshqa xizmatlaridan foydalanaveradi;
  * oxirida butun tarjima bitta DOCX bo'lib keladi.

Pul buyurtmada yechiladi; ish oxirigacha yetmasa, tayyor qismi yuboriladi
va qolgan betlar ulushi hisobga qaytariladi.

Bir vaqtda bitta kitob ishlanadi — kuchsiz serverda va OpenRouter
limitlarida bir nechtasi parallel ketmasin. Qolganlari navbat kutadi.
"""

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from typing import List, Optional

from config import BOOK_PART_PAGES, TEMP_DIR
from services import book_pdf_translate as bpt
from services import workload
from translations import get_text

logger = logging.getLogger(__name__)

JOB_ROOT = os.path.join(TEMP_DIR, "book_jobs")
# Mablag' tugaganda qayta urinishlar oralig'i va soni (jami ~1 soat).
CREDIT_WAIT = 10 * 60
CREDIT_TRIES = 6
# Qism shuncha marta yiqilsa, ish to'xtatiladi.
PART_TRIES = 3
# Qismda shundan ko'p bo'lak tarjima qilinmasa — model ishlamayapti.
MAX_FAILED_SHARE = 0.3
# Shundan eski tugallanmagan ish tiklanmaydi.
JOB_MAX_AGE = 3 * 24 * 3600

_lock = asyncio.Lock()
_tasks: set = set()
_running: set = set()


# ─────────────────────────────────────────────── Ish holati (diskda)

def _job_dir(job_id: str) -> str:
    return os.path.join(JOB_ROOT, job_id)


def _save(job: dict) -> None:
    path = os.path.join(_job_dir(job["id"]), "job.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(job, handle, ensure_ascii=False)
    os.replace(tmp, path)


def create_job(*, user_id: int, chat_id: int, lang: str, pdf_path: str, file_name: str,
               target_lang: str, source_lang: str, start: int, stop: int,
               price: int, charged: int = 0) -> dict:
    """Yangi ish. Kitob fayli ish papkasiga ko'chiriladi (temp tozalanishidan
    himoyalangan joyga)."""
    job_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    folder = _job_dir(job_id)
    os.makedirs(folder, exist_ok=True)
    src = os.path.join(folder, "source.pdf")
    shutil.move(pdf_path, src)
    job = {
        "id": job_id, "user_id": user_id, "chat_id": chat_id, "lang": lang,
        "src": src, "file_name": file_name, "target_lang": target_lang,
        "source_lang": source_lang, "start": start, "stop": stop, "next": start,
        "price": int(price), "charged": int(charged), "parts": [],
        "failed": 0, "segments": 0, "created": time.time(), "status": "queued",
        "status_message": None,
    }
    _save(job)
    return job


def _load_all() -> list:
    jobs = []
    if not os.path.isdir(JOB_ROOT):
        return jobs
    for name in sorted(os.listdir(JOB_ROOT)):
        path = os.path.join(JOB_ROOT, name, "job.json")
        try:
            with open(path, encoding="utf-8") as handle:
                jobs.append(json.load(handle))
        except (OSError, ValueError):
            continue
    return jobs


def _remove(job: dict) -> None:
    shutil.rmtree(_job_dir(job["id"]), ignore_errors=True)


def pending_for(user_id: int) -> Optional[dict]:
    """Mijozning tugallanmagan kitobi (bo'lsa)."""
    for job in _load_all():
        if job["user_id"] == user_id and job["status"] in ("queued", "running"):
            return job
    return None


# ─────────────────────────────────────────────── Xabarlar

def _base_name(job: dict) -> str:
    base = os.path.splitext(job.get("file_name") or "kitob")[0]
    if base.lower().endswith(".pdf"):
        base = base[:-4]
    return base[:80] or "kitob"


async def _status(bot, job: dict, text: str) -> None:
    """Bitta holat xabarini yangilab boradi (har qismga yangi xabar emas)."""
    message_id = job.get("status_message")
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id=job["chat_id"], message_id=message_id)
            return
        except Exception as exc:
            if "not modified" in str(exc):
                return
    try:
        sent = await bot.send_message(job["chat_id"], text)
        job["status_message"] = sent.message_id
        _save(job)
    except Exception as exc:
        logger.warning("Kitob holati yuborilmadi: %s", exc)


async def _delete_status(bot, job: dict) -> None:
    if job.get("status_message"):
        try:
            await bot.delete_message(job["chat_id"], job["status_message"])
        except Exception:
            pass
        job["status_message"] = None


# ─────────────────────────────────────────────── Bitta qism

async def _translate_part(bot, job: dict, start: int, stop: int) -> dict:
    """Qism abzatslarini oladi, tarjima qiladi va diskka yozadi."""
    items = await asyncio.to_thread(bpt.extract_paragraphs, job["src"], start, stop,
                                    job["source_lang"])
    wanted = [i for i, item in enumerate(items) if item["translate"]]
    texts = [items[i]["text"] for i in wanted]
    translated: List[Optional[str]] = []
    if texts:
        credit_tries = 0
        while True:
            try:
                translated = await bpt.translate_texts(texts, job["source_lang"],
                                                       job["target_lang"])
                break
            except bpt.BookNoCredits as exc:
                credit_tries += 1
                if credit_tries == 1:
                    from bot.handlers.premium_presentation import _warn_admins_no_credits

                    await _warn_admins_no_credits(bot, f"Kitob tarjimasi: {exc}")
                    await _status(bot, job, get_text(job["lang"], "book_job_waiting_credits"))
                if credit_tries >= CREDIT_TRIES:
                    raise
                await asyncio.sleep(CREDIT_WAIT)
    failed = 0
    for index, text in zip(wanted, translated):
        if text:
            items[index]["text"] = text
        else:
            failed += 1
    if texts and failed > len(texts) * MAX_FAILED_SHARE:
        raise bpt.BookTranslateError(
            f"{start + 1}-{stop} betlarda {failed}/{len(texts)} bo'lak tarjima qilinmadi")
    path = os.path.join(_job_dir(job["id"]), f"part_{start + 1:04d}_{stop:04d}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(items, handle, ensure_ascii=False)
    return {"path": path, "failed": failed, "segments": len(texts)}


def _collect(job: dict) -> List[dict]:
    items: List[dict] = []
    for path in job["parts"]:
        with open(path, encoding="utf-8") as handle:
            items.extend(json.load(handle))
    return items


async def _deliver(bot, job: dict, partial: bool = False) -> Optional[str]:
    """Tayyor qismlarni DOCX qilib yuboradi. Fayl yo'lini qaytaradi."""
    from aiogram.types import FSInputFile

    if not job["parts"]:
        return None
    items = await asyncio.to_thread(_collect, job)
    base = _base_name(job)
    done = job["next"] - job["start"]
    total = job["stop"] - job["start"]
    suffix = f"_{job['start'] + 1}-{job['next']}" if partial else ""
    name = f"{base}_{job['target_lang']}{suffix}.docx"
    out = os.path.join(TEMP_DIR, f"book_{uuid.uuid4().hex[:8]}.docx")
    await asyncio.to_thread(bpt.build_docx, items, out)
    caption = (get_text(job["lang"], "book_partial_caption", done=done, total=total)
               if partial else get_text(job["lang"], "book_docx_caption"))
    await bot.send_document(job["chat_id"], FSInputFile(out, filename=name),
                            caption=caption, request_timeout=600)
    return out


async def _offer_services(bot, job: dict, path: str) -> None:
    """Kitob asosida referat/taqdimot taklifi — mijoz boshqa ishda bo'lmasa."""
    import webapp
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey

    from bot.keyboards import get_post_translation_keyboard
    from bot.states import BookTranslateStates

    dispatcher = webapp.DISPATCHER
    if dispatcher is None:
        return
    key = StorageKey(bot_id=bot.id, chat_id=job["chat_id"], user_id=job["user_id"])
    state = FSMContext(storage=dispatcher.storage, key=key)
    if await state.get_state() is not None:
        return
    await state.update_data(book_topic=_base_name(job)[:100], translated_path=path,
                            translated_shared=False)
    await state.set_state(BookTranslateStates.post_translation)
    await bot.send_message(job["chat_id"], get_text(job["lang"], "book_translate_post_services"),
                           reply_markup=get_post_translation_keyboard(job["lang"]))


# ─────────────────────────────────────────────── Butun ish

async def _run(bot, job: dict) -> None:
    lang = job["lang"]
    total = job["stop"] - job["start"]
    parts = -(-total // max(1, BOOK_PART_PAGES))
    failures = 0
    while job["next"] < job["stop"]:
        start = job["next"]
        stop = min(start + BOOK_PART_PAGES, job["stop"])
        number = (start - job["start"]) // BOOK_PART_PAGES + 1
        await _status(bot, job, get_text(
            lang, "book_part_status", part=number, parts=parts, first=start + 1,
            last=stop, done=start - job["start"], pages=total,
            percent=int((start - job["start"]) * 100 / max(total, 1))))
        try:
            result = await _translate_part(bot, job, start, stop)
        except bpt.BookNoCredits:
            raise
        except Exception as exc:
            failures += 1
            logger.warning("Kitob qismi %d-%d chiqmadi (%d): %s", start + 1, stop,
                           failures, exc)
            if failures >= PART_TRIES:
                raise
            await asyncio.sleep(15 * failures)
            continue
        failures = 0
        job["parts"].append(result["path"])
        job["failed"] += result["failed"]
        job["segments"] += result["segments"]
        job["next"] = stop
        _save(job)

    await _delete_status(bot, job)
    path = await _deliver(bot, job)
    if job["failed"]:
        await bot.send_message(job["chat_id"], get_text(lang, "book_pdf_partial",
                                                        failed=job["failed"]))
    await bot.send_message(job["chat_id"], get_text(lang, "book_pdf_note"))
    job["status"] = "done"
    _save(job)
    if path:
        await _offer_services(bot, job, path)


async def _refund_rest(job: dict) -> int:
    """Bajarilmagan betlar ulushini qaytaradi."""
    total = max(1, job["stop"] - job["start"])
    done = job["next"] - job["start"]
    refund = min(job["charged"], int(round(job["price"] * (total - done) / total)))
    if refund > 0:
        from database.database import Database

        await Database.update_user_balance(job["user_id"], refund)
        job["charged"] -= refund
    return refund


async def _fail(bot, job: dict, exc: Exception) -> None:
    job["status"] = "failed"
    _save(job)
    await _delete_status(bot, job)
    lang = job["lang"]
    try:
        if job["parts"]:
            await _deliver(bot, job, partial=True)
    except Exception as deliver_exc:
        logger.warning("Tayyor qism yuborilmadi: %s", deliver_exc)
    refund = await _refund_rest(job)
    _save(job)
    if isinstance(exc, bpt.BookNoCredits):
        text = get_text(lang, "book_no_credits")
    else:
        text = get_text(lang, "book_job_failed", done=job["next"] - job["start"],
                        refund=refund)
    try:
        await bot.send_message(job["chat_id"], text)
    except Exception:
        pass
    await _tell_admins(bot, job, exc, refund)


async def run(bot, job: dict) -> None:
    """Ishni navbat bilan bajaradi. Xato bo'lsa mijoz va adminlarga aytadi."""
    if job["id"] in _running:
        return
    _running.add(job["id"])
    try:
        if _lock.locked():
            await bot.send_message(job["chat_id"], get_text(job["lang"], "book_job_queued"))
        async with _lock:
            job["status"] = "running"
            _save(job)
            key = workload.begin(f"Kitob tarjimasi ({job['stop'] - job['start']} bet)")
            try:
                await _run(bot, job)
            except Exception as exc:
                logger.exception("Kitob tarjimasi to'xtadi: %s", exc)
                await _fail(bot, job, exc)
            finally:
                workload.end(key)
            if job["status"] in ("done", "failed"):
                _remove(job)
    finally:
        _running.discard(job["id"])


async def _tell_admins(bot, job: dict, exc: Exception, refund: int) -> None:
    from config import ADMIN_IDS

    text = (f"⚠️ Kitob tarjimasi to'xtadi: {job.get('file_name')}\n"
            f"Foydalanuvchi: {job['user_id']}, {job['next'] - job['start']}/"
            f"{job['stop'] - job['start']} bet tayyor, {refund:,} so'm qaytarildi.\n"
            f"Sabab: {str(exc)[:300]}")
    for admin in ADMIN_IDS:
        try:
            await bot.send_message(admin, text, parse_mode=None)
        except Exception:
            pass


def start(bot, job: dict) -> None:
    """Ishni fonda boshlaydi (handler kutib o'tirmaydi)."""
    task = asyncio.create_task(run(bot, job))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def resume_all(bot) -> None:
    """Bot qayta ishga tushganda tugallanmagan kitoblarni davom ettiradi."""
    now = time.time()
    for job in _load_all():
        if job.get("status") not in ("queued", "running"):
            _remove(job)
            continue
        if now - job.get("created", now) > JOB_MAX_AGE or not os.path.exists(job["src"]):
            logger.warning("Eskirgan kitob ishi tashlandi: %s", job["id"])
            try:
                await _fail(bot, job, RuntimeError("ish eskirdi yoki fayl yo'q"))
            except Exception:
                pass
            _remove(job)
            continue
        logger.info("Kitob tarjimasi davom ettirilmoqda: %s (%d-betdan)",
                    job["id"], job["next"] + 1)
        job["status_message"] = None
        try:
            await bot.send_message(job["chat_id"], get_text(
                job["lang"], "book_job_resumed", page=job["next"] + 1))
        except Exception:
            pass
        start(bot, job)
