"""Katta kitobni sayt orqali yuklash va tayyor tarjimani saytdan olish.

Telegram oddiy Bot API orqali bot'ga 20 MB dan katta faylni bermaydi,
50 MB dan kattasini yuborishga ham ruxsat bermaydi. Rasmga boy darsliklar
esa 40-100 MB bo'ladi. Shunday faylni mijoz bot bergan bir martalik
havola orqali brauzerda yuklaydi; tayyor tarjima Telegram'ga sig'masa,
u ham shu yerdan yuklab olinadi.

Havolalar faqat xotirada turadi: bot qayta ishga tushsa ular bekor
bo'ladi — bu to'g'ri, chunki shu paytdagi ish ham uziladi.
"""

import asyncio
import html
import logging
import os
import secrets
import time
import uuid
from urllib.parse import quote, unquote

from aiohttp import web

import webapp
from config import BOOK_MAX_UPLOAD_MB, TEMP_DIR

logger = logging.getLogger(__name__)

UPLOAD_TTL = 3 * 3600
DOWNLOAD_TTL = 48 * 3600
_EXTENSIONS = {".pdf": b"%PDF", ".docx": b"PK"}

_uploads: dict = {}
_downloads: dict = {}

# Yuklash tugagach chaqiriladi: `await ON_UPLOAD(record, path, file_name)`.
# Bot tomoni (kitob tarjimasi) uni ishga tushishda o'rnatadi.
ON_UPLOAD = None


def _sweep() -> None:
    now = time.time()
    for token in [t for t, r in _uploads.items() if r["expires"] < now]:
        _drop_part(_uploads.pop(token, None))
    for token in [t for t, r in _downloads.items() if r["expires"] < now]:
        record = _downloads.pop(token, None)
        if record:
            try:
                os.remove(record["path"])
            except OSError:
                pass


def _drop_part(record) -> None:
    """Chala yuklangan faylni o'chiradi."""
    path = (record or {}).get("part")
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def new_upload_link(user_id: int, chat_id: int, lang: str) -> str:
    """Bir martalik yuklash havolasi (3 soat amal qiladi)."""
    _sweep()
    forget_upload_links(user_id)
    token = secrets.token_urlsafe(18)
    _uploads[token] = {"user_id": user_id, "chat_id": chat_id, "lang": lang,
                       "expires": time.time() + UPLOAD_TTL, "busy": False,
                       "part": None, "received": 0, "size": 0,
                       "lock": asyncio.Lock()}
    return webapp.public_url(f"/book/upload/{token}")


def forget_upload_links(user_id: int) -> None:
    for token in [t for t, r in _uploads.items() if r["user_id"] == user_id]:
        _drop_part(_uploads.pop(token, None))


def new_download_link(path: str, file_name: str) -> str:
    """Tayyor faylni saytdan olish havolasi (48 soat)."""
    _sweep()
    token = secrets.token_urlsafe(18)
    _downloads[token] = {"path": path, "name": file_name,
                         "expires": time.time() + DOWNLOAD_TTL}
    return webapp.public_url(f"/book/download/{token}")


_TEXTS = {
    "uz": {
        "title": "Kitobni yuklash",
        "lead": "Tarjima qilinadigan kitobni tanlang (PDF yoki Word, {mb} MB gacha). "
                "Yuklash tugagach botga qayting — davomi o'sha yerda.",
        "pick": "Faylni tanlash",
        "send": "Yuklash",
        "sending": "Yuklanmoqda…",
        "retry": "Internet uzildi, qayta ulanmoqda… ({n})",
        "done": "✅ Fayl qabul qilindi. Botga qayting.",
        "big": "❌ Fayl juda katta. Eng ko'pi {mb} MB.",
        "type": "❌ Faqat PDF yoki Word (DOCX) fayl.",
        "fail": "❌ Yuklab bo'lmadi. Internetni tekshirib, qayta urinib ko'ring.",
        "proxy": "❌ Sayt serveri bunday katta faylni qabul qilmadi. Administratorga xabar bering.",
        "dead": "Havola eskirgan yoki allaqachon ishlatilgan. Botda /book buyrug'ini qayta yuboring.",
    },
    "ru": {
        "title": "Загрузка книги",
        "lead": "Выберите книгу для перевода (PDF или Word, до {mb} МБ). "
                "После загрузки вернитесь в бот — продолжение там.",
        "pick": "Выбрать файл",
        "send": "Загрузить",
        "sending": "Загрузка…",
        "retry": "Связь прервалась, переподключение… ({n})",
        "done": "✅ Файл принят. Вернитесь в бот.",
        "big": "❌ Файл слишком большой. Максимум {mb} МБ.",
        "type": "❌ Только PDF или Word (DOCX).",
        "fail": "❌ Не удалось загрузить. Проверьте интернет и попробуйте снова.",
        "proxy": "❌ Сервер сайта не принял такой большой файл. Сообщите администратору.",
        "dead": "Ссылка устарела или уже использована. Отправьте /book в боте ещё раз.",
    },
    "en": {
        "title": "Upload a book",
        "lead": "Choose the book to translate (PDF or Word, up to {mb} MB). "
                "When the upload finishes, go back to the bot.",
        "pick": "Choose file",
        "send": "Upload",
        "sending": "Uploading…",
        "retry": "Connection lost, retrying… ({n})",
        "done": "✅ File received. Go back to the bot.",
        "big": "❌ The file is too large. Maximum {mb} MB.",
        "type": "❌ PDF or Word (DOCX) only.",
        "fail": "❌ Upload failed. Check your connection and try again.",
        "proxy": "❌ The site server refused such a large file. Please tell the administrator.",
        "dead": "This link has expired or was already used. Send /book to the bot again.",
    },
}

