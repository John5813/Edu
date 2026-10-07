"""Sayt API (`/api/v1`): Telegram orqali kirish, buyurtmalar, hamyon.

Mijoz ma'lumotlari bot bilan bir xil: kirish Telegram ID bilan bo'ladi, balans esa bir xil jadvalda
turadi. Parol yo'q: brauzer bir martalik token oladi, bot uni `/start weblogin_<token>` bilan
tasdiqlaydi, brauzer so'rab turib sessiya cookie'sini oladi.
"""
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, Optional
from urllib.parse import quote as url_quote

from aiohttp import web

import webapp
from database import web_store
from database.database import Database
from services import web_jobs
from services import web_kinds  # xizmatlarni ro'yxatga oladi

log = logging.getLogger(__name__)

SITE_DIR = Path(__file__).parent / "site"
COOKIE = "edu_session"
_MAX_JSON = 64 * 1024
_MAX_JOB_JSON = 400 * 1024       # buyurtma: mijoz manbasi (60 000 belgigacha, kirillda 2 bayt) bilan birga

_hits: Dict[str, Deque[float]] = defaultdict(deque)


def _limited(key: str, limit: int, per: float) -> bool:
    """Oddiy tezlik chegarasi: `per` soniyada `limit` tadan ko'p emas."""
    now = time.monotonic()
    queue = _hits[key]
    while queue and now - queue[0] > per:
        queue.popleft()
    if len(queue) >= limit:
        return True
    queue.append(now)
    if len(_hits) > 5000:           # xotira o'smasligi uchun eskilari tozalanadi
        for stale in [k for k, q in _hits.items() if not q or now - q[-1] > per]:
            _hits.pop(stale, None)
    return False


def _ip(request: web.Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.remote) or "?"


def _secure(request: web.Request) -> bool:
    return request.secure or request.headers.get("X-Forwarded-Proto", "") == "https"


def _error(message: str, status: int = 400, code: str = "error") -> web.Response:
    return web.json_response({"ok": False, "error": message, "code": code}, status=status)


async def _json(request: web.Request, limit: int = _MAX_JSON) -> Dict:
    if request.content_length and request.content_length > limit:
        raise web.HTTPRequestEntityTooLarge(max_size=limit, actual_size=request.content_length)
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text='{"ok": false, "error": "JSON kerak"}', content_type="application/json")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text='{"ok": false, "error": "JSON obyekt kerak"}', content_type="application/json")
    return data


@web.middleware
async def guard(request: web.Request, handler):
    """POST so'rovlar faqat shu saytdan kelsin (Origin tekshiruvi) — begona sahifa nomidan buyurtma bo'lmasin."""
    if request.method == "POST" and request.path.startswith("/api/v1/"):
        origin = request.headers.get("Origin")
        if origin:
            host = request.headers.get("X-Forwarded-Host") or request.host
            if origin.split("://", 1)[-1].rstrip("/") != host:
                return _error("Ruxsat yo'q", 403, "origin")
    return await handler(request)


async def _user_id(request: web.Request) -> Optional[int]:
    return await web_store.session_user(request.cookies.get(COOKIE, ""))


async def _require(request: web.Request) -> int:
    telegram_id = await _user_id(request)
    if telegram_id is None:
        raise web.HTTPUnauthorized(text='{"ok": false, "error": "Kirish kerak", "code": "auth"}',
                                   content_type="application/json")
    return telegram_id


# ───────────────────────────────────────────────────────────────────────── kirish

async def auth_start(request: web.Request) -> web.Response:
    if _limited("auth:" + _ip(request), 12, 60):
        return _error("Juda ko'p urinish. Bir daqiqadan keyin qayta urining.", 429, "rate")
    if not webapp.BOT_USERNAME:
        return _error("Bot hali ishga tushmoqda, birozdan keyin urining.", 503, "bot")
    token = await web_store.start_login()
    return web.json_response({"ok": True, "token": token, "expires_in": web_store.LOGIN_TTL,
                              "url": f"https://t.me/{webapp.BOT_USERNAME}?start=weblogin_{token}",
                              "bot": webapp.BOT_USERNAME})


