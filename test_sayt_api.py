"""Sayt API: Telegram orqali kirish, buyurtma (to'lov/qaytarish), fayl yuklash, chek yuklash.

Haqiqiy baza (vaqtinchalik) va aiohttp test serveri; Telegram, AI va taqdimot yaratish soxta.

    python test_sayt_api.py
"""
import asyncio, os, sys, tempfile, types, time
from datetime import datetime, timedelta

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
from database import web_store
from services import web_jobs, web_kinds  # noqa
from services.receipts import reader, rules, flow
import webapp
from aiohttp.test_utils import TestClient, TestServer

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
NOW = datetime(2026, 10, 6, 20, 10)
rules.now_tashkent = lambda: NOW
config.RECEIPT_AI = True
config.RECEIPT_AUTO = False
ADMIN = config.ADMIN_IDS[0]


# ── soxta Telegram
class FakeBot:
    def __init__(self):
        self.sent, self.photos, self.docs, self.n = [], [], [], 500
    async def send_message(self, chat_id, text, **kw):
        self.n += 1
        item = types.SimpleNamespace(chat=types.SimpleNamespace(id=chat_id), message_id=self.n, text=text, kw=kw)
        self.sent.append(item); return item
    async def send_photo(self, chat_id, photo, **kw):
        self.n += 1; self.photos.append((chat_id, kw))
        return types.SimpleNamespace(photo=[types.SimpleNamespace(file_id=f"ph{self.n}")])
    async def send_document(self, chat_id, document, **kw):
        self.n += 1; self.docs.append((chat_id, kw))
        return types.SimpleNamespace(document=types.SimpleNamespace(file_id=f"doc{self.n}"))
BOT = FakeBot()
webapp.BOT, webapp.BOT_USERNAME = BOT, "Edufayl_bot"

# ── soxta taqdimot yaratish
CALLS = {"fail": False, "slow": 0.0}
async def fake_run(params, report):
    report("writing", 20)
    if CALLS["slow"]:
        await asyncio.sleep(CALLS["slow"])
    if CALLS["fail"]:
        raise RuntimeError("model javob bermadi")
    report("render", 90)
    path = os.path.join(TMP, f"deck_{time.time_ns()}.pptx")
    open(path, "wb").write(b"PPTX:" + params["topic"].encode())
    return path, "Taqdimot_test.pptx"
web_jobs.KINDS["premium_presentation"].run = fake_run

# ── soxta chek o'qish
QUEUE = []
reader._call = lambda kind, images, text, now: QUEUE.pop(0) if QUEUE else {}
reader.prepare = lambda data, filename="", mime="": reader.Prepared(images=[b"img"], text="", meta_flags=[])

def raw(amount=10_000, rid="7001", **kw):
    base = {"doc_type": "transfer", "status": "success", "readable": True, "amount": amount, "fee": 110, "currency": "UZS",
            "date": {"year": 2026, "month": 10, "day": 6, "hour": 20, "minute": 4}, "ids": [rid],
            "sender_name": "FARXOD N.", "sender_card": "986012******6989", "receiver_name": "JAVLONBEK M.",
            "receiver_card": "986016****6655", "app": "click",
            "screenshot": {"is_screenshot": True, "clock": "20:04", "battery": 28}, "cropped": False,
            "tamper": "none", "confidence": 0.95}
    base.update(kw); return base


async def wait_job(client, job_id, limit=8.0):
    end = time.time() + limit
    while time.time() < end:
        data = await (await client.get(f"/api/v1/jobs/{job_id}")).json()
        if data["job"]["status"] in ("done", "failed"):
            return data
        await asyncio.sleep(0.05)
    return data