_PAGE = """<!DOCTYPE html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{title}</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--ink:#1d2330;--muted:#5b6474;--accent:#2f6fed;--line:#dde2ea}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12151b;--card:#1b2029;--ink:#e8ecf2;--muted:#9aa4b4;--accent:#5b8dff;--line:#2c3340}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:520px;margin:40px auto;padding:0 16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px}}
h1{{font-size:21px;margin:0 0 8px}}
p{{color:var(--muted);margin:0 0 18px}}
label.pick{{display:block;border:2px dashed var(--line);border-radius:12px;padding:22px;text-align:center;cursor:pointer}}
input[type=file]{{display:none}}
#name{{display:block;margin-top:6px;color:var(--ink);word-break:break-all}}
button{{margin-top:16px;width:100%;padding:13px;border:0;border-radius:10px;background:var(--accent);color:#fff;font-size:16px;font-weight:600}}
button:disabled{{opacity:.5}}
.bar{{height:8px;background:var(--line);border-radius:6px;margin-top:16px;overflow:hidden;display:none}}
.bar i{{display:block;height:100%;width:0;background:var(--accent)}}
#msg{{margin-top:14px;font-weight:600}}
</style></head>
<body><main><div class="card">
<h1>{title}</h1>
<p>{lead}</p>
{body}
</div></main>
<script>
const T = {texts};
const f = document.getElementById('file');
// Fayl bo'laklab yuboriladi: bitta katta so'rovni oraliq server (nginx,
// Cloudflare) to'xtatib qo'yishi yoki mobil internet uzib yuborishi mumkin.
// Uzilsa, yuklash to'xtagan joyidan davom etadi.
const CHUNK = 768 * 1024;
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function call(url, opts) {{
  const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), 90000);
  try {{ return await fetch(url, Object.assign({{signal: ctl.signal, cache: 'no-store'}}, opts)); }}
  finally {{ clearTimeout(timer); }}
}}
async function problem(r) {{
  if (r.status === 413) return T.proxy;
  try {{ return (await r.json()).error || T.fail; }} catch (e) {{ return T.fail; }}
}}
if (f) {{
  const btn = document.getElementById('send'), msg = document.getElementById('msg');
  const bar = document.querySelector('.bar'), fill = document.querySelector('.bar i');
  const base = location.pathname.replace(/\/$/, '');
  f.addEventListener('change', () => {{
    document.getElementById('name').textContent = f.files[0] ? f.files[0].name : '';
    btn.disabled = !f.files[0]; msg.textContent = '';
  }});
  btn.addEventListener('click', async () => {{
    const file = f.files[0]; if (!file) return;
    if (!/\.(pdf|docx)$/i.test(file.name)) {{ msg.textContent = T.type; return; }}
    if (file.size > T.max) {{ msg.textContent = T.big; return; }}
    btn.disabled = true; f.disabled = true; bar.style.display = 'block'; msg.textContent = T.sending;
    const fail = text => {{ msg.textContent = text; btn.disabled = false; f.disabled = false; }};
    let offset = 0, errors = 0;
    while (offset < file.size) {{
      try {{
        const end = Math.min(offset + CHUNK, file.size);
        const r = await call(`${{base}}/chunk?offset=${{offset}}&size=${{file.size}}`,
                             {{method: 'POST', body: file.slice(offset, end),
                              headers: {{'Content-Type': 'application/octet-stream'}}}});
        if (r.status === 409) {{ offset = (await r.json()).received; continue; }}
        if (!r.ok) {{ if (r.status >= 500) throw new Error(r.status); return fail(await problem(r)); }}
        offset = (await r.json()).received; errors = 0;
        fill.style.width = (100 * offset / file.size) + '%';
        msg.textContent = `${{T.sending}} ${{Math.floor(100 * offset / file.size)}}%`;
      }} catch (e) {{
        errors += 1;
        if (errors > 40) return fail(T.fail);
        msg.textContent = T.retry.replace('{{n}}', errors);
        await sleep(Math.min(15000, 1500 * errors));
        try {{
          const st = await call(`${{base}}/status`);
          if (st.ok) offset = (await st.json()).received;
        }} catch (e2) {{}}
      }}
    }}
    for (let attempt = 1; attempt <= 5; attempt++) {{
      try {{
        const r = await call(`${{base}}/finish`, {{method: 'POST',
          headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{name: file.name}})}});
        if (r.ok) {{ msg.textContent = T.done; btn.style.display = 'none'; return; }}
        return fail(await problem(r));
      }} catch (e) {{ await sleep(3000 * attempt); }}
    }}
    fail(T.fail);
  }});
}}
</script></body></html>"""


