"""Saytdagi taqdimot formasi botdagi qadamlar bilan bir xil bo'lishi: slayd soni (5–30), til avto,
manba (matn / fayl / sayt), ism, AI ga istak, rang va uslub; oddiy taqdimotda orqa fon, ikonka, reja.

Haqiqiy baza (vaqtinchalik); AI, taqdimot yaratish va sayt o'qish soxta.

    python test_sayt_taqdimot.py
"""
import asyncio, io, os, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import aiohttp
import database.database as dbmod
from database.database import Database, init_db
from database import web_store
from services import web_jobs, web_kinds, uz_script
import webapp
from webapp import api
from aiohttp.test_utils import TestClient, TestServer

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
webapp.BOT_USERNAME = "Edufayl_bot"


def docx_bytes(words=60):
    from docx import Document
    doc = Document(); doc.add_paragraph(" ".join(f"so'z{i}" for i in range(words)))
    buf = io.BytesIO(); doc.save(buf); return buf.getvalue()


async def login(client, origin, telegram_id):
    start = await (await client.post("/api/v1/auth/start", headers=origin)).json()
    await web_store.confirm_login(start["token"], telegram_id)
    await client.get("/api/v1/auth/poll", params={"token": start["token"]})


async def wait_job(client, job_id, limit=8.0):
    end = time.time() + limit
    while time.time() < end:
        data = await (await client.get(f"/api/v1/jobs/{job_id}")).json()
        if data["job"]["status"] in ("done", "failed"):
            return data
        await asyncio.sleep(0.05)
    return data


