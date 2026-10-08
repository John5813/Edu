"""Sayt interfeysi 4 tilda (uz, ru, en, kk): barcha ekranlar ochiladi, tarjima qilinmagan matn qolmaganini tekshiradi;
Google bilan kirish oynasi, til almashtirish va profilda saqlash brauzerda sinaladi.

AI va Google soxta. Matnlarni yig'ish: `HARVEST=/yo'l/matnlar.json python test_sayt_tillar.py` (faqat o'zbekcha ekranlar).

    python test_sayt_tillar.py
"""
import asyncio, json, os, re, sys, tempfile, time, types

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
from services import web_jobs, web_kinds  # noqa
from services.premium_presentation import html_render, html_slides, llm_client
import webapp
from webapp import account_api
from aiohttp import web

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "t.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
webapp.BOT_USERNAME = "Edufayl_bot"
webapp.WEBAPP_DOMAIN = "edufayl.org"
PORT = 8793
BASE = f"http://127.0.0.1:{PORT}"
config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET = "cid", "secret"


class FakeBot:
    async def send_document(self, *a, **k): return types.SimpleNamespace()
    async def send_message(self, *a, **k): return types.SimpleNamespace(message_id=1, chat=types.SimpleNamespace(id=1))
webapp.BOT = FakeBot()


def slide(title, text, dark=False):
    if dark:
        return f'<section class="slide dark"><div class="body"><h1 class="title big">{title}</h1><p class="lead">{text}</p></div></section>'
    return (f'<section class="slide"><div class="head"><h2 class="title">{title}</h2><div class="rule"></div></div>'
            f'<div class="body"><p class="lead">{text}</p><div class="list"><div class="item"><span class="item-dot"></span>'
            f'<div class="item-text">{text} band</div></div></div></div></section>')

TITLES = ["Raqamli iqtisodiyot", "Taqdimot rejasi", "Kirish", "Rivojlanish", "Natijalar", "Xulosa"]
BODIES = [slide(TITLES[0], "Mavzu", True), slide(TITLES[1], "Reja")] + [slide(t, "Matn " + t) for t in TITLES[2:]]
# «Natijalar» sahifasida diagramma: qo'lda tahrirlash (diagramma raqamlari) ekrani ham tekshiriladi
BODIES[4] = BODIES[4][:-len("</div></section>")] + '<div class="chart" data-kind="bar" data-labels="2022,2023,2024" '\
    'data-series="1,2,3"></div></div></section>'
html_slides.write_slides = lambda topic, count, theme, language="uz", **kw: (
    kw.get("outline_out") is not None and kw["outline_out"].update(family="umumiy", outline=[{"title": t, "brief": t, "category": "kartalar"} for t in TITLES]),
    html_slides.build_pages(BODIES, theme, language))[1]

LONG = {"s": 0}
def fake_json(system, user, temperature=0.7, max_tokens=1000, **kw):
    if "art director" in system:
        return {"category": "diagramma", "title": "Ulush", "brief": "ulush", "chart_kind": "halqa"}
    return {"ok": True, "kind": "donut", "labels": ["A", "B", "C"], "series": [{"name": "", "values": [55, 30, 15]}],
            "unit": "%", "xlabel": "", "source": "Statistika agentligi, 2024", "approx": False, "forecast": False, "reason": ""}
llm_client._call_openrouter = fake_json
llm_client._call_openrouter_text = lambda *a, **k: (time.sleep(LONG["s"]), slide("Ulush", "Matn"))[1]


# Sahifadagi barcha ko'rinadigan matn va atributlar
COLLECT = r"""() => {
  const out = new Set();
  const skip = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'NOSCRIPT']);
  const walk = (n) => {
    if (n.nodeType === 3) { const t = n.data.replace(/\s+/g, ' ').trim(); if (t) out.add(t); return; }
    if (n.nodeType !== 1 || skip.has(n.nodeName)) return;
    for (const a of ['placeholder', 'title', 'aria-label', 'alt']) { const v = n.getAttribute(a); if (v && v.trim()) out.add(v.trim()); }
    n.childNodes.forEach(walk);
  };
  walk(document.body);
  return Array.from(out);
}"""

