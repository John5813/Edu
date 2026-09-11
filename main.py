import asyncio
import glob
import io
import logging
import os
import signal
import time
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent, BufferedInputFile

# Load environment variables from .env file
load_dotenv()
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import start, documents, payments, admin, settings, samples, media
from bot.handlers import converter
from bot.handlers import pptx_converter
from bot.handlers import book_translate
from bot.handlers import test as test_handler
from bot.handlers import premium_presentation as premium_presentation_handler
from bot.handlers import project_work
from bot.middlewares import LanguageMiddleware, DatabaseMiddleware
from database.database import init_db
from config import ADMIN_IDS, BOT_TOKEN, DOCUMENTS_DIR, TEMP_DIR
import webapp
from webapp.server import start_web_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# temp/ ichida qoladigan yagona fayl — u ish vaqtidagi holat, axlat emas.
_TEMP_KEEP = {"doc_tokens.json"}
# Bir soat: eng uzun generatsiya ham bundan qisqa, shuning uchun faol ishni
# buzmaydi, lekin tashlandiq fayl uzoq yotib qolmaydi.
_TEMP_MAX_AGE = 3600
# Bo'yalgan ikonka keshi foydali (qayta bo'yash shart bo'lmaydi), lekin
# cheksiz emas: mavzu ranglari har taqdimotda boshqacha bo'lgani uchun
# kombinatsiyalar soni chegaralanmasa fayl soni o'sib ketadi.
_ICON_CACHE_MAX = 400


def _remove(path: str) -> bool:
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def _prune_temp(now: float) -> int:
    """temp/ dagi eskirgan fayllarni va bo'shab qolgan kataloglarni o'chiradi.

    Eski versiya faqat `temp/*.png` kabi yuza shablonlarni ko'rardi, shuning
    uchun kichik kataloglar (qa_*, code_run_*) va .pptx/.docx fayllari
    umuman tozalanmasdan yig'ilib borardi.
    """
    temp_dir = TEMP_DIR
    icon_dir = os.path.join(temp_dir, "icons")
    removed = 0

    for root, dirs, files in os.walk(temp_dir, topdown=False):
        if os.path.abspath(root) == os.path.abspath(icon_dir):
            continue  # kesh alohida qoidalar bilan boshqariladi
        for name in files:
            if name in _TEMP_KEEP:
                continue
            path = os.path.join(root, name)
            try:
                if now - os.path.getmtime(path) < _TEMP_MAX_AGE:
                    continue
            except OSError:
                continue
            removed += _remove(path)

        if os.path.abspath(root) == os.path.abspath(temp_dir):
            continue
        try:
            if not os.listdir(root):
                os.rmdir(root)
        except OSError:
            pass

    return removed


def _prune_icon_cache() -> int:
    """Ikonka keshini eng yaqinda ishlatilgan fayllar bilan cheklaydi."""
    icon_dir = os.path.join(TEMP_DIR, "icons")
    try:
        entries = [os.path.join(icon_dir, n) for n in os.listdir(icon_dir)]
    except OSError:
        return 0
    if len(entries) <= _ICON_CACHE_MAX:
        return 0

    try:
        entries.sort(key=os.path.getmtime, reverse=True)
    except OSError:
        return 0
    return sum(_remove(path) for path in entries[_ICON_CACHE_MAX:])


def cleanup_temp_files() -> int:
    """Eskirgan vaqtinchalik fayllar va tashlandiq hujjatlarni o'chiradi.

    - temp/ : bir soatdan eski hamma narsa, kataloglar ichi bilan birga
    - temp/icons/ : kesh, eng yangi _ICON_CACHE_MAX tasi qoladi
    - hujjatlar : 25 soatdan eski yetimlar (token 24 soatda tugaydi)
    """
    removed = 0
    now = time.time()

    removed += _prune_temp(now)
    removed += _prune_icon_cache()

    # Katalog nomi konfigdan olinadi. Ilgari bu yerda "documents/" yozilgan
    # edi, holbuki fayllar "generated_documents/" ga yoziladi — shu sababli
    # yetim hujjatlar hech qachon o'chirilmagan.
    doc_cutoff = now - 90000  # 25 soat
    for extension in ("docx", "pptx", "pdf", "xlsx"):
        for path in glob.glob(os.path.join(DOCUMENTS_DIR, f"*.{extension}")):
            try:
                if os.path.getmtime(path) < doc_cutoff:
                    removed += _remove(path)
            except OSError:
                pass

    if removed:
        logger.info(f"Temp cleanup: removed {removed} old file(s)")
    return removed


