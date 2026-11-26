"""Saytdagi «🧩 3D modellarni o'zim tanlayman» brauzerda (telefon 390px va kompyuter 1366px).

- tekshiruvdan keyin fan bo'yicha tugma («🧬 Biologiya modellarini o'zim tanlayman»);
- oyna: kompyuterda eniga 5 ta, telefonda 3 ta; pastga scroll qilinsa keyingi sahifalar o'zi yuklanadi;
- mavzuga mos modellar boshida («Mavzuga mos» belgisi) va oldindan belgilangan; bo'limlar, qidiruv, kattalashtirish;
- «Boshqa fanlar modellarini ko'rish» — hamma fanlar; ko'pi bilan 12 ta; 1 ta bilan «Tayyor» bo'lmaydi;
- buyurtmaga aynan tanlangan modellar boradi va reja «chosen» rejimida tuziladi (tekshiruv chaqirilmaydi);
- mos 3D topilmagan mavzu ham qo'lda tanlangan modellar bilan yaratiladi;
- serverda: yo'q/takror/ortiqcha model buyurtmadan o'tmaydi.

    python test_sayt_3d_tanlov.py
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
from database import web_accounts, web_store  # noqa: E402
import services.kat3d as kat3d  # noqa: E402
from services import katalog3d, three_d_gate, web_jobs, web_kinds  # noqa: E402,F401
from services.kat3d import tanlov  # noqa: E402
import webapp  # noqa: E402

TMP = tempfile.mkdtemp()
OUT = sys.argv[1] if len(sys.argv) > 1 else TMP
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
webapp.BOT_USERNAME = "Edufayl_bot"

offer = {m["id"] for m in tanlov._offerable()}
BIO = [i for i in ("bio_hayvon_hujayrasi", "bio_mitoxondriya", "bio_dnk_spiral", "bio_osimlik_hujayrasi") if i in offer]
CHECKS, BUILDS = [], []


def result(topic):
    if "plural" in topic.lower():
        return {"ok": False, "mode": "", "ids": [], "partial": False, "sure": True, "names": []}
    return {"ok": True, "mode": "catalog", "ids": BIO, "partial": False, "sure": True,
            "names": [katalog3d.katalog()[i]["nom_uz"] for i in BIO]}


async def fake_check(topic, language="uz", *, fresh=False):
    CHECKS.append(topic)
    return result(topic)


async def fake_build(topic, count, ids, **kw):
    BUILDS.append({"topic": topic, "ids": list(ids), "chosen": kw.get("chosen")})
    from pptx import Presentation
    out = os.path.join(TMP, f"{len(BUILDS)}.pptx")
    Presentation().save(out)
    return out, count


three_d_gate.check = fake_check
three_d_gate.cached = lambda topic, language="uz": result(topic)
kat3d.build_deck = fake_build
web_jobs.KINDS["presentation_3d"].heavy = False


async def main():
    from aiohttp import web
    from playwright.async_api import async_playwright

    from services.premium_presentation import html_render
    from webapp.server import create_web_app

    print("0) Server: tanlovni tozalash")
    clean = tanlov.toza(["yo'q_model", BIO[0], BIO[0], BIO[1]])
    check("yo'q va takror model o'tmaydi", clean == BIO[:2], clean)
    check("bitta model — tanlov hisoblanmaydi (avtomatik)", tanlov.toza([BIO[0]]) == [])
    many = sorted(offer)[:20]
    check("ko'pi bilan 12 ta", len(tanlov.toza(many)) == tanlov.MAX_MODELS)
    p = web_kinds._three_d_normalize({"topic": "Hujayra tuzilishi", "slide_count": 8, "models": BIO[:3]})
    check("buyurtma parametrlarida tanlangan modellar", p.get("models") == BIO[:3], p)
    page = tanlov.royxat("biologiya", suggested=BIO)
    check("mavzuga mos modellar boshida, «mos» belgisi bilan", [i["id"] for i in page["items"][:len(BIO)]] == BIO
          and all(i["mos"] for i in page["items"][:len(BIO)]), page["items"][:5])
    check("sahifalab: 40 tadan, keyingisi bor", len(page["items"]) == tanlov.PAGE and page["next"] == tanlov.PAGE, page["total"])

    if not html_render.available():
        print("brauzer yo'q — o'tkazib yuborildi"); return
    await init_db()
    await Database.create_user(556, "vali", "Vali", "uz")
    await Database.update_user_balance(556, 200000)
    port = 8795; base = f"http://127.0.0.1:{port}"
    runner = web.AppRunner(create_web_app()); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=html_render._executable(), args=html_render._LAUNCH_ARGS)

        async def page_for(vp):
            ctx = await browser.new_context(viewport=vp, device_scale_factor=2)
            await ctx.add_cookies([{"name": "edu_session", "value": await web_accounts.create_session(556), "url": base}])
            pg = await ctx.new_page(); errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            return ctx, pg, errors

        async def open_3d(pg, n, topic):
            await pg.goto(base + f"/?n={n}#yaratish?kind=presentation_3d")
            await pg.wait_for_function("window.__studioReady")
            # oldingi buyurtma natijasi ochiq turishi mumkin — «Yangi mavzu»
            await pg.wait_for_selector("#topic:visible, #f-new", timeout=20000)
            if await pg.locator("#f-new").count():
                await pg.click("#f-new")
            await pg.fill("#topic", topic)
            await pg.wait_for_selector("#studio .st-main")
            await pg.evaluate("document.activeElement && document.activeElement.blur()")

        async def columns(pg):
            return await pg.evaluate("getComputedStyle(document.querySelector('.mp-grid')).gridTemplateColumns.split(' ').length")

        print("1) Kompyuter (1366px): fan tugmasi → oyna → tanlash → buyurtma")
        ctx, pg, errors = await page_for({"width": 1366, "height": 900})
        await open_3d(pg, 1, "Hujayra tuzilishi")
        await pg.wait_for_selector(".c3d-pick [data-a=pick]", timeout=8000)
        label = await pg.inner_text(".c3d-pick [data-a=pick]")
        check("tugmada fan nomi: «Biologiya modellarini o'zim tanlayman»", "Biologiya" in label, label)
        await pg.click(".c3d-pick [data-a=pick]")
        await pg.wait_for_selector(".mp-card")
        check("eniga 5 ta model", await columns(pg) == 5, await columns(pg))
        first = await pg.locator(".mp-card").count()
        on = await pg.eval_on_selector_all(".mp-card.on", "e => e.map(x => x.dataset.id)")
        check("mavzuga mos modellar oldindan belgilangan", on == BIO, on)
        check("«Mavzuga mos» belgisi", await pg.locator(".mp-card .mp-mos").count() == len(BIO))
        fans = await pg.locator(".mp-fans .chip").all_inner_texts()
        check("avval faqat mavzu fani + «Boshqa fanlar modellarini ko'rish»", any("Biologiya" in f for f in fans)
              and any("Boshqa fanlar" in f for f in fans) and len(fans) <= 3, fans)
        await pg.screenshot(path=os.path.join(OUT, "tanlov_kompyuter.png"))
        await pg.eval_on_selector(".mp-scroll", "e => e.scrollTop = e.scrollHeight")
        await pg.wait_for_function(f"document.querySelectorAll('.mp-card').length > {first}", timeout=8000)
        check("pastga scroll — keyingi modellar o'zi yuklandi", await pg.locator(".mp-card").count() > first)
        kats = await pg.locator(".mp-kats .chip").count()
        check("bo'limlar (toifalar) chiplari", kats >= 3, kats)
        await pg.click(".mp-kats .chip >> nth=1")
        await pg.wait_for_timeout(500)
        kat = (await pg.inner_text(".mp-kats .chip.on")).rsplit(" ", 1)[0]
        check("bo'lim tanlandi — faqat shu bo'lim modellari", await pg.locator(".mp-card").count() >= 1, kat)
        await pg.click(".mp-fans .mp-other")
        fans_all = await pg.locator(".mp-fans .chip").count()
        check("«Boshqa fanlar» — hamma fanlar ochildi", fans_all >= 8, fans_all)
        await pg.click(".mp-fans .chip >> text=Kimyo")
        await pg.wait_for_selector(".mp-card")
        await pg.fill(".mp-q", "suv")
        await pg.wait_for_function("[...document.querySelectorAll('.mp-card b')].some(b => /suv/i.test(b.textContent))", timeout=8000)
        names = await pg.locator(".mp-card b").all_inner_texts()
        check("qidiruv: «suv» — suv molekulasi", any("Suv molekulasi" in n for n in names), names[:5])
        await pg.click(".mp-card >> nth=0")
        await pg.click(".mp-card .mp-zoom >> nth=0")
        check("🔍 — katta rasm", await pg.locator(".mp-lb img").count() == 1)
        await pg.click(".mp-lb")
        cnt = await pg.inner_text(".mp-cnt")
        check("hisoblagich: Tanlandi: 5", "Tanlandi: 5" in cnt, cnt)
        await pg.click("[data-m=done]")
        await pg.wait_for_selector(".c3d-pick.on")
        check("tanlov qatori: «Siz tanlagan 5 ta model» va rasmlari", "5 ta model" in await pg.inner_text(".c3d-pick.on")
              and await pg.locator(".c3d-pick.on img").count() == 5)
        check("xulosada: «3D modellar — Siz tanlagan: 5 ta»", "Siz tanlagan: 5 ta" in await pg.inner_text("#sum"))
        await pg.evaluate("window.scrollTo(0, document.querySelector('#c3d').getBoundingClientRect().top + scrollY - 120)")
        await pg.screenshot(path=os.path.join(OUT, "tanlov_natija_kompyuter.png"))
        CHECKS.clear()
        await pg.click("#go")
        await pg.wait_for_selector("#forge-out .forge-act, #forge-out .warn3d", timeout=60000)
        b = BUILDS[-1]
        check("buyurtmaga aynan tanlangan 5 ta model, reja «chosen» rejimida", len(b["ids"]) == 5 and b["ids"][:4] == BIO
              and b["chosen"] is True, b)
        check("xatolar yo'q", not errors, errors)
        await ctx.close()

        print("2) Telefon (390px): eniga 3 ta, chegara, mos topilmagan mavzu")
        ctx, pg, errors = await page_for({"width": 390, "height": 844})
        await open_3d(pg, 2, "Plural Noun")
        await pg.wait_for_selector(".c3d-st.no", timeout=8000)
        check("mos topilmasa ham «3D modellarni o'zim tanlayman» tugmasi", await pg.locator(".c3d-pick [data-a=pick]").count() == 1)
        await pg.click(".c3d-pick [data-a=pick]")
        await pg.wait_for_selector(".mp-card")
        check("telefonda eniga 3 ta", await columns(pg) == 3, await columns(pg))
        box = await pg.locator(".mp-box").bounding_box()
        check("oyna butun ekranda, gorizontal scroll yo'q", box["width"] == 390 and await pg.evaluate(
            "document.querySelector('.mp-scroll').scrollWidth <= document.querySelector('.mp-scroll').clientWidth"), box)
        await pg.screenshot(path=os.path.join(OUT, "tanlov_telefon.png"))
        await pg.click(".mp-card >> nth=0")
        await pg.click("[data-m=done]")
        check("1 ta bilan «Tayyor» — oyna yopilmaydi (kamida 2 ta)", await pg.locator(".mp-box").count() == 1)
        for k in range(1, 14):
            await pg.click(f".mp-card >> nth={k}")
        cnt = await pg.inner_text(".mp-cnt")
        check("ko'pi bilan 12 ta", "Tanlandi: 12" in cnt and await pg.locator(".mp-card.on").count() == 12, cnt)
        await pg.click("[data-m=clear]")
        for k in range(3):
            await pg.click(f".mp-card >> nth={k}")
        await pg.click("[data-m=done]")
        await pg.wait_for_selector(".c3d-pick.on")
        await pg.click("#go")
        await pg.wait_for_selector("#forge-out .forge-act, #forge-out .warn3d", timeout=60000)
        check("mos topilmagan mavzu — qo'lda tanlangan 3 ta model bilan buyurtma", len(BUILDS[-1]["ids"]) == 3
              and BUILDS[-1]["chosen"], BUILDS[-1])
        check("xatolar yo'q", not errors, errors)
        await ctx.close()

        print("3) Avtomatik tanlovga qaytish")
        ctx, pg, errors = await page_for({"width": 390, "height": 844})
        await open_3d(pg, 3, "Hujayra organoidlari")
        await pg.wait_for_selector(".c3d-pick [data-a=pick]", timeout=8000)
        await pg.click(".c3d-pick [data-a=pick]"); await pg.wait_for_selector(".mp-card.on")
        await pg.click("[data-m=done]"); await pg.wait_for_selector(".c3d-pick.on")
        await pg.click("[data-a=auto]")
        check("«Avtomatik tanlovga qaytish» — yana fan tugmasi", await pg.locator(".c3d-pick.on").count() == 0
              and await pg.locator(".c3d-pick [data-a=pick]").count() == 1)
        await pg.click("#go")
        await pg.wait_for_selector("#forge-out .forge-act, #forge-out .warn3d", timeout=60000)
        check("avtomatik: tekshiruv modellari, odatiy reja", BUILDS[-1]["ids"] == BIO and not BUILDS[-1]["chosen"], BUILDS[-1])
        check("xatolar yo'q", not errors, errors)
        await ctx.close()
        await browser.close()
    await runner.cleanup()
    print("skrinshotlar:", OUT)


asyncio.run(main())
print("\n✅ hammasi o'tdi" if not FAILS else f"\n❌ {len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
