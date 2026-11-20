"""Sayt buyurtmalari: tekshirish → to'lov → fon vazifasi → tayyor fayl.

Bot va sayt bir xil xizmatlarni chaqiradi; bu modul faqat sayt tomonidagi "buyurtma qatlami":
- har xizmat `Kind` sifatida ro'yxatga olinadi (qiymatlarni tekshirish, narx, bajarish);
- narx balansdan atomik yechiladi, xatoda to'liq qaytariladi;
- bir vaqtda ishlaydigan og'ir ishlar soni cheklangan (brauzer bilan chizish og'ir);
- tayyor fayl yopiq Telegram guruhiga (ombor, `web_archive`) yuklanadi va «Hujjatlarim» da 30 kun turadi;
  serverdagi nusxa `data/web_jobs` da (vaqtinchalik `temp/` emas — u har 30 daqiqada va qayta ishga tushganda
  tozalanadi) 3 kun turadi, keyin kerak bo'lsa ombordan qaytariladi.
"""
import asyncio
import html
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

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Doimiy papka: `temp/` dagi hamma narsa bir soatdan keyin (har 30 daqiqada va bot qayta ishga tushganda) o'chirilardi —
# saytdagi tayyor fayllar va taqdimot nusxalari ham. Shuning uchun yangilashdan keyin «Fayl topilmadi» chiqardi.
RESULTS_DIR = os.getenv("WEB_JOBS_DIR") or os.path.join(_ROOT, "data", "web_jobs")
LEGACY_RESULTS_DIR = os.path.join(_ROOT, "temp", "web_jobs")
LOCAL_CACHE_HOURS = 6        # ombordan qayta olingan nusxa serverda shuncha turadi
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

# Ishlayotgan buyurtmaning jonli tafsiloti (faqat xotirada: jarayon shu protsessda ishlaydi, server
# qayta ishga tushsa buyurtma ham to'xtaydi). Kutish animatsiyasi shundan haqiqiy reja sarlavhalarini
# va nechta slayd yozilganini oladi: {"plan": [{title, category}], "done": 3, "total": 12}.
LIVE: Dict[str, Dict] = {}


def note(job_id: str, **info) -> None:
    """Jonli tafsilotni yangilaydi; istalgan oqimdan chaqirish mumkin."""
    if job_id:
        LIVE[job_id] = {**LIVE.get(job_id, {}), **info}


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
    from database import web_accounts

    # Telegramsiz (Google bilan kirgan) akkaunt kanalga a'zo bo'la olmaydi: tekshiruv o'tkazilmaydi.
    if web_accounts.is_web_only(telegram_id):
        return
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

_STAGE_TEXT = {"queued": "Tayyorlanmoqda", "writing": "Matn yozilmoqda", "images": "Rasmlar tanlanmoqda",
               "render": "Fayl yig'ilmoqda", "done": "Tayyor", "failed": "Xato"}


