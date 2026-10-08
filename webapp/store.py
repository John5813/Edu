"""Ommaviy do'kon: katalog, qidiruv va ko'rgazma rasmlari.

Tahrirlash Mini App'idan (server.py) farqli o'laroq bu qism oddiy
brauzerga mo'ljallangan — Telegram konteksti ham, initData ham yo'q.
Shu sababli bu yerda faqat ochiq ma'lumot beriladi: fayllarning o'zi
yopiq Telegram kanalida qoladi va ular saytdan hech qachon yuklab
olinmaydi, sotib olish botda amalga oshadi.
"""

import hashlib
import html
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlencode

from aiohttp import web

import webapp
from config import STORE_PREVIEW_DIR, STORE_PREVIEW_MAX

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
STORE_HTML = _HERE / "store.html"
ITEM_HTML = _HERE / "store_item.html"
STORE_CSS = _HERE / "store.css"


def _with_style_version(page: str) -> str:
    """Uslub havolasiga fayl mazmunidan olingan belgi qo'shadi.

    style.css bir soat keshlanadi; belgisiz havolada yangilangan dizayn
    mijozga bir soatgacha ko'rinmasdi. Fayl o'zgarsa havola ham o'zgaradi
    va brauzer yangisini darhol yuklaydi.
    """
    try:
        version = hashlib.sha1(STORE_CSS.read_bytes()).hexdigest()[:10]
    except OSError:
        return page
    return page.replace('href="/shop/style.css"', f'href="/shop/style.css?v={version}"')

# Kod havolada keladi va ko'rgazma rasmining yo'liga qo'shiladi, shuning
# uchun u qat'iy tekshiriladi — aks holda "../" bilan katalogdan chiqib
# ketish mumkin bo'lardi.
_CODE_RE = re.compile(r"^[A-Z0-9]{8}$")
_PAGE_SIZE = 24


def _item_json(row: dict) -> dict:
    from config import work_label

    code = row["public_code"]
    return {
        "code": code,
        "title": row["title"],
        "description": row.get("description") or "",
        "category": row.get("category") or "",
        "work_type": row.get("work_type") or "",
        "work_label": work_label(row.get("work_type") or ""),
        "language": row.get("language") or "uz",
        "slide_count": row.get("slide_count") or 0,
        "file_type": row.get("file_type") or "pptx",
        "price": row.get("price") or 0,
        "sale_count": row.get("sale_count") or 0,
        "preview": _image_path(row),
        "preview_count": row.get("preview_count") or 0,
        "url": _item_path(row),
    }


def _slug(row: dict) -> str:
    from services.store_seo import item_slug

    return item_slug(row.get("title") or "", row.get("work_type") or "")


def _item_path(row: dict) -> str:
    """Ish manzili: kod + mavzu nomi (/shop/AB12CD34/iqtisodiyot-asoslari-kurs-ishi)."""
    return f"/shop/{row['public_code']}/{_slug(row)}"


def _image_path(row: dict, number: int = 0) -> str:
    """Ko'rgazma rasmining nomli manzili; 0 — katalogdagi kichik rasm.

    Google Rasmlar fayl nomini ham o'qiydi: `iqtisodiyot-taqdimot-3.jpg` "3.jpg" dan yaxshi topiladi.
    """
    # Kichik rasm "-kichik" bilan: mavzu raqam bilan tugasa ("Matematika 9") u varaq raqami deb o'qilmasin.
    return f"/shop/img/{row['public_code']}/{_slug(row)}-{number or 'kichik'}.jpg"


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