async def main():
    from webapp.server import create_web_app
    await init_db()
    user = await Database.create_user(100, "ali", "Ali", "uz")
    await Database.update_user_balance(100, 20_000)

    server = TestServer(create_web_app())
    client = TestClient(server)
    await client.start_server()
    origin = {"Origin": f"http://{server.host}:{server.port}"}

    print("1) Kirish: bot orqali tasdiqlash, bir martalik token")
    r = await client.post("/api/v1/auth/start", headers=origin)
    start = await r.json()
    check("token va bot havolasi beriladi", r.status == 200 and "weblogin_" + start["token"] in start["url"], start)
    check("token bazada ochiq ko'rinishda emas",
          start["token"] not in open(dbmod.DATABASE_FILE, "rb").read().decode("latin1"))
    r = await client.get("/api/v1/auth/poll", params={"token": start["token"]})
    check("tasdiqlanmaguncha kutish holati", (await r.json())["status"] == "pending" and "edu_session" not in r.cookies)
    check("eski/noto'g'ri token tasdiqlanmaydi", not await web_store.confirm_login("yo'q-token", 100))
    check("bot tasdiqlaydi", await web_store.confirm_login(start["token"], 100))
    check("ikkinchi marta tasdiqlab bo'lmaydi (boshqa odam tokenni o'g'irlay olmaydi)",
          not await web_store.confirm_login(start["token"], 999))
    r = await client.get("/api/v1/auth/poll", params={"token": start["token"]})
    check("sessiya cookie berildi (HttpOnly, SameSite)", (await r.json())["status"] == "ok"
          and "httponly" in r.headers["Set-Cookie"].lower() and "samesite=lax" in r.headers["Set-Cookie"].lower(), r.headers)
    r = await client.get("/api/v1/auth/poll", params={"token": start["token"]})
    check("token bir martalik: qayta ishlatib bo'lmaydi", (await r.json())["status"] == "pending")
    me = await (await client.get("/api/v1/me")).json()
    check("/me: ism va balans", me["user"]["id"] == 100 and me["user"]["balance"] == 20_000, me)

    print("2) Himoya")
    r = await client.post("/api/v1/jobs", json={"kind": "premium_presentation", "params": {"topic": "Test"}},
                          headers={"Origin": "https://boshqa-sayt.example"})
    check("begona saytdan POST rad etiladi", r.status == 403, r.status)
    saved = client.session.cookie_jar.filter_cookies(server.make_url("/"))
    client.session.cookie_jar.clear()
    r = await client.get("/api/v1/jobs")
    check("sessiyasiz buyurtmalar ro'yxati — 401", r.status == 401, r.status)
    r = await client.get("/api/v1/me")
    check("sessiyasiz /me — user yo'q", (await r.json())["user"] is None)
    for morsel in saved.values():
        client.session.cookie_jar.update_cookies({morsel.key: morsel.value}, server.make_url("/"))
    check("cookie qaytarilgach kirish tiklandi", (await (await client.get("/api/v1/me")).json())["user"]["id"] == 100)

    print("3) Katalog va narx")
    cat = await (await client.get("/api/v1/catalog")).json()
    check("katalog: xizmat, uslub, til, narxlar", cat["kinds"] and len(cat["styles"]) == 5 and len(cat["languages"]) == 5
          and cat["premium_prices"][0]["price"] >= 3000, cat["premium_prices"][:2])
    from services.premium_presentation import pipeline
    q = await (await client.post("/api/v1/quote", json={"kind": "premium_presentation",
                                                         "params": {"topic": "Kiberxavfsizlik", "slide_count": 12}},
                                 headers=origin)).json()
    check("narx botdagi bilan bir xil", q["price"] == pipeline.price_for(12) and q["enough"], q)
    q2 = await (await client.post("/api/v1/quote", json={"kind": "premium_presentation",
                                                          "params": {"topic": "ab"}}, headers=origin)).json()
    check("qisqa mavzu rad etiladi", q2["ok"] is False and "kamida 3" in q2["error"], q2)

    print("4) Buyurtma: yechish → bajarish → fayl")
    price = pipeline.price_for(10)
    r = await client.post("/api/v1/jobs", json={"kind": "premium_presentation",
                                                 "params": {"topic": "Kiberxavfsizlik asoslari", "slide_count": 10,
                                                            "style": "noma'lum", "language": "xx"}}, headers=origin)
    created = await r.json()
    check("buyurtma qabul qilindi, balans yechildi", r.status == 200 and created["balance"] == 20_000 - price, created)
    done = await wait_job(client, created["job"]["id"])
    check("ish tugadi va fayl tayyor", done["job"]["status"] == "done" and done["job"]["ready"], done)
    r = await client.get(f"/api/v1/jobs/{created['job']['id']}/file")
    body = await r.read()
    check("fayl yuklab olinadi (nomi UTF-8)", r.status == 200 and body.startswith(b"PPTX:Kiberxavfsizlik")
          and "Taqdimot_test.pptx" in r.headers["Content-Disposition"], r.headers.get("Content-Disposition"))
    check("fayl Telegramga ham yuborildi", any(chat == 100 for chat, kw in BOT.docs), BOT.docs)
    lst = await (await client.get("/api/v1/jobs")).json()
    check("ro'yxatda ko'rinadi, saqlash muddati aytiladi", len(lst["jobs"]) == 1 and lst["ttl_hours"] == web_store.JOB_TTL_HOURS)
    other = await Database.create_user(200, "vali", "Vali", "uz")
    stranger = await web_store.get_job(created["job"]["id"], 200)
    check("boshqa mijoz bu ishni ko'ra olmaydi", stranger is None)

    norm = web_jobs.KINDS["premium_presentation"].normalize({"topic": "  Yaxshi   mavzu ", "style": "noma'lum",
                                                             "language": "xx", "slide_count": "999", "theme": "yo'q"})
    check("noto'g'ri uslub, til, rang va son sukutga tushadi", norm["style"] == "toza" and norm["language"] == "uz"
          and norm["theme"] == "" and norm["slide_count"] == 30 and norm["topic"] == "Yaxshi mavzu", norm)

    print("5) Xato: pul to'liq qaytariladi")
    CALLS["fail"] = True
    before = (await Database.get_user(100)).balance
    r = await client.post("/api/v1/jobs", json={"kind": "premium_presentation", "params": {"topic": "Xato mavzu"}}, headers=origin)
    failed_job = (await r.json())["job"]
    res = await wait_job(client, failed_job["id"])
    check("ish muvaffaqiyatsiz, sabab ko'rsatildi", res["job"]["status"] == "failed" and "qaytarildi" in res["job"]["error"], res["job"])
    check("balans avvalgidek", (await Database.get_user(100)).balance == before, (await Database.get_user(100)).balance)
    CALLS["fail"] = False

    print("6) Balans yetmasa — hech narsa yechilmaydi")
    poor = await Database.create_user(300, "kam", "Kam", "uz")
    await Database.update_user_balance(300, 1000)
    check("atomik yechish: yetmasa False", not await Database.charge_balance(300, 5000) and (await Database.get_user(300)).balance == 1000)
    try:
        await web_jobs.submit(300, "premium_presentation", {"topic": "Mavzu uchun", "slide_count": 10})
        check("balans yetmasa rad etiladi", False)
    except web_jobs.JobError as exc:
        check("balans yetmasa rad etiladi (402 kodi)", exc.code == "no_balance" and "Balans yetarli emas" in str(exc), str(exc))
    check("balans o'zgarmadi", (await Database.get_user(300)).balance == 1000)
    CALLS["slow"] = 0.6
    await Database.update_user_balance(100, 50_000)
    ids = []
    for i in range(2):
        r = await client.post("/api/v1/jobs", json={"kind": "premium_presentation", "params": {"topic": f"Sekin {i}"}}, headers=origin)
        ids.append(r.status)
    r = await client.post("/api/v1/jobs", json={"kind": "premium_presentation", "params": {"topic": "Uchinchi"}}, headers=origin)
    check("bir vaqtda 2 tadan ko'p buyurtma yo'q (409)", ids == [200, 200] and r.status == 409, (ids, r.status))
    for job in await web_store.list_jobs(100, 10):
        await wait_job(client, job["id"])
    CALLS["slow"] = 0.0

    print("7) Qayta ishga tushish va tozalash")
    await Database.update_user_balance(300, 20_000)
    await web_store.create_job("stuck1", 300, "premium_presentation", "Yarim qolgan", {"topic": "x"}, 5000)
    await web_store.update_job("stuck1", status="running")
    bal = (await Database.get_user(300)).balance
    n = await web_jobs.recover()
    check("yarim qolgan ish bekor qilinib pul qaytarildi", n == 1 and (await Database.get_user(300)).balance == bal + 5000, n)
    check("qayta ishga tushganda ikkinchi marta qaytarilmaydi", await web_jobs.recover() == 0)
    old = await web_store.get_job(created["job"]["id"])
    import aiosqlite
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        await conn.execute("UPDATE web_jobs SET created_at = ? WHERE id = ?", (time.time() - 80 * 3600, old["id"]))
        await conn.commit()
    removed = await web_jobs.purge()
    check("muddati o'tgan ish va fayli o'chdi (maxfiylik)", removed == 1 and not os.path.exists(old["result_path"])
          and await web_store.get_job(old["id"]) is None)

    print("8) Hamyon: usullar")
    w = await (await client.get("/api/v1/wallet")).json()
    keys = {m["key"]: m["enabled"] for m in w["methods"]}
    check("chek yuklash yoqilgan; Click/Payme/Uzum — tez orada", keys == {"receipt": True, "click": False, "payme": False, "uzum": False}, keys)
    check("kartalar ko'rsatiladi, summa tanlovlari bor", w["methods"][0]["cards"] and w["presets"] and w["min"] == 1000)

    print("9) Chek yuklash (Telegramsiz)")
    from aiohttp import FormData
    def form(amount, data, name="chek.jpg", mime="image/jpeg"):
        f = FormData(); f.add_field("amount", str(amount)); f.add_field("file", data, filename=name, content_type=mime); return f
    QUEUE[:] = [raw()]
    started = (NOW - timedelta(minutes=15)).isoformat()
    f = form(10_000, b"CHEK-1"); f.add_field("started", started)
    r = await client.post("/api/v1/wallet/receipt", data=f, headers=origin)
    res = await r.json()
    check("haqiqiy chek adminga boradi (qo'lda tasdiq), pul hali qo'shilmadi", r.status == 200 and res["verdict"] == "review"
          and res["pending"] and not res["credited"], res)
    check("adminga chek rasmi va kartochka tugmalar bilan yetdi",
          any(c == ADMIN for c, kw in BOT.photos) and any(m.chat.id == ADMIN and m.kw.get("reply_markup") for m in BOT.sent),
          [(c) for c, _ in BOT.photos])
    pend = await Database.get_pending_payments()
    check("to'lov yozuvi chek rasmi bilan yaratildi", len(pend) == 1 and (pend[0].screenshot_file_id or "").startswith("ph"), pend)
    r = await client.post("/api/v1/wallet/receipt", data=form(10_000, b"CHEK-1"), headers=origin)
    res = await r.json()
    check("o'sha fayl qayta yuborilsa — mijozga tushuntirish, adminga hech narsa bormaydi",
          res["verdict"] in ("own_pending", "duplicate") and res["message"] and len(await Database.get_pending_payments()) == 1, res)
    QUEUE[:] = [{"doc_type": "other", "status": "unknown", "readable": True}]
    r = await client.post("/api/v1/wallet/receipt", data=form(10_000, b"RASM-2"), headers=origin)
    res = await r.json()
    check("chek bo'lmagan rasm — qayta yuborish so'raladi, adminga bormaydi",
          res["verdict"] == "not_receipt" and res["retry"] and len(await Database.get_pending_payments()) == 1, res)
    r = await client.post("/api/v1/wallet/receipt", data=form(500, b"x"), headers=origin)
    check("kichik summa rad etiladi", r.status == 400 and "1 000" in (await r.json())["error"], await r.text())
    r = await client.post("/api/v1/wallet/receipt", data=form(10_000, b""), headers=origin)
    check("bo'sh fayl rad etiladi", r.status == 400)

    print("10) Botdagi /start weblogin tugmasi")
    src = open("bot/handlers/start.py", encoding="utf8").read()
    check("start handler weblogin_ ni tasdiqlaydi", "weblogin_" in src and "confirm_login" in src)

    print("11) Sahifalar")
    home = await client.get("/")
    html = await home.text()
    check("bosh sahifa ochiladi: logotip, Tayyor mavzular, kirish", home.status == 200 and "/static/logo.jpg" in html
          and "Tayyor mavzular" in html and 'id="actions"' in html)
    check("'Botdagi hamma xizmat' kabi ortiqcha gaplar yo'q", "brauzerda ham" not in html and "bir xil natija" not in html)
    r = await client.get("/app")
    check("kabinet sahifasi ochiladi", r.status == 200 and "app.js" in await r.text())
    for name, kind in (("site.css", "css"), ("site.js", "javascript"), ("app.js", "javascript"), ("logo.jpg", "image")):
        r = await client.get(f"/static/{name}")
        check(f"/static/{name} beriladi", r.status == 200 and kind in r.headers["Content-Type"], r.headers.get("Content-Type"))
    r = await client.get("/static/..%2f..%2fapi.py")
    check("papkadan tashqariga chiqib bo'lmaydi", r.status == 404, r.status)
    r = await client.get("/shop")
    check("do'kon sahifasi avvalgidek ishlaydi", r.status == 200 and "/static/logo.jpg" in await r.text())

    await client.close()
    print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
    sys.exit(1 if FAILS else 0)

asyncio.run(main())
