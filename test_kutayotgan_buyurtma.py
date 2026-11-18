"""Saytda balans yetmasa: buyurtma saqlanadi, to'lov tushishi bilan o'zi boshlanadi; chala buyurtma qoralamasi.

- /pending: faqat yetishmagan summa (kamida 1 000 so'm); bepul sinov va «sahifani qayta yozish» qabul qilinmaydi;
- har qanday balans qo'shilishi (credit_approved_payment: Click, Payme, Uzum, chek) buyurtmani boshlaydi —
  mijoz saytga qaytmasa ham; yetmasa kutib turadi; ikki to'lov bir vaqtda kelsa ham buyurtma bitta;
- mijoz o'zi buyurtma bersa kutayotgani va qoralamasi o'chadi;
- qoralama serverda saqlanadi (botdan qayta kelganda yangi oynada tiklanadi);
- sayt rejimida bot to'lov haqida yozmaydi;
- brauzerda: «Yaratish» → hamyon (summa tayyor) → to'lov tushdi → buyurtma sahifasi.

    python test_kutayotgan_buyurtma.py
"""
import asyncio, os, sys, tempfile, time, types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import database.database as dbmod
from database.database import Database, init_db
from database import web_store, web_accounts
from services import web_jobs, web_kinds, site_mode  # noqa
import webapp
from aiohttp.test_utils import TestClient, TestServer

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
webapp.WEBAPP_DOMAIN = "edufayl.org"
webapp.BOT_USERNAME = "Edufayl_bot"


class FakeBot:
    def __init__(self): self.msgs, self.docs = [], []
    async def send_message(self, chat_id, text, **kw):
        self.msgs.append((chat_id, text)); return types.SimpleNamespace(message_id=1, chat=types.SimpleNamespace(id=chat_id))
    async def send_document(self, chat_id, document, **kw): self.docs.append(chat_id); return types.SimpleNamespace()
    async def send_photo(self, chat_id, photo, **kw): return types.SimpleNamespace(photo=[types.SimpleNamespace(file_id="p")])
BOT = FakeBot()
webapp.BOT = BOT

RUNS = []
async def fake_run(params, report):
    RUNS.append(params.get("topic"))
    path = os.path.join(TMP, f"r{time.time_ns()}.docx"); open(path, "wb").write(b"DOCX")
    return path, "Referat.docx"
web_jobs.KINDS["referat"].run = fake_run

REFERAT = {"kind": "referat", "params": {"topic": "Globallashuv va iqtisodiyot", "language": "uz", "size": "10_15"}}


async def credit(telegram_id, amount, source="click"):
    from bot.handlers.admin import credit_approved_payment
    user = await Database.get_user(telegram_id)
    pid = await Database.create_payment(user.id, amount, "", source)
    await credit_approved_payment(BOT, Database, await Database.get_payment_by_id(pid), user_message="to'landi")


async def wait_job(telegram_id, n=1):
    for _ in range(100):
        jobs = [j for j in await web_store.list_jobs(telegram_id) if j["status"] == "done"]
        if len(jobs) >= n: return jobs
        await asyncio.sleep(0.05)
    return []


