"""Tanishtiruv videosini yozib olish uchun namoyish serveri.

Sayt — haqiqiy (o'sha kod, o'sha sahifalar). Faqat AI soxta: taqdimot uchun tayyor, chiroyli mazmun
qaytaradi (slaydlar haqiqiy generatorda chiziladi), hujjatlar uchun shakli to'g'ri matn. Do'kon namunaviy
ishlar bilan to'ldiriladi. Mijozlarning hech qanday ma'lumoti ishlatilmaydi.
"""
import asyncio, os, shutil, sys, tempfile, time, types

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="intro_")
os.environ["STORE_PREVIEW_DIR"] = os.path.join(TMP, "store_previews")
os.environ.setdefault("BOT_TOKEN", "1:x")
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE); os.chdir(ROOT)

import database.database as dbmod
from database.database import Database, init_db
from services import web_jobs, web_kinds  # noqa
from services.premium_presentation import deck_logic, html_slides, llm_client
import webapp
from aiohttp import web
import demo_content as dc

dbmod.DATABASE_FILE = os.path.join(TMP, "t.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
webapp.BOT_USERNAME = "Edufayl_bot"


class FakeBot:
    async def send_document(self, *a, **k): return types.SimpleNamespace()
    async def send_message(self, *a, **k): return types.SimpleNamespace(message_id=1, chat=types.SimpleNamespace(id=1))
webapp.BOT = FakeBot()

SLOW = float(os.getenv("SLOW", "9"))


def fake_write(topic, count, theme, language="uz", level=2, preferences="", source_text="", author="",
               progress_cb=None, outline_out=None, plan_cb=None):
    n = count + 2
    deck = [dc.DECK[0], dc.DECK[1]] + [dc.DECK[2 + i % (len(dc.DECK) - 3)] for i in range(n - 3)] + [dc.DECK[-1]]
    time.sleep(1.6)      # reja tuzilmoqda
    if plan_cb:
        plan_cb([{"title": t, "category": c} for c, t, _ in deck])
    bodies = []
    for i, (cat, title, body) in enumerate(deck):
        if body is None:     # reja sahifasi — qolgan sarlavhalardan
            body = deck_logic.plan_slide([(t, "") for _, t, _ in deck[2:-1]], language)
        if i == 0 and author:
            body = body.replace("</div></section>", f'<p class="note">Tayyorladi: {author}</p></div></section>', 1)
        bodies.append(fill_photos(body))
    for done in range(0, n, 3):
        if progress_cb:
            progress_cb(done, n)
        time.sleep(SLOW / max(1, n / 3))
    if outline_out is not None:
        outline_out.update(family="umumiy", outline=[{"title": t, "brief": t, "category": c} for c, t, _ in deck])
    return with_cover(html_slides.build_pages(bodies, theme, language))


PHOTO_DIR = os.getenv("PHOTO_DIR") or os.path.join(HERE, "photos")
_SLOT = __import__("re").compile(r'<div class="rasm"><img class="photo" data-demo="(\w+)" alt=""></div>')


def photo_uri(name):
    """photos/<name>.(jpg|jpeg|png|webp) → siqilgan JPEG data URI (bo'lmasa — None)."""
    import base64, io
    from PIL import Image
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = os.path.join(PHOTO_DIR, name + ext)
        if os.path.exists(path):
            im = Image.open(path).convert("RGB")
            im.thumbnail((1600, 1600))
            buf = io.BytesIO(); im.save(buf, "JPEG", quality=84)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return None


def fill_photos(body):
    """Namoyish slaydlariga haqiqiy rasmlar (mahsulotda ular internetdan topiladi yoki AI chizadi)."""
    def fill(m):
        uri = photo_uri(m.group(1))
        return (f'<div class="rasm photo-in"><img class="photo" src="{uri}" alt="" style="object-position:50% 50%"></div>'
                if uri else "")
    return _SLOT.sub(fill, body)


def with_cover(pages):
    from services.premium_presentation import html_images
    cover = photo_uri("cover")
    if cover and pages:
        pages[0] = html_images.with_cover_photo(pages[0], cover)
    return pages


html_slides.write_slides = fake_write
llm_client._call_openrouter = lambda *a, **k: {"ok": False}
llm_client._call_openrouter_text = lambda *a, **k: ""

_E2E = open(os.path.join(HERE, "fake_docs.py"), encoding="utf-8").read()
_NS = {"__name__": "e2e"}
exec("import asyncio, io, json, os, random, re, sys, tempfile, time, types\n"
     + _E2E[_E2E.index("WORDS ="):_E2E.index("async def wait_job")], _NS)


async def seed_shop():
    src = os.path.join(HERE, "shop_prev")
    for code, title, wt, price, style, colour, n in dc.SHOP:
        shutil.copytree(os.path.join(src, code), os.path.join(os.environ["STORE_PREVIEW_DIR"], code))
        await Database.create_store_item(public_code=code, title=title, file_id="demo", price=price,
                                         description="Tayyor taqdimot: reja, diagrammalar va xulosa bilan.",
                                         category="", work_type=wt, language="uz", slide_count=n, preview_count=3)


async def demo_bot(request):
    return web.FileResponse(os.path.join(HERE, "botchat.html"))


async def demo_go(request):
    """Botdagi «🌐 Ochish» tugmasi: haqiqiy bir martalik kirish havolasi (bot ham xuddi shunday beradi)."""
    from database import web_store
    return web.json_response({"token": await web_store.start_go(100)})


async def demo_pay(request):
    """Click to'lovi o'rnida: yetishmagan summa hisobga tushadi va kutib turgan buyurtma o'zi boshlanadi."""
    from database import web_store
    add = int(request.query.get("add") or 0)
    if add:
        await Database.update_user_balance(100, add)
        return web.json_response({"ok": True, "paid": add})
    row = await web_store.get_pending(100)
    user = await Database.get_user(100)
    missing = max(0, int(row["price"]) - int(user.balance or 0)) if row else 0
    if missing:
        await Database.update_user_balance(100, missing)
    await web_jobs.start_pending(100)
    return web.json_response({"ok": True, "paid": missing})


async def main():
    from webapp.server import create_web_app
    from bot.queue_service import get_doc_queue
    from database import web_accounts
    from services import site_mode, click_pay, payme_pay, uzum_pay
    import config
    site_mode.ON = True                      # videoda sayt rejimi: xarid va to'lov saytning o'zida
    async def _on():
        return True
    click_pay.available = payme_pay.available = uzum_pay.available = _on
    from services.receipts import web as receipt_web
    receipt_web.card_view = lambda number: number         # haqiqiy karta raqami videoga tushmasin
    config.PAYMENT_CARD, config.PAYMENT_CARD_2, config.PAYMENT_CARD_OWNER = "8600 •••• •••• ••••", "", "Edufayl"
    await init_db()
    await _NS["patch_ai"](); get_doc_queue().start()
    await Database.create_user(100, "ali", "Ali Valiyev", "uz")
    await Database.update_user_balance(100, int(os.getenv("BALANCE", "0")))
    await seed_shop()
    tok = await web_accounts.create_session(100)
    open(os.path.join(HERE, "session.txt"), "w").write(tok)
    app = create_web_app()
    app.router.add_get("/demo/bot", demo_bot)
    app.router.add_post("/demo/go", demo_go)
    app.router.add_post("/demo/pay", demo_pay)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 8798).start()
    print("ready", flush=True)
    while True:
        await asyncio.sleep(3600)

asyncio.run(main())