async def generate_daily_excel(date_str: str) -> bytes:
    """Generate Excel file of users who registered on date_str (YYYY-MM-DD)."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from database.database import DATABASE_FILE
    import aiosqlite

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Yangi foydalanuvchilar"

    # Header style
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2E86C1")
    headers = ["№", "Telegram ID", "Ism", "Username", "Til", "Balans (so'm)", "Ro'yxatdan o'tgan vaqt"]
    col_widths = [5, 15, 20, 20, 6, 15, 22]

    for col_idx, (header, width) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = width

    ws.row_dimensions[1].height = 20

    # Fetch users
    async with aiosqlite.connect(DATABASE_FILE) as db_conn:
        db_conn.row_factory = aiosqlite.Row
        async with db_conn.execute(
            "SELECT telegram_id, first_name, username, language, balance, created_at "
            "FROM users WHERE date(created_at) = ? ORDER BY created_at",
            (date_str,)
        ) as cursor:
            rows = await cursor.fetchall()

    even_fill = PatternFill("solid", fgColor="EBF5FB")
    for row_idx, row in enumerate(rows, 2):
        username = f"@{row['username']}" if row['username'] else "—"
        created = row['created_at'] or ""
        # Trim microseconds if present
        if "." in created:
            created = created[:19]
        values = [
            row_idx - 1,
            row['telegram_id'],
            row['first_name'] or "—",
            username,
            (row['language'] or "uz").upper(),
            row['balance'] or 0,
            created,
        ]
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.alignment = Alignment(horizontal="left", vertical="center")
            if row_idx % 2 == 0:
                cell.fill = even_fill

    # Summary row
    summary_row = len(rows) + 2
    ws.cell(row=summary_row, column=1, value="Jami:").font = Font(bold=True)
    ws.cell(row=summary_row, column=2, value=len(rows)).font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


async def daily_user_report(bot: Bot):
    """Every day at 23:55 Uzbekistan time (18:55 UTC) send new-user Excel to admins."""
    UZT_OFFSET = timedelta(hours=5)
    REPORT_HOUR = 23
    REPORT_MINUTE = 55

    while True:
        # Current time in Uzbekistan (UTC+5)
        now_uzt = datetime.now(timezone.utc).replace(tzinfo=None) + UZT_OFFSET
        target = now_uzt.replace(hour=REPORT_HOUR, minute=REPORT_MINUTE, second=0, microsecond=0)
        if now_uzt >= target:
            # Already past today's target — schedule for tomorrow
            target += timedelta(days=1)
        wait_seconds = (target - now_uzt).total_seconds()
        logger.info(f"Daily report scheduled in {wait_seconds/3600:.1f}h (at {target.strftime('%H:%M')} UZT)")
        await asyncio.sleep(wait_seconds)

        # Generate report for today
        now_uzt = datetime.now(timezone.utc).replace(tzinfo=None) + UZT_OFFSET
        report_date = now_uzt.strftime("%Y-%m-%d")
        display_date = now_uzt.strftime("%d.%m.%Y")
        try:
            excel_bytes = await generate_daily_excel(report_date)
        except Exception as exc:
            logger.error(f"Daily Excel generation failed: {exc}", exc_info=True)
            await asyncio.sleep(60)
            continue

        filename = f"yangi_foydalanuvchilar_{report_date}.xlsx"
        caption = (
            f"📊 <b>Kunlik hisobot — {display_date}</b>\n\n"
            f"Bugun ro'yxatdan o'tgan foydalanuvchilar ro'yxati."
        )
        from config import ADMIN_IDS
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_document(
                    chat_id=admin_id,
                    document=BufferedInputFile(excel_bytes, filename=filename),
                    caption=caption,
                    parse_mode="HTML",
                )
            except Exception as send_exc:
                logger.warning(f"Could not send daily report to admin {admin_id}: {send_exc}")

        # Wait a bit to avoid double-send if sleep wakes slightly early
        await asyncio.sleep(120)


async def periodic_cleanup(interval_seconds: int = 1800, storage=None):
    """Run cleanup every interval_seconds (default 30 min).

    Note: The FSM storage is NOT periodically wiped anymore. The previous
    behaviour cleared every active user's state every 4 hours, which abruptly
    interrupted users mid-conversation. /start already calls state.clear(),
    which is enough to recover any stuck user.
    """
    _ = storage  # kept for signature compatibility
    while True:
        await asyncio.sleep(interval_seconds)
        cleanup_temp_files()
        # Bir soatdan oshgan to'lanmagan buyurtmalar bot xotirasida qolmasin.
        try:
            from bot import checkout
            dropped = checkout.purge_expired()
            if dropped:
                logger.info("Eskirgan %s ta to'lanmagan buyurtma o'chirildi", dropped)
        except Exception:
            pass
        # Release matplotlib global figure registry
        try:
            import matplotlib.pyplot as plt
            plt.close("all")
        except Exception:
            pass
        # Force Python GC
        try:
            import gc
            gc.collect()
        except Exception:
            pass
        # Return freed memory pages back to OS (Linux glibc only)
        try:
            import ctypes
            ctypes.cdll.LoadLibrary("libc.so.6").malloc_trim(0)
        except Exception:
            pass
        logger.info("Periodic memory cleanup done (plt.close('all') + gc.collect())")


# Pullik oqimlar og'ir modullarni faqat buyurtma kelganda import qiladi —
# bu botni tez ishga tushirish uchun qilingan. Salbiy tomoni: kutubxona
# yetishmasa, buni birinchi bo'lib TO'LOV QILGAN mijoz biladi. Premium
# taqdimot aynan shu sababdan "No module named 'requests'" bilan to'xtadi.
# Shuning uchun import zanjiri ishga tushishda bir marta tekshiriladi.
_LAZY_MODULES = (
    "services.premium_presentation.pipeline",
    "services.premium_presentation.renderer",
    "services.project_work.builder",
    "services.document_service",
    "services.together_service",
)


def check_lazy_imports() -> list[str]:
    """Buyurtma paytida kerak bo'ladigan modullarni oldindan tekshiradi."""
    import importlib

    broken = []
    for name in _LAZY_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:
            broken.append(f"{name}: {type(exc).__name__}: {exc}")
    return broken


