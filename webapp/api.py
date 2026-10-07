"""Sayt API (`/api/v1`): Telegram orqali kirish, buyurtmalar, hamyon.

Mijoz ma'lumotlari bot bilan bir xil: kirish Telegram ID bilan bo'ladi, balans esa bir xil jadvalda
turadi. Parol yo'q: brauzer bir martalik token oladi, bot uni `/start weblogin_<token>` bilan
tasdiqlaydi, brauzer so'rab turib sessiya cookie'sini oladi.
"""
import logging
import os
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
from services import web_kinds  # noqa: F401  (xizmatlarni ro'yxatga oladi)

log = logging.getLogger(__name__)

SITE_DIR = Path(__file__).parent / "site"
COOKIE = "edu_session"
_MAX_JSON = 64 * 1024

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


async def _json(request: web.Request) -> Dict:
    if request.content_length and request.content_length > _MAX_JSON:
        raise web.HTTPRequestEntityTooLarge(max_size=_MAX_JSON, actual_size=request.content_length)
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

def _catalog() -> Dict:
    from services.premium_presentation import pipeline, themes

    sizes = [5, 8, 10, 12, 15, 20, 25, 30]
    return {
        "kinds": [{"key": kind.key, "label": kind.label} for kind in web_jobs.KINDS.values()],
        "languages": [{"key": "uz", "label": "O'zbek (lotin)"}, {"key": "uz-cyrl", "label": "Ўзбек (кирилл)"},
                      {"key": "ru", "label": "Русский"}, {"key": "en", "label": "English"},
                      {"key": "kk", "label": "Қазақша"}],
        "styles": [{"key": "toza", "label": "Toza"}, {"key": "jurnal", "label": "Jurnal"},
                   {"key": "blok", "label": "Blok"}, {"key": "kontur", "label": "Kontur"},
                   {"key": "qorongu", "label": "Qorong'u"}],
        "themes": [{"key": t.key, "label": t.name, "background": "#" + t.background, "accent": "#" + t.accent,
                    "heading": "#" + t.heading} for t in themes.choices()],
        "premium_prices": [{"slides": n, "price": pipeline.price_for(n)} for n in sizes],
    }


async def catalog(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, **_catalog()})


async def quote(request: web.Request) -> web.Response:
    telegram_id = await _require(request)
    data = await _json(request)
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


# ───────────────────────────────────────────────────────────────────────── ishlar

async def jobs_create(request: web.Request) -> web.Response:
    telegram_id = await _require(request)
    if _limited(f"job:{telegram_id}", 6, 60):
        return _error("Juda tez-tez buyurtma. Bir daqiqa kuting.", 429, "rate")
    data = await _json(request)
    try:
        job = await web_jobs.submit(telegram_id, str(data.get("kind")), dict(data.get("params") or {}))
    except web_jobs.JobError as exc:
        status = 402 if exc.code == "no_balance" else 409 if exc.code == "busy" else 400
        return _error(str(exc), status, exc.code)
    user = await Database.get_user(telegram_id)
    return web.json_response({"ok": True, "job": job, "balance": int(getattr(user, "balance", 0) or 0)})


async def jobs_list(request: web.Request) -> web.Response:
    telegram_id = await _require(request)
    jobs = await web_store.list_jobs(telegram_id, 30)
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

def _page(name: str):
    async def handler(request: web.Request) -> web.StreamResponse:
        return web.FileResponse(SITE_DIR / name, headers={"Cache-Control": "no-cache"})
    return handler


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
    add("GET", "/api/v1/catalog", catalog)
    add("POST", "/api/v1/quote", quote)
    add("POST", "/api/v1/jobs", jobs_create)
    add("GET", "/api/v1/jobs", jobs_list)
    add("GET", "/api/v1/jobs/{id}", jobs_get)
    add("GET", "/api/v1/jobs/{id}/file", jobs_file)
    add("GET", "/api/v1/wallet", wallet)
    add("POST", "/api/v1/wallet/receipt", wallet_receipt)
    add("GET", "/app", _page("app.html"))
    add("GET", "/static/{name}", static_file)