async def auth_poll(request: web.Request) -> web.Response:
    token = request.query.get("token", "")
    if not token or len(token) > 80:
        return _error("Token yo'q")
    if _limited("poll:" + _ip(request), 120, 60):
        return _error("Juda ko'p so'rov", 429, "rate")
    session = await web_store.poll_login(token)
    if not session:
        return web.json_response({"ok": True, "status": "pending"})
    response = web.json_response({"ok": True, "status": "ok"})
    response.set_cookie(COOKIE, session, max_age=web_store.SESSION_TTL, httponly=True, samesite="Lax",
                        secure=_secure(request), path="/")
    return response


async def auth_logout(request: web.Request) -> web.Response:
    await web_store.end_session(request.cookies.get(COOKIE, ""))
    response = web.json_response({"ok": True})
    response.del_cookie(COOKIE, path="/")
    return response


async def me(request: web.Request) -> web.Response:
    telegram_id = await _user_id(request)
    if telegram_id is None:
        return web.json_response({"ok": True, "user": None})
    user = await Database.get_user(telegram_id)
    if not user:
        return web.json_response({"ok": True, "user": None, "needs_bot": True})
    return web.json_response({"ok": True, "user": {
        "id": telegram_id, "name": user.first_name or user.username or "Foydalanuvchi",
        "username": user.username or "", "balance": int(user.balance or 0), "language": user.language}})


# ──────────────────────────────────────────────────────────────────── katalog va narx

# «Sahifani o'zgartirish» da chat ostida turadigan tayyor iltimoslar (bosilsa, yuboriladi).
REWRITE_PROMPTS = [
    {"icon": "📊", "text": "Sahifani doirasimon diagrammali qilib ber"},
    {"icon": "📈", "text": "Ustunli diagramma bilan ko'rsat"},
    {"icon": "🖼", "text": "Rasm va matn qo'yib ber"},
    {"icon": "🧩", "text": "Kartochkalar ko'rinishida qilib ber"},
    {"icon": "🪜", "text": "Qadamma-qadam jarayon ko'rinishida yoz"},
    {"icon": "⚖️", "text": "Ikki ustunli taqqoslash qilib ber"},
    {"icon": "⏳", "text": "Vaqt o'qi (xronologiya) ko'rinishida yoz"},
    {"icon": "🔢", "text": "Asosiy raqamlarni yirik ko'rsat"},
    {"icon": "✨", "text": "Qisqaroq va ta'sirliroq qilib ber"},
    {"icon": "📚", "text": "Ko'proq tafsilot va misol qo'sh"},
    {"icon": "💬", "text": "Mashhur iqtibos bilan boshla"},
]


def _rewrite_price() -> int:
    from config import SLIDE_REWRITE_PRICE
    return int(SLIDE_REWRITE_PRICE)


STYLE_NOTES = {"toza": "Yengil va ixcham", "jurnal": "Klassik va nafis", "blok": "Yorqin va kuchli",
               "kontur": "Aniq va texnik", "qorongu": "Zamonaviy va jasur"}


def _catalog() -> Dict:
    from services.premium_presentation import pipeline, themes

    return {
        "bot": webapp.BOT_USERNAME or "Edufayl_bot",
        "kinds": [{"key": kind.key, "label": kind.label, "heavy": kind.heavy, "options": kind.options or {}}
                  for kind in (web_jobs.KINDS[key] for key in web_kinds.KINDS_ORDER if key in web_jobs.KINDS)],
        "languages": [{"key": "uz", "label": "O'zbek (lotin)"}, {"key": "uz-cyrl", "label": "Ўзбек (кирилл)"},
                      {"key": "ru", "label": "Русский"}, {"key": "en", "label": "English"},
                      {"key": "kk", "label": "Қазақша"}],
        "styles": [{"key": key, "label": label, "note": STYLE_NOTES[key]} for key, label in
                   (("toza", "Toza"), ("jurnal", "Jurnal"), ("blok", "Blok"), ("kontur", "Kontur"),
                    ("qorongu", "Qorong'u"))],
        "themes": [{"key": t.key, "label": t.name, "background": "#" + t.background, "accent": "#" + t.accent,
                    "heading": "#" + t.heading} for t in themes.choices()],
        "templates": [{"id": tid, "name": t["name"].get("uz", tid), "url": f"/api/template-image/{tid}"}
                      for tid, t in web_kinds._simple_templates().items()],
        # Slayd sonini mijoz o'zi belgilaydi (5–30): har son uchun narx.
        "premium_prices": [{"slides": n, "price": pipeline.price_for(n)}
                           for n in range(pipeline.MIN_SLIDES, pipeline.MAX_SLIDES + 1)],
        "rewrite": {"price": _rewrite_price(), "prompts": REWRITE_PROMPTS},
        "premium_range": {"min": pipeline.MIN_SLIDES, "max": pipeline.MAX_SLIDES, "popular": [5, 8, 10, 12, 15, 20, 25, 30]},
    }


