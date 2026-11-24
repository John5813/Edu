"""Saytda taqdimot: 4 tur (Infografik, Zamonaviy, Klassik, 3D — tez orada), rang va rasm manbasi.

- «Taqdimot» tanlanishi bilan (mavzudan oldin) 4 ta namunali kartochka; 3D bosilmaydi;
- Infografik → zamonaviy taqdimot, matn hajmi "kam", uslub so'ralmaydi; Zamonaviy → "kop", 5 uslub;
- Klassik → shablonli taqdimot (simple_presentation): shablon, slaydlar soni, reja slaydi, ikonka;
- rang (botdagi 6 ta rang yoki avto) va rasm manbasi (aralash / internet / AI) taqdimotga yetadi;
  bepul sinovda — rang yo'q, rasmlar faqat internetdan;
- ruscha sayt: yangi matnlar tarjima qilingan.

    python test_sayt_taqdimot_turlari.py
"""
import asyncio, os, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import database.database as dbmod
from database.database import Database, init_db
from database import web_accounts, web_store
from services import web_jobs, web_kinds
import webapp

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
webapp.BOT_USERNAME = "Edufayl_bot"
SEEN = []


def fake_file(name):
    path = os.path.join(TMP, f"{time.time_ns()}.pptx"); open(path, "wb").write(b"PPTX"); return path, name


async def fake_premium(params, report):
    SEEN.append(("premium", dict(params))); return fake_file("Taqdimot.pptx")


async def fake_simple(params, report):
    SEEN.append(("simple", dict(params))); return fake_file("Taqdimot.pptx")


web_jobs.KINDS["premium_presentation"].run = fake_premium
web_jobs.KINDS["simple_presentation"].run = fake_simple