async def handle_items(request: web.Request) -> web.Response:
    from database.database import Database

    query = (request.query.get("q") or "").strip()[:100]
    category = (request.query.get("category") or "").strip()[:50]
    work_type = (request.query.get("type") or "").strip()[:50]
    language = (request.query.get("language") or "").strip()[:10]
    sort = (request.query.get("sort") or "new").strip()
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1

    result = await Database.list_store_items(
        query=query, category=category, work_type=work_type, language=language,
        sort=sort, limit=_PAGE_SIZE, offset=(page - 1) * _PAGE_SIZE,
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
    data["previews"] = [_image_path(row, n) for n in range(1, count + 1)]
    # Ko'rgazmada faqat boshlanishi bor; qolgani son bo'lib beriladi.
    data["hidden_pages"] = max((row.get("slide_count") or count) - count, 0)
    data["buy_url"] = _bot_url(f"buy_{code}")
    return web.json_response(data)


def _money(value: int) -> str:
    return f"{value or 0:,}".replace(",", " ") + " so'm"


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _json_ld(data) -> str:
    # `</script>` JSON matni ichida uchrasa sahifani buzardi.
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _unit(row: dict) -> str:
    """Taqdimotda slayd, Word hujjatida varaq sanaladi."""
    return "varaq" if (row.get("file_type") or "pptx") == "docx" else "slayd"


def _cut(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:—- ") + "…"


_LANG_NAMES = {"uz": "o'zbek", "ru": "rus", "en": "ingliz", "kk": "qozoq"}
_APPS = {"pptx": "PowerPoint", "docx": "Word"}

# Ko'rgazma rasmining o'lchami (sahifa yuklanayotganda joy oldindan ajratilsin — Google buni baholaydi).
_DIMS: dict = {}


def _preview_file(code: str, number: int = 0) -> str:
    """Ko'rgazma rasmi fayli (0 — kichik rasm); bo'lmasa bo'sh satr."""
    name = f"{number}.jpg" if number else "thumb.jpg"
    base = os.path.realpath(STORE_PREVIEW_DIR)
    path = os.path.realpath(os.path.join(base, code, name))
    return path if path.startswith(base + os.sep) and os.path.exists(path) else ""


def _dims(path: str) -> tuple:
    try:
        stamp = (path, os.path.getmtime(path))
        if stamp not in _DIMS:
            from PIL import Image

            with Image.open(path) as image:
                _DIMS[stamp] = image.size
            if len(_DIMS) > 5000:
                _DIMS.clear()
        return _DIMS[stamp]
    except Exception:
        return (0, 0)


def _summary(row: dict, outline: list) -> str:
    """Qidiruv natijasida ko'rinadigan qisqa tavsif (meta description)."""
    from config import work_label

    kind = (work_label(row.get("work_type") or "") or "ish").lower()
    head = f"«{row['title']}» mavzusida tayyor {kind}"
    if row.get("slide_count"):
        head += f": {row['slide_count']} {_unit(row)}, {(row.get('file_type') or 'pptx').upper()}"
    parts = [head + "."]
    if row.get("description"):
        parts.append(row["description"])
    if outline:
        parts.append("Reja: " + "; ".join(outline[:4]) + ".")
    parts.append("Ko'rgazmani bepul ko'ring va yuklab oling.")
    return _cut(" ".join(parts), 300)


def _card(row: dict, lazy: bool = True) -> str:
    """Katalog kartochkasi (server tomonda — qidiruv tizimi havolalarni JavaScriptsiz ko'rsin)."""
    from config import work_label

    label = work_label(row.get("work_type") or "")
    tags = []
    if row.get("slide_count"):
        tags.append(f'<span class="tag">{row["slide_count"]} {_unit(row)}</span>')
    if row.get("category"):
        tags.append(f'<span class="tag">{_esc(row["category"])}</span>')
    alt = f"{row['title']} — {label.lower()}" if label else row["title"]
    lazy_attr = ' loading="lazy"' if lazy else ""
    return (f'<a class="card" href="{_esc(_item_path(row))}">'
            f'<img class="thumb" src="{_esc(_image_path(row))}" alt="{_esc(alt)}"'
            f'{lazy_attr} width="480" height="270">'
            f'<div class="card-b">'
            + (f'<div class="card-kind">{_esc(label)}</div>' if label else "")
            + f'<div class="card-t">{_esc(row["title"])}</div>'
            f'<div class="card-m">{"".join(tags)}</div>'
            f'<div class="price">{_esc(_money(row.get("price")))}</div></div></a>')


def _breadcrumb_ld(origin: str, crumbs: list) -> dict:
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": n, "name": name, "item": origin + path}
        for n, (name, path) in enumerate(crumbs, start=1)]}


async def _category_slugs(work_type: str = "") -> dict:
    """Fan nomining manzildagi ko'rinishi → fan nomi."""
    from database.database import Database
    from services.store_seo import slugify

    return {slugify(c["name"]): c["name"] for c in await Database.get_store_categories(work_type)
            if slugify(c["name"])}


def _catalog_path(work_type: str = "", category: str = "") -> str:
    from services.store_seo import slugify, type_slug

    if work_type and category:
        return f"/shop/tur/{type_slug(work_type)}/{slugify(category)}"
    if work_type:
        return f"/shop/tur/{type_slug(work_type)}"
    if category:
        return f"/shop/fan/{slugify(category)}"
    return "/shop"


# ───────────────────────────────────────────────────────────── ish sahifasi

