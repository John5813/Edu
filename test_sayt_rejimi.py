"""«Sayt rejimi» va botdan saytga bir bosishda kirish (/go).

- sukut bo'yicha rejim o'chiq: bot hozirgidek (menyuda «To'lov qilish», router hech narsani ushlamaydi);
- yoqilganda: xizmat tugmasi saytni ochadigan havola beradi, saytda yo'q xizmat — «tez orada», hisob — kabinet;
- /go: GET tokenni ishlatmaydi, POST bir marta sessiya beradi, eski sessiya almashadi, Google akkaunti
  birlashtirish taklif qilinadi; manzil faqat saytning o'zi (ochiq yo'naltirish yo'q);
- Telegram «Login URL» imzosi tekshiriladi, qayta ishlatilmaydi;
- admin tugmasi holatni saqlaydi va bitta bosishda qaytaradi.

    python test_sayt_rejimi.py
"""
import asyncio, hashlib, hmac, os, sys, tempfile, time, types
from urllib.parse import parse_qs, urlparse

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
from database import web_accounts, web_store
from services import web_jobs, web_kinds, site_mode  # noqa
import webapp
from webapp import api
from aiohttp.test_utils import TestClient, TestServer

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
webapp.BOT_USERNAME = "Edufayl_bot"
webapp.WEBAPP_DOMAIN = "edufayl.org"


class Msg:
    """Bot xabari o'rnini bosuvchi: javoblarni yig'adi."""
    def __init__(self, text, uid=555):
        self.text = text
        self.from_user = types.SimpleNamespace(id=uid)
        self.sent = []
    async def answer(self, text, reply_markup=None, **kw):
        self.sent.append((text, reply_markup)); return types.SimpleNamespace()


class State:
    async def clear(self): self.cleared = True


def tg_login(uid, bot_token=None, age=0, **extra):
    fields = {"id": str(uid), "first_name": "Ali", "auth_date": str(int(time.time()) - age), **extra}
    data = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hashlib.sha256((bot_token or config.BOT_TOKEN).encode()).digest()
    fields["hash"] = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
    return fields


