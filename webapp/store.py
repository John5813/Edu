"""Ommaviy do'kon: katalog, qidiruv va ko'rgazma rasmlari.

Tahrirlash Mini App'idan (server.py) farqli o'laroq bu qism oddiy
brauzerga mo'ljallangan — Telegram konteksti ham, initData ham yo'q.
Shu sababli bu yerda faqat ochiq ma'lumot beriladi: fayllarning o'zi
yopiq Telegram kanalida qoladi va ular saytdan hech qachon yuklab
olinmaydi, sotib olish botda amalga oshadi.
"""

import html
import json
import logging
import os
import re
from pathlib import Path

from aiohttp import web

import webapp
from config import STORE_PREVIEW_DIR, STORE_PREVIEW_MAX

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
STORE_HTML = _HERE / "store.html"
ITEM_HTML = _HERE / "store_item.html"
STORE_CSS = _HERE / "store.css"

# Kod havolada keladi va ko'rgazma rasmining yo'liga qo'shiladi, shuning
# uchun u qat'iy tekshiriladi — aks holda "../" bilan katalogdan chiqib
# ketish mumkin bo'lardi.
_CODE_RE = re.compile(r"^[A-Z0-9]{8}$")
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
        "file_type": row.get("file_type") or "pptx",
        "price": row.get("price") or 0,
        "sale_count": row.get("sale_count") or 0,
        "preview": f"/shop/preview/{code}/thumb.jpg",
        "preview_count": row.get("preview_count") or 0,
    }


_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")


def _bot_url(payload: str = "") -> str:
    """Botga havola. Nom hali olinmagan bo'lsa bo'sh satr."""
    name = webapp.BOT_USERNAME or ""
    if not _USERNAME_RE.match(name):
        return ""
    return f"https://t.me/{name}" + (f"?start={payload}" if payload else "")


def _origin(request: web.Request) -> str:
    """Sayt manzili. Qidiruv tizimlari uchun havolalar to'liq bo'lishi kerak.

    Proksi ortida `request.url` sxemasi http bo'lib qoladi, shuning uchun
    haqiqiy sxema sarlavhadan olinadi.
    """
    scheme = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip()
    host = request.headers.get("X-Forwarded-Host", "").split(",")[0].strip()
    host = host or request.headers.get("Host", "") or webapp.WEBAPP_DOMAIN
    # Proksi sarlavhasi bo'lmasa — ulanishning o'z sxemasi. Ilgari bu yerda
    # "localhost bo'lmasa https" deb taxmin qilinardi: domensiz, IP orqali
    # ochilgan saytda hamma havola ishlamaydigan https ga ketardi.
    return f"{scheme or request.scheme}://{host}" if host else ""


async def handle_style(request: web.Request) -> web.Response:
    return web.FileResponse(STORE_CSS, headers={
        "Content-Type": "text/css; charset=utf-8",
        "Cache-Control": "public, max-age=3600",
    })


async def handle_store_page(request: web.Request) -> web.Response:
    try:
        page = STORE_HTML.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Do'kon sahifasi o'qilmadi: %s", exc)
        return web.Response(text="Do'kon vaqtincha ishlamayapti", status=503)
    # Botga havola sahifaga darhol kerak ("Yangi yaratish" tugmasi), shuning
    # uchun u alohida so'rovsiz, HTML ichiga qo'yib yuboriladi.
    page = page.replace("__BOT_URL__", html.escape(_bot_url(), quote=True))
    page = page.replace("{{CANONICAL}}", html.escape(_origin(request) + "/shop", quote=True))
    return web.Response(text=page, content_type="text/html")


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
        # Aniq moslik topilmay, yaqin mavzular qaytarilgani — sahifa buni
        # tashrifchiga aytishi kerak.
        "fuzzy": result.get("fuzzy", False),
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
    count = min(row.get("preview_count") or 0, STORE_PREVIEW_MAX)
    data["previews"] = [f"/shop/preview/{code}/{n}.jpg" for n in range(1, count + 1)]
    data["buy_url"] = _bot_url(f"buy_{code}")
    return web.json_response(data)