async def handle_item_redirect(request: web.Request) -> web.Response:
    """Eski qisqa manzil (/shop/KOD) — nomli manzilga doimiy yo'naltiriladi."""
    from database.database import Database

    code = request.match_info.get("code", "")
    if not _CODE_RE.match(code):
        raise web.HTTPNotFound(text="Topilmadi")
    row = await Database.get_store_item(code)
    if not row:
        raise web.HTTPNotFound(text="Bu ish topilmadi")
    raise web.HTTPMovedPermanently(_item_path(row))


async def handle_item_page(request: web.Request) -> web.Response:
    """Har bir ishning o'z manzili — Google shu sahifani indekslaydi."""
    from config import work_label
    from database.database import Database
    from services import store_seo

    code = request.match_info.get("code", "")
    if not _CODE_RE.match(code):
        raise web.HTTPNotFound(text="Topilmadi")
    row = await Database.get_store_item(code)
    if not row:
        raise web.HTTPNotFound(text="Bu ish topilmadi")
    # Nom o'zgargan yoki noto'g'ri yozilgan bo'lsa — bitta to'g'ri manzil (takror sahifa bo'lmasin).
    if request.match_info.get("slug", "") != _slug(row):
        raise web.HTTPMovedPermanently(_item_path(row))
    await Database.bump_store_view(code)

    origin = _origin(request)
    path = _item_path(row)
    canonical = origin + path
    unit = _unit(row)
    title, category = row["title"], row.get("category") or ""
    work_type = row.get("work_type") or ""
    work_name = work_label(work_type)
    kind = (work_name or "ish").lower()
    file_type = (row.get("file_type") or "pptx").lower()
    language = row.get("language") or "uz"
    outline = store_seo.outline_of(row)
    excerpt = row.get("excerpt") or ""
    summary = _summary(row, outline)

    count = min(row.get("preview_count") or 0, STORE_PREVIEW_MAX)
    numbers = [n for n in range(1, count + 1) if _preview_file(code, n)] or list(range(1, count + 1))
    shots = [(n, _image_path(row, n), _preview_file(code, n)) for n in numbers]
    if not shots:
        shots = [(0, _image_path(row), _preview_file(code))]
    # Ishning qolgan varaqlari umuman rasmga aylantirilmagan — ular faqat son bo'lib ko'rsatiladi.
    hidden = max((row.get("slide_count") or len(shots)) - len(shots), 0)

    facts = []
    if row.get("slide_count"):
        facts.append(f'<span class="tag">{row["slide_count"]} {unit}</span>')
    if category:
        facts.append(f'<a class="tag" href="{_esc(_catalog_path(category=category))}">{_esc(category)}</a>')
    facts.append(f'<span class="tag">{_esc(file_type.upper())}</span>')
    facts.append(f'<span class="tag">{_esc(language.upper())}</span>')
    # Ichki kod mijozga ko'rsatilmaydi — u admin uchun, /nashr javobida bor.

    trail = [("Katalog", "/shop")]
    if work_type:
        trail.append((f"Tayyor {store_seo.plural(work_type)}", _catalog_path(work_type)))
    if category:
        trail.append((category, _catalog_path(work_type, category) if work_type else _catalog_path(category=category)))
    crumbs = " / ".join(f'<a href="{_esc(p)}">{_esc(n)}</a>' for n, p in trail) + " / " + _esc(title)

    buy_url = _bot_url(f"buy_{code}")
    buy = (f'<a class="buy" href="{_esc(buy_url)}" target="_blank" rel="noopener">'
           f'Botda sotib olish</a>') if buy_url else \
          '<div class="note">Sotib olish vaqtincha ishlamayapti.</div>'
    create_url = _bot_url()
    create_top = (f'<a class="create" href="{_esc(create_url)}" target="_blank" '
                  f'rel="noopener">+ Yangi yaratish</a>') if create_url else ""

    figures = []
    for index, (number, src, file_path) in enumerate(shots):
        width, height = _dims(file_path) if file_path else (0, 0)
        size = f' width="{width}" height="{height}"' if width and height else ' width="1000"'
        # Birinchi rasm darhol (sahifaning asosiy rasmi), qolganlari ko'rinishga yaqinlashganda.
        load = ' fetchpriority="high"' if index == 0 else ' loading="lazy"'
        label = f"{number}-{unit}" if number else "Muqova"
        figures.append(f'<figure><img src="{_esc(src)}" alt="{_esc(f"{title} — {kind}, {label}")}"'
                       f'{size}{load} decoding="async"><figcaption>{_esc(label)}</figcaption></figure>')

    if hidden:
        note = (f"Ko'rgazmada ishning dastlabki {len(shots)} ta {unit} "
                f"ko'rsatilgan, yana {hidden} tasi to'liq faylda. Shtampsiz, "
                f"tahrirlash mumkin bo'lgan to'liq {file_type.upper()} fayl to'lovdan "
                f"so'ng botda yuboriladi.")
        more_pages = (
            f'<div class="more-pages"><strong>Yana {hidden} ta {unit}</strong>'
            f'<span>Ko\'rgazmada faqat boshlanishi turadi. To\'liq ish '
            f'({row.get("slide_count")} {unit}) to\'lovdan keyin fayl '
            f'ko\'rinishida yuboriladi.</span></div>')
    else:
        note = (f"Ishning hamma {len(shots)} ta {unit} shu yerda — rasmlarda "
                f"shtamp bor. Shtampsiz, tahrirlash mumkin bo'lgan {file_type.upper()} "
                f"fayl to'lovdan so'ng botda yuboriladi.")
        more_pages = ""

    # «Ish haqida» — oddiy gaplar bilan: mavzu, tur (boshqa atalishlari bilan), fan, hajm, format.
    about = [f"«{_esc(title)}» — " + (f"{_esc(category)} faniga oid " if category else "")
             + f"tayyor {_esc(kind)}."]
    if row.get("slide_count"):
        about.append(f"Ish {row['slide_count']} ta {unit}dan iborat, {file_type.upper()} formatida, "
                     f"{_LANG_NAMES.get(language, language)} tilida; uni {_APPS.get(file_type, 'Office')} "
                     f"dasturida ochib tahrirlash mumkin.")
    if store_seo.SYNONYMS.get(work_type):
        about.append(f"Ish turi: {_esc(store_seo.SYNONYMS[work_type])}.")
    other = store_seo.other_script(title) if language == "uz" else ""
    if other:
        about.append(f"Mavzu {'lotin' if not _CYRILLIC_RE.search(other) else 'kirill'} yozuvida: "
                     f"«{_esc(other)}».")
    about.append(f"Ko'rgazmada dastlabki {len(shots)} ta {unit} bepul ko'rsatilgan. Kerakli mavzu "
                 f"topilmasa, Edufayl yangi ishni bir necha daqiqada tayyorlab beradi.")
    about_block = '<section class="about"><h2>Ish haqida</h2><p>' + " ".join(about) + "</p></section>"

    outline_block = ""
    if outline:
        heading = "Taqdimot rejasi" if file_type == "pptx" else "Reja"
        outline_block = (f'<section class="about"><h2>{heading}</h2><ul class="outline">'
                         + "".join(f"<li>{_esc(line)}</li>" for line in outline) + "</ul></section>")
    excerpt_block = (f'<section class="about"><h2>Ishdan parcha</h2>'
                     f'<blockquote class="excerpt">{_esc(excerpt)}</blockquote></section>') if excerpt else ""

    related = await Database.related_store_items(code, work_type, category, 8)
    related_block = ""
    if related:
        related_block = ('<section class="related"><h2>O\'xshash ishlar</h2><div class="grid">'
                         + "".join(_card(r) for r in related) + "</div></section>")

    images = [origin + src for _, src, _ in shots[:8]]
    product = {
        "@type": "Product",
        "@id": canonical + "#ish",
        "name": f"{title} — {kind}",
        "description": summary,
        "sku": code,
        "image": images,
        "brand": {"@type": "Brand", "name": "Edufayl"},
        "inLanguage": language,
        "offers": {
            "@type": "Offer",
            "price": str(row.get("price") or 0),
            "priceCurrency": "UZS",
            "availability": "https://schema.org/InStock",
            "url": canonical,
        },
    }
    if category:
        product["category"] = category
    graph = [product, _breadcrumb_ld(origin, trail + [(title, path)])]
    graph += [{"@type": "ImageObject", "contentUrl": url, "name": f"{title} — {kind}, {n}-{unit}",
               "representativeOfPage": i == 0}
              for i, (url, (n, _, _)) in enumerate(zip(images, shots))]

    try:
        template = ITEM_HTML.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Ish sahifasi o'qilmadi: %s", exc)
        return web.Response(text="Sahifa vaqtincha ishlamayapti", status=503)

    page_title = f"{title} — tayyor {kind}"
    if row.get("slide_count"):
        page_title += f" ({row['slide_count']} {unit})"
    page_title += " yuklab olish"
    values = {
        "{{LANG}}": _esc(language),
        "{{PAGE_TITLE}}": _esc(page_title),
        "{{TITLE}}": _esc(title),
        "{{META_DESC}}": _esc(summary),
        "{{CANONICAL}}": _esc(canonical),
        "{{OG_IMAGE}}": _esc(images[0]),
        "{{OG_ALT}}": _esc(f"{title} — {kind}"),
        "{{JSONLD}}": _json_ld({"@context": "https://schema.org", "@graph": graph}),
        "{{CRUMBS}}": crumbs,
        # Ish turi sarlavha ustida, mayda qalin harflar bilan — tashrifchi
        # bu nima ekanini birinchi qarashda bilishi kerak.
        "{{KIND}}": (f'<a class="kind" href="{_esc(_catalog_path(work_type))}">'
                     f'{_esc(work_name)}</a>') if work_name else "",
        "{{DESC_BLOCK}}": (f'<p class="item-desc">{_esc(row["description"])}</p>'
                           if row.get("description") else ""),
        "{{FACTS}}": "".join(facts),
        "{{PRICE}}": _esc(_money(row.get("price"))),
        "{{BUY}}": buy,
        "{{CREATE_TOP}}": create_top,
        "{{NOTE}}": _esc(note),
        "{{SLIDES}}": "\n".join(figures),
        "{{MORE_PAGES}}": more_pages,
        "{{ABOUT}}": about_block + outline_block + excerpt_block,
        "{{RELATED}}": related_block,
    }
    for token, value in values.items():
        template = template.replace(token, value)
    return web.Response(text=_with_style_version(template), content_type="text/html")