def public(job: Dict) -> Dict:
    """Brauzerga beriladigan qisqa ko'rinish (fayl yo'li va ichki maydonlarsiz)."""
    status = job["status"]
    return {"id": job["id"], "kind": job["kind"], "title": job["title"], "status": status,
            "stage": job["stage"] or ("done" if status == "done" else "queued"),
            "stage_text": _STAGE_TEXT.get(job["stage"] or status, ""),
            "progress": 100 if status == "done" else int(job["progress"] or 0),
            "price": int(job["price"] or 0), "ready": status == "done" and bool(job.get("result_path") or job.get("vault_file_id")),
            "file_name": job.get("result_name") or "", "error": job.get("error") or "",
            "created_at": job["created_at"], "expires_at": web_store.expires_at(job),
            "archived": bool(job.get("vault_file_id")),
            "telegram": int(job.get("tg_sent") or 0),
            "live": LIVE.get(job["id"], {}) if status in ("queued", "running") else {}}


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
    # Muallif — faqat mijoz formada yozgan ism (Telegram profilidagi ism qo'yilmaydi: hujjat muqovasida
    # buyurtmachining profil ismi chiqib qolardi).
    raw["_default_author"] = ""
    raw["_telegram_id"] = int(telegram_id)
    params = kind.normalize(raw)
    price = int(kind.price(params))

    active = [job for job in await web_store.list_jobs(telegram_id, 10) if job["status"] in ("queued", "running")]
    if len(active) >= MAX_ACTIVE_PER_USER:
        raise JobError("Avvalgi buyurtmalaringiz tayyor bo'lishini kuting (bir vaqtda 2 tagacha).", "busy")

    job_id = uuid.uuid4().hex
    trial = bool(params.get("trial"))
    if trial:
        # Bepul sinov — har akkauntga bir marta. Band qilish atomar: ikki marta bosilsa ham bittasi o'tadi.
        from database import free_trial
        if not free_trial.SITE_ENABLED:     # saytda o'chirilgan: eski sahifadan kelsa ham pul yechilmaydi, tushuntiriladi
            raise JobError("Bepul sinov taqdimoti endi mavjud emas. Oddiy buyurtma bering.", "trial_off")
        if not await free_trial.claim(telegram_id, job_id):
            raise JobError("Bepul sinov taqdimotidan avval foydalangansiz. Endi oddiy buyurtma bering.", "trial_used")
    elif not await Database.charge_balance(telegram_id, price):
        raise JobError(f"Balans yetarli emas: {price:,} so'm kerak, sizda {int(user.balance or 0):,} so'm.".replace(",", " "),
                       "no_balance")

    try:
        await web_store.create_job(job_id, telegram_id, kind.key, kind.title(params), params, price, charged=True)
    except Exception:
        if trial:
            from database import free_trial
            await free_trial.release(telegram_id, job_id)
        else:
            await Database.update_user_balance(telegram_id, price)
        raise
    task = asyncio.get_running_loop().create_task(_execute(job_id, telegram_id, kind, params, price))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return public(await web_store.get_job(job_id))


async def _refund(job_id: str, telegram_id: int, price: int) -> None:
    """Pulni bir marta qaytaradi (`charged` bayrog'i qayta qaytarishdan saqlaydi).

    Bepul sinov buyurtmasida pul yo'q — uning o'rniga sinov imkoniyati qaytariladi.
    """
    from database import free_trial

    job = await web_store.get_job(job_id)
    if job and job["charged"]:
        await web_store.update_job(job_id, charged=0)
        if price:
            await Database.update_user_balance(telegram_id, price)
        await free_trial.release(telegram_id, job_id)


async def _run_kind(kind: Kind, params: Dict, report: Report) -> Tuple[str, str]:
    """Xizmatni bajaradi. Yangi o'zbek alifbosi ("uz-yangi"): ichkarida oddiy "uz" ishlaydi
    (model eski lotinda yozadi), tayyor matn va fayl yangi alifboga o'giriladi."""
    from services import uz_script

    if params.get("language") != uz_script.UZ_NEW_LANG:
        return await kind.run(params, report)
    token = uz_script.use(uz_script.LATIN_NEW)
    try:
        path, name = await kind.run({**params, "language": "uz",
                                     "topic": uz_script.to_latin_old(params.get("topic", ""))}, report)
        await asyncio.to_thread(uz_script.normalize_file, path, uz_script.LATIN_NEW)
        return path, name
    finally:
        uz_script.reset(token)


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
            path, name = await _run_kind(kind, {**params, "_job_id": job_id}, report)
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
            back = (f"{price:,} so'm hisobingizga qaytarildi.".replace(",", " ") if price
                    else "Bepul sinov imkoniyati sizda qoldi — qayta urinib ko'ring.")
            await web_store.update_job(job_id, status="failed", stage="failed", error=f"{message} {back}",
                                       finished_at=time.time(), params={})
            if not kind.quiet:
                await _tell_failed(telegram_id, kind, params)
        finally:
            workload.end(work_id)
            LIVE.pop(job_id, None)

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


