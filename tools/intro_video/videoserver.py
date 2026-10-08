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
        bodies.append(body)
    for done in range(0, n, 3):
        if progress_cb:
            progress_cb(done, n)
        time.sleep(SLOW / max(1, n / 3))
    if outline_out is not None:
        outline_out.update(family="umumiy", outline=[{"title": t, "brief": t, "category": c} for c, t, _ in deck])
    return html_slides.build_pages(bodies, theme, language)


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


async def main():
    from webapp.server import create_web_app
    from bot.queue_service import get_doc_queue
    from database import web_accounts
    await init_db()
    await _NS["patch_ai"](); get_doc_queue().start()
    await Database.create_user(100, "ali", "Ali Valiyev", "uz")
    await Database.update_user_balance(100, 120_000)
    await seed_shop()
    tok = await web_accounts.create_session(100)
    open(os.path.join(HERE, "session.txt"), "w").write(tok)
    runner = web.AppRunner(create_web_app()); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 8798).start()
    print("ready", flush=True)
    while True:
        await asyncio.sleep(3600)

asyncio.run(main())