_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")


# ───────────────────────────────────────────────────────────── katalog

def _pager(base: str, page: int, pages: int) -> str:
    if pages <= 1:
        return ""
    link = lambda n: base + (f"?page={n}" if n > 1 else "")
    shown = sorted({1, pages, *range(max(1, page - 2), min(pages, page + 2) + 1)})
    parts, last = [], 0
    if page > 1:
        parts.append(f'<a rel="prev" href="{_esc(link(page - 1))}">‹ Oldingi</a>')
    for n in shown:
        if n - last > 1:
            parts.append("<span>…</span>")
        parts.append(f'<b>{n}</b>' if n == page else f'<a href="{_esc(link(n))}">{n}</a>')
        last = n
    if page < pages:
        parts.append(f'<a rel="next" href="{_esc(link(page + 1))}">Keyingi ›</a>')
    return '<nav class="pager" id="pager" aria-label="Sahifalar">' + "".join(parts) + "</nav>"


async def _render_catalog(request: web.Request, work_type: str = "", category: str = "") -> web.Response:
    from database.database import Database
    from services import store_seo

    query = (request.query.get("q") or "").strip()[:100]
    sort = (request.query.get("sort") or "new").strip()
    try:
        page = max(1, int(request.query.get("page", "1")))
    except ValueError:
        page = 1

    result = await Database.list_store_items(query=query, category=category, work_type=work_type,
                                             sort=sort, limit=_PAGE_SIZE, offset=(page - 1) * _PAGE_SIZE)
    total, items = result["total"], result["items"]
    if page > 1 and not items:
        raise web.HTTPNotFound(text="Bu sahifa yo'q")
    pages = max(1, -(-total // _PAGE_SIZE))

    origin = _origin(request)
    base = _catalog_path(work_type, category)
    canonical = origin + base + (f"?page={page}" if page > 1 else "")
    plural = store_seo.plural(work_type) if work_type else ""

    if work_type and category:
        h1 = f"Tayyor {plural}: {category}"
        title = f"{category} bo'yicha tayyor {plural} — {total} ta mavzu, yuklab olish"
        intro = (f"{category} faniga oid tayyor {plural}: {total} ta mavzu. Har bir ishning dastlabki "
                 f"varaqlarini bepul ko'ring va darhol yuklab oling.")
    elif work_type:
        h1 = f"Tayyor {plural}"
        title = f"Tayyor {plural} — {total} ta mavzu, yuklab olish"
        intro = (f"Tayyor {plural} to'plami: {total} ta mavzu. Fan bo'yicha tanlang, ishning dastlabki "
                 f"varaqlarini bepul ko'ring va darhol yuklab oling.")
    elif category:
        h1 = f"{category}: tayyor ishlar"
        title = f"{category} bo'yicha tayyor taqdimot, referat va kurs ishlari — {total} ta"
        intro = (f"{category} faniga oid tayyor taqdimot, referat, mustaqil ish va kurs ishlari: "
                 f"{total} ta mavzu.")
    else:
        h1 = "Tayyor mavzular"
        title = f"Tayyor taqdimotlar, kurs ishlari, referatlar va mustaqil ishlar — {total} ta mavzu"
        intro = ("Tayyor taqdimot (prezentatsiya, slayd), referat, mustaqil ish, kurs ishi va boshqa ishlar. "
                 "Fan bo'yicha tanlang, dastlabki varaqlarni bepul ko'ring va darhol yuklab oling.")
    if store_seo.SYNONYMS.get(work_type):
        intro += f" Ish turi: {store_seo.SYNONYMS[work_type]}."
    if page > 1:
        title += f" — {page}-sahifa"
    if query:
        title = f"«{query}» — tayyor ishlar qidiruvi"

    # Ish turlari va fanlar — oddiy havolalar (har biri o'z sahifasi).
    kinds = await Database.get_store_work_types()
    on = lambda flag: " on" if flag else ""
    kinds_html = ""
    if kinds:
        kinds_html = (f'<a class="kind-tab{on(not work_type)}" href="{_esc(_catalog_path(category=category))}">'
                      f'Hammasi</a>' + "".join(
                          f'<a class="kind-tab{on(k["key"] == work_type)}" '
                          f'href="{_esc(_catalog_path(k["key"]))}">{_esc(k["label"])} <i>{k["count"]}</i></a>'
                          for k in kinds))
    cats = await Database.get_store_categories(work_type)
    cats_html = (f'<a class="chip{on(not category)}" href="{_esc(_catalog_path(work_type))}">Hammasi</a>'
                 + "".join(f'<a class="chip{on(c["name"] == category)}" '
                           f'href="{_esc(_catalog_path(work_type, c["name"]))}">'
                           f'{_esc(c["name"])} ({c["count"]})</a>' for c in cats))

    create_url = _bot_url()
    create = (f'<a class="create" href="{_esc(create_url)}" target="_blank" rel="noopener">'
              f'+ Shu mavzuni yaratish</a>') if create_url else ""
    notice = ""
    if not total:
        grid = (f'<div class="state" style="grid-column:1/-1"><b>Hech narsa topilmadi</b>'
                f'Bu mavzu katalogda yo\'q — uni hoziroq yaratib olsangiz bo\'ladi. {create}</div>'
                if query or category else
                '<div class="state" style="grid-column:1/-1"><b>Katalog hozircha bo\'sh</b>'
                'Tez orada tayyor ishlar qo\'shiladi.</div>')
    else:
        grid = "".join(_card(row, lazy=i >= 4) for i, row in enumerate(items))
        if result.get("fuzzy") and query:
            notice = (f'<div class="notice"><span><b>«{_esc(query)}»</b> aynan topilmadi — shunga yaqin '
                      f'mavzular:</span>{create}</div>')

    trail = [("Katalog", "/shop")]
    if work_type:
        trail.append((f"Tayyor {plural}", _catalog_path(work_type)))
    if category:
        trail.append((category, base))
    crumbs = (" / ".join(f'<a href="{_esc(p)}">{_esc(n)}</a>' for n, p in trail[:-1])
              + (" / " if len(trail) > 1 else "") + _esc(trail[-1][0])) if len(trail) > 1 else ""

    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "name": h1, "description": intro, "url": canonical,
         "mainEntity": {"@type": "ItemList", "numberOfItems": total, "itemListElement": [
             {"@type": "ListItem", "position": (page - 1) * _PAGE_SIZE + n, "url": origin + _item_path(row),
              "name": row["title"]} for n, row in enumerate(items, start=1)]}},
        _breadcrumb_ld(origin, trail)]}

    init = {"q": query, "type": work_type, "category": category, "sort": sort, "page": page,
            "total": total, "loaded": len(items), "base": base, "fuzzy": bool(result.get("fuzzy"))}

    try:
        page_html = STORE_HTML.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Do'kon sahifasi o'qilmadi: %s", exc)
        return web.Response(text="Do'kon vaqtincha ishlamayapti", status=503)
    first_image = _image_path(items[0]) if items else "/static/logo.jpg"
    values = {
        "{{PAGE_TITLE}}": _esc(title),
        "{{META_DESC}}": _esc(_cut(intro, 300)),
        "{{CANONICAL}}": _esc(canonical),
        "{{ROBOTS}}": "noindex,follow" if query or sort != "new" else "index,follow",
        "{{OG_IMAGE}}": _esc(origin + first_image),
        "{{JSONLD}}": _json_ld(ld),
        "{{CRUMBS}}": f'<nav class="crumbs">{crumbs}</nav>' if crumbs else "",
        "{{H1}}": _esc(h1),
        "{{INTRO}}": _esc(intro),
        "{{KINDS}}": kinds_html,
        "{{CATS}}": cats_html,
        "{{NOTICE}}": notice,
        "{{COUNT}}": f"{total} ta ish topildi" if total else "",
        "{{GRID}}": grid,
        "{{MORE_HIDDEN}}": "" if page * _PAGE_SIZE < total else "hidden",
        "{{PAGER}}": "" if query else _pager(base, page, pages),
        "{{INIT}}": _json_ld(init),
        "{{Q}}": _esc(query),
        "__BOT_URL__": _esc(_bot_url()),
    }
    for token, value in values.items():
        page_html = page_html.replace(token, value)
    return web.Response(text=_with_style_version(page_html), content_type="text/html")