async def catalog(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, **_catalog()})


async def quote(request: web.Request) -> web.Response:
    telegram_id = await _require(request)
    data = await _json(request, _MAX_JOB_JSON)
    kind = web_jobs.KINDS.get(str(data.get("kind")))
    if not kind:
        return _error("Bunday xizmat yo'q", 404, "unknown_kind")
    try:
        params = kind.normalize(dict(data.get("params") or {}))
    except web_jobs.JobError as exc:
        return _error(str(exc), 400, exc.code)
    user = await Database.get_user(telegram_id)
    balance = int(getattr(user, "balance", 0) or 0)
    price = int(kind.price(params))
    return web.json_response({"ok": True, "price": price, "balance": balance, "enough": balance >= price,
                              "missing": max(price - balance, 0)})


async def suggest(request: web.Request) -> web.Response:
    """Mavzuga qarab til va rang tavsiyasi (bot ham shunday tavsiya qiladi)."""
    from services.premium_presentation import themes

    data = await _json(request)
    topic = str(data.get("topic") or "").strip()[:300]
    theme = themes.suggest(topic)
    language = web_kinds.detect_language(topic) if len(topic) >= 3 else ""
    return web.json_response({"ok": True, "language": language,
                              "theme": {"key": theme.key, "label": theme.name}})


SOURCE_EXTS = (".pdf", ".docx", ".pptx")
SOURCE_MAX_BYTES = 10 * 1024 * 1024