def _texts(lang: str) -> dict:
    texts = dict(_TEXTS.get(lang, _TEXTS["uz"]))
    for key in ("lead", "big"):
        texts[key] = texts[key].format(mb=BOOK_MAX_UPLOAD_MB)
    return texts


async def handle_upload_page(request: web.Request) -> web.Response:
    _sweep()
    record = _uploads.get(request.match_info.get("token", ""))
    lang = record["lang"] if record else "uz"
    texts = _texts(lang)
    if record:
        body = (f'<label class="pick">{html.escape(texts["pick"])}'
                '<input id="file" type="file" accept=".pdf,.docx,application/pdf">'
                '<span id="name"></span></label>'
                f'<button id="send" disabled>{html.escape(texts["send"])}</button>'
                '<div class="bar"><i></i></div><div id="msg"></div>')
        lead = texts["lead"]
    else:
        body, lead = "", texts["dead"]
    import json

    page = _PAGE.format(
        lang=lang, title=html.escape(texts["title"]), lead=html.escape(lead), body=body,
        texts=json.dumps({**texts, "max": BOOK_MAX_UPLOAD_MB * 1024 * 1024},
                         ensure_ascii=False).replace("</", "<\\/"),
    )
    return web.Response(text=page, content_type="text/html",
                        headers={"Cache-Control": "no-store"})


def _error(texts: dict, key: str, status: int) -> web.Response:
    return web.json_response({"error": texts[key]}, status=status)


