"""Sayt interfeysi haqiqiy brauzerda: «AI ishlayapti» animatsiyasi, taqdimotni varaqlash (tugma, klaviatura),
sahifani o'zgartirish chati va tayyor iltimoslar, qayta yozish jarayoni, telefon o'lchami.

AI soxta; sahifalar va PPTX haqiqiy brauzerda yig'iladi.

    python test_sayt_dekk_brauzer.py
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
from database import web_store
from services import web_jobs, web_kinds  # noqa
from services.premium_presentation import html_render, html_slides, llm_client
import webapp
from aiohttp import web

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "t.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
webapp.BOT_USERNAME = "Edufayl_bot"
PORT = 8791


class FakeBot:
    async def send_document(self, *a, **k): return types.SimpleNamespace()
    async def send_message(self, *a, **k): return types.SimpleNamespace(message_id=1)
webapp.BOT = FakeBot()


def slide(title, text, dark=False):
    if dark:
        return f'<section class="slide dark"><div class="body"><h1 class="title big">{title}</h1><p class="lead">{text}</p></div></section>'
    return (f'<section class="slide"><div class="head"><h2 class="title">{title}</h2><div class="rule"></div></div>'
            f'<div class="body"><p class="lead">{text}</p><div class="list"><div class="item"><span class="item-dot"></span>'
            f'<div class="item-text">{text} birinchi band</div></div></div></div></section>')

TITLES = ["Raqamli iqtisodiyot", "Taqdimot rejasi", "Kirish va tushunchalar", "Rivojlanish bosqichlari", "Natijalar", "Xulosa"]
BODIES = [slide(TITLES[0], "Mavzu", True), slide(TITLES[1], "Reja")] + [slide(t, "Matn " + t) for t in TITLES[2:]]
SLOW = {"s": 3}

def fake_write(topic, count, theme, language="uz", level=2, preferences="", source_text="", author="",
               progress_cb=None, outline_out=None):
    time.sleep(SLOW["s"])
    if outline_out is not None:
        outline_out.update(family="umumiy", outline=[{"title": t, "brief": t, "category": "kartalar"} for t in TITLES])
    return html_slides.build_pages(BODIES, theme, language)
html_slides.write_slides = fake_write

def fake_json(system, user, temperature=0.7, max_tokens=1000, **kw):
    if "art director" in system:
        return {"category": "diagramma", "title": "Raqamli xizmatlar ulushi", "brief": "ulush", "chart_kind": "halqa"}
    return {"ok": True, "kind": "donut", "labels": ["A", "B", "C"], "series": [{"name": "", "values": [55, 30, 15]}],
            "unit": "%", "xlabel": "", "source": "Statistika agentligi, 2024", "approx": False, "forecast": False, "reason": ""}
llm_client._call_openrouter = fake_json
def fake_text(system, user, temperature=0.7, max_tokens=1000, accept=None, **kw):
    time.sleep(2)
    return slide("Raqamli xizmatlar ulushi", "Xizmatlar ulushi o'smoqda")
llm_client._call_openrouter_text = fake_text


async def main():
    if not html_render.available():
        check("brauzer o'rnatilgan", False); return
    from playwright.async_api import async_playwright
    from webapp.server import create_web_app
    import aiohttp
    await init_db()
    await Database.create_user(100, "ali", "Ali Valiyev", "uz")
    await Database.update_user_balance(100, 50_000)
    runner = web.AppRunner(create_web_app()); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()
    base = f"http://127.0.0.1:{PORT}"
    async with aiohttp.ClientSession() as s:
        st = await (await s.post(base + "/api/v1/auth/start", headers={"Origin": base})).json()
        await web_store.confirm_login(st["token"], 100)
        r = await s.get(base + "/api/v1/auth/poll", params={"token": st["token"]})
        cookie = r.cookies["edu_session"].value

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=html_render._executable(), args=html_render._LAUNCH_ARGS)
        for name, size in (("kompyuter", {"width": 1366, "height": 900}), ("telefon", {"width": 390, "height": 844})):
            print(f"— {name}")
            ctx = await browser.new_context(viewport=size)
            await ctx.add_cookies([{"name": "edu_session", "value": cookie, "url": base}])
            page = await ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "ERR_CERT" not in m.text else None)
            SLOW["s"] = 8 if name == "kompyuter" else 1
            await page.goto(base + "/app#/create"); await page.wait_for_selector("#topic")
            await page.fill("#topic", "Raqamli iqtisodiyot")
            await page.click("#go")

            await page.wait_for_selector(".aiw", timeout=20000)
            if name == "kompyuter":
                await page.wait_for_timeout(1200)
                a = await page.evaluate("[document.querySelector('.aiw-cursor').style.transform, document.querySelector('.typed').textContent, document.querySelector('.aiw-feedin').getBoundingClientRect().top]")
                await page.wait_for_timeout(1500)
                b = await page.evaluate("[document.querySelector('.aiw-cursor').style.transform, document.querySelector('.typed').textContent, document.querySelector('.aiw-feedin').getBoundingClientRect().top]")
                check("kutish animatsiyasi: kursor harakatlanadi", a[0] and a[0] != b[0], (a, b))
                check("qidiruv matni yoziladi", bool(a[1]) and a[1] != b[1], (a[1], b[1]))
                check("faoliyat ro'yxati tinimsiz aylanadi", a[2] != b[2], (a[2], b[2]))
                shown = (await page.inner_text('.aiw')).lower()
                check("animatsiyada haqiqiy sayt nomlari yo'q", not any(x in shown for x in ("wikipedia", "google", ".com", ".org")))
            await page.wait_for_selector("#simg", timeout=180000)
            await page.wait_for_function("document.getElementById('simg').complete && document.getElementById('simg').naturalWidth > 0")
            check("tayyor taqdimot varaqlash ko'rinishida ochildi", (await page.inner_text("#snum")) == "1 / 6", await page.inner_text("#snum"))
            check("surat 1280 px", await page.evaluate("document.getElementById('simg').naturalWidth") == 1280)
            check("6 ta eskiz", await page.locator("#thumbs .th").count() == 6)
            await page.click("#next")
            check("«keyingi» tugmasi 2-sahifaga o'tkazadi", (await page.inner_text("#snum")) == "2 / 6")
            check("reja sahifasida «o'zgartirish» o'chiq", await page.is_disabled("#edit"))
            await page.keyboard.press("ArrowRight")
            check("o'ng strelka klaviaturada ishlaydi", (await page.inner_text("#snum")) == "3 / 6")
            check("oddiy sahifada «o'zgartirish» yoqiq", not await page.is_disabled("#edit"))
            await page.click("#thumbs .th[data-n='5']")
            await page.click("#thumbs .th[data-n='3']")
            check("eskizni bosish sahifani ochadi", (await page.inner_text("#snum")) == "3 / 6")

            await page.click("#edit"); await page.wait_for_selector("#vside:not([hidden])")
            check("chat ochildi, sahifa nomi so'raladi", "3-sahifa" in await page.inner_text("#chat"))
            check("tayyor iltimoslar chat ostida", await page.locator("#vprompts [data-t]").count() >= 8)
            first = await page.inner_text("#vprompts [data-t]")
            check("birinchi tayyor iltimos — doirasimon diagramma", "doirasimon diagramma" in first, first)
            if name == "telefon":
                check("telefonda gorizontal siljish yo'q", await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"))
            before = await page.evaluate("document.getElementById('simg').src")
            balance_before = (await Database.get_user(100)).balance
            await page.click("#vprompts [data-t]")
            await page.wait_for_selector("#sai:not([hidden]) .aiw", timeout=15000)
            check("qayta yozish vaqtida sahifa ustida animatsiya", True)
            check("jarayonda yuborish tugmasi o'chiq", await page.is_disabled("#vsend"))
            check("narx 900 so'm yechildi", (await Database.get_user(100)).balance == balance_before - 900)
            await page.wait_for_selector("#sai[hidden]", state="attached", timeout=240000)
            await page.wait_for_function("document.querySelector('#chat').innerText.includes('tayyor')", timeout=30000)
            after = await page.evaluate("document.getElementById('simg').src")
            check("sahifa surati yangilandi (versiya o'zgardi)", before != after and "v=2" in after, (before, after))
            await page.wait_for_function("document.getElementById('simg').complete")
            check("tugma qayta ishga tushdi", not await page.is_disabled("#vsend"))
            check("xatolar yo'q", not errors, errors)
            await ctx.close()
        await browser.close()
    await runner.cleanup()


asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