async def source(request: web.Request) -> web.Response:
    """Mijoz manbasi: fayl (PDF/DOCX/PPTX) yoki sayt havolalari → matn (bot bilan bir xil o'qish)."""
    import tempfile

    from services import document_source
    from services.project_work import source as source_module

    telegram_id = await _require(request)
    if _limited(f"source:{telegram_id}", 8, 60):
        return _error("Juda tez-tez yuborildi. Bir daqiqa kuting.", 429, "rate")
    try:
        if (request.content_type or "").startswith("multipart/"):
            reader = await request.multipart()
            part = await reader.next()
            name = (getattr(part, "filename", "") or "").strip()
            if part is None or part.name != "file" or not name.lower().endswith(SOURCE_EXTS):
                return _error("PDF, DOCX yoki PPTX fayl yuboring.", 415, "type")
            folder = tempfile.mkdtemp(prefix="websrc_")
            path = os.path.join(folder, "source" + os.path.splitext(name.lower())[1])
            try:
                size = 0
                with open(path, "wb") as handle:
                    while True:
                        chunk = await part.read_chunk(256 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > SOURCE_MAX_BYTES:
                            return _error("Fayl 10 MB dan katta.", 413, "too_big")
                        handle.write(chunk)
                material = await source_module.from_file(path, name)
            finally:
                import shutil
                shutil.rmtree(folder, ignore_errors=True)
        else:
            data = await _json(request)
            from services.url_book_service import extract_urls_from_text, validate_url
            urls = [u for u in extract_urls_from_text(str(data.get("urls") or "")[:2000]) if validate_url(u)[0]]
            if not urls:
                return _error("To'g'ri sayt havolasini kiriting (https://...).", 400, "urls")
            material = await source_module.from_urls(urls[:5])
    except document_source.SourceTooLarge:
        return _error("Fayl 10 MB dan katta.", 413, "too_big")
    except document_source.SourceUnreadable:
        return _error("Fayldan yetarli matn o'qib bo'lmadi. Matnli PDF yoki DOCX yuboring.", 422, "unreadable")
    except web.HTTPException:
        raise
    except Exception as exc:
        log.warning("Manba o'qilmadi: %s", exc)
        return _error("Manbadan matn olib bo'lmadi. Boshqa fayl yoki havola sinab ko'ring.", 422, "source")
    return web.json_response({"ok": True, "kind": material.kind, "label": material.label,
                              "words": len(material.text.split()), "text": material.text})


# ───────────────────────────────────────────────────────────────────────── ishlar

async def jobs_create(request: web.Request) -> web.Response:
    telegram_id = await _require(request)
    if _limited(f"job:{telegram_id}", 6, 60):
        return _error("Juda tez-tez buyurtma. Bir daqiqa kuting.", 429, "rate")
    data = await _json(request, _MAX_JOB_JSON)
    try:
        job = await web_jobs.submit(telegram_id, str(data.get("kind")), dict(data.get("params") or {}))
    except web_jobs.JobError as exc:
        status = 402 if exc.code == "no_balance" else 409 if exc.code == "busy" else 400
        return _error(str(exc), status, exc.code)
    user = await Database.get_user(telegram_id)
    return web.json_response({"ok": True, "job": job, "balance": int(getattr(user, "balance", 0) or 0)})


async def jobs_list(request: web.Request) -> web.Response:
    telegram_id = await _require(request)
    jobs = [job for job in await web_store.list_jobs(telegram_id, 40) if job["kind"] != "slide_rewrite"][:30]
    return web.json_response({"ok": True, "jobs": [web_jobs.public(job) for job in jobs],
                              "ttl_hours": web_store.JOB_TTL_HOURS})


async def jobs_get(request: web.Request) -> web.Response:
    telegram_id = await _require(request)
    job = await web_store.get_job(request.match_info["id"], telegram_id)
    if not job:
        return _error("Topilmadi", 404, "not_found")
    user = await Database.get_user(telegram_id)
    return web.json_response({"ok": True, "job": web_jobs.public(job),
                              "balance": int(getattr(user, "balance", 0) or 0)})


async def jobs_file(request: web.Request) -> web.StreamResponse:
    telegram_id = await _require(request)
    job = await web_store.get_job(request.match_info["id"], telegram_id)
    path = (job or {}).get("result_path")
    if not job or job["status"] != "done" or not path or not os.path.exists(path):
        return _error("Fayl topilmadi yoki muddati o'tgan", 404, "not_found")
    name = job.get("result_name") or os.path.basename(path)
    return web.FileResponse(path, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(name)}",
        "Cache-Control": "private, no-store"})


# ───────────────────────────────────────────────── taqdimotni ko'rish va sahifani qayta yozish

async def _own_deck(request: web.Request):
    """(telegram_id, buyurtma, taqdimot) — faqat egasiga va faqat tayyor zamonaviy taqdimotga."""
    from services import web_decks

    telegram_id = await _require(request)
    job_id = request.match_info["id"]
    job = await web_store.get_job(job_id, telegram_id)
    if not job or job["kind"] not in ("premium_presentation", "simple_presentation"):
        raise web.HTTPNotFound(text='{"ok": false, "error": "Topilmadi", "code": "not_found"}',
                               content_type="application/json")
    deck = web_decks.load(job_id) if job["status"] == "done" else None
    return telegram_id, job, deck


async def _active_rewrite(telegram_id: int, parent: str) -> Optional[dict]:
    for row in await web_store.list_jobs(telegram_id, 20):
        if row["kind"] != "slide_rewrite" or row["status"] not in ("queued", "running"):
            continue
        try:
            if json.loads(row.get("params") or "{}").get("parent") == parent:
                return row
        except ValueError:
            continue
    return None


async def deck_info(request: web.Request) -> web.Response:
    from services import web_decks

    telegram_id, job, deck = await _own_deck(request)
    if not deck:
        return web.json_response({"ok": True, "available": False, "status": job["status"]})
    busy = await _active_rewrite(telegram_id, job["id"])
    return web.json_response({"ok": True, "available": True, "status": job["status"],
                              "deck": web_decks.public(job["id"], deck), "price": _rewrite_price(),
                              "busy": busy["id"] if busy else None,
                              "file_name": job.get("result_name") or "",
                              "expires_at": job["created_at"] + web_store.JOB_TTL_HOURS * 3600})