async def main():
    await init_db()
    await Database.create_user(555, "ali", "Ali", "uz")
    await Database.create_user(777, "vali", "Vali", "ru")
    server = TestServer(__import__("webapp.server", fromlist=["x"]).create_web_app())
    client = TestClient(server)
    await client.start_server()
    client.session.cookie_jar.update_cookies({"edu_session": await web_accounts.create_session(555)})
    await Database.update_user_balance(555, 2000)

    print("1) Balans yetmaydi — buyurtma saqlanadi")
    r = await client.post("/api/v1/pending", json=REFERAT); d = await r.json()
    check("narx 5 000, balans 2 000 → yana 3 000", d["enough"] is False and d["price"] == 5000 and d["missing"] == 3000, d)
    p = (await (await client.get("/api/v1/pending")).json())["pending"]
    check("hamyon eslatmasi: nom va qolgan summa", p and p["title"] == "Globallashuv va iqtisodiyot" and p["missing"] == 3000, p)
    r = await client.post("/api/v1/pending", json={**REFERAT, "params": {**REFERAT["params"], "trial": True}})
    check("bepul sinov — qabul qilinmaydi", r.status == 400)
    r = await client.post("/api/v1/pending", json={"kind": "slide_rewrite", "params": {}})
    check("sahifani qayta yozish — qabul qilinmaydi", r.status == 404)

    print("2) Yetmagan to'lov — kutib turadi; yetganda o'zi boshlanadi")
    await credit(555, 1000)
    check("1 000 so'm — hali boshlanmadi", not RUNS and (await web_store.get_pending(555))["job_id"] is None)
    await credit(555, 2000)
    jobs = await wait_job(555)
    check("yana 2 000 — buyurtma o'zi boshlandi va tayyor", len(jobs) == 1 and RUNS == ["Globallashuv va iqtisodiyot"], RUNS)
    check("balansdan narx yechildi (2000+3000-5000=0)", (await Database.get_user(555)).balance == 0)
    d = await (await client.get("/api/v1/pending")).json()
    check("sayt: «to'lov tushdi — tayyorlanmoqda», havola bilan", d["started"] and d["started"]["id"] == jobs[0]["id"], d)
    d = await (await client.get("/api/v1/pending")).json()
    check("eslatma bir marta ko'rsatiladi", d["pending"] is None and not d.get("started"), d)

    print("3) Ikki to'lov bir vaqtda — buyurtma bitta")
    RUNS.clear()
    await client.post("/api/v1/pending", json=REFERAT)
    await Database.update_user_balance(555, 20000)
    results = await asyncio.gather(*[web_jobs.start_pending(555) for _ in range(5)])
    await asyncio.sleep(0.3)
    check("faqat bitta ish boshlandi", sum(1 for r in results if r) == 1 and len(RUNS) == 1, (results, RUNS))

    print("4) Mijoz o'zi buyurtma bersa — kutayotgani va qoralamasi o'chadi")
    await client.post("/api/v1/pending", json={**REFERAT, "params": {**REFERAT["params"], "size": "25_30"}})
    await client.put("/api/v1/draft", json={"draft": {"kind": "referat", "topic": "Eski mavzu"}})
    r = await client.post("/api/v1/jobs", json=REFERAT)
    check("buyurtma qabul qilindi", r.status == 200, await r.text())
    check("kutayotgan va qoralama o'chdi", await web_store.get_pending(555) is None and await web_store.get_draft(555) is None)

    print("5) Qoralama")
    r = await client.put("/api/v1/draft", json={"draft": {"kind": "course_work", "topic": "Xarajatlarni boshqarish", "size": "x"}})
    d = (await (await client.get("/api/v1/draft")).json())["draft"]
    check("saqlandi va qaytdi", r.status == 200 and d["data"]["topic"] == "Xarajatlarni boshqarish", d)
    await client.put("/api/v1/draft", json={"draft": {"kind": "course_work", "topic": "  "}})
    check("mavzu o'chirilsa — qoralama ham", (await (await client.get("/api/v1/draft")).json())["draft"] is None)
    r = await client.put("/api/v1/draft", json={"draft": {"topic": "x" * 300000}})
    check("juda katta qoralama rad etiladi", r.status == 413, r.status)
    r = await client.put("/api/v1/draft", json={"draft": {"topic": "x"}}, headers={"Origin": "https://evil.example"})
    check("begona saytdan PUT — rad etiladi", r.status == 403, r.status)

    print("6) Muddati o'tgan buyurtma eslatilmaydi")
    await client.post("/api/v1/pending", json=REFERAT)
    import aiosqlite
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        await conn.execute("UPDATE web_pending SET created_at = ?", (time.time() - web_store.PENDING_TTL - 5,)); await conn.commit()
    check("6 soatdan keyin yo'q", await web_store.get_pending(555) is None)

    print("7) Sayt rejimida ham to'lov tasdig'i mijozga botda boradi")
    BOT.msgs.clear()
    site_mode.ON = True
    await credit(777, 5000)
    site_mode.ON = False
    check("balans qo'shildi, mijozga tasdiq xabari", (await Database.get_user(777)).balance == 5000 and [m for m in BOT.msgs if m[0] == 777], BOT.msgs)
    await credit(777, 1000)
    check("rejim o'chiq — avvalgidek xabar boradi", any(m[0] == 777 for m in BOT.msgs))

    await client.close()
    await browser_flow()


