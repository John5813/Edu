"""Ommaviy do'kon: katalog, qidiruv va ko'rgazma rasmlari.

Tahrirlash Mini App'idan (server.py) farqli o'laroq bu qism oddiy
brauzerga mo'ljallangan — Telegram konteksti ham, initData ham yo'q.
Shu sababli bu yerda faqat ochiq ma'lumot beriladi: fayllarning o'zi
yopiq Telegram kanalida qoladi va ular saytdan hech qachon yuklab
olinmaydi, sotib olish botda amalga oshadi.
"""

import logging
import os
import re
from pathlib import Path

from aiohttp import web

import webapp
from config import STORE_PREVIEW_DIR

logger = logging.getLogger(__name__)

STORE_HTML = Path(__file__).parent / "store.html"

# Kod havolada keladi va ko'rgazma rasmining yo'liga qo'shiladi, shuning
# uchun u qat'iy tekshiriladi — aks holda "../" bilan katalogdan chiqib
# ketish mumkin bo'lardi.
_CODE_RE = re.compile(r"^[A-Z0-9]{8}$")
_MAX_PREVIEWS = 20
_PAGE_SIZE = 24


def _item_json(row: dict) -> dict:
    code = row["public_code"]
    return {
        "code": code,
        "title": row["title"],
        "description": row.get("description") or "",
        "category": row.get("category") or "",
        "language": row.get("language") or "uz",
        "slide_count": row.get("slide_count") or 0,
        "price": row.get("price") or 0,
        "sale_count": row.get("sale_count") or 0,
        "preview": f"/shop/preview/{code}/1.jpg",
        "preview_count": row.get("preview_count") or 0,
    }


async def handle_store_page(request: web.Request) -> web.Response:
    try:
        return web.Response(text=STORE_HTML.read_text(encoding="utf-8"),
                            content_type="text/html")
    except OSError as exc:
        logger.error("Do'kon sahifasi o'qilmadi: %s", exc)
        return web.Response(text="Do'kon vaqtincha ishlamayapti", status=503)


async def handle_items(request: web.Request) -> web.Response:
    from database.database import Database

    query = (request.query.get("q") or "").strip()[:100]
    category = (request.query.get("category") or "").strip()[:50]
    language = (request.query.get("language") or "").strip()[:10]
    sort = (request.query.get("sort") or "new").strip()
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1

    result = await Database.list_store_items(
        query=query, category=category, language=language, sort=sort,
        limit=_PAGE_SIZE, offset=(page - 1) * _PAGE_SIZE,
    )
    return web.json_response({
        "total": result["total"],
        "page": page,
        "page_size": _PAGE_SIZE,
        "items": [_item_json(row) for row in result["items"]],
    })


async def handle_item(request: web.Request) -> web.Response:
    from database.database import Database

    code = request.match_info.get("code", "")
    if not _CODE_RE.match(code):
        return web.json_response({"error": "not found"}, status=404)

    row = await Database.get_store_item(code)
    if not row:
        return web.json_response({"error": "not found"}, status=404)

    await Database.bump_store_view(code)

    data = _item_json(row)
    count = min(row.get("preview_count") or 0, _MAX_PREVIEWS)
    data["previews"] = [f"/shop/preview/{code}/{n}.jpg" for n in range(1, count + 1)]
    data["buy_url"] = (
        f"https://t.me/{webapp.BOT_USERNAME}?start=buy_{code}"
        if webapp.BOT_USERNAME else ""
    )
    return web.json_response(data)


async def handle_categories(request: web.Request) -> web.Response:
    from database.database import Database

    return web.json_response({"categories": await Database.get_store_categories()})


async def handle_preview(request: web.Request) -> web.Response:
    code = request.match_info.get("code", "")
    number = request.match_info.get("number", "")
    if not _CODE_RE.match(code) or not number.isdigit():
        return web.Response(status=404)
    if not 1 <= int(number) <= _MAX_PREVIEWS:
        return web.Response(status=404)

    base = os.path.realpath(STORE_PREVIEW_DIR)
    path = os.path.realpath(os.path.join(base, code, f"{int(number)}.jpg"))
    if not path.startswith(base + os.sep) or not os.path.exists(path):
        return web.Response(status=404)

    return web.FileResponse(path, headers={
        "Content-Type": "image/jpeg",
        "Cache-Control": "public, max-age=86400",
    })


def setup_store_routes(app: web.Application) -> None:
    """Do'kon marshrutlarini tahrirlovchi bilan bir xil ilovaga qo'shadi."""
    app.router.add_get("/shop", handle_store_page)
    app.router.add_get("/api/shop/items", handle_items)
    app.router.add_get("/api/shop/items/{code}", handle_item)
    app.router.add_get("/api/shop/categories", handle_categories)
    app.router.add_get("/shop/preview/{code}/{number}.jpg", handle_preview)