async def main():
    """Main function to start the bot"""
    broken = check_lazy_imports()
    if broken:
        logger.error(
            "DIQQAT: quyidagi modullar yuklanmadi — ularga bog'liq xizmatlar "
            "buyurtma paytida xato beradi. Kutubxonalarni o'rnating: "
            "venv/bin/pip install -r requirements.txt"
        )
        for line in broken:
            logger.error("   %s", line)

    # Initialize database
    await init_db()

    # Set Mini App domain from environment
    webapp.WEBAPP_DOMAIN = os.environ.get("REPLIT_DEV_DOMAIN", "localhost:5000")

    # Restore tokens saved before last restart
    webapp.load_tokens_from_disk()

    # Initialize bot and dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher(storage=MemoryStorage())

    # ── Global error handler ───────────────────────────────────────────────────
    # Catches TelegramBadRequest (expired/invalid callback query IDs) and other
    # Telegram API errors BEFORE they bubble up through the dispatcher and create
    # a tight CPU-burning retry loop.  Without this, every stale inline-button
    # click causes an unhandled exception that aiogram keeps re-propagating,
    # pegging the CPU at ~100%.
    @dp.errors()
    async def global_error_handler(event: ErrorEvent) -> bool:
        exception = event.exception
        exc_name = type(exception).__name__
        exc_msg = str(exception)

        # Silently drop expired / invalid callback query errors.
        # These happen when a user clicks an inline button that is older than
        # Telegram's 48-hour callback-query lifetime.
        stale_callback_phrases = (
            "query is too old",
            "query ID is invalid",
            "MESSAGE_ID_INVALID",
            "message to edit not found",
            "message is not modified",
            "message can't be edited",
        )
        if any(phrase in exc_msg for phrase in stale_callback_phrases):
            logger.debug(f"Ignored stale callback error [{exc_name}]: {exc_msg[:120]}")
            # Try to silently answer the callback so Telegram stops showing
            # the loading spinner on the user's device.
            update = event.update
            if update and update.callback_query:
                try:
                    await update.callback_query.answer()
                except Exception:
                    pass
            return True  # mark as handled — do NOT re-raise

        # Drop "bot was blocked / kicked" errors silently (common with broadcasts)
        blocked_phrases = (
            "bot was blocked by the user",
            "user is deactivated",
            "chat not found",
            "bot was kicked",
            "Forbidden",
        )
        if any(phrase in exc_msg for phrase in blocked_phrases):
            logger.debug(f"Ignored blocked-user error [{exc_name}]: {exc_msg[:120]}")
            return True

        # Drop network / flood-control errors that resolve on their own
        transient_phrases = (
            "Too Many Requests",
            "retry_after",
            "FLOOD_WAIT",
            "Connection",
            "TimeoutError",
            "ServerDisconnectedError",
        )
        if any(phrase in exc_msg for phrase in transient_phrases):
            logger.warning(f"Transient Telegram error [{exc_name}]: {exc_msg[:120]}")
            return True

        # All other errors: log them with full traceback but do NOT crash the bot
        logger.error(
            f"Unhandled error in update handler [{exc_name}]: {exc_msg[:300]}",
            exc_info=exception,
        )
        return True  # returning True prevents aiogram from re-raising

    # Register middlewares
    dp.message.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())
    dp.pre_checkout_query.middleware(DatabaseMiddleware())
    dp.message.middleware(LanguageMiddleware())
    dp.callback_query.middleware(LanguageMiddleware())
    dp.pre_checkout_query.middleware(LanguageMiddleware())
    
    # Block check middleware - must be last to check after database is injected
    from bot.middlewares import BlockedUserMiddleware
    dp.message.middleware(BlockedUserMiddleware())
    dp.callback_query.middleware(BlockedUserMiddleware())
    
    # Register handlers - important order: specific handlers first, catch-all last!
    dp.include_router(admin.router)  # Admin commands first
    dp.include_router(settings.router)  # Handle settings buttons
    dp.include_router(converter.router)  # Handle PDF → DOCX conversion (before payments to keep state-specific callbacks)
    dp.include_router(pptx_converter.router)  # Handle PPTX → PDF conversion
    # Premium presentation must precede the generic successful_payment handler,
    # otherwise Stars payments are credited as balance instead of starting the deck.
    dp.include_router(premium_presentation_handler.router)  # Premium taqdimot — Ustalar tizimi
    # Xizmat uchun qilingan Stars to'lovi payments.py dagi umumiy handlerga
    # tushib, balansga yozilib ketmasligi uchun bu undan oldin turadi.
    dp.include_router(project_work.router)  # Loyiha ishi — client picks field and source
    dp.include_router(payments.router)  # Handle payment buttons
    dp.include_router(samples.router)  # Handle samples view and admin management
    dp.include_router(media.router)   # Legacy media router (empty)
    dp.include_router(book_translate.router)  # Handle book translation service
    dp.include_router(test_handler.router)  # Handle test generation service
    dp.include_router(documents.router)  # Handles document creation and topic input - MUST BE BEFORE start.router
    dp.include_router(start.router)  # LAST - has catch-all handler for unknown messages
    
    # Share bot instance with web server for sending files
    webapp.BOT = bot

    # Clean up old temp files left from previous runs
    cleanup_temp_files()

    # Delete any existing webhook before starting polling
    # drop_pending_updates=True ensures stale callback queries accumulated
    # while the bot was offline do NOT flood the handler on startup.
    await bot.delete_webhook(drop_pending_updates=True)

    # Start the heavy-document generation queue (single worker).
    # Heavy docs (kurs ishi, diplom ishi, dissertatsiya, bitiruv ishi) are
    # serialised here so only ONE big generation runs at a time, preventing
    # OOM spikes on the production server.
    from bot.queue_service import get_doc_queue
    get_doc_queue().start()

    # Start both bot and web server concurrently
    logger.info("Bot started")
    logger.info(f"Mini App domain: {webapp.WEBAPP_DOMAIN}")

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received, stopping bot...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    polling_task = asyncio.create_task(dp.start_polling(bot))
    web_task     = asyncio.create_task(start_web_server(port=5000))
    cleanup_task = asyncio.create_task(periodic_cleanup(storage=dp.storage))
    report_task  = asyncio.create_task(daily_user_report(bot))

    try:
        await stop_event.wait()
    finally:
        logger.info("Cancelling tasks...")
        for task in (polling_task, web_task, cleanup_task, report_task):
            task.cancel()
        await asyncio.gather(polling_task, web_task, cleanup_task, report_task, return_exceptions=True)

        await bot.session.close()
        from services.ai_service import close_ai_service
        from services.together_service import close_together_service
        await close_ai_service()
        await close_together_service()
        logger.info("Bot stopped cleanly")

if __name__ == "__main__":
    asyncio.run(main())
