"""Bosh sahifadagi yaratish oynasi (studio.js): narx doim ko'rinib tursin.

- telefonda (bir ustunli ko'rinish) «Narx + Yaratish» ekran pastiga yopishgan panel: slaydlar soni qayerda
  tanlanmasin, narx ko'rinadi va darhol yangilanadi; «Botga qaytish» tugmasi panel ustida, ustma-ust emas;
- taqdimot slaydlari soni tugmalari (5…30) va +/− hisoblagich yonida shu son uchun narx;
- mustaqil ish hajm tugmalari telefonda keyingi qatorga o'tadi — 25–30 varoq ham ko'rinadi;
- kompyuterda o'ng ustun avvalgidek (panel emas), pastga aylantirilganda ham narx ko'rinib turadi.

    python test_sayt_narx_panel.py
"""
import asyncio
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


import database.database as dbmod  # noqa: E402
from database.database import Database, init_db  # noqa: E402
from database import web_accounts  # noqa: E402
from services import web_jobs  # noqa: E402
import webapp  # noqa: E402

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
webapp.BOT_USERNAME = "Edufayl_bot"

STATE = """() => { const g = document.querySelector('.st-go'), b = g.getBoundingClientRect(), t = document.querySelector('#tg-back');
  const tb = t && t.getBoundingClientRect();
  return {pos: getComputedStyle(g).position, display: getComputedStyle(g).display, top: b.top, bottom: b.bottom, left: b.left,
    right: b.right, vh: innerHeight, vw: innerWidth, sw: document.documentElement.scrollWidth,
    price: document.querySelector('#s-price').textContent, cprice: (document.querySelector('#c-price') || {}).textContent || '',
    tgBottom: tb ? tb.bottom : null}; }"""
norm = lambda t: (t or "").replace(" ", " ").replace("\xa0", " ")


async def main():
    from services.premium_presentation import html_render, pipeline
    if not html_render.available():
        print("brauzer yo'q — o'tkazib yuborildi"); return
    from aiohttp import web
    from playwright.async_api import async_playwright
    from webapp.server import create_web_app

    await init_db()
    await Database.create_user(555, "ali", "Ali", "uz")
    await Database.update_user_balance(555, 100000)
    port = 8795; base = f"http://127.0.0.1:{port}"
    runner = web.AppRunner(create_web_app()); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()
    fmt = lambda n: f"{n:,}".replace(",", " ")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=html_render._executable(), args=html_render._LAUNCH_ARGS)

        async def page_for(vp, n):
            ctx = await browser.new_context(viewport=vp)
            await ctx.add_cookies([{"name": "edu_session", "value": await web_accounts.create_session(555), "url": base}])
            page = await ctx.new_page(); errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            return ctx, page, errors

        async def studio(page, kind, n):
            await page.goto(base + f"/?n={n}#yaratish?kind={kind}")
            await page.wait_for_function("window.__studioReady")
            await page.fill("#topic", "Kiberxavfsizlik asoslari")
            await page.wait_for_selector("#studio #s-price", state="attached")
            await page.wait_for_timeout(500)                 # xeshdan keyin mavzu maydoni fokuslanadi
            await page.evaluate("document.activeElement && document.activeElement.blur()")

        print("1) Telefon (390px): taqdimot")
        ctx, page, errors = await page_for({"width": 390, "height": 844}, 1)
        await studio(page, "premium_presentation", 1)
        await page.evaluate("document.querySelector('#c-pop').scrollIntoView({block:'center'})")
        await page.wait_for_timeout(200)
        st = await page.evaluate(STATE)
        check("«Narx + Yaratish» — ekran pastiga yopishgan panel", st["pos"] == "fixed" and st["display"] != "none"
              and abs(st["bottom"] - st["vh"]) <= 1 and st["left"] == 0 and st["right"] == st["vw"], st)
        check("«Botga qaytish» panel ustida (ustma-ust emas)", st["tgBottom"] is not None and st["tgBottom"] <= st["top"], st)
        check("gorizontal siljish yo'q", st["sw"] <= st["vw"], st)
        chips = await page.locator("#c-pop .chip").all_inner_texts()
        got = [(norm(c).split()[0], " ".join(norm(c).split()[1:])) for c in chips]
        want = [(str(n), fmt(pipeline.price_for(n))) for n in (5, 8, 10, 12, 15, 20, 25, 30)]
        check("slaydlar soni tugmalarida narx (5 — 3 000 … 30 — 16 000)", got == want, got)
        await page.click("#c-pop [data-n='30']")
        st = await page.evaluate(STATE)
        check("30 slayd — narx panelda va hisoblagich yonida darhol 16 000",
              "16 000" in norm(st["price"]) and "16 000" in norm(st["cprice"]), st)
        await page.click("#c-minus")
        st = await page.evaluate(STATE)
        p29 = fmt(pipeline.price_for(29))
        check(f"− bosildi (29) — narx {p29} ikkala joyda", p29 in norm(st["price"]) and p29 in norm(st["cprice"]), st)
        check("xatolar yo'q", not errors, errors)
        await ctx.close()

        print("2) Telefon: mustaqil ish hajmi")
        ctx, page, errors = await page_for({"width": 390, "height": 844}, 2)
        await studio(page, "independent_work", 2)
        await page.evaluate("document.querySelector('#st-size').scrollIntoView({block:'center'})")
        inview = await page.evaluate("[...document.querySelectorAll('#st-size .chip')].map(c=>{const b=c.getBoundingClientRect();return b.left>=0&&b.right<=innerWidth})")
        check("hajm tugmalari keyingi qatorga o'tadi — hammasi (25–30 varoq ham) ko'rinadi", inview and all(inview), inview)
        btns = page.locator("#st-size .chip")
        await btns.nth(await btns.count() - 1).click()
        st = await page.evaluate(STATE)
        last = " ".join(norm(await btns.nth(await btns.count() - 1).inner_text()).split()[-2:])
        check("eng katta hajm tanlandi — paneldagi narx yangilandi", st["pos"] == "fixed" and last in norm(st["price"]), (last, st))
        await ctx.close()

        print("3) Kompyuter (1366px): o'ng ustun buzilmagan")
        ctx, page, errors = await page_for({"width": 1366, "height": 900}, 3)
        await studio(page, "premium_presentation", 3)
        await page.evaluate("document.querySelector('#c-pop').scrollIntoView({block:'center'})")
        await page.click("#c-pop [data-n='20']")
        st = await page.evaluate(STATE)
        side = await page.evaluate("(()=>{const s=document.querySelector('.st-side').getBoundingClientRect(),m=document.querySelector('.st-main').getBoundingClientRect();return {sideLeft:s.left, mainRight:m.right, sum:getComputedStyle(document.querySelector('.st-sum')).display}})()")
        check("panel emas: o'ng ustunda, xulosa bilan", st["pos"] != "fixed" and side["sideLeft"] > side["mainRight"] and side["sum"] != "none", (st, side))
        check("pastga aylantirilganda ham narx ko'rinadi va yangilanadi (20 — 10 000)",
              0 <= st["top"] and st["bottom"] <= st["vh"] and "10 000" in norm(st["price"]), st)
        check("pastki bo'shliq qo'shilmagan (panel faqat telefonda)", await page.evaluate("getComputedStyle(document.body).paddingBottom") == "0px")
        check("xatolar yo'q", not errors, errors)
        await ctx.close()
        await browser.close()
    await runner.cleanup()


asyncio.run(main())
print("\n✅ hammasi o'tdi" if not FAILS else f"\n❌ {len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
