"""Bepul sinov taqdimoti: har akkauntga bir marta, 5 slayd, Gemini 2.5 Flash Lite, rasmsiz.

- varaq soni qat'iy (mijoz boshqa son yuborsa ham 5), pul olinmaydi;
- ikkinchi marta (hatto bir vaqtda ikki so'rov bo'lsa ham) — rad etiladi;
- taqdimot tayyorlanmay qolsa, imkoniyat qaytariladi;
- arzon model faqat shu buyurtmada (boshqa oqim/tarmoqlarda ham) — pullik taqdimotlarga ta'sir qilmaydi;
- rasm chizdirilmaydi, katalogga (do'konga) qo'yilmaydi;
- akkauntlar birlashganda ham bir marta;
- saytda «Imtiyozdan foydalanish»: varaq soni qulflanadi, narx «Bepul», so'rovda `trial: true`.

    python test_bepul_sinov.py
"""
import asyncio, os, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import config
import database.database as dbmod
from database.database import Database, init_db
from database import free_trial, web_accounts
from services import web_jobs, web_kinds  # noqa
from services.premium_presentation import chart_data, html_render, llm_client, pipeline
import webapp
from aiohttp import web

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "t.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
PORT = 8797
BASE = f"http://127.0.0.1:{PORT}"
LITE = "google/gemini-2.5-flash-lite"


class FakeBot:
    def __init__(self): self.docs = []
    async def send_document(self, chat_id, document, **kw):
        self.docs.append(chat_id); return types.SimpleNamespace()
webapp.BOT, webapp.BOT_USERNAME = FakeBot(), "Edufayl_bot"

# Taqdimot yaratishning o'rnida: modelni har bosqichda (asosiy oqim, run_step oqimi, chart_data oqimlari) yozib oladi.
SEEN = []
MODE = {"fail": False}


async def fake_build_deck(topic, slide_count, **kw):
    loop = asyncio.get_running_loop()
    in_step = await pipeline.run_step(loop, lambda: llm_client._models("text")[0], step="brief", label="sinov")
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        in_pool = list(pool.map(chart_data._in_context(lambda _: llm_client._models("text")[0]), [1, 2]))
    SEEN.append({"slides": slide_count, "photos": kw.get("photos"), "main": llm_client._models("text")[0],
                 "step": in_step, "pool": in_pool})
    if MODE["fail"]:
        raise RuntimeError("sinov xatosi")
    path = os.path.join(TMP, f"deck{len(SEEN)}.pptx")
    open(path, "wb").write(b"PK")
    return path, slide_count, 0

pipeline.build_deck = fake_build_deck
PUBLISHED = []
import services.store_publisher as sp
sp.schedule_publish = lambda *a, **k: PUBLISHED.append(a)
web_jobs._require_subscription = lambda tid: asyncio.sleep(0)


async def wait(job_id, limit=10.0):
    from database import web_store
    t = 0.0
    while t < limit:
        job = await web_store.get_job(job_id)
        if job and job["status"] in ("done", "failed"):
            return job
        await asyncio.sleep(0.05); t += 0.05
    return await web_store.get_job(job_id)


