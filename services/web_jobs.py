"""Sayt buyurtmalari: tekshirish → to'lov → fon vazifasi → tayyor fayl.

Bot va sayt bir xil xizmatlarni chaqiradi; bu modul faqat sayt tomonidagi "buyurtma qatlami":
- har xizmat `Kind` sifatida ro'yxatga olinadi (qiymatlarni tekshirish, narx, bajarish);
- narx balansdan atomik yechiladi, xatoda to'liq qaytariladi;
- bir vaqtda ishlaydigan og'ir ishlar soni cheklangan (brauzer bilan chizish og'ir);
- tayyor fayl `JOB_TTL_HOURS` soatdan keyin o'chadi (maxfiylik: hujjatlar saqlanmaydi).
"""
import asyncio
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from database import web_store
from database.database import Database

log = logging.getLogger(__name__)

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp", "web_jobs")
CONCURRENCY = max(1, int(os.getenv("WEB_JOBS_CONCURRENCY", "2")))
MAX_ACTIVE_PER_USER = 2

_semaphore: Optional[asyncio.Semaphore] = None
_tasks: set = set()


class JobError(Exception):
    """Mijozga ko'rsatiladigan xato (noto'g'ri qiymat, balans yetmaydi ...)."""

    def __init__(self, message: str, code: str = "bad_request"):
        super().__init__(message)
        self.code = code


# Bajaruvchi: (params, report) -> (fayl yo'li, fayl nomi). `report(stage, progress)` har safar chaqirilishi mumkin.
Report = Callable[[str, int], None]
Runner = Callable[[Dict, Report], Awaitable[Tuple[str, str]]]


@dataclass
class Kind:
    key: str
    label: str
    normalize: Callable[[Dict], Dict]
    price: Callable[[Dict], int]
    title: Callable[[Dict], str]
    run: Runner
    publish_as: str = ""          # do'kon katalogi uchun ish turi ("" — qo'yilmaydi)
    heavy: bool = False           # katta hujjat: botdagi umumiy navbatda birin-ketin bajariladi
    options: Optional[Dict] = None  # sahifadagi forma uchun: hajmlar, qo'shimchalar, maydonlar
    quiet: bool = False           # yordamchi ish (masalan sahifani qayta yozish): Telegramga yuborilmaydi, statistikaga kirmaydi


KINDS: Dict[str, Kind] = {}


def register(kind: Kind) -> Kind:
    KINDS[kind.key] = kind
    return kind


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(CONCURRENCY)
    return _semaphore


# Majburiy kanallar: botdagi kabi saytda ham buyurtma berishdan oldin tekshiriladi (60 soniya keshlanadi).
_subscribed: Dict[int, float] = {}

STAT_TYPE = {"premium_presentation": "presentation", "simple_presentation": "presentation",
             "article": "maqola", "thesis": "tezis"}


async def _require_subscription(telegram_id: int) -> None:
    import webapp

    if _subscribed.get(telegram_id, 0) > time.time() or webapp.BOT is None:
        return
    try:
        channels = await Database.get_active_channels()
        if not channels:
            return
        from services.channel_service import ChannelService

        if await ChannelService(webapp.BOT).check_user_subscription(telegram_id, channels):
            _subscribed[telegram_id] = time.time() + 60
            return
    except Exception as exc:          # tekshiruv ishlamasa mijoz to'sib qo'yilmaydi (botdagi qoida)
        log.warning("Kanal obunasini tekshirib bo'lmadi: %s", exc)
        return
    names = ", ".join(("@" + c.channel_username.lstrip("@")) if c.channel_username else c.title for c in channels)
    raise JobError(f"Avval majburiy kanallarga a'zo bo'ling: {names}. Keyin shu yerda qayta urining.", "subscribe")


# ─────────────────────────────────────────────────────────────── ommaviy ko'rinish

_STAGE_TEXT = {"queued": "Navbatda", "writing": "Matn yozilmoqda", "images": "Rasmlar tanlanmoqda",
               "render": "Fayl yig'ilmoqda", "done": "Tayyor", "failed": "Xato"}