async def start_pending(telegram_id: int) -> Optional[Dict]:
    """Balans to'lgach: to'lovni kutayotgan sayt buyurtmasini o'zi boshlaydi (mijoz saytga qaytmasa ham).

    Har qanday balans qo'shilishidan keyin chaqiriladi (Click, Payme, Uzum, chek). Xato ko'tarmaydi.
    """
    try:
        row = await web_store.get_pending(telegram_id)
        if not row or row.get("job_id"):
            return None
        kind = KINDS.get(row["kind"])
        user = await Database.get_user(telegram_id)
        if not kind or not user:
            await web_store.clear_pending(telegram_id)
            return None
        if int(user.balance or 0) < int(kind.price(kind.normalize(dict(row["params"])))):
            return None
        if not await web_store.claim_pending(telegram_id):
            return None
        try:
            job = await submit(telegram_id, row["kind"], dict(row["params"]))
        except JobError as exc:
            log.warning("Kutayotgan sayt buyurtmasi boshlanmadi (%s): %s", telegram_id, exc)
            await web_store.clear_pending(telegram_id)
            return None
        await web_store.mark_pending(telegram_id, job["id"])
        await web_store.clear_draft(telegram_id)
        log.info("To'lov tushdi — sayt buyurtmasi o'zi boshlandi: %s (%s)", job["id"], row["kind"])
        return job
    except Exception as exc:
        log.warning("Kutayotgan sayt buyurtmasini tekshirib bo'lmadi (%s): %s", telegram_id, exc)
        return None


async def _friendly(exc: Exception) -> str:
    if isinstance(exc, JobError):       # xizmatning o'zi aytgan tushunarli sabab (masalan: mos 3D topilmadi)
        return str(exc)
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
    """Tayyor faylni omborga (yopiq guruh) qo'yadi, Telegramga ham yuboradi va katalogga qo'yadi (hammasi ixtiyoriy)."""
    try:
        import webapp
        from database import web_accounts
        from services import web_archive
        bot = webapp.BOT
        file_id = ""
        job = await web_store.get_job(job_id)
        if job and web_archive.enabled():          # 30 kun saqlanadi; serverdan o'chsa ham shundan qaytadi
            file_id = await web_archive.store(job, path, name)
        if bot is None or web_accounts.is_web_only(telegram_id):
            return          # Telegramsiz akkaunt: fayl faqat saytdan yuklab olinadi
        status = await deliver_to_telegram(bot, telegram_id, kind.title(params) or name, path, name, file_id=file_id,
                                           remind=True)
        await web_store.update_job(job_id, tg_sent=status, tg_version=file_version(path) if status > 0 else "")
        if kind.key == "presentation_3d" and status > 0:      # botdagi kabi: 3D qanday ochilishi — yo'riqnoma videosi
            await _send_3d_guide(bot, telegram_id)
        if kind.publish_as and not params.get("trial"):     # bepul sinov katalogga qo'yilmaydi
            from services.store_publisher import schedule_publish
            schedule_publish(bot, path, kind.title(params), kind.publish_as,
                             customer_name=params.get("author", ""), language=params.get("language", "uz"))
    except Exception as exc:
        log.warning("Tayyor faylni Telegramga yuborib bo'lmadi (%s): %s", job_id, exc)


def file_version(path: str) -> str:
    """Fayl nusxasi belgisi: tahrirdan keyin (PPTX qayta yig'ilgach) o'zgaradi."""
    try:
        st = os.stat(path)
        return f"{st.st_size}-{st.st_mtime_ns}"
    except OSError:
        return ""


_sending: set = set()
_sent_at: Dict[str, float] = {}
DOWNLOAD_GAP = 60.0      # shu soniya ichidagi takror «Yuklab olish» — bitta yuborish (iPhone faylni bir necha so'rovda oladi)