async def server_checks():
    await init_db()
    await Database.create_user(701, "ali", "Ali", "uz")
    await Database.update_user_balance(701, 10_000)

    print("1) Imkoniyat jadvali")
    check("boshida bor", await free_trial.available(701))
    results = await asyncio.gather(free_trial.claim(701, "a"), free_trial.claim(701, "b"))
    check("bir vaqtda ikki marta band qilinsa — faqat bittasi o'tadi", sorted(results) == [False, True], results)
    check("boshqa buyurtma qaytara olmaydi", not await free_trial.release(701, "zzz") and not await free_trial.available(701))
    winner = "a" if results[0] else "b"
    check("o'z buyurtmasi qaytaradi", await free_trial.release(701, winner) and await free_trial.available(701))

    print("2) Bepul buyurtma")
    job = await web_jobs.submit(701, "premium_presentation", {"topic": "Suv resurslari", "slide_count": 20, "trial": True})
    done = await wait(job["id"])
    seen = SEEN[-1]
    user = await Database.get_user(701)
    check("tayyor bo'ldi", done["status"] == "done", done.get("error"))
    check("varaq soni 5 (mijoz 20 yuborgan bo'lsa ham)", seen["slides"] == 5, seen)
    check("narx 0, balansdan pul olinmadi", job["price"] == 0 and int(user.balance) == 10_000, (job["price"], user.balance))
    check("rasm chizdirilmaydi", seen["photos"] is False, seen)
    check("Flash Lite — asosiy oqimda, run_step oqimida va chart_data oqimlarida",
          seen["main"] == LITE and seen["step"] == LITE and seen["pool"] == [LITE, LITE], seen)
    check("imkoniyat ishlatildi", not await free_trial.available(701))
    check("bepul taqdimot do'konga qo'yilmaydi", not PUBLISHED, PUBLISHED)
    check("buyurtmadan keyin global model o'zgarmagan", llm_client._models("text")[0] != LITE
          and llm_client._WORKING.get("text") != LITE, llm_client._models("text")[:2])
    try:
        await web_jobs.submit(701, "premium_presentation", {"topic": "Yana bir", "trial": True})
        check("ikkinchi marta rad etiladi", False)
    except web_jobs.JobError as exc:
        check("ikkinchi marta rad etiladi", exc.code == "trial_used", exc.code)

    print("3) Pullik taqdimot o'zgarmagan")
    job = await web_jobs.submit(701, "premium_presentation", {"topic": "Pullik", "slide_count": 10})
    await wait(job["id"])
    seen = SEEN[-1]
    user = await Database.get_user(701)
    check("pullik: 10 slayd, rasmlar yoqiq, pul olindi", seen["slides"] == 10 and seen["photos"] is True
          and int(user.balance) == 10_000 - pipeline.price_for(10), (seen, user.balance))
    check("pullik: Flash Lite emas", seen["main"] != LITE and seen["step"] != LITE, seen)
    check("pullik taqdimot do'konga qo'yiladi", len(PUBLISHED) == 1)

    print("4) Tayyorlanmay qolsa imkoniyat qaytadi")
    await Database.create_user(702, "vali", "Vali", "uz")
    MODE["fail"] = True
    job = await web_jobs.submit(702, "premium_presentation", {"topic": "Xato", "trial": True})
    failed = await wait(job["id"])
    MODE["fail"] = False
    check("xato: imkoniyat qaytdi", failed["status"] == "failed" and await free_trial.available(702), failed.get("error"))
    check("xato xabari pul haqida emas", "qoldi" in (failed.get("error") or "") and "so'm" not in failed["error"], failed.get("error"))
    job = await web_jobs.submit(702, "premium_presentation", {"topic": "Qayta", "trial": True})
    check("qayta urinish ishlaydi", (await wait(job["id"]))["status"] == "done")

    print("5) Akkauntlar birlashganda ham bir marta")
    wid = await web_accounts.create_web_user("google", "g-1", "a@gmail.com", "A", "uz")
    job = await web_jobs.submit(wid, "premium_presentation", {"topic": "Saytda", "trial": True})
    await wait(job["id"])
    await Database.create_user(703, "sami", "Sami", "uz")
    check("Telegram akkauntda hali bor", await free_trial.available(703))
    await web_accounts.merge(wid, 703)
    check("sayt akkauntida ishlatilgan bo'lsa, birlashgach ham ishlatilgan", not await free_trial.available(703))


async def browser_checks():
    if not html_render.available():
        check("brauzer o'rnatilgan", False); return
    from playwright.async_api import async_playwright
    from webapp.server import create_web_app

    await Database.create_user(801, "nodir", "Nodir", "uz")
    runner = web.AppRunner(create_web_app()); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=html_render._executable(), args=html_render._LAUNCH_ARGS)

        async def open_home(tid):
            ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
            await ctx.add_cookies([{"name": "edu_session", "value": await web_accounts.create_session(tid), "url": BASE}])
            page = await ctx.new_page()
            await page.goto(BASE + "/", wait_until="networkidle")
            await page.fill("#topic", "Quyosh energiyasi")
            await page.wait_for_selector("#studio .st-main")
            return ctx, page

        ctx, page = await open_home(801)
        check("imtiyoz taklifi ko'rinadi", await page.locator("#trial-on").is_visible())
        await page.click("#trial-on")
        check("imtiyoz yoqildi: varaq soni 5 va o'zgartirib bo'lmaydi",
              await page.locator("#c-num").inner_text() == "5" and await page.locator("#c-minus").count() == 0
              and await page.locator("#c-range").count() == 0)
        check("narx «Bepul», tugma «Bepul yaratish»", await page.locator("#s-price").inner_text() == "Bepul"
              and await page.locator("#go").inner_text() == "Bepul yaratish")
        sent = {}

        async def grab(route, request):
            if request.method == "POST":
                import json
                sent.update(json.loads(request.post_data or "{}"))
            await route.continue_()
        await page.route("**/api/v1/jobs", grab)
        await page.click("#go")
        await page.wait_for_selector("#forge-anim", timeout=8000)
        params = sent.get("params", {})
        check("so'rovda trial: true va 5 slayd", params.get("trial") is True and params.get("slide_count") == 5, params)
        await page.wait_for_timeout(1500)
        await ctx.close()

        ctx, page = await open_home(801)
        check("ishlatilgandan keyin taklif chiqmaydi", await page.locator("#trial-on").count() == 0
              and await page.locator("#c-plus").count() == 1)
        await ctx.close()

        ctx, page = await open_home(701)     # 1-qismda ishlatgan
        check("avval ishlatgan odamga chiqmaydi", await page.locator("#trial").count() == 0)
        await ctx.close()
        await browser.close()
    await runner.cleanup()


async def main():
    await server_checks()
    print("6) Saytda")
    await browser_checks()

asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
