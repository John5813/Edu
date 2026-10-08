"""Bosh sahifa: kirmagan odamga kirish/ro'yxatdan o'tish oynasi o'zi ochiladi.

- har tashrifda bir marta (yopsa, sahifani yangilaganda qayta chiqmaydi; yangi tashrifda yana chiqadi);
- kirgan odamga chiqmaydi;
- qidiruv botlariga (Googlebot, Yandex) chiqmaydi — Google sahifani oyna bilan yopilgan holda ko'rmasin;
- telefonda ham to'liq ko'rinadi, «Yopish» ishlaydi.

    python test_sayt_kirish_oynasi.py
"""
import asyncio, os, sys, tempfile

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
from database import web_accounts
from services.premium_presentation import html_render
import webapp
from aiohttp import web

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "t.db")
webapp.BOT_USERNAME = "Edufayl_bot"
PORT = 8795
BASE = f"http://127.0.0.1:{PORT}"
config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET = "cid", "secret"

PHONE_UA = ("Mozilla/5.0 (Linux; Android 14; SM-A546E) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Mobile Safari/537.36")
GOOGLEBOT_UA = ("Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
# Avtomatlashtirilgan brauzer belgisini yashiramiz — oyna haqiqiy foydalanuvchiga qanday chiqsa, shunday sinalsin.
REAL_USER = "Object.defineProperty(navigator, 'webdriver', {get: () => false});"
MODAL = ".modal .box.login"


async def main():
    if not html_render.available():
        check("brauzer o'rnatilgan", False); return
    from playwright.async_api import async_playwright
    from webapp.server import create_web_app

    await init_db()
    await Database.create_user(901, "ali", "Ali Valiyev", "uz")
    runner = web.AppRunner(create_web_app()); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=html_render._executable(), args=html_render._LAUNCH_ARGS)

        async def visit(ua=PHONE_UA, real=True, cookie=None, path="/"):
            ctx = await browser.new_context(viewport={"width": 390, "height": 844}, user_agent=ua)
            if real:
                await ctx.add_init_script(REAL_USER)
            if cookie:
                await ctx.add_cookies([{"name": "edu_session", "value": cookie, "url": BASE}])
            page = await ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            await page.goto(BASE + path, wait_until="networkidle")
            await page.wait_for_timeout(500)
            return ctx, page, errors

        # 1) Birinchi tashrif: oyna o'zi ochiladi
        ctx, page, errors = await visit()
        check("kirmagan odamga oyna o'zi ochiladi", await page.locator(MODAL).is_visible())
        check("oynada Google va Telegram tugmalari", await page.locator("#lg-gbtn").is_visible()
              and await page.locator("#lg-tg").is_visible())
        box = await page.locator(MODAL).bounding_box()
        check("telefonda oyna ekranga sig'adi", box and box["x"] >= 0 and box["x"] + box["width"] <= 390, box)
        await page.screenshot(path=os.path.join(TMP, "oyna.png"))
        await page.click("#lg-x")
        check("«Yopish» bosilsa yopiladi", await page.locator(".modal").count() == 0)
        await page.reload(wait_until="networkidle"); await page.wait_for_timeout(500)
        check("shu tashrifda qayta chiqmaydi (yangilansa ham)", await page.locator(".modal").count() == 0)
        await page.click("#hd-login")
        check("«Kirish» tugmasi baribir oynani ochadi", await page.locator(MODAL).is_visible())
        check("JavaScript xatosi yo'q", not errors, errors)
        await ctx.close()

        # 2) Yangi tashrif (yangi brauzer seansi) — yana chiqadi
        ctx, page, _ = await visit()
        check("yangi tashrifda yana chiqadi", await page.locator(MODAL).is_visible())
        await ctx.close()

        # 3) Kirgan odamga chiqmaydi
        ctx, page, _ = await visit(cookie=await web_accounts.create_session(901))
        check("kirgan odamga chiqmaydi", await page.locator(".modal").count() == 0
              and await page.locator("#hd-login").count() == 0)
        await ctx.close()

        # 4) Qidiruv botlari — oyna yo'q, sahifa matni ochiq
        ctx, page, _ = await visit(ua=GOOGLEBOT_UA, real=True)
        check("Googlebot'ga chiqmaydi", await page.locator(".modal").count() == 0)
        # Googlebot inglizcha brauzer — sahifa baribir asl o'zbekcha matnda ko'rinishi kerak.
        check("Googlebot sahifani o'zbekcha ko'radi",
              (await page.title()).startswith("Edufayl — taqdimot, mustaqil ish")
              and await page.locator('.foot-links a[href="/mustaqil-ish"]').inner_text() == "Mustaqil ish",
              await page.title())
        html = await page.content()
        check("bosh sahifa: to'liq canonical va JSON-LD (Organization, WebSite)",
              f'href="{BASE}/"' in html and '"@type":"Organization"' in html and "__ORIGIN__" not in html)
        await ctx.close()
        ctx, page, _ = await visit()
        check("oddiy inglizcha brauzerda sayt tarjima qilinadi (foydalanuvchilar uchun o'zgarmadi)",
              (await page.title()).startswith("Edufayl — presentations"), await page.title())
        await ctx.close()
        ctx, page, _ = await visit(ua="Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)")
        check("YandexBot'ga chiqmaydi", await page.locator(".modal").count() == 0)
        await ctx.close()

        # 5) Telegram ichidagi brauzer — oddiy foydalanuvchi, oyna chiqadi
        ctx, page, _ = await visit(ua=PHONE_UA + " Telegram-Android/11.2.3 (Samsung SM-A546E; Android 14)")
        check("Telegram ichidagi brauzerda chiqadi", await page.locator(MODAL).is_visible())
        await ctx.close()

        # 6) Boshqa sahifalarda (do'kon) avtomatik chiqmaydi
        ctx, page, _ = await visit(path="/shop")
        check("do'kon sahifasida avtomatik chiqmaydi", await page.locator(".modal").count() == 0)
        await ctx.close()

        await browser.close()
    await runner.cleanup()


asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