# Mijoz kiritgan yoki o'zgarmas nomlar: tarjima qilinmaydi
KEEP = {"O‘zbekcha", "O'zbekcha", "English", "Русский", "Қазақша", "Ўзбек (кирилл)", "O'zbek (lotin)", "UZ", "RU", "EN", "KK",
        "Raqamli iqtisodiyot", "Globallashuv va iqtisodiyot", "Korxonada xarajatlar", "Sun'iy intellekt", "Ali Valiyev",
        "ali@gmail.com", "@ali", "@javlon58_02", "@Edufayl_bot", "Moʻydinov Javlonbek", "ab", "Ali Valiyev"}
DECK_TITLES = {"Raqamli iqtisodiyot", "Taqdimot rejasi", "Kirish", "Rivojlanish", "Natijalar", "Xulosa", "Ulush"}
LATIN_OK = {"edufayl.org", "click", "payme", "uzum", "javlonbek", "moʻydinov", "edufayl_bot", "javlon58_02", "telegram", "google", "pptx", "docx", "pdf", "imrad", "ai", "edufayl", "start", "mb", "kpi", "ru", "uz", "en", "kk",
            "ok", "powerpoint", "word", "id", "svg", "png", "jpg", "jpeg", "ic", "html", "url", "http", "https", "t.me", "bot"}
UZ_MARK = re.compile(r"[ʻ‘]|\b(?:so'm|so‘m|uchun|bilan|kerak|mavzu|taqdimot|yaratish|hujjat|sahifa|tayyor|bo'lsa|ham|yoki|"
                     r"va)\b", re.IGNORECASE)


NAMES_IN_TEXT = ("O'zbek (lotin)", "O‘zbek (lotin)", "Moʻydinov Javlonbek", "Ulush", "Raqamli iqtisodiyot")


def leftovers(texts, lang, deck=False, uzset=frozenset()):
    """Tarjima qilinmay qolgan matnlar (tilga qarab)."""
    bad = []
    for t in texts:
        for name in NAMES_IN_TEXT:       # mijoz ma'lumoti va til nomlari tarjima qilinmaydi
            t = t.replace(name, "")
        t = t.strip(" ·«»“”")
        if t in KEEP or t.startswith("O'zbek (lotin)") or (deck and t in DECK_TITLES) or re.fullmatch(r"[\d\s.,:/+\-–—·()%]+", t):
            continue
        if lang in ("ru", "kk"):
            words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’‘ʻ.]+", t) if len(w) >= 3]
            if any(w.lower().strip(".") not in LATIN_OK for w in words) or re.search(r"[ʻ‘]", t):
                bad.append(t)
        elif lang == "en":
            same_as_uz = t in uzset and not all(w.lower().strip(".") in LATIN_OK for w in re.findall(r"[A-Za-z][A-Za-z'’‘ʻ.]+", t))
            if UZ_MARK.search(t) or re.search(r"[А-Яа-яЁё]", t) or same_as_uz:
                bad.append(t)
    return bad