async def handle_upload(request: web.Request) -> web.Response:
    """Faylni diskka oqim bilan yozadi — xotiraga butunlay yuklanmaydi."""
    _sweep()
    token = request.match_info.get("token", "")
    record = _uploads.get(token)
    texts = _texts(record["lang"] if record else "uz")
    if not record or record["busy"]:
        return _error(texts, "dead", 410)
    limit = BOOK_MAX_UPLOAD_MB * 1024 * 1024
    if request.content_length and request.content_length > limit + 64 * 1024:
        return _error(texts, "big", 413)

    record["busy"] = True
    path = None
    try:
        reader = await request.multipart()
        part = await reader.next()
        while part is not None and part.name != "file":
            part = await reader.next()
        if part is None or not part.filename:
            return _error(texts, "fail", 400)
        # Ba'zi mijozlar nomni %XX ko'rinishida yuboradi.
        file_name = os.path.basename(unquote(part.filename))[:120]
        extension = os.path.splitext(file_name)[1].lower()
        if extension not in _EXTENSIONS:
            return _error(texts, "type", 415)

        os.makedirs(TEMP_DIR, exist_ok=True)
        path = os.path.join(TEMP_DIR, f"bt_web_{uuid.uuid4().hex[:10]}{extension}")
        size = 0
        head = b""
        with open(path, "wb") as out:
            while True:
                chunk = await part.read_chunk(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    return _error(texts, "big", 413)
                if len(head) < 8:
                    head += chunk[:8]
                out.write(chunk)
        if not head.startswith(_EXTENSIONS[extension]):
            return _error(texts, "type", 415)

        _uploads.pop(token, None)
        logger.info("Kitob saytdan yuklandi: %s, %.1f MB, user=%s",
                    file_name, size / 1024 / 1024, record["user_id"])
        if ON_UPLOAD is not None:
            ready_path, path = path, None
            asyncio.create_task(_deliver(record, ready_path, file_name))
        return web.json_response({"ok": True})
    except Exception as exc:
        logger.warning("Kitobni saytdan yuklashda xato: %s", exc)
        return _error(texts, "fail", 400)
    finally:
        record["busy"] = False
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def _record(request: web.Request):
    _sweep()
    token = request.match_info.get("token", "")
    return token, _uploads.get(token)


async def handle_status(request: web.Request) -> web.Response:
    _, record = _record(request)
    if not record:
        return _error(_texts("uz"), "dead", 410)
    return web.json_response({"received": record["received"]},
                             headers={"Cache-Control": "no-store"})


async def handle_chunk(request: web.Request) -> web.Response:
    """Faylning bitta bo'lagi. Bo'lak aynan kutilgan joydan boshlanishi kerak —
    aks holda 409 va qayerdan davom etish kerakligi qaytariladi."""
    _, record = _record(request)
    texts = _texts(record["lang"] if record else "uz")
    if not record:
        return _error(texts, "dead", 410)
    try:
        offset = int(request.query.get("offset", "-1"))
        size = int(request.query.get("size", "0"))
    except ValueError:
        return _error(texts, "fail", 400)
    limit = BOOK_MAX_UPLOAD_MB * 1024 * 1024
    if size <= 0 or size > limit:
        return _error(texts, "big", 413)

    async with record["lock"]:
        if offset == 0 and record["received"] and record["size"] != size:
            # Boshqa fayl tanlangan — eskisini tashlab, boshidan boshlaymiz.
            _drop_part(record)
            record.update(part=None, received=0)
        if offset != record["received"]:
            return web.json_response({"received": record["received"]}, status=409)
        data = await request.read()
        if not data or offset + len(data) > size:
            return _error(texts, "fail", 400)
        if record["part"] is None:
            os.makedirs(TEMP_DIR, exist_ok=True)
            record["part"] = os.path.join(TEMP_DIR, f"bt_part_{uuid.uuid4().hex[:10]}")
            record["size"] = size
        with open(record["part"], "ab") as out:
            out.write(data)
        record["received"] = offset + len(data)
        record["expires"] = max(record["expires"], time.time() + 3600)
        return web.json_response({"received": record["received"]})


async def handle_finish(request: web.Request) -> web.Response:
    """Hamma bo'lak kelgach: tur tekshiriladi va kitob botga uzatiladi."""
    token, record = _record(request)
    texts = _texts(record["lang"] if record else "uz")
    if not record:
        return _error(texts, "dead", 410)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    file_name = os.path.basename(str(payload.get("name") or ""))[:120]
    extension = os.path.splitext(file_name)[1].lower()
    async with record["lock"]:
        if extension not in _EXTENSIONS:
            return _error(texts, "type", 415)
        part = record["part"]
        if not part or record["received"] != record["size"] or not os.path.exists(part):
            return _error(texts, "fail", 400)
        with open(part, "rb") as source:
            head = source.read(8)
        if not head.startswith(_EXTENSIONS[extension]):
            _drop_part(record)
            record.update(part=None, received=0, size=0)
            return _error(texts, "type", 415)
        path = part + extension
        os.replace(part, path)
        _uploads.pop(token, None)
    logger.info("Kitob saytdan yuklandi: %s, %.1f MB, user=%s",
                file_name, record["size"] / 1024 / 1024, record["user_id"])
    if ON_UPLOAD is not None:
        asyncio.create_task(_deliver(record, path, file_name))
    return web.json_response({"ok": True})


async def _deliver(record: dict, path: str, file_name: str) -> None:
    try:
        await ON_UPLOAD(record, path, file_name)
    except Exception:
        logger.exception("Saytdan yuklangan kitobni botga uzatib bo'lmadi")
        try:
            os.remove(path)
        except OSError:
            pass


async def handle_download(request: web.Request) -> web.StreamResponse:
    _sweep()
    record = _downloads.get(request.match_info.get("token", ""))
    if not record or not os.path.exists(record["path"]):
        raise web.HTTPNotFound(text="Havola eskirgan yoki fayl o'chirilgan.")
    name = record["name"]
    ascii_name = name.encode("ascii", "ignore").decode() or "kitob.pdf"
    return web.FileResponse(record["path"], headers={
        "Content-Disposition": (f'attachment; filename="{ascii_name}"; '
                                f"filename*=UTF-8''{quote(name)}"),
        "Cache-Control": "no-store",
    })


def setup_book_routes(app: web.Application) -> None:
    app.router.add_get("/book/upload/{token}", handle_upload_page)
    app.router.add_post("/book/upload/{token}", handle_upload)
    app.router.add_get("/book/upload/{token}/status", handle_status)
    app.router.add_post("/book/upload/{token}/chunk", handle_chunk)
    app.router.add_post("/book/upload/{token}/finish", handle_finish)
    app.router.add_get("/book/download/{token}", handle_download)