def public(job: Dict) -> Dict:
    """Brauzerga beriladigan qisqa ko'rinish (fayl yo'li va ichki maydonlarsiz)."""
    status = job["status"]
    return {"id": job["id"], "kind": job["kind"], "title": job["title"], "status": status,
            "stage": job["stage"] or ("done" if status == "done" else "queued"),
            "stage_text": _STAGE_TEXT.get(job["stage"] or status, ""),
            "progress": 100 if status == "done" else int(job["progress"] or 0),
            "price": int(job["price"] or 0), "ready": status == "done" and bool(job.get("result_path")),
            "file_name": job.get("result_name") or "", "error": job.get("error") or "",
            "created_at": job["created_at"], "expires_at": job["created_at"] + web_store.JOB_TTL_HOURS * 3600}


# ───────────────────────────────────────────────────────────────────────── buyurtma

async def submit(telegram_id: int, kind_key: str, raw: Dict) -> Dict:
    kind = KINDS.get(kind_key)
    if not kind:
        raise JobError("Bunday xizmat yo'q", "unknown_kind")
    user = await Database.get_user(telegram_id)
    if not user:
        raise JobError("Avval botda /start bosing, so'ng saytga qayta kiring.", "no_user")
    await _require_subscription(telegram_id)
    raw = dict(raw or {})
    raw["_default_author"] = (user.first_name or "")[:80]
    raw["_telegram_id"] = int(telegram_id)
    params = kind.normalize(raw)
    price = int(kind.price(params))

    active = [job for job in await web_store.list_jobs(telegram_id, 10) if job["status"] in ("queued", "running")]
    if len(active) >= MAX_ACTIVE_PER_USER:
        raise JobError("Avvalgi buyurtmalaringiz tayyor bo'lishini kuting (bir vaqtda 2 tagacha).", "busy")
    if not await Database.charge_balance(telegram_id, price):
        raise JobError(f"Balans yetarli emas: {price:,} so'm kerak, sizda {int(user.balance or 0):,} so'm.".replace(",", " "),
                       "no_balance")

    job_id = uuid.uuid4().hex
    try:
        await web_store.create_job(job_id, telegram_id, kind.key, kind.title(params), params, price, charged=True)
    except Exception:
        await Database.update_user_balance(telegram_id, price)
        raise
    task = asyncio.get_running_loop().create_task(_execute(job_id, telegram_id, kind, params, price))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return public(await web_store.get_job(job_id))


async def _refund(job_id: str, telegram_id: int, price: int) -> None:
    """Pulni bir marta qaytaradi (`charged` bayrog'i qayta qaytarishdan saqlaydi)."""
    job = await web_store.get_job(job_id)
    if job and job["charged"]:
        await web_store.update_job(job_id, charged=0)
        await Database.update_user_balance(telegram_id, price)


async def _execute(job_id: str, telegram_id: int, kind: Kind, params: Dict, price: int) -> None:
    from services import workload

    loop = asyncio.get_running_loop()
    outcome: Dict = {}

    def report(stage: str, progress: int) -> None:
        """Istalgan oqimdan chaqirish mumkin."""
        fut = asyncio.run_coroutine_threadsafe(
            web_store.update_job(job_id, stage=stage, progress=max(0, min(int(progress), 99))), loop)
        fut.add_done_callback(lambda f: f.exception())

    async def core() -> None:
        work_id = workload.begin(f"sayt: {kind.key}")
        try:
            await web_store.update_job(job_id, status="running", stage="writing", progress=3)
            path, name = await kind.run({**params, "_job_id": job_id}, report)
            os.makedirs(RESULTS_DIR, exist_ok=True)
            stored = os.path.join(RESULTS_DIR, f"{job_id}{os.path.splitext(path)[1]}")
            shutil.move(path, stored)
            await web_store.update_job(job_id, status="done", stage="done", progress=100, result_path=stored,
                                       result_name=name, finished_at=time.time(), params={})
            outcome.update(path=stored, name=name)
        except asyncio.CancelledError:
            await _refund(job_id, telegram_id, price)
            await web_store.update_job(job_id, status="failed", stage="failed",
                                       error="Bekor qilindi, pul qaytarildi.", finished_at=time.time(), params={})
            raise
        except Exception as exc:
            log.exception("Sayt buyurtmasi bajarilmadi (%s): %s", kind.key, exc)
            message = await _friendly(exc)
            await _refund(job_id, telegram_id, price)
            await web_store.update_job(job_id, status="failed", stage="failed",
                                       error=f"{message} {price:,} so'm hisobingizga qaytarildi.".replace(",", " "),
                                       finished_at=time.time(), params={})
        finally:
            workload.end(work_id)

    if kind.heavy:
        # Katta hujjatlar botdagi bilan BIR navbatda: server xotirasi bir vaqtda faqat bittasiga yetadi.
        from bot.queue_service import HeavyDocTask, get_doc_queue

        done = asyncio.Event()
        task = HeavyDocTask(task_id=f"web-{job_id}", coro_factory=core, user_telegram_id=telegram_id,
                            chat_id=telegram_id, lang="uz", doc_type=kind.key, topic=params.get("topic", ""),
                            bot=None, done_event=done)
        position = await get_doc_queue().enqueue(task)
        await web_store.update_job(job_id, stage="queued", progress=1 if position > 1 else 2)
        await done.wait()
    else:
        async with _get_semaphore():
            await core()
    if outcome and not kind.quiet:
        try:    # admin statistikasiga shaxsiy ma'lumotsiz qator (faqat tur va vaqt)
            await Database.record_document_stat(STAT_TYPE.get(kind.key, kind.key))
        except Exception as exc:
            log.debug("Statistika yozilmadi: %s", exc)
        await _after_done(job_id, telegram_id, kind, params, outcome["path"], outcome["name"])