async def main():
    if not html_render.available():
        check("brauzer o'rnatilgan", False); return
    from playwright.async_api import async_playwright
    from webapp.server import create_web_app
    import aiohttp

    await init_db()
    tg = await Database.create_user(901, "ali", "Ali Valiyev", "uz")
    await Database.update_user_balance(901, 12_000)
    wid = await web_accounts.create_web_user("google", "g-t", "ali@gmail.com", "Ali Valiyev", "uz")
    await Database.update_user_balance(wid, 20_000)
    runner = web.AppRunner(create_web_app()); await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", PORT).start()

    async def cookie_for(tid):
        return await web_accounts.create_session(tid)

    harvest = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=html_render._executable(), args=html_render._LAUNCH_ARGS)

        async def screens(lang, tid, label):
            """Barcha ekranlarni ochib, har biridagi matnlarni qaytaradi."""
            if tid:     # kirgan odamning tili akkauntida saqlanadi (sayt shu tilda ochiladi)
                await web_accounts.update_profile(tid, None, lang)
            ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
            await ctx.add_init_script(f"try{{localStorage.setItem('edu_lang','{lang}')}}catch(e){{}}")
            if tid:
                await ctx.add_cookies([{"name": "edu_session", "value": await cookie_for(tid), "url": BASE}])
            page = await ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "ERR_CERT" not in m.text and "Failed to load resource" not in m.text else None)
            got = {}

            async def snap(name):
                await page.wait_for_timeout(350)
                got[name] = await page.evaluate(COLLECT)

            if not tid:
                await page.goto(BASE + "/"); await page.wait_for_selector("#kind-chips [data-kind=thesis]"); await snap("bosh sahifa")
                await page.fill("#topic", "Raqamli iqtisodiyot"); await page.wait_for_selector("#studio .st-main"); await page.wait_for_timeout(700)
                await snap("yaratish oynasi (mehmon)")
                await page.goto(BASE + "/app"); await page.wait_for_selector("#lg"); await snap("kirish kartasi")
                await page.click("#lg"); await page.wait_for_selector(".modal .box"); await page.wait_for_selector("#lg-gbtn"); await snap("kirish oynasi")
                await page.click("#lg-tg"); await page.wait_for_selector("#lg-body a.btn", timeout=15000); await snap("telegram kirish")
            else:
                await page.goto(BASE + "/app#/welcome"); await page.wait_for_selector("#w-go"); await snap("xush kelibsiz")
                # Yaratish bosh sahifada: mavzu yozilgach oyna kattalashib, tanlangan xizmatning sozlamalari ochiladi
                await page.goto(BASE + "/app#/create"); await page.wait_for_url("**/#yaratish"); await page.wait_for_selector("#kind-chips [data-kind=thesis]")
                await page.fill("#topic", "Raqamli iqtisodiyot"); await page.wait_for_selector("#studio .st-main"); await page.wait_for_timeout(700)
                await snap("taqdimot: mavzu yozilgan")
                await page.click("#srcs [data-k=text]"); await snap("manba: matn")
                await page.click("#srcs [data-k=file]"); await snap("manba: fayl")
                await page.click("#srcs [data-k=url]"); await snap("manba: havola")
                await page.click("#srcs [data-k=ai]")
                await page.click("#styles [data-k=jurnal]"); await page.click("#themes [data-k='yashil']"); await snap("taqdimot: uslub va rang")
                await page.fill("#topic", "ab"); await page.click("#go"); await snap("taqdimot: xato")
                await page.fill("#topic", "Raqamli iqtisodiyot")
                for kind in ("independent_work", "referat", "article", "thesis", "course_work", "diploma_work", "bitiruv_ishi", "dissertatsiya"):
                    await page.click(f"#kind-chips [data-kind={kind}]"); await page.wait_for_selector("#studio .st-main"); await snap("forma: " + kind)
                if tid == wid:      # tayyorlanayotgan buyurtmalar: «Slaydlar ustaxonasi» animatsiyasi
                    await page.goto(BASE + "/app#/job/" + "b" * 32); await page.wait_for_selector(".forge .fg-card"); await snap("ustaxona: hujjat yozilmoqda")
                    await page.goto(BASE + "/app#/job/" + "c" * 32); await page.wait_for_selector(".forge .fg-card"); await snap("ustaxona: navbatda")
                await page.goto(BASE + "/app#/docs"); await page.wait_for_selector("#view .card"); await snap("hujjatlarim")
                await page.goto(BASE + "/app#/wallet"); await page.wait_for_selector("#presets"); await snap("hamyon")
                await page.click("#presets .chip >> nth=0"); await snap("hamyon: summa tanlandi")
                await page.goto(BASE + "/app#/profile"); await page.wait_for_selector("#p-save"); await snap("profil")
                if await page.locator("#p-tg").count():
                    await page.click("#p-tg", no_wait_after=True); await page.wait_for_selector("#p-note .note"); await snap("profil: Telegramni ulash")
            check(f"[{label}] sahifa xatolarisiz ochildi", not errors, errors[:2])
            await ctx.close()
            return got

        async def deck_screens(lang, tid, job_id):
            # Bir vaqtda 2 tagacha faol buyurtma: ro'yxat uchun qo'yilgan «ishlayapti» qatorlari vaqtincha yopiladi.
            await web_store.update_job("b" * 32, status="done"); await web_store.update_job("c" * 32, status="done")
            try:
                return await _deck_screens(lang, tid, job_id)
            finally:
                await web_store.update_job("b" * 32, status="running"); await web_store.update_job("c" * 32, status="queued")

        async def _deck_screens(lang, tid, job_id):
            await web_accounts.update_profile(tid, None, lang)
            ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
            await ctx.add_init_script(f"try{{localStorage.setItem('edu_lang','{lang}')}}catch(e){{}}")
            await ctx.add_cookies([{"name": "edu_session", "value": await cookie_for(tid), "url": BASE}])
            page = await ctx.new_page()
            got = {}
            await page.goto(BASE + f"/app#/job/{job_id}"); await page.wait_for_selector("#simg", timeout=60000)
            await page.wait_for_timeout(500); got["taqdimot ko'rish"] = await page.evaluate(COLLECT)
            await page.click("#edit"); await page.wait_for_selector("#vside:not([hidden])"); await page.wait_for_timeout(300)
            got["sahifani o'zgartirish chati"] = await page.evaluate(COLLECT)
            await page.click("#next"); await page.click("#next")
            LONG["s"] = 6
            await page.click("#vprompts [data-t]")
            await page.wait_for_selector("#sai:not([hidden]) .aiw", timeout=15000); await page.wait_for_timeout(500)
            got["AI ishlamoqda (sahifa)"] = await page.evaluate(COLLECT)
            await page.wait_for_selector("#sai[hidden]", state="attached", timeout=120000)
            LONG["s"] = 0
            await page.wait_for_function("document.querySelector('#chat').innerText.length > 80", timeout=30000)
            got["chat: natija"] = await page.evaluate(COLLECT)
            # Qo'lda tahrirlash (bepul): diagramma raqamlari, slaydlar tartibi, matn
            await page.click("#thumbs .th[data-n='5']"); await page.click("#t-chart"); await page.wait_for_selector(".ed-tbl")
            got["qo'lda: diagramma"] = await page.evaluate(COLLECT); await page.click("#ed-x")
            await page.click("#t-order"); await page.wait_for_selector(".ed-list"); got["qo'lda: tartib"] = await page.evaluate(COLLECT); await page.click("#ed-x")
            await page.click("#t-text"); await page.wait_for_selector("#ed-ok"); got["qo'lda: matn"] = await page.evaluate(COLLECT); await page.click("#ed-x")
            await ctx.close()
            return got

        # ── 1) taqdimot yaratiladi (ko'rish ekranlari uchun)
        print("1) Taqdimot tayyorlanadi")
        ctx = await browser.new_context(); await ctx.add_cookies([{"name": "edu_session", "value": await cookie_for(wid), "url": BASE}])
        async with aiohttp.ClientSession(cookies={"edu_session": await cookie_for(wid)}) as s:
            r = await s.post(BASE + "/api/v1/jobs", json={"kind": "premium_presentation", "params": {"topic": "Raqamli iqtisodiyot", "slide_count": 4}},
                             headers={"Origin": BASE})
            job_id = (await r.json())["job"]["id"]
            for _ in range(600):
                j = await (await s.get(BASE + f"/api/v1/jobs/{job_id}")).json()
                if j["job"]["status"] in ("done", "failed"): break
                await asyncio.sleep(0.3)
        await ctx.close()
        check("taqdimot tayyor", j["job"]["status"] == "done", j)
        # turli holatdagi buyurtmalar (ro'yxat uchun)
        now = time.time()
        for jid, kind, title, status, stage, err in (
                ("a" * 32, "referat", "Globallashuv va iqtisodiyot", "failed", "failed", "Xatolik yuz berdi: Fayl yaratilmadi. 5 000 so'm hisobingizga qaytarildi."),
                ("b" * 32, "course_work", "Korxonada xarajatlar", "running", "writing", ""),
                ("c" * 32, "article", "Sun'iy intellekt", "queued", "queued", "")):
            await web_store.create_job(jid, wid, kind, title, {}, 5000, charged=True)
            await web_store.update_job(jid, status=status, stage=stage, error=err, progress=40)
        pay = await Database.create_payment((await Database.get_user(wid)).id, 10_000, "", "web")
        await Database.create_payment((await Database.get_user(wid)).id, 5_000, "", "web")
        await Database.update_payment_status(pay, "approved")


        # ── 2) o'zbekcha: matnlarni yig'ish
        print("2) O'zbekcha ekranlar")
        uz = {}
        for tid, label in ((None, "mehmon"), (wid, "Google akkaunt"), (901, "Telegram akkaunt")):
            part = await screens("uz", tid, "uz " + label)
            uz.update({f"{label}: {k}": v for k, v in part.items()})
        uz.update({f"ko'rish: {k}": v for k, v in (await deck_screens("uz", wid, job_id)).items()})
        harvest = uz
        uz_all = {t for v in uz.values() for t in v}
        if os.environ.get("HARVEST"):
            allv = sorted({t for v in uz.values() for t in v})
            json.dump(allv, open(os.environ["HARVEST"], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"  {len(allv)} ta matn yozildi")

        # ── 3) boshqa tillar
        for lang in ("ru", "en", "kk"):
            print(f"3) {lang}: tarjima to'liqligi")
            allbad = {}
            for tid, label in ((None, "mehmon"), (wid, "Google akkaunt"), (901, "Telegram akkaunt")):
                part = await screens(lang, tid, f"{lang} {label}")
                for screen, texts in part.items():
                    for t in leftovers(texts, lang, uzset=uz_all):
                        allbad.setdefault(t, f"{label}: {screen}")
            for screen, texts in (await deck_screens(lang, wid, job_id)).items():
                for t in leftovers(texts, lang, deck=True, uzset=uz_all):
                    allbad.setdefault(t, f"ko'rish: {screen}")
            check(f"{lang}: tarjima qilinmagan matn qolmadi", not allbad,
                  "; ".join(f"«{t}» ({w})" for t, w in list(allbad.items())[:25]) + f" … jami {len(allbad)}")

        # ── 4) til almashtirish va saqlash
        print("4) Til almashtirish")
        ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
        await ctx.add_cookies([{"name": "edu_session", "value": await cookie_for(wid), "url": BASE}])
        page = await ctx.new_page()
        await page.goto(BASE + "/app#/profile"); await page.wait_for_selector("#p-langs")
        await page.click("#p-langs [data-lang=ru]"); await page.wait_for_timeout(800)
        check("profilda til tanlansa sayt shu tilga o'tadi", await page.evaluate("document.documentElement.lang") == "ru"
              and "Профиль" in await page.inner_text("nav.nav"))
        check("til akkauntda saqlandi (botda ham shu til)", web_accounts.user_language(await Database.get_user(wid)) == "ru")
        await page.reload(); await page.wait_for_selector("#p-save")
        check("qayta ochilganda til saqlanib qoladi", await page.evaluate("document.documentElement.lang") == "ru")
        await page.click("#langbtn"); await page.click("#langmenu [data-lang=kk]"); await page.wait_for_timeout(800)
        check("sarlavhadagi til tanlagich ishlaydi va saqlaydi", await page.evaluate("document.documentElement.lang") == "kk"
              and web_accounts.user_language(await Database.get_user(wid)) == "kk")
        await page.click("#langbtn"); await page.click("#langmenu [data-lang=uz]"); await page.wait_for_timeout(500)
        check("o'zbekchaga qaytganda matn asliga qaytadi", "Profil" in await page.inner_text("nav.nav")
              and not re.search(r"[А-Яа-я]", await page.inner_text("nav.nav")))
        await ctx.close()

        # mehmon: til tanlansa kirish oynasi shu tilda va Google havolasiga til yoziladi
        ctx = await browser.new_context(viewport={"width": 1366, "height": 900})
        page = await ctx.new_page()
        await page.goto(BASE + "/app"); await page.wait_for_selector("#lg")
        await page.click("#lg"); await page.wait_for_selector("#lg-gbtn")
        await page.click("#lg-langs [data-lang=en]"); await page.wait_for_timeout(500)
        check("kirish oynasida til tanlanadi: matn inglizcha", "Continue with Google" in await page.inner_text(".modal .box"), await page.inner_text(".modal .box"))
        check("Google havolasiga tanlangan til qo'shiladi", (await page.get_attribute("#lg-gbtn", "href")).endswith("lang=en"),
              await page.get_attribute("#lg-gbtn", "href"))
        await ctx.close()
        await browser.close()
    await runner.cleanup()


asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