def _money(value: int) -> str:
    return f"{value or 0:,}".replace(",", " ") + " so'm"


def _summary(row: dict) -> str:
    """Qidiruv natijasida ko'rinadigan qisqa tavsif."""
    parts = [row["title"]]
    if row.get("description"):
        parts.append(row["description"])
    if row.get("slide_count"):
        unit = "varaq" if (row.get("file_type") or "pptx") == "docx" else "slayd"
        parts.append(f"{row['slide_count']} {unit}.")
    parts.append("Tayyor ish — darhol yuklab olish mumkin.")
    return " ".join(parts)[:300]


async def handle_item_page(request: web.Request) -> web.Response:
    """Har bir ishning o'z manzili — Google shu sahifani indekslaydi."""
    from database.database import Database

    code = request.match_info.get("code", "")
    if not _CODE_RE.match(code):
        raise web.HTTPNotFound(text="Topilmadi")

    row = await Database.get_store_item(code)
    if not row:
        raise web.HTTPNotFound(text="Bu ish topilmadi")
    await Database.bump_store_view(code)

    origin = _origin(request)
    canonical = f"{origin}/shop/{code}"
    count = min(row.get("preview_count") or 0, STORE_PREVIEW_MAX)
    shots = [f"/shop/preview/{code}/{n}.jpg" for n in range(1, count + 1)]
    if not shots:
        shots = [f"/shop/preview/{code}/thumb.jpg"]

    esc = lambda value: html.escape(str(value or ""), quote=True)
    title, category = row["title"], row.get("category") or ""
    summary = _summary(row)

    # Taqdimotda slayd, Word hujjatida varaq sanaladi.
    unit = "varaq" if (row.get("file_type") or "pptx") == "docx" else "slayd"
    facts = []
    if row.get("slide_count"):
        facts.append(f'<span class="tag">{row["slide_count"]} {unit}</span>')
    if category:
        facts.append(f'<a class="tag" href="/shop?category={esc(category)}">{esc(category)}</a>')
    facts.append(f'<span class="tag">{esc((row.get("language") or "uz").upper())}</span>')
    facts.append(f'<span class="tag">Kod: {esc(code)}</span>')

    crumbs = ['<a href="/shop">Katalog</a>']
    if category:
        crumbs.append(f'<a href="/shop?category={esc(category)}">{esc(category)}</a>')
    crumbs.append(esc(title))

    buy_url = _bot_url(f"buy_{code}")
    buy = (f'<a class="buy" href="{esc(buy_url)}" target="_blank" rel="noopener">'
           f'Botda sotib olish</a>') if buy_url else \
          '<div class="note">Sotib olish vaqtincha ishlamayapti.</div>'

    create_url = _bot_url()
    create_top = (f'<a class="create" href="{esc(create_url)}" target="_blank" '
                  f'rel="noopener">+ Yangi yaratish</a>') if create_url else ""

    slides = "\n".join(
        f'<figure><img src="{esc(src)}" alt="{esc(title)} — {n}-{unit}" '
        f'loading="lazy" width="1000"><figcaption>{n}-{unit}</figcaption></figure>'
        for n, src in enumerate(shots, start=1)
    )

    jsonld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "description": summary,
        "sku": code,
        "image": [origin + s for s in shots[:6]],
        "offers": {
            "@type": "Offer",
            "price": str(row.get("price") or 0),
            "priceCurrency": "UZS",
            "availability": "https://schema.org/InStock",
            "url": canonical,
        },
    }
    if category:
        jsonld["category"] = category

    try:
        template = ITEM_HTML.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Ish sahifasi o'qilmadi: %s", exc)
        return web.Response(text="Sahifa vaqtincha ishlamayapti", status=503)

    description_block = (f'<p class="item-desc">{esc(row["description"])}</p>'
                         if row.get("description") else "")
    note = (f"Ishning barcha {len(shots)} ta varag'i shu yerda — rasmlarda shtamp bor. "
            f"Shtampsiz, tahrirlash mumkin bo'lgan PPTX fayl to'lovdan so'ng "
            f"botda yuboriladi.")

    values = {
        "{{TITLE}}": esc(title),
        "{{META_DESC}}": esc(summary),
        "{{CANONICAL}}": esc(canonical),
        "{{OG_IMAGE}}": esc(origin + shots[0]),
        # `</script>` JSON matni ichida uchrasa sahifani buzardi.
        "{{JSONLD}}": json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/"),
        "{{CRUMBS}}": " / ".join(crumbs),
        "{{DESC_BLOCK}}": description_block,
        "{{FACTS}}": "".join(facts),
        "{{PRICE}}": esc(_money(row.get("price"))),
        "{{BUY}}": buy,
        "{{CREATE_TOP}}": create_top,
        "{{NOTE}}": esc(note),
        "{{SLIDES}}": slides,
    }
    for token, value in values.items():
        template = template.replace(token, value)
    return web.Response(text=template, content_type="text/html")