async def handle_store_page(request: web.Request) -> web.Response:
    """/shop. Eski `?type=…&category=…` havolalari tur/fan sahifasiga doimiy yo'naltiriladi."""
    from config import STORE_WORK_LABELS

    work_type = (request.query.get("type") or "").strip()[:50]
    category = (request.query.get("category") or "").strip()[:50]
    if (work_type or category) and not request.query.get("q"):
        known = work_type in STORE_WORK_LABELS or not work_type
        target = _catalog_path(work_type, category)
        if known and not target.endswith("/"):
            extra = {k: v for k, v in request.query.items() if k in ("page", "sort")}
            raise web.HTTPMovedPermanently(target + (("?" + urlencode(extra)) if extra else ""))
    return await _render_catalog(request, work_type, category)


async def handle_type_page(request: web.Request) -> web.Response:
    from database.database import Database
    from services.store_seo import type_from_slug

    work_type = type_from_slug(request.match_info["type"])
    if not any(k["key"] == work_type for k in await Database.get_store_work_types()):
        raise web.HTTPNotFound(text="Bu bo'lim yo'q")
    category = ""
    if request.match_info.get("cat"):
        category = (await _category_slugs(work_type)).get(request.match_info["cat"], "")
        if not category:
            raise web.HTTPNotFound(text="Bu bo'lim yo'q")
    return await _render_catalog(request, work_type, category)


