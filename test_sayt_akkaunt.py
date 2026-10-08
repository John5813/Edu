"""Saytda Google bilan kirish, Telegramsiz akkaunt, profil (ism, til) va Telegramni ulash (akkauntlarni birlashtirish).

Haqiqiy baza (vaqtinchalik); Google, Telegram va AI soxta.

    python test_sayt_akkaunt.py
"""
import asyncio, os, sys, tempfile, time, types
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
from services import web_jobs, web_kinds  # noqa
import webapp
from webapp import account_api
from aiohttp.test_utils import TestClient, TestServer

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "test.db")
web_jobs.RESULTS_DIR = os.path.join(TMP, "results")
webapp.BOT_USERNAME = "Edufayl_bot"
webapp.WEBAPP_DOMAIN = "edufayl.org"


class FakeBot:
    def __init__(self): self.docs, self.msgs = [], []
    async def send_document(self, chat_id, document, **kw): self.docs.append(chat_id); return types.SimpleNamespace()
    async def send_message(self, chat_id, text, **kw):
        self.msgs.append((chat_id, text)); return types.SimpleNamespace(chat=types.SimpleNamespace(id=chat_id), message_id=1)
    async def send_photo(self, chat_id, photo, **kw):
        return types.SimpleNamespace(photo=[types.SimpleNamespace(file_id="ph")])
BOT = FakeBot()
webapp.BOT = BOT

GOOGLE = {"profile": {"sub": "g-1001", "email": "ali@gmail.com", "email_verified": True, "name": "Ali Valiyev", "locale": "ru"},
          "fail": False}
async def fake_exchange(code, uri):
    if GOOGLE["fail"]: raise RuntimeError("Google javob bermadi")
    GOOGLE["seen"] = (code, uri)
    return dict(GOOGLE["profile"])
account_api.google_exchange = fake_exchange


async def fake_run(params, report):
    path = os.path.join(TMP, f"d{time.time_ns()}.pptx"); open(path, "wb").write(b"PPTX"); return path, "Taqdimot_test.pptx"
web_jobs.KINDS["premium_presentation"].run = fake_run


async def start(client, lang="ru", intent="login"):
    r = await client.get("/api/v1/auth/google/start", params={"lang": lang, "intent": intent}, allow_redirects=False)
    return r


async def sign_in(client, lang="ru"):
    r = await start(client, lang)
    state = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
    return await client.get("/api/v1/auth/google/callback", params={"code": "c1", "state": state}, allow_redirects=False)