async def deck_slide(request: web.Request) -> web.StreamResponse:
    from services import web_decks

    _, job, deck = await _own_deck(request)
    try:
        number = int(request.match_info["n"])
    except ValueError:
        return web.Response(status=404)
    path = web_decks.preview_path(job["id"], number) if deck and 1 <= number <= web_decks.count(deck) else ""
    if not path or not os.path.exists(path):
        return web.Response(status=404)
    return web.FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


async def deck_rewrite(request: web.Request) -> web.Response:
    """Tanlangan sahifani AI ga qayta yozdirish (pulli: har urinish uchun SLIDE_REWRITE_PRICE)."""
    telegram_id, job, deck = await _own_deck(request)
    if not deck:
        return _error("Bu taqdimotni qayta yozib bo'lmaydi (yangi buyurtmalarda ishlaydi).", 404, "no_deck")
    if deck.get("view_only"):
        return _error("Sahifani AI ga qayta yozdirish «Zamonaviy taqdimot» da mavjud.", 400, "view_only")
    data = await _json(request)
    try:
        index = int(data.get("index")) - 1
    except (TypeError, ValueError):
        return _error("Sahifani tanlang.", 400, "bad_request")
    pages = len(deck["pages"])
    if not 0 <= index < pages:
        return _error("Bunday sahifa yo'q.", 400, "bad_request")
    if index == 1 and pages > 3:
        return _error("Reja sahifasi boshqa sahifalar sarlavhalaridan o'zi yig'iladi. "
                      "Kerakli sahifani o'zgartiring — reja o'zi yangilanadi.", 400, "plan_slide")
    if _limited(f"rewrite:{telegram_id}", 10, 60):
        return _error("Juda tez-tez yuborildi. Bir daqiqa kuting.", 429, "rate")
    if await _active_rewrite(telegram_id, job["id"]):
        return _error("Avvalgi o'zgartirish tugashini kuting.", 409, "busy")
    try:
        row = await web_jobs.submit(telegram_id, "slide_rewrite", {
            "parent": job["id"], "index": index, "instruction": str(data.get("instruction") or "")})
    except web_jobs.JobError as exc:
        status = 402 if exc.code == "no_balance" else 409 if exc.code == "busy" else 400
        return _error(str(exc), status, exc.code)
    user = await Database.get_user(telegram_id)
    return web.json_response({"ok": True, "job": row, "balance": int(getattr(user, "balance", 0) or 0)})


# ──────────────────────────────────────────────────────────────────────── hamyon

async def wallet(request: web.Request) -> web.Response:
    from services.receipts import web as receipt_web

    telegram_id = await _require(request)
    user = await Database.get_user(telegram_id)
    if not user:
        return _error("Avval botda /start bosing.", 409, "no_user")
    history = await Database.get_recent_payments(user.id, 10)
    return web.json_response({
        "ok": True, "balance": int(user.balance or 0), "methods": receipt_web.methods(),
        "presets": list(receipt_web.PRESETS), "min": receipt_web.MIN_AMOUNT, "max": receipt_web.MAX_AMOUNT,
        "history": [{"id": row["id"], "amount": int(row["amount"] or 0), "status": row["status"],
                     "created_at": str(row["created_at"])[:16]} for row in history]})