async def handle_category_page(request: web.Request) -> web.Response:
    category = (await _category_slugs()).get(request.match_info["cat"], "")
    if not category:
        raise web.HTTPNotFound(text="Bu bo'lim yo'q")
    return await _render_catalog(request, "", category)


# ───────────────────────────────────────────────────────────── qidiruv tizimlari uchun

async def handle_robots(request: web.Request) -> web.Response:
    origin = _origin(request)
    lines = [
        "User-agent: *",
        "Allow: /shop",
        # Bosh sahifa tayyor ishlar ro'yxatini shu yerdan oladi — Google sahifani to'liq ko'rsin.
        "Allow: /api/shop/",
        # Tahrirlovchi shaxsiy hujjatlar bilan ishlaydi — indekslanmasin.
        "Disallow: /edit",
        "Disallow: /api/",
        "Disallow: /app",
        # Ichki qidiruv va saralash natijalari — takror sahifalar.
        "Disallow: /*?q=",
        "Disallow: /*&q=",
        "Disallow: /*sort=",
        "",
        f"Sitemap: {origin}/sitemap.xml" if origin else "",
    ]
    return web.Response(text="\n".join(filter(None, lines)) + "\n",
                        content_type="text/plain")


async def handle_sitemap(request: web.Request) -> web.Response:
    """Sayt xaritasi: bosh sahifa, katalog bo'limlari va har bir ish (rasmlari bilan — Google Rasmlar uchun)."""
    from collections import Counter

    from database.database import Database

    origin = html.escape(_origin(request))
    rows = await Database.all_store_codes()
    from webapp.landing import LANDINGS

    urls = [f"  <url><loc>{origin}/</loc></url>", f"  <url><loc>{origin}/shop</loc></url>"]
    urls += [f"  <url><loc>{origin}/{slug}</loc></url>" for slug in LANDINGS]

    types = Counter(r["work_type"] for r in rows if r["work_type"])
    cats = Counter(r["category"] for r in rows if r["category"])
    pairs = Counter((r["work_type"], r["category"]) for r in rows if r["work_type"] and r["category"])
    sections = ([_catalog_path(t) for t in types] + [_catalog_path(category=c) for c in cats]
                + [_catalog_path(t, c) for (t, c), n in pairs.items() if n >= 2])
    seen = set()
    for path in sections:
        if path not in seen and not path.endswith("/"):
            seen.add(path)
            urls.append(f"  <url><loc>{origin}{html.escape(path)}</loc></url>")

    for row in rows:
        item = {"public_code": row["code"], "title": row["title"], "work_type": row["work_type"]}
        loc = f"{origin}{html.escape(_item_path(item))}"
        stamp = (row.get("created_at") or "")[:10]
        lastmod = f"<lastmod>{stamp}</lastmod>" if len(stamp) == 10 else ""
        count = min(row.get("preview_count") or 0, STORE_PREVIEW_MAX)
        shots = [_image_path(item, n) for n in range(1, count + 1)] or [_image_path(item)]
        images = "".join(f"<image:image><image:loc>{origin}{html.escape(src)}</image:loc></image:image>"
                         for src in shots)
        urls.append(f"  <url><loc>{loc}</loc>{lastmod}{images}</url>")

    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
            + "\n".join(urls) + "\n</urlset>\n")
    return web.Response(text=body, content_type="application/xml")


