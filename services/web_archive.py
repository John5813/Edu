"""Saytdagi tayyor fayllar ombori: yopiq Telegram guruhi (do'kon uchun ishlatiladigan o'sha `STORE_VAULT_CHAT_ID`).

Nega: fayl serverda faqat 3 kun turadi, server qayta ishga tushganda yoki disk tozalanganda yo'qolishi mumkin edi.
Endi tayyor fayl bir marta yopiq guruhga yuklanadi va `file_id` bazada saqlanadi:

- «Hujjatlarim» da 30 kun turadi (`web_store.ARCHIVE_TTL_HOURS`), serverdagi nusxa esa 3 kundan keyin o'chadi;
- mijozning botiga yuborish `file_id` bilan — serverdan qayta yuklanmaydi (hostga yuk yo'q);
- saytdan yuklab olishda nusxa serverda bo'lmasa — ombordan olinadi (Telegram bot 20 MB gacha faylni qaytaradi;
  kattaroq fayl Telegram orqali beriladi);
- tahrirdan keyin (fayl o'zgargach) yangi nusxa yuklanadi.

Guruh `WEB_ARCHIVE_CHAT_ID` bilan alohida ko'rsatilishi mumkin; bo'lmasa do'kon ombori ishlatiladi. Ikkalasi ham
bo'lmasa — ombor o'chiq, fayl avvalgidek faqat serverda (3 kun).
"""
import logging
import os
from typing import Dict, Optional

log = logging.getLogger(__name__)

UPLOAD_LIMIT = 49 * 1024 * 1024        # bot 50 MB gacha fayl yubora oladi
FETCH_LIMIT = 20 * 1024 * 1024         # bot 20 MB gacha faylni qaytarib ola oladi


def chat_id() -> str:
    import config
    return (os.getenv("WEB_ARCHIVE_CHAT_ID") or getattr(config, "STORE_VAULT_CHAT_ID", "") or "").strip()


def enabled() -> bool:
    return bool(chat_id())


def _bot():
    import webapp
    return webapp.BOT


def current(job: Dict, path: str) -> str:
    """Ombordagi nusxa serverdagi fayl bilan bir xil bo'lsa — uning `file_id` si, aks holda ""."""
    from services.web_jobs import file_version
    file_id = job.get("vault_file_id") or ""
    if not file_id:
        return ""
    if path and os.path.exists(path) and (job.get("vault_version") or "") != file_version(path):
        return ""                               # fayl tahrirlangan — ombordagi eski
    return file_id


async def store(job: Dict, path: str, name: str = "") -> str:
    """Faylni yopiq guruhga yuklaydi, `file_id` ni buyurtmaga yozadi. Xato bo'lsa — "" (ish to'xtamaydi)."""
    from aiogram.types import FSInputFile

    from database import web_store
    from services.web_jobs import file_version

    bot, chat = _bot(), chat_id()
    if bot is None or not chat or not path or not os.path.exists(path):
        return ""
    if os.path.getsize(path) > UPLOAD_LIMIT:
        log.info("Ombor: fayl 50 MB dan katta, yuklanmadi (%s)", job.get("id"))
        return ""
    name = name or job.get("result_name") or os.path.basename(path)
    caption = f"🗂 Sayt · {str(job.get('id', ''))[:8]} · {job.get('title') or name}"[:1000]
    version = file_version(path)
    try:
        sent = await bot.send_document(chat, FSInputFile(path, filename=name), caption=caption,
                                       parse_mode=None, disable_notification=True)
    except Exception as exc:
        log.warning("Ombor: fayl yopiq guruhga yuklanmadi (%s): %s", job.get("id"), exc)
        return ""
    file_id = getattr(getattr(sent, "document", None), "file_id", "") or ""
    if file_id:
        await web_store.update_job(job["id"], vault_file_id=file_id, vault_version=version)
        job["vault_file_id"], job["vault_version"] = file_id, version
    return file_id


async def ensure(job: Dict, path: str, name: str = "") -> str:
    """Ombordagi nusxa dolzarb bo'lsa — uning `file_id`, aks holda (yangi yoki tahrirlangan) — yuklab qaytaradi."""
    file_id = current(job, path)
    if file_id or not enabled():
        return file_id
    return await store(job, path, name)


async def fetch(job: Dict, dest: str) -> bool:
    """Serverda nusxa yo'q: ombordan `dest` ga olib keladi. 20 MB dan katta yoki xato — False."""
    bot, file_id = _bot(), job.get("vault_file_id") or ""
    if bot is None or not file_id:
        return False
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".part"
    try:
        info = await bot.get_file(file_id)
        if (getattr(info, "file_size", 0) or 0) > FETCH_LIMIT:
            return False
        await bot.download_file(info.file_path, destination=tmp)
        os.replace(tmp, dest)
        # Qaytarilgan nusxa ombordagi bilan aynan bir xil: belgisi yangilanadi, aks holda u «tahrirlangan» deb
        # hisoblanib, har yuklab olishda omborga qayta yuklanardi.
        from database import web_store
        from services.web_jobs import file_version
        version = file_version(dest)
        await web_store.update_job(job["id"], vault_version=version)
        job["vault_version"] = version
        return True
    except Exception as exc:
        log.warning("Ombor: fayl qaytarib olinmadi (%s): %s", job.get("id"), exc)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False