async def main():
    await init_db()
    db = Database()
    await Database.create_user(555, "ali", "Ali", "uz")
    await Database.create_user(777, "vali", "Vali", "ru")
    from bot import keyboards
    from bot.handlers import site_mode as handler
    from translations import get_text

    print("1) Sukut: rejim o'chiq — bot avvalgidek")
    check("bazada yozuv yo'q bo'lsa o'chiq", await site_mode.load(db) is False and site_mode.ON is False)
    texts = [b.text for row in keyboards.get_main_keyboard("uz").keyboard for b in row]
    check("menyuda «To'lov qilish» va «Mening hisobim» bor", get_text("uz", "main_menu.payment") in texts
          and get_text("uz", "main_menu.my_account") in texts, texts)
    check("router filtri hech narsani ushlamaydi", handler._on() is False)

    print("2) Admin tugmasi: yoqish va qaytarish")
    kb = keyboards.get_feature_management_keyboard(True, site_mode_enabled=False)
    first = kb.inline_keyboard[0][0]
    check("tugma «O'chirilgan (hammasi botda)»", "O'chirilgan" in first.text and first.callback_data == "toggle_site_mode_on", first.text)
    await site_mode.set(db, True)
    check("yoqildi va saqlandi", site_mode.ON and await db.get_feature_status(site_mode.FEATURE, default=False))
    site_mode.ON = False
    check("qayta ishga tushganda bazadan o'qiladi", await site_mode.load(db) is True)
    texts = [b.text for row in keyboards.get_main_keyboard("uz").keyboard for b in row]
    check("menyuda to'lov o'rnida «Kabinetim»", get_text("uz", "main_menu.payment") not in texts
          and get_text("uz", "site_mode_cabinet_btn") in texts, texts)

    print("3) Bot: xizmat tugmasi saytni ochadi")
    m = Msg(get_text("uz", "main_menu.presentation"))
    await handler.menu_service(m, State(), "uz")
    text, markup = m.sent[-1]
    url = markup.inline_keyboard[0][0].url
    q = parse_qs(urlparse(url).query)
    check("havola edufayl.org/go, kerakli xizmat bilan", url.startswith("https://edufayl.org/go?") and q["to"] == ["premium_presentation"], url)
    check("matnda narx va to'lov so'zi yo'q", not any(w in text.lower() for w in ("so'm", "to'lov", "narx", "karta", "stars")), text)
    m = Msg(get_text("ru", "main_menu.presentation_3d"))
    await handler.menu_service(m, State(), "ru")
    check("saytda yo'q xizmat (3D) — «скоро на сайте», tugmasiz", "скоро" in m.sent[-1][0] and m.sent[-1][1] is None, m.sent[-1])
    m = Msg(get_text("uz", "main_menu.payment"))
    await handler.menu_cabinet(m, State(), "uz")
    check("«To'lov qilish» → kabinet havolasi", "to=profile" in m.sent[-1][1].inline_keyboard[0][0].url)
    check("barcha tillardagi xizmat yozuvlari ushlanadi", {get_text(l, "main_menu.referat") for l in ("uz", "ru", "en")} <= set(handler.MENU_LABELS))
    other = types.SimpleNamespace(data="os:tezis", from_user=types.SimpleNamespace(id=555), message=Msg(""))
    async def _ans(*a, **k): pass
    other.answer = _ans
    await handler.other_service(other, State(), "uz")
    check("«Boshqa xizmatlar» → tezis saytda", "to=thesis" in other.message.sent[-1][1].inline_keyboard[0][0].url)
    check("bepul PPTX→PDF botda qoladi (ushlanmaydi)", "pptx_to_pdf" not in site_mode.OTHER)
    os.environ["SITE_LOGIN_URL"] = "1"
    kb = await handler.site_keyboard(555, "referat", "Ochish")
    btn = kb.inline_keyboard[0][0]
    check("SITE_LOGIN_URL=1 — Telegram «Login URL» tugmasi", btn.login_url and btn.login_url.url == "https://edufayl.org/go/tg?to=referat", btn)
    os.environ["SITE_LOGIN_URL"] = "0"

    print("4) /go: tokenni faqat sahifa skripti ishlatadi")
    server = TestServer(__import__("webapp.server", fromlist=["x"]).create_web_app())
    client = TestClient(server)
    await client.start_server()
    token = q["t"][0]
    r = await client.get("/go", params={"t": token, "to": "premium_presentation"})
    check("GET /go — sahifa, cookie berilmaydi", r.status == 200 and "go.js" in await r.text()
          and "edu_session" not in "".join(r.headers.getall("Set-Cookie", [])))
    r = await client.post("/api/v1/auth/go", json={"token": token, "to": "premium_presentation"})
    d = await r.json()
    check("POST — sessiya va xizmat manzili", r.status == 200 and d["to"] == "/#yaratish?kind=premium_presentation"
          and "edu_session=" in "".join(r.headers.getall("Set-Cookie", [])), d)
    me = (await (await client.get("/api/v1/me")).json())["user"]
    check("sayt shu mijozni taniydi (555, tili uz)", me and me["id"] == 555 and me["language"] == "uz", me)
    r = await client.post("/api/v1/auth/go", json={"token": token})
    check("token ikkinchi marta ishlamaydi (410)", r.status == 410 and (await r.json())["code"] == "expired")

    print("5) Eski sessiya almashadi")
    old_session = client.session.cookie_jar.filter_cookies(server.make_url("/"))["edu_session"].value
    token2 = await web_store.start_go(777)
    await client.post("/api/v1/auth/go", json={"token": token2, "to": "docs"})
    me = (await (await client.get("/api/v1/me")).json())["user"]
    check("telefonda boshqa Telegram akkaunt — endi u ko'rinadi", me["id"] == 777, me)
    check("eski sessiya yopildi", await web_store.session_user(old_session) is None)
    off = await (await client.get("/api/v1/auth/merge")).json()
    check("Telegram→Telegram: birlashtirish taklif qilinmaydi", off["offer"] is None, off)

    print("6) Avval Google bilan kirgan bo'lsa — birlashtirish so'raladi")
    web_id = await web_accounts.create_web_user("google", "g-9", "ali@gmail.com", "Ali", "uz")
    await Database.update_user_balance(web_id, 7000)
    client.session.cookie_jar.clear()
    client.session.cookie_jar.update_cookies({"edu_session": await web_accounts.create_session(web_id)})
    before = (await Database.get_user(555)).balance
    await client.post("/api/v1/auth/go", json={"token": await web_store.start_go(555)})
    offer = (await (await client.get("/api/v1/auth/merge")).json())["offer"]
    check("taklif: email va balans", offer == {"email": "ali@gmail.com", "balance": 7000}, offer)
    r = await client.post("/api/v1/auth/merge", json={"accept": True})
    d = await r.json()
    check("«Ha» — balans qo'shildi, Google akkaunti o'chdi", d.get("moved") == 7000
          and (await Database.get_user(555)).balance == before + 7000 and await Database.get_user(web_id) is None, d)
    check("taklif boshqa chiqmaydi", (await (await client.get("/api/v1/auth/merge")).json())["offer"] is None)

    print("7) Manzil faqat saytning o'zi")
    check("noma'lum joy — bosh sahifa", api.go_target("https://evil.example") == "/" and api.go_target("../x") == "/")
    check("slayd qayta yozish — xizmat emas", api.go_target("slide_rewrite") == "/")
    check("kabinet va hujjatlar", api.go_target("profile") == "/app#/profile" and api.go_target("docs") == "/app#/docs")

    print("8) Telegram «Login URL» imzosi")
    client.session.cookie_jar.clear()
    good = tg_login(777)
    r = await client.get("/go/tg", params={**good, "to": "referat"}, allow_redirects=False)
    check("to'g'ri imzo — sessiya va /go?done=1", r.status == 302 and "done=1" in r.headers["Location"]
          and "edu_session=" in "".join(r.headers.getall("Set-Cookie", [])), r.headers.get("Location"))
    r = await client.get("/go/tg", params={**good, "to": "referat"}, allow_redirects=False)
    check("o'sha havola qayta ishlamaydi", "bad=1" in r.headers["Location"])
    r = await client.get("/go/tg", params={**tg_login(777, bot_token="2:y"), "to": "referat"}, allow_redirects=False)
    check("boshqa bot imzosi rad etiladi", "bad=1" in r.headers["Location"])
    r = await client.get("/go/tg", params={**tg_login(777, age=3600), "to": "referat"}, allow_redirects=False)
    check("eskirgan imzo rad etiladi", "bad=1" in r.headers["Location"])
    forged = dict(tg_login(555)); forged["id"] = "777"
    r = await client.get("/go/tg", params=forged, allow_redirects=False)
    check("o'zgartirilgan ID rad etiladi", "bad=1" in r.headers["Location"])

    print("9) Rejimni o'chirish — hammasi avvalgidek")
    await site_mode.set(db, False)
    texts = [b.text for row in keyboards.get_main_keyboard("uz").keyboard for b in row]
    check("menyuda yana «To'lov qilish»", get_text("uz", "main_menu.payment") in texts and not handler._on())

    await client.close()
    await browser_flow()