async def handle_indexnow_key(request: web.Request) -> web.Response:
    from services.store_seo import indexnow_key

    return web.Response(text=indexnow_key(), content_type="text/plain")


# ───────────────────────────────────────────────────────────── API va rasmlar

async def handle_categories(request: web.Request) -> web.Response:
    from database.database import Database

    work_type = (request.query.get("type") or "").strip()[:50]
    cats = await Database.get_store_categories(work_type)
    for cat in cats:
        cat["url"] = _catalog_path(work_type, cat["name"])
    return web.json_response({"categories": cats})


async def handle_work_types(request: web.Request) -> web.Response:
    from database.database import Database

    types = await Database.get_store_work_types()
    for kind in types:
        kind["url"] = _catalog_path(kind["key"])
    return web.json_response({"types": types})


def _image_response(code: str, number: int) -> web.Response:
    path = _preview_file(code, number)
    if not path:
        return web.Response(status=404)
    return web.FileResponse(path, headers={
        "Content-Type": "image/jpeg",
        "Cache-Control": "public, max-age=86400",
    })


async def handle_preview(request: web.Request) -> web.Response:
    """Eski rasm manzili (/shop/preview/KOD/3.jpg) — ochiq turgan eski sahifalar uchun."""
    code = request.match_info.get("code", "")
    name = request.match_info.get("name", "")
    if not _CODE_RE.match(code):
        return web.Response(status=404)
    if name == "thumb":
        return _image_response(code, 0)
    if name.isdigit() and 1 <= int(name) <= STORE_PREVIEW_MAX:
        return _image_response(code, int(name))
    return web.Response(status=404)