async def send_current(job: Dict, telegram_id: int, force: bool = False) -> int:
    """Tayyor faylni mijoz botiga yuboradi (Telegram orqali kirgan bo'lsa).

    «Yuklab olish» HAR bosilganda chaqiriladi: fayl telefonga ham, Telegramga ham boradi — taqdimot tayyor bo'lganda
    avtomatik yuborilgan bo'lsa ham (mijoz uni topa olmagan yoki yana olmoqchi). Faqat bir daqiqa ichidagi takror
    so'rovlar (iPhone brauzeri faylni ochishda bir necha marta so'raydi, ikki marta bosish) bitta hisoblanadi.
    `force` («📩 Telegramga yuborish» tugmasi) bu oraliqqa qaramaydi. Qaytaradi: deliver_to_telegram holati,
    0 — yuborilmadi (Telegramsiz akkaunt yoki takror so'rov)."""
    import webapp
    from database import web_accounts
    from services import web_archive
    path = job.get("result_path") or ""
    local = bool(path) and os.path.exists(path)
    if webapp.BOT is None or web_accounts.is_web_only(telegram_id) or not (local or job.get("vault_file_id")):
        return 0
    now = time.monotonic()
    if not force and now - _sent_at.get(job["id"], -DOWNLOAD_GAP) < DOWNLOAD_GAP:
        return 0
    if job["id"] in _sending:            # hozir yuborilmoqda — ikkinchisi kerak emas
        return 0
    _sending.add(job["id"])
    _sent_at[job["id"]] = now
    try:
        name = job.get("result_name") or os.path.basename(path)
        # Ombordagi nusxa (tahrirdan keyin — yangisi yuklanadi): Telegramga serverdan qayta yuklanmaydi.
        file_id = await web_archive.ensure(job, path, name) if local else (job.get("vault_file_id") or "")
        status = await deliver_to_telegram(webapp.BOT, telegram_id, job.get("title") or name, path if local else "",
                                           name, file_id=file_id, remind=int(job.get("tg_sent") or 0) <= 0)
        await web_store.update_job(job["id"], tg_sent=status, tg_version=file_version(path) if status > 0 and local else "")
        if status < 0:
            _sent_at.pop(job["id"], None)        # yetmadi — keyingi bosishda yana urinadi
        return status
    finally:
        _sending.discard(job["id"])


TG_FILE_LIMIT = 49 * 1024 * 1024     # bot Telegramga 50 MB gacha fayl yubora oladi
DELIVERY_TRIES = 3
_pause = asyncio.sleep          # testlarda kutishsiz almashtiriladi


async def _bot_language(telegram_id: int) -> str:
    try:
        user = await Database.get_user(telegram_id)
    except Exception:
        user = None
    if user and getattr(user, "kazakh", False):
        return "kk"
    return (getattr(user, "language", "") or "uz") if user else "uz"