async def browser_flow():
    """Haqiqiy brauzer: telefon ekranida /go sahifasi."""
    from services.premium_presentation import html_render
    if not html_render.available():
        print("10) brauzer yo'q — o'tkazib yuborildi"); return
    from aiohttp import web
    from playwright.async_api import async_playwright
    from webapp.server import create_web_app

    print("10) Brauzerda: botdan kelgan mijoz")
    port = 8797
    base = f"http://127.0.0.1:{port}"
    runner = web.AppRunner(create_web_app()); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=html_render._executable(), args=html_render._LAUNCH_ARGS)

        async def phone(lang="uz"):
            ctx = await browser.new_context(viewport={"width": 390, "height": 844}, locale=lang)
            return ctx, await ctx.new_page()

        ctx, page = await phone()
        token = await web_store.start_go(555)
        await page.goto(f"{base}/go?t={token}&to=referat")
        await page.wait_for_url("**/#yaratish?kind=referat", timeout=20000)
        me = await page.evaluate("fetch('/api/v1/me').then(r => r.json())")
        check("kirgan holda, referat oynasida ochildi", me["user"] and me["user"]["id"] == 555, me)
        await page.goto(f"{base}/go?t={token}&to=docs")
        await page.wait_for_url("**/app#/docs", timeout=20000)
        check("eskirgan havola, lekin sessiya bor — baribir kerakli joyga", True)
        await ctx.close()

        ctx, page = await phone("ru")
        await page.goto(f"{base}/go?t={token}&to=referat")
        await page.wait_for_selector("#go a.btn")
        text = await page.inner_text("#go")
        href = await page.get_attribute("#go a.btn", "href")
        check("sessiyasiz eskirgan havola — tushuntirish va «botga qaytish»", "t.me/Edufayl_bot" in href, href)
        check("ruscha brauzerda matn ruscha", "Ссылка устарела" in text and "Вернуться в бот" in text, text)
        check("token manzil satrida qolmaydi", "t=" not in page.url, page.url)
        await ctx.close()

        ctx, page = await phone()
        web_id = await web_accounts.create_web_user("google", "g-10", "vali@gmail.com", "Vali", "uz")
        await Database.update_user_balance(web_id, 3000)
        await ctx.add_cookies([{"name": "edu_session", "value": await web_accounts.create_session(web_id),
                                "url": base}])
        before = (await Database.get_user(777)).balance
        await page.goto(f"{base}/go?t={await web_store.start_go(777)}&to=course_work")
        await page.wait_for_selector("#m-yes")
        check("Google akkaunti ko'rsatildi", "vali@gmail.com" in await page.inner_text("#go"))
        await page.click("#m-yes")
        await page.wait_for_url("**/#yaratish?kind=course_work", timeout=20000)
        check("«Ha» — birlashdi, kurs ishi oynasiga o'tdi", (await Database.get_user(777)).balance == before + 3000)
        await ctx.close()
        await browser.close()
    await runner.cleanup()


asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