_IMAGE_NAME = re.compile(r"^[a-z0-9-]{0,120}-(\d{1,2}|kichik)$")


async def handle_image(request: web.Request) -> web.Response:
    """Nomli rasm manzili: /shop/img/KOD/mavzu-nomi-taqdimot-3.jpg (…-kichik.jpg — katalogdagi kichik rasm)."""
    code = request.match_info.get("code", "")
    match = _IMAGE_NAME.match(request.match_info.get("name", ""))
    if not _CODE_RE.match(code) or not match:
        return web.Response(status=404)
    number = 0 if match.group(1) == "kichik" else int(match.group(1))
    if not number and match.group(1) != "kichik":
        return web.Response(status=404)
    if number > STORE_PREVIEW_MAX:
        return web.Response(status=404)
    return _image_response(code, number)


def setup_store_routes(app: web.Application) -> None:
    """Do'kon marshrutlarini tahrirlovchi bilan bir xil ilovaga qo'shadi."""
    from services.store_seo import indexnow_key

    app.router.add_get("/shop", handle_store_page)
    # Aniq yo'llar `/shop/{code}` dan oldin turishi shart: u ham bitta
    # bo'lakni ushlaydi va "style.css" ni o'ziga tortib ketardi.
    app.router.add_get("/shop/style.css", handle_style)
    app.router.add_get("/shop/preview/{code}/{name}.jpg", handle_preview)
    app.router.add_get("/shop/img/{code}/{name}.jpg", handle_image)
    app.router.add_get("/shop/tur/{type}", handle_type_page)
    app.router.add_get("/shop/tur/{type}/{cat}", handle_type_page)
    app.router.add_get("/shop/fan/{cat}", handle_category_page)
    app.router.add_get("/shop/{code}", handle_item_redirect)
    app.router.add_get("/shop/{code}/{slug}", handle_item_page)
    app.router.add_get("/robots.txt", handle_robots)
    app.router.add_get("/sitemap.xml", handle_sitemap)
    app.router.add_get(f"/{indexnow_key()}.txt", handle_indexnow_key)
    app.router.add_get("/api/shop/items", handle_items)
    app.router.add_get("/api/shop/items/{code}", handle_item)
    app.router.add_get("/api/shop/categories", handle_categories)
    app.router.add_get("/api/shop/types", handle_work_types)