def _docs_button(lang: str):
    """«Saytda ochish»: bosilganda bot yangi bir martalik kirish havolasini beradi (eski xabarda ham ishlaydi)."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from translations import get_text
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=get_text(lang, "web_open_docs_btn"), callback_data="golink:docs")]])


async def deliver_to_telegram(bot, telegram_id: int, title: str, path: str, name: str, file_id: str = "",
                              remind: bool = False) -> int:
    """Faylni mijozning botiga yuboradi. Qaytaradi: 1 — fayl, 2 — katta fayl uchun havola, -1 — yetmadi.

    Fayl ostida faqat mavzu yoziladi. `remind` — birinchi yetkazishda fayldan keyin botdagi eski tizimdagi kabi
    «💡 Muhim eslatma: hujjat AI yordamida yaratilgan, o'qib chiqing va tekshiring» xabari ham boradi.

    Tarmoq xatosi yoki Telegram cheklovida bir necha marta qayta uriniladi; mijoz botni bloklagan bo'lsa
    darhol to'xtaydi (sayt buni ko'rsatadi).
    """
    from aiogram.exceptions import (TelegramBadRequest, TelegramEntityTooLarge, TelegramForbiddenError,
                                    TelegramNetworkError, TelegramRetryAfter, TelegramServerError)
    from aiogram.types import FSInputFile
    from translations import get_text

    lang = await _bot_language(telegram_id)
    # Bot xabarlari HTML rejimida: nomdagi «<», «>», «&» (masalan «C++ & Java», «x < 5») Telegram'da «can't parse
    # entities» xatosini berib, fayl umuman yetmasdi. Nom HTML uchun tozalanadi; baribir rad etilsa — formatsiz.
    title = html.escape((title or name or "")[:180], quote=False)
    local = bool(path) and os.path.exists(path)
    # Ombordagi nusxa (`file_id`) bo'lsa — u yuboriladi: serverdan qayta yuklanmaydi va hajm cheklovi yo'q.
    big = not file_id and local and os.path.getsize(path) > TG_FILE_LIMIT
    if not file_id and not local:
        return -1
    plain = {}
    for attempt in range(DELIVERY_TRIES):
        try:
            if big:
                size = round(os.path.getsize(path) / 1024 / 1024)
                await bot.send_message(telegram_id, get_text(lang, "web_file_big", title=title, size=size),
                                       reply_markup=_docs_button(lang), **plain)
                return 2
            document = file_id or FSInputFile(path, filename=name)
            await bot.send_document(telegram_id, document, caption=title or None, **plain)
            if remind:
                try:
                    await bot.send_message(telegram_id, get_text(lang, "document_reminder"), parse_mode="Markdown")
                except Exception as exc:                 # eslatma yetmasa ham fayl yetgan
                    log.info("Eslatma yuborilmadi (%s): %s", telegram_id, exc)
            return 1
        except TelegramEntityTooLarge:
            big = True
        except TelegramForbiddenError as exc:          # botni bloklagan yoki o'chirgan
            log.info("Fayl Telegramga yetmadi (bot bloklangan) %s: %s", telegram_id, exc)
            return -1
        except TelegramRetryAfter as exc:
            await _pause(min(float(exc.retry_after) + 1, 60))
        except (TelegramNetworkError, TelegramServerError) as exc:
            log.warning("Telegramga yuborishda tarmoq xatosi (%s), urinish %d: %s", telegram_id, attempt + 1, exc)
            await _pause(2 * (attempt + 1))
        except TelegramBadRequest as exc:
            if file_id and local and "parse entities" not in str(exc).lower():
                log.warning("Ombordagi nusxa yuborilmadi (%s), fayl serverdan yuboriladi: %s", telegram_id, exc)
                file_id = ""                            # yaroqsiz file_id — serverdagi nusxa bilan qayta urinish
                big = os.path.getsize(path) > TG_FILE_LIMIT
                continue
            if "too big" in str(exc).lower() or "too large" in str(exc).lower():
                big = True
                continue
            if "parse entities" in str(exc).lower() and not plain:
                log.warning("Telegram xabar formatini qabul qilmadi (%s), formatsiz yuboriladi: %s", telegram_id, exc)
                title, plain = html.unescape(title), {"parse_mode": None}
                continue
            log.warning("Telegram faylni qabul qilmadi (%s): %s", telegram_id, exc)
            return -1
    return -1


async def _send_3d_guide(bot, telegram_id: int) -> None:
    """3D taqdimot bilan birga botdagi yo'riqnoma videosi (PowerPoint'da qanday ochish); bo'lmasa — matn."""
    from aiogram.types import FSInputFile
    from bot.handlers import premium_presentation as ppt

    lang = await _bot_language(telegram_id)
    caption = ppt.med3d_note(lang)[:1024]
    video = ppt._med3d_guide_id or (FSInputFile(ppt.MED3D_GUIDE_VIDEO) if os.path.exists(ppt.MED3D_GUIDE_VIDEO) else None)
    try:
        if video is not None:
            sent = await bot.send_video(telegram_id, video=video, caption=caption, width=1080, height=1920,
                                        supports_streaming=True)
            if getattr(sent, "video", None):
                ppt._med3d_guide_id = sent.video.file_id
            return
        await bot.send_message(telegram_id, caption)
    except Exception as exc:
        log.info("3D yo'riqnoma videosi yuborilmadi (%s): %s", telegram_id, exc)


async def _tell_failed(telegram_id: int, kind: Kind, params: Dict) -> None:
    """Buyurtma bajarilmadi: mijoz saytni yopib qo'ygan bo'lsa ham bilsin (tafsilot va qaytgan pul saytda)."""
    try:
        import webapp
        from database import web_accounts
        from translations import get_text
        if webapp.BOT is None or web_accounts.is_web_only(telegram_id):
            return
        lang = await _bot_language(telegram_id)
        title = html.escape((kind.title(params) or "")[:180], quote=False)
        await webapp.BOT.send_message(telegram_id, get_text(lang, "web_job_failed", title=title),
                                      reply_markup=_docs_button(lang))
    except Exception as exc:
        log.info("Bajarilmagan buyurtma haqida Telegramga yozilmadi (%s): %s", telegram_id, exc)


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