async def handle_robots(request: web.Request) -> web.Response:
    origin = _origin(request)
    lines = [
        "User-agent: *",
        "Allow: /shop",
        # Tahrirlovchi shaxsiy hujjatlar bilan ishlaydi — indekslanmasin.
        "Disallow: /edit",
        "Disallow: /api/",
        "",
        f"Sitemap: {origin}/sitemap.xml" if origin else "",
    ]
    return web.Response(text="\n".join(filter(None, lines)) + "\n",
                        content_type="text/plain")


async def handle_sitemap(request: web.Request) -> web.Response:
    from database.database import Database

    origin = _origin(request)
    rows = await Database.all_store_codes()
    urls = [f"  <url><loc>{html.escape(origin)}/shop</loc></url>"]
    for row in rows:
        loc = f"{html.escape(origin)}/shop/{row['code']}"
        stamp = (row.get("created_at") or "")[:10]
        lastmod = f"<lastmod>{stamp}</lastmod>" if len(stamp) == 10 else ""
        urls.append(f"  <url><loc>{loc}</loc>{lastmod}</url>")

    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")
    return web.Response(text=body, content_type="application/xml")


async def handle_categories(request: web.Request) -> web.Response:
    from database.database import Database

    return web.json_response({"categories": await Database.get_store_categories()})


async def handle_preview(request: web.Request) -> web.Response:
    code = request.match_info.get("code", "")
    name = request.match_info.get("name", "")
    if not _CODE_RE.match(code):
        return web.Response(status=404)
    if name == "thumb":
        file_name = "thumb.jpg"
    elif name.isdigit() and 1 <= int(name) <= STORE_PREVIEW_MAX:
        file_name = f"{int(name)}.jpg"
    else:
        return web.Response(status=404)

    base = os.path.realpath(STORE_PREVIEW_DIR)
    path = os.path.realpath(os.path.join(base, code, file_name))
    if not path.startswith(base + os.sep) or not os.path.exists(path):
        return web.Response(status=404)

    return web.FileResponse(path, headers={
        "Content-Type": "image/jpeg",
        "Cache-Control": "public, max-age=86400",
    })


def setup_store_routes(app: web.Application) -> None:
    """Do'kon marshrutlarini tahrirlovchi bilan bir xil ilovaga qo'shadi."""
    app.router.add_get("/shop", handle_store_page)
    # Aniq yo'llar `/shop/{code}` dan oldin turishi shart: u ham bitta
    # bo'lakni ushlaydi va "style.css" ni o'ziga tortib ketardi.
    app.router.add_get("/shop/style.css", handle_style)
    app.router.add_get("/shop/preview/{code}/{name}.jpg", handle_preview)
    app.router.add_get("/shop/{code}", handle_item_page)
    app.router.add_get("/robots.txt", handle_robots)
    app.router.add_get("/sitemap.xml", handle_sitemap)
    app.router.add_get("/api/shop/items", handle_items)
    app.router.add_get("/api/shop/items/{code}", handle_item)
    app.router.add_get("/api/shop/categories", handle_categories)