async def main():
    print("1) Server: rang va rasm manbasi")
    norm = web_jobs.KINDS["premium_presentation"].normalize
    p = norm({"topic": "Samarqand tarixi", "theme": "yashil", "photos": "ai", "volume": "kam"})
    check("tanlangan rang va AI rasmlar saqlanadi", p["theme"] == "yashil" and p["photos"] == "ai" and p["volume"] == "kam", p)
    p = norm({"topic": "Samarqand tarixi", "theme": "sariq", "photos": "boshqa"})
    check("noma'lum rang — avto, noma'lum manba — aralash", p["theme"] == "" and p["photos"] == "mix", p)
    p = norm({"topic": "Samarqand tarixi", "theme": "yashil", "photos": "ai", "trial": True})
    check("bepul sinov: rangsiz, rasm faqat internetdan", p["theme"] == "" and p["photos"] == "web", p)
    from webapp import api
    cat = api._catalog()
    check("katalogda 6 ta rang (botdagi bilan bir xil) va Klassik", [c["key"] for c in cat["colors"]] == list(web_kinds.COLOR_KEYS)
          and any(k["key"] == "simple_presentation" for k in cat["kinds"]) and cat["templates"], [c["key"] for c in cat["colors"]])

    from services.premium_presentation import html_render
    if not html_render.available():
        print("brauzer yo'q — qolgani o'tkazib yuborildi"); return
    from aiohttp import web
    from playwright.async_api import async_playwright
    from webapp.server import create_web_app

    await init_db()
    await Database.create_user(555, "ali", "Ali", "uz")
    await Database.update_user_balance(555, 100000)
    port = 8796; base = f"http://127.0.0.1:{port}"
    runner = web.AppRunner(create_web_app()); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", port).start()

    async def wait_seen(n):
        for _ in range(100):
            if len(SEEN) >= n: return True
            await asyncio.sleep(0.1)
        return False

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=html_render._executable(), args=html_render._LAUNCH_ARGS)

        async def phone(lang="uz"):
            ctx = await browser.new_context(viewport={"width": 390, "height": 844}, locale=lang)
            await ctx.add_cookies([{"name": "edu_session", "value": await web_accounts.create_session(555), "url": base}])
            page = await ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            return ctx, page, errors

        print("2) «Taqdimot» — mavzudan oldin 4 ta tur")
        ctx, page, errors = await phone()
        await page.goto(base + "/#yaratish?kind=premium_presentation")
        await page.wait_for_selector("#ptypes .ptype")
        names = await page.locator("#ptypes .ptype b").all_inner_texts()
        check("4 ta tur namunasi bilan", names == ["🎨 Infografik", "📝 Zamonaviy", "📄 Klassik", "🧊 3D taqdimot"]
              and await page.locator("#ptypes .ptype img").count() == 4, names)
        check("studiya hali yopiq (mavzu yozilmagan)", not await page.locator("#studio #go").count())
        await page.click("#ptypes [data-t='3d']")
        await page.fill("#topic", "Yurak tuzilishi"); await page.wait_for_selector("#studio #st-size")
        check("3D tanlanadi: slaydlar soni, PowerPoint eslatmasi, oldindan 8 slayd — 12 000",
              "on" in (await page.get_attribute("#ptypes [data-t='3d']", "class")).split()
              and "PowerPoint" in await page.inner_text("#studio")
              and "12 000" in (await page.inner_text("#s-price")).replace("\u202f", " ").replace("\xa0", " "))
        await page.fill("#topic", "")
        await page.click("#kind-chips [data-kind=referat]")
        check("boshqa xizmatda turlar yo'qoladi", await page.locator("#ptypes .ptype").count() == 0)
        await page.click("#kind-chips [data-kind=premium_presentation]")

        print("3) Infografik: rang va AI rasmlar bilan buyurtma")
        await page.click("#ptypes [data-t='info']")
        await page.fill("#topic", "Samarqand tarixi")
        await page.wait_for_selector("#studio #go")
        check("uslub so'ralmaydi, rang va rasm tanlovi bor", not await page.locator("#styles").count()
              and await page.locator("#colors [data-c]").count() == 7 and await page.locator("#photos .src").count() == 3)
        await page.click("#colors [data-c='yashil']")
        await page.click("#photos [data-k='ai']")
        await page.click("#go")
        await wait_seen(1)
        kind, params = SEEN[-1]
        check("serverga: infografik (kam), yashil, AI rasmlar", kind == "premium" and params["volume"] == "kam"
              and params["theme"] == "yashil" and params["photos"] == "ai", params)
        await ctx.close()

        print("4) Zamonaviy: 5 uslub")
        ctx, page, errors = await phone()
        await page.goto(base + "/#yaratish?kind=premium_presentation")
        await page.wait_for_selector("#ptypes .ptype")
        await page.click("#ptypes [data-t='modern']")
        await page.fill("#topic", "Iqtisodiyot asoslari")
        await page.wait_for_selector("#studio #go")
        check("5 ta uslub", await page.locator("#styles .st-sty").count() == 5)
        await page.click("#styles [data-k='jurnal']")
        await page.click("#go")
        await wait_seen(2)
        kind, params = SEEN[-1]
        check("serverga: zamonaviy (kop), jurnal, rang avto, rasm aralash", params["volume"] == "kop" and params["style"] == "jurnal"
              and params["theme"] == "" and params["photos"] == "mix", params)
        await ctx.close()

        print("5) Klassik: shablon, slaydlar soni, reja slaydi, ikonka")
        ctx, page, errors = await phone()
        await page.goto(base + "/#yaratish?kind=premium_presentation")
        await page.wait_for_selector("#ptypes .ptype")
        await page.click("#ptypes [data-t='classic']")
        check("«Taqdimot» chipi yoniq qoladi", "on" in (await page.get_attribute("#kind-chips [data-kind=premium_presentation]", "class")).split())
        await page.fill("#topic", "Samarqand — Sharq durdonasi")
        await page.wait_for_selector("#tpls .st-tpl")
        tpl = await page.get_attribute("#tpls .st-tpl:nth-child(3)", "data-k")
        await page.click("#tpls .st-tpl:nth-child(3)")
        await page.click("#st-size [data-v='15']")
        await page.click("#st-plan [data-v='1']")
        await page.click("#st-icons [data-v='0']")
        check("narx 15 slayd — 7 000", "7 000" in (await page.inner_text("#s-price")).replace(" ", " ").replace("\xa0", " "),
              await page.inner_text("#s-price"))
        await page.click("#go")
        await wait_seen(3)
        kind, params = SEEN[-1]
        check("serverga: klassik, tanlangan shablon, 15 slayd, reja bor, ikonkasiz", kind == "simple"
              and params["template"] == tpl and params["slide_count"] == 15 and params["plan_slide"] is True
              and params["icons"] is False, params)
        await page.wait_for_selector(".forge .fg-card", timeout=20000)
        check("brauzerda xato yo'q", not errors, errors)
        await ctx.close()

        print("6) Ruscha sayt")
        ctx, page, errors = await phone("ru")
        await page.goto(base + "/#yaratish?kind=premium_presentation")
        await page.evaluate("Edu.chooseLang('ru')")
        await page.wait_for_selector("#ptypes .ptype")
        await page.fill("#topic", "История Самарканда")
        await page.wait_for_selector("#photos .src")
        text = await page.inner_text("#prompt-form")
        check("turlar, rang va rasm manbasi ruscha", all(w in text for w in ("Выберите тип презентации", "Инфографика",
              "Классическая", "3D-презентация", "Откуда брать изображения", "Из интернета")), text[:400])
        await page.click("#ptypes [data-t='classic']")
        await page.wait_for_selector("#tpls .st-tpl")
        text = await page.inner_text("#prompt-form")
        check("klassik bo'limlari ruscha", all(w in text for w in ("Шаблон", "фон и оформление", "Да", "Нет")), text[:600])
        await ctx.close()
        await browser.close()
    await runner.cleanup()


asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