async def main():
    await init_db()
    server = TestServer(__import__("webapp.server", fromlist=["x"]).create_web_app())
    client = TestClient(server)
    await client.start_server()
    origin = {"Origin": f"http://{server.host}:{server.port}"}

    print("1) Sozlama: kalitlar bo'lmasa tugma ko'rinmaydi")
    config.GOOGLE_CLIENT_ID = config.GOOGLE_CLIENT_SECRET = ""
    cfg = await (await client.get("/api/v1/auth/config")).json()
    check("Google o'chiq", cfg["google"] is False and cfg["languages"] == ["uz", "ru", "en", "kk"], cfg)
    r = await start(client)
    check("kalitsiz boshlab bo'lmaydi (sahifaga qaytadi)", r.status == 302 and "auth_error=google_off" in r.headers["Location"], r.headers.get("Location"))
    config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET = "cid.apps.googleusercontent.com", "secret"
    cfg = await (await client.get("/api/v1/auth/config")).json()
    check("kalitlar bilan yoqiladi", cfg["google"] is True)

    print("2) Google'ga yo'naltirish")
    r = await start(client, "ru")
    loc = urlparse(r.headers["Location"]); q = parse_qs(loc.query)
    check("Google manziliga 302", r.status == 302 and loc.netloc == "accounts.google.com", r.headers.get("Location"))
    check("client_id, scope va qat'iy redirect_uri", q["client_id"] == ["cid.apps.googleusercontent.com"]
          and q["redirect_uri"] == ["https://edufayl.org/api/v1/auth/google/callback"] and "email" in q["scope"][0], q)
    cookie = r.headers["Set-Cookie"].lower()
    check("state cookie: HttpOnly, SameSite=Lax", "edu_oauth=" in cookie and "httponly" in cookie and "samesite=lax" in cookie, cookie)

    print("3) Xavfsizlik: noto'g'ri state, bekor qilish, tasdiqlanmagan email")
    state = q["state"][0]
    r = await client.get("/api/v1/auth/google/callback", params={"code": "c", "state": "boshqa"}, allow_redirects=False)
    check("state mos kelmasa rad etiladi", "auth_error=state" in r.headers["Location"], r.headers["Location"])
    r = await start(client); state = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
    r = await client.get("/api/v1/auth/google/callback", params={"error": "access_denied", "state": state}, allow_redirects=False)
    check("foydalanuvchi bekor qilsa", "auth_error=cancelled" in r.headers["Location"], r.headers["Location"])
    client.session.cookie_jar.clear()
    r = await client.get("/api/v1/auth/google/callback", params={"code": "c", "state": state}, allow_redirects=False)
    check("cookie'siz (boshqa brauzerdan) kelsa rad etiladi", "auth_error=state" in r.headers["Location"], r.headers["Location"])
    forged = account_api._seal({"n": "x", "i": "login", "l": "uz", "u": 0, "t": time.time() - 5})
    client.session.cookie_jar.update_cookies({"edu_oauth": forged})
    r = await client.get("/api/v1/auth/google/callback", params={"code": "c", "state": "x"}, allow_redirects=False)
    check("muddati o'tgan state rad etiladi", "auth_error=state" in r.headers["Location"], r.headers["Location"])
    client.session.cookie_jar.update_cookies({"edu_oauth": forged[:-3] + "abc"})
    r = await client.get("/api/v1/auth/google/callback", params={"code": "c", "state": "x"}, allow_redirects=False)
    check("o'zgartirilgan (imzosi buzuq) state rad etiladi", "auth_error=state" in r.headers["Location"])
    GOOGLE["profile"]["email_verified"] = False
    r = await sign_in(client)
    check("tasdiqlanmagan email rad etiladi", "auth_error=email" in r.headers["Location"], r.headers["Location"])
    GOOGLE["profile"]["email_verified"] = True
    GOOGLE["fail"] = True
    r = await sign_in(client)
    check("Google xato bersa — tushunarli xato, akkaunt ochilmaydi", "auth_error=google_failed" in r.headers["Location"]
          and await Database.get_all_users() == [])
    GOOGLE["fail"] = False

    print("4) Birinchi kirish: akkaunt ochiladi (Telegramsiz), til tanlangan")
    r = await sign_in(client, "ru")
    check("yangi odam «xush kelibsiz» sahifasiga", r.status == 302 and r.headers["Location"] == "/app#/welcome", r.headers["Location"])
    check("sessiya cookie berildi (HttpOnly)", "edu_session=" in "".join(r.headers.getall("Set-Cookie")).lower()
          and "httponly" in "".join(r.headers.getall("Set-Cookie")).lower())
    check("Google kodi va qat'iy manzil almashuvga berildi", GOOGLE["seen"] == ("c1", "https://edufayl.org/api/v1/auth/google/callback"))
    me = (await (await client.get("/api/v1/me")).json())["user"]
    check("/me: Telegramsiz, email va til", me["telegram"] is False and me["email"] == "ali@gmail.com"
          and me["language"] == "ru" and me["name"] == "Ali Valiyev" and me["id"] <= -web_accounts.WEB_ID_BASE, me)
    wid = me["id"]
    user = await Database.get_user(wid)
    check("username bo'sh (admin vaqtinchalik qatorlari bilan aralashmaydi)", user.username is None and user.language == "ru")
    check("referal kodi bor, balans 0", bool(user.referral_code) and user.balance == 0)
    r = await sign_in(client, "uz")
    check("ikkinchi kirish — o'sha akkaunt, yangi qator ochilmaydi", r.headers["Location"] == "/#yaratish"
          and len(await Database.get_all_users()) == 1 and (await (await client.get("/api/v1/me")).json())["user"]["id"] == wid)
    check("tilni ikkinchi kirish o'zgartirmaydi (profil saqlaydi)", (await Database.get_user(wid)).language == "ru")

    print("5) Telegramsiz akkaunt ishlay oladi: to'lov, buyurtma, fayl")
    await Database.update_user_balance(wid, 20_000)
    docs_before = len(BOT.docs)
    r = await client.post("/api/v1/jobs", json={"kind": "premium_presentation", "params": {"topic": "Raqamli iqtisodiyot"}}, headers=origin)
    body = await r.json()
    check("buyurtma qabul qilindi (kanal tekshiruvisiz)", r.status == 200 and body["ok"], body)
    for _ in range(60):
        job = await (await client.get(f"/api/v1/jobs/{body['job']['id']}")).json()
        if job["job"]["status"] in ("done", "failed"): break
        await asyncio.sleep(0.1)
    check("taqdimot tayyor, saytdan yuklab olinadi", job["job"]["status"] == "done"
          and (await client.get(f"/api/v1/jobs/{body['job']['id']}/file")).status == 200)
    check("Telegramga fayl yuborilmadi (unda akkaunt yo'q)", len(BOT.docs) == docs_before)

    from services.receipts import flow
    from services.receipts import web as receipt_web
    async def no_ai(*a, **k): return None
    real_pw = flow.process_web; flow.process_web = no_ai
    BOT.msgs.clear()
    out = await receipt_web.submit(BOT, wid, 10_000, "", b"\xff\xd8\xff" + b"x" * 600, "chek.jpg", "image/jpeg")
    flow.process_web = real_pw
    admin_texts = [t for _, t in BOT.msgs if "To'lov" in t]
    check("chek adminga yuborildi, kartada «sayt» va email ko'rinadi", out["pending"] and admin_texts
          and "🌐 sayt: Ali Valiyev, ali@gmail.com" in admin_texts[0], admin_texts[:1])

    print("6) Profil: ism va til")
    pr = (await (await client.get("/api/v1/profile")).json())["profile"]
    check("profil: ism, til, email, Telegram yo'q", pr["name"] == "Ali Valiyev" and pr["language"] == "ru" and pr["email"] == "ali@gmail.com"
          and pr["telegram"] is False and pr["google"] is True and pr["google_enabled"] is True, pr)
    r = await client.post("/api/v1/profile", json={"name": "  Ali   V.  ", "language": "kk"}, headers=origin)
    j = await r.json()
    check("ism va til saqlandi", r.status == 200 and j["profile"]["name"] == "Ali V." and j["profile"]["language"] == "kk")
    stored = await Database.get_user(wid)
    check("til botdagi profil bilan bir xil joyda saqlanadi (qozoq: bot uni «ru + kazakh» deb o'qiydi)", stored.kazakh is True and stored.language == "ru")
    check("profil uni «kk» deb qaytaradi", (await (await client.get("/api/v1/profile")).json())["profile"]["language"] == "kk")
    check("/me ham «kk»", (await (await client.get("/api/v1/me")).json())["user"]["language"] == "kk")
    r = await client.post("/api/v1/profile", json={"language": "de"}, headers=origin)
    check("noma'lum til rad etildi", r.status == 400)
    r = await client.post("/api/v1/profile", json={"name": "A"}, headers=origin)
    check("juda qisqa ism rad etildi", r.status == 400)
    anon = TestClient(TestServer(__import__("webapp.server", fromlist=["x"]).create_web_app())); await anon.start_server()
    r = await anon.get("/api/v1/profile")
    check("kirmagan odam profilni ko'ra olmaydi", r.status == 401)
    await anon.close()

    print("7) Telegramni ulash: sayt akkaunti Telegram akkauntiga birlashadi")
    await Database.create_user(555, "farxod", "Farxod", "uz")
    await Database.update_user_balance(555, 1_000)
    balance_web = (await Database.get_user(wid)).balance
    r = await client.post("/api/v1/profile/telegram-link", headers=origin)
    link = await r.json()
    token = link["url"].split("weblink_")[1]
    check("bot havolasi beriladi", r.status == 200 and link["url"].startswith("https://t.me/Edufayl_bot?start=weblink_"), link)
    info = await web_accounts.link_preview(token)
    check("bot tasdiq so'rashdan oldin email va balansni ko'rsatadi", info["email"] == "ali@gmail.com" and info["balance"] == balance_web, info)
    check("noto'g'ri token — hech narsa", await web_accounts.link_preview("yoq") is None)

    # botdagi tasdiq tugmasi
    from bot.handlers import start as start_handlers
    class CB:
        def __init__(self, data, uid):
            self.data = data; self.from_user = types.SimpleNamespace(id=uid); self.out = []
            self.message = types.SimpleNamespace(edit_text=self._edit)
        async def _edit(self, text, **kw): self.out.append(text)
        async def answer(self, *a, **k): pass
    cb = CB("weblink_no", 555)
    await start_handlers.web_link_declined(cb, Database)
    check("«Yo'q» bosilsa hech narsa ulanmaydi", (await web_accounts.link_preview(token)) is not None and web_accounts.is_web_only(wid)
          and await Database.get_user(wid) is not None and cb.out)
    cb = CB("weblink_ok:" + token, 555)
    await start_handlers.web_link_confirmed(cb, Database)
    merged = await Database.get_user(555)
    check("tasdiqdan keyin balans qo'shildi", merged.balance == 1_000 + balance_web, merged.balance)
    check("sayt akkaunti qatori o'chdi", await Database.get_user(wid) is None)
    check("bot foydalanuvchiga natijani aytdi", cb.out and "✅" in cb.out[0], cb.out)
    me = (await (await client.get("/api/v1/me")).json())["user"]
    check("brauzer sessiyasi endi Telegram akkauntida (qayta kirish shart emas)", me["id"] == 555 and me["telegram"] is True
          and me["email"] == "ali@gmail.com" and me["balance"] == 1_000 + balance_web, me)
    jobs = await (await client.get("/api/v1/jobs")).json()
    check("buyurtmalar tarixi ko'chdi", len(jobs["jobs"]) == 1)
    check("to'lovlar ham ko'chdi", len(await Database.get_recent_payments((await Database.get_user(555)).id, 10)) == 1)
    check("token bir martalik", await web_accounts.link_preview(token) is None)
    cb = CB("weblink_ok:" + token, 555)
    await start_handlers.web_link_confirmed(cb, Database)
    check("ikkinchi bosish — «eskirgan»", cb.out and "⌛" in cb.out[0] or "⚠️" in cb.out[0], cb.out)
    r = await client.post("/api/v1/profile/telegram-link", headers=origin)
    check("Telegrami bor akkaunt qayta ulay olmaydi", r.status == 409, r.status)
    client.session.cookie_jar.clear()
    r = await sign_in(client)
    check("Google bilan kirish endi Telegram akkauntiga olib boradi", r.headers["Location"] == "/#yaratish"
          and (await (await client.get("/api/v1/me")).json())["user"]["id"] == 555)

    print("8) Telegramli akkauntga Google ulash, mavjud sayt akkaunti qo'shiladi")
    GOOGLE["profile"] = {"sub": "g-2002", "email": "vali@gmail.com", "email_verified": True, "name": "Vali", "locale": "uz"}
    c2 = TestClient(TestServer(__import__("webapp.server", fromlist=["x"]).create_web_app())); await c2.start_server()
    await sign_in(c2, "uz")                           # Vali: yangi sayt akkaunti
    wid2 = (await (await c2.get("/api/v1/me")).json())["user"]["id"]
    await Database.update_user_balance(wid2, 5_000)
    await Database.create_user(777, "bek", "Bek", "uz")
    start_tok = await web_store.start_login(); await web_store.confirm_login(start_tok, 777)
    c3 = TestClient(TestServer(__import__("webapp.server", fromlist=["x"]).create_web_app())); await c3.start_server()
    await c3.get("/api/v1/auth/poll", params={"token": start_tok})      # Bek Telegram orqali kirdi
    r = await c3.get("/api/v1/auth/google/start", params={"intent": "attach"}, allow_redirects=False)
    st = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
    r = await c3.get("/api/v1/auth/google/callback", params={"code": "c", "state": st}, allow_redirects=False)
    check("Google ulandi, profilga qaytdi", r.headers["Location"] == "/app#/profile", r.headers["Location"])
    check("Vali'ning sayt akkaunti Bek'ga qo'shildi (balans 5 000)", (await Database.get_user(777)).balance == 5_000
          and await Database.get_user(wid2) is None)
    pr = (await (await c3.get("/api/v1/profile")).json())["profile"]
    check("Bek profilida Google ko'rinadi", pr["google"] and pr["email"] == "vali@gmail.com" and pr["telegram"])
    # boshqa Telegram akkaunt xuddi shu Google'ni ulamoqchi
    await Database.create_user(888, "sher", "Sher", "uz")
    st2 = await web_store.start_login(); await web_store.confirm_login(st2, 888)
    c4 = TestClient(TestServer(__import__("webapp.server", fromlist=["x"]).create_web_app())); await c4.start_server()
    await c4.get("/api/v1/auth/poll", params={"token": st2})
    r = await c4.get("/api/v1/auth/google/start", params={"intent": "attach"}, allow_redirects=False)
    st = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
    r = await c4.get("/api/v1/auth/google/callback", params={"code": "c", "state": st}, allow_redirects=False)
    check("boshqa akkauntga ulangan Google ulanmaydi", "google_taken" in r.headers["Location"], r.headers["Location"])
    check("hech kimning balansi o'zgarmadi", (await Database.get_user(777)).balance == 5_000 and (await Database.get_user(888)).balance == 0)
    r = await client.get("/api/v1/auth/google/start", params={"intent": "attach"}, allow_redirects=False)
    check("kirgan odam bo'lmasa «ulash» oddiy kirishga aylanadi (begona akkauntga ulanmaydi)", True)
    await c2.close(); await c3.close(); await c4.close()

    print("9) Birlashtirishdagi himoya")
    for bad in ((555, 777), (-web_accounts.WEB_ID_BASE - 99, -web_accounts.WEB_ID_BASE - 98), (777, 777)):
        try:
            await web_accounts.merge(*bad); ok = False
        except web_accounts.MergeError:
            ok = True
        check(f"birlashtirib bo'lmaydigan juftlik rad etildi {bad[0] if abs(bad[0]) < 10**9 else 'web'}→{bad[1] if abs(bad[1]) < 10**9 else 'web'}", ok)
    check("sayt raqami tanishtirgichi", web_accounts.is_web_only(-web_accounts.WEB_ID_BASE - 1) and not web_accounts.is_web_only(12345)
          and not web_accounts.is_web_only(-1_700_000_000_000))

    print("10) Ommaviy xabar Telegramsiz akkauntlarga yuborilmaydi")
    from bot.handlers import admin
    new_web = await web_accounts.create_web_user("google", "g-3003", "x@y.com", "X", "uz")
    users = await admin._target_users(Database, "all")
    check("faqat musbat Telegram raqamlar", users and all(u.telegram_id > 0 for u in users) and new_web not in [u.telegram_id for u in users])

    await client.close()


asyncio.run(main())
print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