async def main():
    from services.premium_presentation import pipeline
    await init_db()
    await Database.create_user(100, "ali", "Ali", "uz")
    await Database.update_user_balance(100, 200_000)
    server = TestServer(__import__("webapp.server", fromlist=["x"]).create_web_app())
    client = TestClient(server)
    await client.start_server()
    origin = {"Origin": f"http://{server.host}:{server.port}"}

    print("1) Katalog: slayd soni 5–30, har bir son uchun narx")
    cat = await (await client.get("/api/v1/catalog")).json()
    sizes = [p["slides"] for p in cat["premium_prices"]]
    check("5 dan 30 gacha har bir son bor", sizes == list(range(5, 31)), sizes[:6])
    check("narx botdagi bilan bir xil", all(p["price"] == pipeline.price_for(p["slides"]) for p in cat["premium_prices"]))
    check("narx slayd soni bilan o'sadi", cat["premium_prices"][0]["price"] < cat["premium_prices"][-1]["price"])
    check("tez tanlash sonlari", cat["premium_range"]["popular"] == [5, 8, 10, 12, 15, 20, 25, 30]
          and cat["premium_range"]["min"] == 5 and cat["premium_range"]["max"] == 30, cat["premium_range"])
    check("uslublarda qisqa tavsif bor", all(st.get("note") for st in cat["styles"]) and len(cat["styles"]) == 5)
    check("beshta til (lotin, kirill, rus, ingliz, qozoq)", [l["key"] for l in cat["languages"]] == ["uz", "uz-cyrl", "ru", "en", "kk"])
    check("ranglar nomi va ranglari bilan", cat["themes"] and all(t["label"] and t["accent"].startswith("#") for t in cat["themes"]))

    print("2) Zamonaviy taqdimot parametrlari")
    norm = web_jobs.KINDS["premium_presentation"].normalize
    p = norm({"topic": "Iqtisodiyotda raqamlashtirish", "slide_count": 7, "language": "ru", "author": "  Ali  Valiyev ",
              "preferences": "Qisqa va vizual", "style": "qorongu", "theme": ""})
    check("7 slayd (tayyor tugmalarda yo'q son) qabul qilindi", p["slide_count"] == 7)
    check("narx 7 slayd uchun chiziqli hisoblanadi", web_jobs.KINDS["premium_presentation"].price(p) == pipeline.price_for(7))
    check("ism tozalandi, istak saqlandi", p["author"] == "Ali Valiyev" and p["preferences"] == "Qisqa va vizual", p)
    check("aniq tanlangan til saqlandi", p["language"] == "ru")
    check("slayd soni 30 dan oshmaydi, 5 dan kam bo'lmaydi",
          norm({"topic": "Mavzu", "slide_count": 99})["slide_count"] == 30 and norm({"topic": "Mavzu", "slide_count": 1})["slide_count"] == 5)
    check("ism bo'sh qolsa — muqovada ism yo'q (botdagi 'o'tkazib yuborish' kabi)", norm({"topic": "Mavzu", "_default_author": "Ali"})["author"] == "")
    check("avto: ruscha mavzu → ru", norm({"topic": "Влияние цифровизации на экономику"})["language"] == "ru")
    check("avto: o'zbekcha kirill mavzu → uz-cyrl", norm({"topic": "Ўзбекистонда рақамли иқтисодиётни ривожлантириш"})["language"] == uz_script.UZ_CYRILLIC_LANG)
    check("avto: inglizcha mavzu → en", norm({"topic": "The impact of artificial intelligence on education"})["language"] == "en")
    check("avto: lotin o'zbekcha mavzu → uz", norm({"topic": "O'zbekistonda kichik biznesni rivojlantirish"})["language"] == "uz")
    check("noto'g'ri til qiymati o'rniga avto", norm({"topic": "Влияние цифровизации на экономику", "language": "xx"})["language"] == "ru")
    src = "Birinchi qator\n\nIkkinchi qator " + "x" * 70_000
    q = norm({"topic": "Mavzu", "source_text": src, "source_label": "kitob.pdf"})
    check("manba matni qator uzilishlari bilan, 60 000 belgigacha", q["source_text"].startswith("Birinchi qator\n\nIkkinchi") and len(q["source_text"]) == 60_000)
    check("manba nomi saqlandi", q["source_label"] == "kitob.pdf")

    print("3) Oddiy taqdimot (chiroyli orqa fonlar) parametrlari")
    sn = web_jobs.KINDS["simple_presentation"].normalize
    sp = sn({"topic": "Amir Temur davri", "slide_count": 14, "template": "template_3", "icons": False, "plan_slide": True,
             "preferences": "Maktab o'quvchilari uchun", "language": "kk", "_default_author": "Ali"})
    check("14 slayd eng yaqin tayyor hajmga (15) tushdi", sp["slide_count"] == 15)
    check("qozoq tili, ikonkasiz, reja slaydi, istak", sp["language"] == "kk" and sp["icons"] is False and sp["plan_slide"] is True
          and sp["preferences"] == "Maktab o'quvchilari uchun", sp)
    check("ism bo'sh bo'lsa — akkaunt ismi (botdagidek)", sp["author"] == "Ali")
    check("oddiy taqdimotda ham 5 ta til", sn({"topic": "Mavzu uchun", "language": "uz-cyrl"})["language"] == "uz-cyrl")

    print("4) /suggest: mavzuga qarab til va rang")
    await login(client, origin, 100)
    r = await client.post("/api/v1/suggest", json={"topic": "Влияние цифровизации на экономику"}, headers=origin)
    sg = await r.json()
    check("til va rang tavsiya qilinadi", r.status == 200 and sg["language"] == "ru" and sg["theme"]["key"] and sg["theme"]["label"], sg)
    r = await client.post("/api/v1/suggest", json={"topic": "ab"}, headers=origin)
    check("juda qisqa mavzuda til bo'sh", (await r.json())["language"] == "")

    print("5) /source: fayl va sayt havolasi")
    anon = TestClient(TestServer(__import__("webapp.server", fromlist=["x"]).create_web_app()))
    await anon.start_server()
    r = await anon.post("/api/v1/source", json={"urls": "https://example.com"},
                        headers={"Origin": f"http://{anon.server.host}:{anon.server.port}"})
    check("kirmagan odam manba yuklay olmaydi", r.status == 401, r.status)
    await anon.close()

    form = aiohttp.FormData(); form.add_field("file", docx_bytes(), filename="konspekt.docx")
    r = await client.post("/api/v1/source", data=form, headers=origin)
    out = await r.json()
    check("DOCX dan matn olindi", r.status == 200 and out["words"] >= 50 and out["text"].startswith("so'z0") and out["label"] == "konspekt.docx", out)

    form = aiohttp.FormData(); form.add_field("file", b"MZ....", filename="dastur.exe")
    r = await client.post("/api/v1/source", data=form, headers=origin)
    check("noto'g'ri fayl turi rad etildi", r.status == 415, r.status)

    form = aiohttp.FormData(); form.add_field("file", b"%PDF-1.4 yaroqsiz", filename="buzuq.pdf")
    r = await client.post("/api/v1/source", data=form, headers=origin)
    check("o'qib bo'lmaydigan fayl tushunarli xato bilan rad etildi", r.status == 422 and (await r.json())["error"], r.status)

    old = api.SOURCE_MAX_BYTES; api.SOURCE_MAX_BYTES = 1000
    form = aiohttp.FormData(); form.add_field("file", docx_bytes(500), filename="katta.docx")
    r = await client.post("/api/v1/source", data=form, headers=origin)
    check("katta fayl rad etildi (413)", r.status == 413, r.status)
    api.SOURCE_MAX_BYTES = old

    r = await client.post("/api/v1/source", json={"urls": "matn, havola emas"}, headers=origin)
    check("havolasiz so'rov rad etildi", r.status == 400, r.status)

    from services.project_work import source as source_module
    async def fake_urls(urls):
        return source_module.SourceMaterial(kind="url", text="sayt matni " * 40, label="example.com")
    real_urls = source_module.from_urls; source_module.from_urls = fake_urls
    r = await client.post("/api/v1/source", json={"urls": "https://example.com/maqola"}, headers=origin)
    out = await r.json()
    check("sayt havolasidan matn olindi", r.status == 200 and out["label"] == "example.com" and out["words"] == 80, out)
    source_module.from_urls = real_urls

    print("6) Buyurtma: katta manba bilan zamonaviy taqdimot")
    seen = {}
    async def fake_build(topic, count, **kw):
        seen.update(kw, topic=topic, count=count)
        path = os.path.join(TMP, f"d{time.time_ns()}.pptx"); open(path, "wb").write(b"PPTX"); return path, count, 0
    real_build = pipeline.build_deck; pipeline.build_deck = fake_build
    big = "Ўзбекистон иқтисодиёти. " * 2600           # 62 400 belgi, kirillda ~120 KB
    r = await client.post("/api/v1/jobs", json={"kind": "premium_presentation", "params": {
        "topic": "Ўзбекистон иқтисодиёти", "slide_count": 12, "style": "blok", "theme": "", "author": "Ali Valiyev",
        "preferences": "Investorlar uchun", "source_text": big, "source_label": "kitob.pdf", "language": ""}}, headers=origin)
    body = await r.json()
    check("katta manbali buyurtma qabul qilindi", r.status == 200 and body["ok"], (r.status, body))
    job = await wait_job(client, body["job"]["id"])
    check("taqdimot yaratildi", job["job"]["status"] == "done", job)
    check("AI ga manba, ism va istak yetib bordi", seen.get("source_text", "").startswith("Ўзбекистон иқтисодиёти.")
          and len(seen["source_text"]) == 60_000 and seen["author"] == "Ali Valiyev" and seen["preferences"] == "Investorlar uchun", {k: str(v)[:30] for k, v in seen.items()})
    check("til mavzudan aniqlandi (kirill)", seen["language"] == uz_script.UZ_CYRILLIC_LANG, seen.get("language"))
    check("slayd soni va uslub uzatildi", seen["count"] == 12 and seen["style"] == "blok")
    pipeline.build_deck = real_build

    print("7) Buyurtma: oddiy taqdimot (orqa fon, manba, istak, til)")
    calls = {}
    class FakeAI:
        async def generate_presentation_in_batches(self, topic, count, lang):
            calls.setdefault("topics", []).append(topic); calls["lang"] = lang
            return {"slides": [{"layout": "content", "title": "Sarlavha", "content": "Matn"}]}
        async def generate_plan_items(self, topic, lang):
            calls["plan_topic"] = topic; return ["Kirish", "Asosiy qism"]
    class FakeDocs:
        use_icons = True
        async def create_presentation_with_template_background(self, topic, content, author, template, ts, lang, refs, plan):
            calls.update(doc_topic=topic, author=author, template=template, doc_lang=lang, plan=plan, icons=self.use_icons)
            path = os.path.join(TMP, f"s{time.time_ns()}.pptx"); open(path, "wb").write(b"PPTX"); return path
    import services.ai_service as ais, services.document_service as dss
    real_ai, real_docs = ais.get_ai_service, dss.get_document_service
    ais.get_ai_service = lambda: FakeAI(); dss.get_document_service = lambda: FakeDocs()
    real_norm = uz_script.normalize_pptx; uz_script.normalize_pptx = lambda path, script: None
    r = await client.post("/api/v1/jobs", json={"kind": "simple_presentation", "params": {
        "topic": "Amir Temur davri", "slide_count": 10, "template": "template_3", "icons": False, "plan_slide": True,
        "preferences": "Maktab o'quvchilari uchun", "source_text": "Amir Temur 1336 yilda tug'ilgan. " * 5, "source_label": "dars.docx",
        "language": "uz", "author": "Ali Valiyev"}}, headers=origin)
    body = await r.json()
    job = await wait_job(client, body["job"]["id"])
    check("oddiy taqdimot yaratildi", job["job"]["status"] == "done", job)
    check("AI ga mavzu + manba + istak berildi", "BOOK CONTENT" in calls["topics"][0] and "Amir Temur 1336" in calls["topics"][0]
          and "Maktab o'quvchilari uchun" in calls["topics"][0], calls["topics"][0][:200])
    check("tanlangan orqa fon, ism, ikonkasiz, reja slaydi", calls["template"] == "template_3" and calls["author"] == "Ali Valiyev"
          and calls["icons"] is False and calls["plan"] == ["Kirish", "Asosiy qism"], calls)
    check("reja ham istak/manba bilan tuzildi", "Maktab o'quvchilari uchun" in calls["plan_topic"])
    check("o'zbekcha lotin: til 'uz'", calls["lang"] == "uz" and calls["doc_lang"] == "uz")
    calls.clear()
    r = await client.post("/api/v1/jobs", json={"kind": "simple_presentation", "params": {
        "topic": "Ўзбекистон тарихи", "slide_count": 10, "language": "uz-cyrl", "author": "Ali"}}, headers=origin)
    job = await wait_job(client, (await r.json())["job"]["id"])
    check("kirill tanlansa mavzu kirillda qoladi", job["job"]["status"] == "done" and calls["topics"][0] == "Ўзбекистон тарихи"
          and calls["lang"] == "uz", calls)
    calls.clear()
    r = await client.post("/api/v1/jobs", json={"kind": "simple_presentation", "params": {
        "topic": "Ўзбекистон тарихи", "slide_count": 10, "language": "uz", "author": "Ali"}}, headers=origin)
    job = await wait_job(client, (await r.json())["job"]["id"])
    check("lotin tanlansa kirill mavzu lotinga o'giriladi", job["job"]["status"] == "done" and calls["topics"][0] == "O'zbekiston tarixi", calls.get("topics"))
    ais.get_ai_service, dss.get_document_service = real_ai, real_docs
    uz_script.normalize_pptx = real_norm


    print("8) Sayt fayllari yangilangach brauzer eskisini ushlab turmasin")
    import re as _re
    page_html = await (await client.get("/app")).text()
    check("/app sahifasida app.js va site.css versiya belgisi bilan", _re.search(r'/static/app\.js\?v=[0-9a-f]+"', page_html)
          and _re.search(r'/static/site\.css\?v=[0-9a-f]+"', page_html), _re.findall(r"/static/[^\"]+", page_html))
    root_html = await (await client.get("/")).text()
    check("bosh sahifada ham", _re.search(r'/static/site\.js\?v=[0-9a-f]+"', root_html) is not None)
    r = await client.get("/app")
    check("sahifaning o'zi keshlanmaydi", "no-cache" in r.headers.get("Cache-Control", ""))
    v1 = await (await client.get("/api/v1/version")).json()
    check("/api/v1/version: commit raqami ko'rinadi", v1["ok"] and v1["commit"] and v1["app_js"], v1)
    path = api.SITE_DIR / "static" / "app.js"
    old = os.stat(path).st_mtime_ns
    os.utime(path, ns=(old + 5_000_000_000, old + 5_000_000_000))
    v2 = await (await client.get("/api/v1/version")).json()
    os.utime(path, ns=(old, old))
    check("fayl o'zgarsa versiya belgisi ham o'zgaradi", v1["app_js"] != v2["app_js"], (v1, v2))

    await client.close()


asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