async def browser_flow():
    from services.premium_presentation import html_render
    if not html_render.available():
        print("8) brauzer yo'q — o'tkazib yuborildi"); return
    from aiohttp import web
    from playwright.async_api import async_playwright
    from webapp.server import create_web_app

    print("8) Brauzerda: yetmasa — hamyon, to'lov tushdi — buyurtma")
    await Database.create_user(901, "sardor", "Sardor", "uz")
    await Database.update_user_balance(901, 2000)
    port = 8798; base = f"http://127.0.0.1:{port}"
    runner = web.AppRunner(create_web_app()); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=html_render._executable(), args=html_render._LAUNCH_ARGS)
        ctx = await browser.new_context(viewport={"width": 390, "height": 844})
        await ctx.add_cookies([{"name": "edu_session", "value": await web_accounts.create_session(901), "url": base}])
        page = await ctx.new_page()
        await page.goto(base + "/#yaratish?kind=referat")
        await page.wait_for_selector("#kind-chips [data-kind=referat].on")
        await page.fill("#topic", "Raqamli iqtisodiyot asoslari")
        await page.wait_for_selector("#s-note .note.wait")
        check("oldindan aytiladi: buyurtma saqlanadi va o'zi boshlanadi", "o‘zi boshlanadi" in await page.inner_text("#s-note"))
        await page.click("#go")
        await page.wait_for_url("**/app#/wallet", timeout=15000)
        await page.wait_for_selector("#pend .note.wait")
        check("hamyonda: buyurtma nomi va yetishmagan 3 000", "Raqamli iqtisodiyot asoslari" in await page.inner_text("#pend")
              and await page.input_value("#amount") == "3000", await page.inner_text("#pend"))
        check("qoralama serverda", ((await web_store.get_draft(901)) or {}).get("data", {}).get("topic") == "Raqamli iqtisodiyot asoslari")
        await credit(901, 3000)      # Click ilovasida to'landi — mijoz saytga qaytmagan
        await page.wait_for_url("**/app#/docs", timeout=20000)
        check("to'lov tushdi — sahifa o'zi buyurtmaga o'tdi", True)
        jobs = await wait_job(901)
        check("buyurtma bajarildi", len(jobs) == 1 and jobs[0]["title"] == "Raqamli iqtisodiyot asoslari")

        print("9) Brauzerda: botdan qayta kelganda qoralama tiklanadi (yangi oyna)")
        await web_store.save_draft(901, {"kind": "course_work", "topic": "Korxonada xarajatlarni boshqarish", "size": ""})
        ctx2 = await browser.new_context(viewport={"width": 390, "height": 844})
        page2 = await ctx2.new_page()
        await page2.goto(f"{base}/go?t={await web_store.start_go(901)}&to=course_work")
        await page2.wait_for_url("**/#yaratish?kind=course_work", timeout=15000)
        await page2.wait_for_function("document.getElementById('topic').value.length > 0", timeout=10000)
        check("mavzu qaytdi", await page2.input_value("#topic") == "Korxonada xarajatlarni boshqarish")
        await ctx2.close()
        ctx3 = await browser.new_context(viewport={"width": 390, "height": 844})
        page3 = await ctx3.new_page()
        await page3.goto(f"{base}/go?t={await web_store.start_go(901)}&to=referat")
        await page3.wait_for_url("**/#yaratish?kind=referat", timeout=15000)
        await page3.wait_for_timeout(1200)
        check("boshqa xizmat bosilgan bo'lsa — eski qoralama aralashmaydi", await page3.input_value("#topic") == "")
        await browser.close()
    await runner.cleanup()


asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