async def wallet_receipt(request: web.Request) -> web.Response:
    """Chek yuklash: multipart (amount, file). Bot bilan bir xil tekshiruv, natija darhol qaytadi."""
    from services.receipts import web as receipt_web

    telegram_id = await _require(request)
    if _limited(f"receipt:{telegram_id}", 5, 60):
        return _error("Juda tez-tez yuborildi. Bir daqiqa kuting.", 429, "rate")
    if webapp.BOT is None:
        return _error("Bot hali ishga tushmoqda, birozdan keyin urining.", 503, "bot")
    amount, started, data, filename, mime = None, "", b"", "", ""
    try:
        reader = await request.multipart()
        async for part in reader:
            if part.name == "file":
                filename, mime = part.filename or "", part.headers.get("Content-Type", "")
                chunks, size = [], 0
                while True:
                    chunk = await part.read_chunk(256 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > receipt_web.MAX_FILE:
                        return _error("Fayl 12 MB dan katta.", 413, "too_big")
                    chunks.append(chunk)
                data = b"".join(chunks)
            elif part.name in ("amount", "started"):
                value = (await part.text())[:40]
                if part.name == "amount":
                    amount = value
                else:
                    started = value
    except Exception:
        return _error("Forma noto'g'ri yuborildi.", 400, "bad_form")
    try:
        result = await receipt_web.submit(webapp.BOT, telegram_id, amount, started, data, filename, mime)
    except ValueError as exc:
        return _error(str(exc), 400, "invalid")
    user = await Database.get_user(telegram_id)
    return web.json_response({"ok": True, **result, "balance": int(getattr(user, "balance", 0) or 0)})


# ──────────────────────────────────────────────────────────────────────── sahifalar

_ASSET = re.compile(r'(/static/[\w.-]+\.(?:js|css|jpg|png))(?=["\'])')


def _asset_tag(name: str) -> str:
    """Fayl o'zgarganda o'zgaradigan belgi (yangilangandan keyin brauzer/CDN eski faylni ushlab turmasin)."""
    try:
        return format((SITE_DIR / "static" / name).stat().st_mtime_ns // 1000, "x")
    except OSError:
        return "0"


def versioned_html(name: str) -> str:
    """Sahifadagi /static/... havolalariga `?v=<belgi>` qo'shadi."""
    text = (SITE_DIR / name).read_text(encoding="utf-8")
    return _ASSET.sub(lambda m: f"{m.group(1)}?v={_asset_tag(m.group(1).rsplit('/', 1)[1])}", text)


def site_page(name: str) -> web.Response:
    return web.Response(text=versioned_html(name), content_type="text/html", charset="utf-8",
                        headers={"Cache-Control": "no-cache"})


def _page(name: str):
    async def handler(request: web.Request) -> web.StreamResponse:
        return site_page(name)
    return handler


_COMMIT = ""


def _commit() -> str:
    """Ishlab turgan kodning commit raqami (yangilash bajarilganini tekshirish uchun)."""
    global _COMMIT
    if not _COMMIT:
        import subprocess
        try:
            _COMMIT = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(SITE_DIR.parent.parent),
                                     capture_output=True, text=True, timeout=5).stdout.strip() or "noma'lum"
        except Exception:
            _COMMIT = "noma'lum"
    return _COMMIT


async def version(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "commit": _commit(), "app_js": _asset_tag("app.js"),
                              "site_css": _asset_tag("site.css")}, headers={"Cache-Control": "no-store"})


async def static_file(request: web.Request) -> web.StreamResponse:
    base = SITE_DIR.resolve()
    path = (SITE_DIR / "static" / request.match_info["name"]).resolve()
    if base not in path.parents or not path.is_file():
        return web.Response(status=404)
    return web.FileResponse(path, headers={"Cache-Control": "public, max-age=300"})


def setup_api_routes(app: web.Application) -> None:
    app.middlewares.append(guard)
    add = app.router.add_route
    add("POST", "/api/v1/auth/start", auth_start)
    add("GET", "/api/v1/auth/poll", auth_poll)
    add("POST", "/api/v1/auth/logout", auth_logout)
    add("GET", "/api/v1/me", me)
    add("GET", "/api/v1/version", version)
    add("GET", "/api/v1/catalog", catalog)
    add("POST", "/api/v1/quote", quote)
    add("POST", "/api/v1/suggest", suggest)
    add("POST", "/api/v1/source", source)
    add("POST", "/api/v1/jobs", jobs_create)
    add("GET", "/api/v1/jobs", jobs_list)
    add("GET", "/api/v1/jobs/{id}", jobs_get)
    add("GET", "/api/v1/jobs/{id}/file", jobs_file)
    add("GET", "/api/v1/jobs/{id}/deck", deck_info)
    add("GET", "/api/v1/jobs/{id}/slide/{n}", deck_slide)
    add("POST", "/api/v1/jobs/{id}/rewrite", deck_rewrite)
    add("GET", "/api/v1/wallet", wallet)
    add("POST", "/api/v1/wallet/receipt", wallet_receipt)
    add("GET", "/app", _page("app.html"))
    add("GET", "/static/{name}", static_file)
