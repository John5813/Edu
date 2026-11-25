"""Saytdagi «🧊 3D taqdimot» brauzerda (telefon 390px va kompyuter 1366px).

- 3D tanlanganda: namuna mavzular (bosilsa — mavzu maydoniga), sariq ogohlantirish «Yaratish» yonida;
- mavzu yozilishi bilan bepul tekshiruv: mos bo'lmasa — «⚠️ topilmadi» va bir bosishda Zamonaviy/Infografik/
  boshqa mavzu; «Yaratish» bosilsa ham pul yechilmaydi, buyurtma yaratilmaydi;
- mos bo'lsa — modellar nomi va rasmi; buyurtma: animatsiyada aynan tanlangan slaydlar soni (8, 10/12 emas);
- tayyor 3D: «Ko'rish» — sahifalar zaxira rasmlari bilan (haqiqiy 3D PPTX, LibreOffice), tepada sariq ogohlantirish;
- bajarilmagan 3D: «Qayta urinish» o'rniga «Zamonaviy bilan yaratish» (shu mavzu bilan) va «Boshqa mavzu yozish»;
- keyingi buyurtma oxirgi tanlangan tur (3D) bilan ochiladi.

    python test_sayt_3d_brauzer.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
import time

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
from services import katalog3d, three_d_gate, web_decks, web_jobs, web_kinds  # noqa: E402,F401
from services.web_jobs import JobError  # noqa: E402
import webapp  # noqa: E402

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")

webapp.BOT_USERNAME = "Edufayl_bot"
CHECKS = []
PREVIEW_IDS = [i for i in katalog3d.katalog() if katalog3d.preview_yoli(i)][:3]
SKULL = os.path.join(TMP, "skull.pptx")


async def fake_check(topic, language="uz", *, fresh=False):
    CHECKS.append(topic)
    if "plural" in topic.lower():
        return {"ok": False, "mode": "", "ids": [], "partial": False, "sure": True, "names": []}
    return {"ok": True, "mode": "catalog", "ids": PREVIEW_IDS, "partial": False, "sure": True,
            "names": ["Quyosh", "Yer sayyorasi", "Mars sayyorasi"]}


async def fake_build(topic, count, ids, **kw):
    if "xato" in topic.lower():
        raise JobError(three_d_gate.NO_3D, "no_3d")
    out = os.path.join(TMP, f"{time.time_ns()}.pptx")
    shutil.copyfile(SKULL, out)
    return out, count


three_d_gate.check = fake_check
kat3d.build_deck = fake_build
web_jobs.KINDS["presentation_3d"].heavy = False      # og'ir navbat ishchisi (bot) testda ishlamaydi
norm = lambda t: (t or "").replace(" ", " ").replace("\xa0", " ")


async def main():
    from services.med3d.deck import DEMO_PLAN, build
    from services.premium_presentation import html_render
    if not html_render.available() or not shutil.which("soffice"):
        print("brauzer yoki LibreOffice yo'q — o'tkazib yuborildi"); return
    build(DEMO_PLAN, SKULL)                                # haqiqiy 3D PPTX (3 slayd, zaxira rasmlari bilan)
    from aiohttp import web
    from playwright.async_api import async_playwright
    from webapp.server import create_web_app

    await init_db()
    await Database.create_user(555, "ali", "Ali", "uz")
    await Database.update_user_balance(555, 100000)
    port = 8794; base = f"http://127.0.0.1:{port}"
    runner = web.AppRunner(create_web_app()); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()

    async def balance():
        return int((await Database.get_user(555)).balance)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=html_render._executable(), args=html_render._LAUNCH_ARGS)

        async def page_for(vp):
            ctx = await browser.new_context(viewport=vp)
            await ctx.add_cookies([{"name": "edu_session", "value": await web_accounts.create_session(555), "url": base}])
            page = await ctx.new_page(); errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            return ctx, page, errors

        async def open_3d(page, n, topic):
            await page.goto(base + f"/?n={n}#yaratish?kind=presentation_3d")
            await page.wait_for_function("window.__studioReady")
            await page.fill("#topic", topic)
            await page.wait_for_selector("#studio .st-main")
            await page.evaluate("document.activeElement && document.activeElement.blur()")

        print("1) Telefon (390px): mos bo'lmagan mavzu — pul yechilmaydi")
        ctx, page, errors = await page_for({"width": 390, "height": 844})
        await open_3d(page, 1, "Plural Noun")
        await page.wait_for_selector(".c3d-st.no", timeout=8000)
        check("mavzu yozilishi bilan tekshirildi: «⚠️ mos 3D topilmadi», «pul yechilmaydi»",
              "topilmadi" in await page.inner_text(".c3d-st.no") and "Pul yechilmaydi" in await page.inner_text(".c3d-st.no"))
        check("bir bosishda: Zamonaviy / Infografik / boshqa mavzu", await page.locator(".c3d-act [data-a]").count() == 3)
        await page.locator(".c3d-st.no").scroll_into_view_if_needed()
        await page.screenshot(path=os.path.join(TMP, "phone_no3d.png"))
        warn = await page.locator("#studio .warn3d").bounding_box()
        go = await page.locator("#go").bounding_box()
        check("sariq ogohlantirish «Yaratish» yonida (telefonda ham ko'rinadi)", warn is not None and go is not None
              and "PowerPoint" in await page.inner_text("#studio .warn3d"), (warn, go))
        before = await balance()
        await page.click("#go"); await page.wait_for_timeout(800)
        jobs = await web_store.list_jobs(555, 10)
        check("«Yaratish» bosildi — buyurtma yaratilmadi, pul yechilmadi", not jobs and await balance() == before, (jobs, before))
        await page.click(".c3d-act [data-a=modern]"); await page.wait_for_timeout(300)
        check("«Zamonaviy bilan yaratish» — tur almashdi, mavzu o'sha", "on" in (await page.get_attribute("#ptypes [data-t=modern]", "class")).split()
              and await page.input_value("#topic") == "Plural Noun")
        check("xatolar yo'q", not errors, errors)
        await ctx.close()

        print("2) Telefon: namuna mavzu → mos → buyurtma (aniq slaydlar soni)")
        ctx, page, errors = await page_for({"width": 390, "height": 844})
        await open_3d(page, 2, "abc")
        chips = await page.locator("#ex3d .chip").all_inner_texts()
        check("3D bilan yaxshi chiqadigan namuna mavzular", len(chips) >= 6 and "Quyosh tizimi sayyoralari" in chips, chips)
        await page.click("#ex3d .chip >> text=Quyosh tizimi sayyoralari")
        await page.wait_for_selector(".c3d-st.ok", timeout=8000)
        check("namuna bosildi — mavzu maydonida", await page.input_value("#topic") == "Quyosh tizimi sayyoralari")
        check("«✅ 3D modellar bor», nomlari va rasmlari", "Yer sayyorasi" in await page.inner_text(".c3d-st.ok")
              and await page.locator(".c3d-pv img").count() == len(PREVIEW_IDS))
        ok_img = await page.evaluate("Promise.all([...document.querySelectorAll('.c3d-pv img')].map(i=>i.decode().then(()=>i.naturalWidth>0).catch(()=>false)))")
        check("model rasmlari yuklandi (/api/v1/3d/model/<id>.jpg)", ok_img and all(ok_img), ok_img)
        sent = []
        page.on("request", lambda r: sent.append(r.url) if "/api/v1/3d/check" in r.url else None)
        await page.click("#go")
        await page.wait_for_selector(".forge .fg-card")
        cards = await page.locator(".forge .fg-card").count()
        check("animatsiyada aynan 8 slayd (avval 10, keyin 12 chiqardi)", cards == 8, cards)
        check("«Yaratish» da brauzer qayta tekshirmaydi (natija eslab qolingan)", not sent, sent)
        try:
            await page.wait_for_selector("#forge-out .warn3d", timeout=90000)
        except Exception:
            print("   DEBUG jobs:", [(j["status"], j["stage"], j["error"]) for j in await web_store.list_jobs(555, 10)],
                  await page.inner_text("#forge-box"))
            raise
        check("tayyor: sariq ogohlantirish va «Ko'rish»", await page.locator("#forge-out a.btn >> text=Ko‘rish").count() == 1)
        jobs = await web_store.list_jobs(555, 10)
        job = jobs[0]
        check("fayl nomi qisqa va toza", job["result_name"] == "Quyosh_tizimi_sayyoralari_3D.pptx", job["result_name"])
        await page.goto(base + f"/app#/job/{job['id']}")
        await page.wait_for_selector("#thumbs .th img")
        await page.wait_for_function("document.querySelector('#simg') && document.querySelector('#simg').naturalWidth > 0")
        check("«Ko'rish»: sahifalar zaxira rasmlari bilan (3 sahifa) va tepada sariq ogohlantirish",
              await page.locator("#thumbs .th").count() == 3 and await page.locator("#view .warn3d").count() == 1)
        check("3D ko'rinishda tahrirlash tugmalari yo'q (faqat ko'rish)", await page.locator("#t-ptext, #edit").count() == 0)
        await page.screenshot(path=os.path.join(TMP, "phone_view.png"))
        await page.goto(base + "/app#/docs"); await page.wait_for_selector("#view .job")
        check("«Hujjatlarim»: 3D buyurtmada «Ko'rish»", await page.locator(f"#view a[href='#/job/{job['id']}']").count() >= 1)
        check("xatolar yo'q", not errors, errors)
        await ctx.close()

        print("3) Keyingi buyurtma — oxirgi tur (3D)")
        ctx, page, errors = await page_for({"width": 390, "height": 844})
        await page.goto(base + "/?n=3")      # xeshsiz: qoralama yo'q
        await page.wait_for_function("window.__studioReady")
        await page.evaluate("localStorage.setItem('edu_last_type', JSON.stringify({kind:'presentation_3d', volume:'kam'}))")
        await page.goto(base + "/?n=4")
        await page.wait_for_function("window.__studioReady")
        await page.fill("#topic", "Yangi mavzu"); await page.wait_for_selector("#studio .st-main")
        check("forma 3D bilan ochildi (Infografik emas)", "on" in (await page.get_attribute("#ptypes [data-t='3d']", "class")).split())
        await ctx.close()

        print("4) Bajarilmagan 3D: «Qayta urinish» tuzog'i yo'q")
        ctx, page, errors = await page_for({"width": 390, "height": 844})
        await open_3d(page, 5, "Xato mavzu")
        await page.wait_for_selector(".c3d-st.ok", timeout=8000)
        await page.click("#go")
        await page.wait_for_selector("#forge-out .note.bad", timeout=60000)
        check("xato kartasida: «Zamonaviy bilan yaratish» va «Boshqa mavzu yozish», «Qayta urinish» yo'q",
              await page.locator("#f-modern").count() == 1 and await page.locator("#f-topic").count() == 1
              and await page.locator("#f-again").count() == 0)
        failed = [j for j in await web_store.list_jobs(555, 10) if j["status"] == "failed"][0]
        await page.click("#f-modern"); await page.wait_for_timeout(400)
        check("«Zamonaviy bilan yaratish» — shu mavzu, tur Zamonaviy", await page.input_value("#topic") == "Xato mavzu"
              and "on" in (await page.get_attribute("#ptypes [data-t=modern]", "class")).split())
        await page.goto(base + f"/app#/job/{failed['id']}"); await page.wait_for_selector("#view .pill.bad")
        href = await page.get_attribute("#view a.btn >> nth=0", "href")
        check("«Hujjatlarim» dagi xato sahifasi: shu mavzu bilan Zamonaviy havolasi", "type=modern" in href and "topic=Xato" in href, href)
        await page.goto(base + href)
        await page.wait_for_function("window.__studioReady"); await page.wait_for_selector("#studio .st-main")
        check("havola bosildi — forma shu mavzu va Zamonaviy bilan ochildi", await page.input_value("#topic") == "Xato mavzu"
              and "on" in (await page.get_attribute("#ptypes [data-t=modern]", "class")).split())
        check("xatolar yo'q", not errors, errors)
        await ctx.close()

        print("5) Kompyuter (1366px)")
        ctx, page, errors = await page_for({"width": 1366, "height": 900})
        await open_3d(page, 6, "Quyosh tizimi sayyoralari")
        await page.wait_for_selector(".c3d-st.ok", timeout=8000)
        side = await page.evaluate("(()=>{const w=document.querySelector('.st-side .warn3d').getBoundingClientRect(),g=document.querySelector('.st-go').getBoundingClientRect(),m=document.querySelector('.st-main').getBoundingClientRect();return {wl:w.left,mr:m.right,gap:g.top-w.bottom}})()")
        check("o'ng ustunda sariq ogohlantirish «Yaratish» ning ustida", side["wl"] > side["mr"] and 0 <= side["gap"] < 60, side)
        await page.evaluate("window.scrollTo(0, document.querySelector('#c3d').getBoundingClientRect().top + scrollY - 120)")
        await page.wait_for_timeout(300)
        await page.screenshot(path=os.path.join(TMP, "desk_studio.png"))
        check("xatolar yo'q", not errors, errors)
        await ctx.close()
        await browser.close()
    await runner.cleanup()
    print("skrinshotlar:", TMP)


asyncio.run(main())
print("\n✅ hammasi o'tdi" if not FAILS else f"\n❌ {len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