async def _friendly(exc: Exception) -> str:
    try:
        from services.premium_presentation.llm_client import NoCredits
        if isinstance(exc, NoCredits):
            await _warn_admins(str(exc))
            return "Xizmat vaqtincha ishlamayapti, admin xabardor qilindi."
    except Exception:
        pass
    return f"Xatolik yuz berdi: {str(exc)[:200]}."


async def _warn_admins(detail: str) -> None:
    try:
        import webapp
        from bot.handlers.premium_presentation import _warn_admins_no_credits
        if webapp.BOT is not None:
            await _warn_admins_no_credits(webapp.BOT, detail)
    except Exception:
        log.debug("Adminga ogohlantirish yuborilmadi", exc_info=True)


async def _after_done(job_id: str, telegram_id: int, kind: Kind, params: Dict, path: str, name: str) -> None:
    """Tayyor faylni Telegramga ham yuboradi va katalogga qo'yadi (ikkalasi ham ixtiyoriy)."""
    try:
        import webapp
        bot = webapp.BOT
        if bot is None:
            return
        from aiogram.types import FSInputFile

        await bot.send_document(telegram_id, FSInputFile(path, filename=name),
                                caption="✅ Saytda buyurtma qilingan fayl tayyor.")
        if kind.publish_as:
            from services.store_publisher import schedule_publish
            schedule_publish(bot, path, kind.title(params), kind.publish_as,
                             customer_name=params.get("author", ""), language=params.get("language", "uz"))
    except Exception as exc:
        log.warning("Tayyor faylni Telegramga yuborib bo'lmadi (%s): %s", job_id, exc)


# ───────────────────────────────────────────────────────── ishga tushish va tozalash

async def recover() -> int:
    """Qayta ishga tushgandan keyin: yarim qolgan ishlar muvaffaqiyatsiz bo'ladi, pul qaytariladi."""
    stuck = await web_store.unfinished_jobs()
    for job in stuck:
        await _refund(job["id"], job["telegram_id"], int(job["price"] or 0))
        await web_store.update_job(job["id"], status="failed", stage="failed", finished_at=time.time(),
                                   error="Server qayta ishga tushdi. Pul hisobingizga qaytarildi.", params={})
    if stuck:
        log.info("Sayt: %d ta yarim qolgan buyurtma qaytarildi", len(stuck))
    return len(stuck)


async def purge() -> int:
    paths = await web_store.purge_expired()
    try:
        from services import web_decks
        await web_decks.purge_orphans()
    except Exception as exc:
        log.warning("Taqdimot nusxalarini tozalab bo'lmadi: %s", exc)
    removed = 0
    for path in paths:
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed


async def housekeeping(interval: int = 3600) -> None:
    """Soatiga bir marta muddati o'tgan fayllarni tozalaydi."""
    await recover()
    while True:
        try:
            await purge()
        except Exception as exc:
            log.warning("Sayt fayllarini tozalab bo'lmadi: %s", exc)
        await asyncio.sleep(interval)