def migrate_legacy() -> int:
    """Eski joydagi (`temp/web_jobs`) fayllarni doimiy papkaga ko'chiradi — bot ishga tushganda, temp tozalanishidan
    OLDIN. Bazadagi yo'llar ham yangilanadi (`fix_legacy_paths`)."""
    if not os.path.isdir(LEGACY_RESULTS_DIR) or os.path.abspath(LEGACY_RESULTS_DIR) == os.path.abspath(RESULTS_DIR):
        return 0
    os.makedirs(RESULTS_DIR, exist_ok=True)
    moved = 0
    for name in os.listdir(LEGACY_RESULTS_DIR):
        src, dst = os.path.join(LEGACY_RESULTS_DIR, name), os.path.join(RESULTS_DIR, name)
        if os.path.exists(dst):
            continue
        try:
            shutil.move(src, dst)
            moved += 1
        except OSError as exc:
            log.warning("Sayt fayli ko'chirilmadi (%s): %s", name, exc)
    shutil.rmtree(LEGACY_RESULTS_DIR, ignore_errors=True)
    if moved:
        log.info("Sayt fayllari doimiy papkaga ko'chirildi: %d ta", moved)
    return moved


async def fix_legacy_paths() -> None:
    """Bazadagi `temp/web_jobs/...` yo'llarini yangi papkaga almashtiradi."""
    import aiosqlite
    from database import database as _db
    old, new = os.path.abspath(LEGACY_RESULTS_DIR), os.path.abspath(RESULTS_DIR)
    if old == new:
        return
    async with aiosqlite.connect(_db.DATABASE_FILE) as conn:
        await web_store.create_tables(conn)
        await conn.execute("UPDATE web_jobs SET result_path = ? || substr(result_path, ?) WHERE result_path LIKE ?",
                           (new, len(old) + 1, old + "%"))
        await conn.commit()


async def backfill_archive(limit: int = 15) -> int:
    """Serverda turgan, lekin omborda yo'q tayyor fayllarni yopiq guruhga yuklaydi (bir martada `limit` tadan)."""
    from services import web_archive
    if not web_archive.enabled():
        return 0
    rows = await web_store._rows("SELECT * FROM web_jobs WHERE status = 'done' AND COALESCE(vault_file_id, '') = '' "
                                 "AND COALESCE(result_path, '') != '' ORDER BY created_at DESC LIMIT ?", (limit * 3,))
    done = 0
    for job in rows:
        path = job.get("result_path") or ""
        if done >= limit or not os.path.exists(path):
            continue
        if await web_archive.store(job, path):
            done += 1
            await asyncio.sleep(1.5)                   # Telegram chegarasiga urilmasin
    return done


async def purge() -> int:
    """Muddati o'tgan buyurtmalarni (omborsiz — 3 kun, omborda — 30 kun) va serverdagi eskirgan nusxalarni o'chiradi."""
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
    # Omborda turgan, 3 kundan eski ish: serverdagi nusxa (va ko'rish/tahrirlash nusxasi) o'chadi — fayl kerak bo'lsa
    # ombordan qaytariladi. Ombordan qaytarilgan nusxa yana LOCAL_CACHE_HOURS turadi.
    now = time.time()
    for row in await web_store.archived_old():
        path = row.get("result_path") or ""
        try:
            if path and os.path.exists(path) and now - os.path.getmtime(path) > LOCAL_CACHE_HOURS * 3600:
                os.remove(path)
                removed += 1
        except OSError:
            pass
        try:
            from services import web_decks
            web_decks.drop(row["id"])
        except Exception:
            pass
    # Ombor yoqilishidan oldin tayyorlangan (hali omborda yo'q) fayllar — har soatda bir nechtadan yuklanadi.
    try:
        await backfill_archive()
    except Exception as exc:
        log.warning("Eski fayllar omborga yuklanmadi: %s", exc)
    # Do'kon xaridi uchun ombordan olingan vaqtinchalik fayllar.
    try:
        for name in os.listdir(RESULTS_DIR):
            path = os.path.join(RESULTS_DIR, name)
            if name.startswith("store_") and os.path.isfile(path) and now - os.path.getmtime(path) > 3600:
                os.remove(path)
                removed += 1
    except OSError:
        pass
    return removed


async def housekeeping(interval: int = 3600) -> None:
    """Soatiga bir marta muddati o'tgan fayllarni tozalaydi."""
    try:
        await fix_legacy_paths()
    except Exception as exc:
        log.warning("Sayt fayllari yo'llari yangilanmadi: %s", exc)
    await recover()
    while True:
        try:
            await purge()
        except Exception as exc:
            log.warning("Sayt fayllarini tozalab bo'lmadi: %s", exc)
        await asyncio.sleep(interval)
