"""Saytdagi tayyor fayllar: yopiq guruh (ombor), 30 kun, yangilashdan keyin yo'qolmaydi, chiroyli «fayl yo'q».

- fayllar `data/web_jobs` da (temp emas): bot qayta ishga tushganda / har 30 daqiqalik tozalashda o'chmaydi;
  eski joydagilar ko'chiriladi, bazadagi yo'llar yangilanadi;
- tayyor fayl yopiq guruhga yuklanadi (`file_id`), «Hujjatlarim» da 30 kun; serverdagi nusxa 3 kundan keyin o'chadi;
- nusxa yo'q bo'lsa: yuklab olishda ombordan qaytariladi, Telegramga `file_id` bilan (serverdan yuklamasdan);
- fayl umuman bo'lmasa — brauzerda tushunarli sahifa (xom JSON emas);
- tahrirdan keyin yangi nusxa omborga yuklanadi.

    python test_sayt_ombor.py
"""
import asyncio
import os
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["WEB_ARCHIVE_CHAT_ID"] = "-100777"
TMP = tempfile.mkdtemp()
os.environ["WEB_JOBS_DIR"] = os.path.join(TMP, "data_web_jobs")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


import aiosqlite  # noqa: E402
import database.database as dbmod  # noqa: E402
from database.database import Database, init_db  # noqa: E402

dbmod.DATABASE_FILE = os.path.join(TMP, "t.db")
import webapp  # noqa: E402
from database import web_accounts, web_store  # noqa: E402
from services import web_archive, web_jobs, web_kinds  # noqa: E402,F401
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

web_jobs.LEGACY_RESULTS_DIR = os.path.join(TMP, "temp", "web_jobs")


class Bot:
    def __init__(self):
        self.vault, self.user_docs, self.fetches, self.n, self.msgs = [], [], 0, 0, []
        self.big = set()
        self.files = {}
    async def send_document(self, chat_id, document, caption=None, **kw):
        self.n += 1
        if str(chat_id) == "-100777":
            fid = f"FID{self.n}"
            self.files[fid] = open(document.path, "rb").read()
            self.vault.append((fid, caption))
            return types.SimpleNamespace(document=types.SimpleNamespace(file_id=fid))
        self.user_docs.append((chat_id, document if isinstance(document, str) else "UPLOAD:" + document.filename))
        self.captions = getattr(self, "captions", []) + [caption]
        return types.SimpleNamespace(document=types.SimpleNamespace(file_id=f"U{self.n}"))
    async def send_message(self, chat_id, text, **kw):
        self.msgs.append((chat_id, text))
        return types.SimpleNamespace(message_id=1, chat=types.SimpleNamespace(id=chat_id))
    async def get_file(self, file_id):
        self.fetches += 1
        size = 30 * 1024 * 1024 if file_id in self.big else len(self.files.get(file_id, b""))
        return types.SimpleNamespace(file_path="f/" + file_id, file_size=size)
    async def download_file(self, file_path, destination):
        open(destination, "wb").write(self.files[file_path.split("/", 1)[1]])


BOT = Bot()
webapp.BOT, webapp.BOT_USERNAME = BOT, "Edufayl_bot"


async def fake_run(params, report):
    path = os.path.join(TMP, f"deck_{time.time_ns()}.pptx")
    open(path, "wb").write(b"PPTX:" + params["topic"].encode())
    return path, "Taqdimot_test.pptx"
web_jobs.KINDS["premium_presentation"].run = fake_run


async def wait_job(client, job_id):
    for _ in range(200):
        data = await (await client.get(f"/api/v1/jobs/{job_id}")).json()
        if data["job"]["status"] in ("done", "failed"):
            return data
        await asyncio.sleep(0.05)
    return data


async def make_job(client, origin, topic):
    r = await client.post("/api/v1/jobs", json={"kind": "premium_presentation", "params": {"topic": topic, "slide_count": 10}},
                          headers=origin)
    job = (await r.json())["job"]
    await wait_job(client, job["id"])
    await asyncio.sleep(0.3)                      # omborga yuklash va Telegramga yuborish (fonda)
    return await web_store.get_job(job["id"])


HTML = {"Accept": "text/html,application/xhtml+xml"}


async def main():
    import main as mainmod
    from webapp.server import create_web_app
    await init_db()
    await Database.create_user(100, "ali", "Ali", "uz")
    await Database.update_user_balance(100, 200_000)

    print("1) Fayllar temp'da emas: tozalash va qayta ishga tushish ularni o'chirmaydi")
    check("doimiy papka (data/web_jobs), temp emas", "temp" not in os.path.relpath(web_jobs.RESULTS_DIR, TMP).split(os.sep)
          and os.path.join("data", "web_jobs") in os.path.join("data", "web_jobs"))
    real_dir = os.path.join(HERE, "data", "web_jobs")
    check("asl papka: <loyiha>/data/web_jobs", web_jobs._ROOT == HERE and real_dir.endswith(os.path.join("data", "web_jobs")))
    legacy = web_jobs.LEGACY_RESULTS_DIR
    os.makedirs(os.path.join(legacy, "decks", "abc"), exist_ok=True)
    old_file = os.path.join(legacy, "eski123.pptx")
    open(old_file, "wb").write(b"PPTX:eski")
    os.utime(old_file, (time.time() - 5 * 3600, time.time() - 5 * 3600))
    await web_store.create_job("eski123", 100, "premium_presentation", "Eski ish", {}, 0)
    await web_store.update_job("eski123", status="done", result_path=old_file, result_name="Eski.pptx")
    moved = web_jobs.migrate_legacy()
    await web_jobs.fix_legacy_paths()
    row = await web_store.get_job("eski123")
    check("eski joydagi fayllar ko'chirildi, bazadagi yo'l yangilandi", moved >= 2 and os.path.exists(row["result_path"])
          and row["result_path"].startswith(web_jobs.RESULTS_DIR), (moved, row["result_path"]))
    temp_web = os.path.join(mainmod.TEMP_DIR, "web_jobs")
    os.makedirs(temp_web, exist_ok=True)
    probe = os.path.join(temp_web, "probe_test.pptx")
    open(probe, "wb").write(b"x"); os.utime(probe, (time.time() - 7200, time.time() - 7200))
    mainmod._prune_temp(time.time())
    check("temp tozalash temp/web_jobs ga tegmaydi (ehtiyot uchun)", os.path.exists(probe))
    os.remove(probe)

    server = TestServer(create_web_app()); client = TestClient(server); await client.start_server()
    origin = {"Origin": f"http://{server.host}:{server.port}"}
    token = await web_accounts.create_session(100)
    client.session.cookie_jar.update_cookies({"edu_session": token}, server.make_url("/"))

    print("2) Tayyor fayl yopiq guruhga yuklanadi, 30 kun")
    job = await make_job(client, origin, "Soliq hisobi")
    check("omborga (yopiq guruhga) yuklandi, file_id saqlandi", job["vault_file_id"] and BOT.vault
          and BOT.vault[-1][0] == job["vault_file_id"] and "Soliq hisobi" in BOT.vault[-1][1], (job["vault_file_id"], BOT.vault))
    check("mijozga Telegramda ombordagi nusxa (file_id) yuborildi — serverdan qayta yuklanmadi",
          BOT.user_docs and BOT.user_docs[-1] == (100, job["vault_file_id"]), BOT.user_docs)
    reminders = [m for m in BOT.msgs if "AI yordamida yaratilgan" in m[1]]
    check("fayl ostida faqat mavzu, keyin bitta «💡 Muhim eslatma» xabari", BOT.captions[-1] == "Soliq hisobi"
          and len(reminders) == 1 and reminders[0][0] == 100, (BOT.captions, BOT.msgs))
    pub = (await (await client.get("/api/v1/jobs")).json())
    j = next(x for x in pub["jobs"] if x["id"] == job["id"])
    days = (j["expires_at"] - time.time()) / 86400
    check("«Hujjatlarim» da 30 kun turadi", 29.9 < days <= 30 and j["archived"] and pub["ttl_days"] == 30, (days, pub["ttl_days"]))

    print("3) Serverdagi nusxa o'chgan (qayta ishga tushish / 3 kun) — ombordan qaytadi")
    os.remove(job["result_path"])
    r = await client.get(f"/api/v1/jobs/{job['id']}/file", headers=HTML)
    body = await r.read()
    check("«Yuklab olish» ishlaydi: fayl ombordan olindi", r.status == 200 and body == b"PPTX:Soliq hisobi" and BOT.fetches == 1,
          (r.status, body[:40]))
    await asyncio.sleep(0.3)
    check("ombordan qaytarilgan nusxa omborga qayta yuklanmaydi (o'sha fayl)", len(BOT.vault) == 1
          and (await web_store.get_job(job["id"]))["vault_file_id"] == job["vault_file_id"], BOT.vault)
    n = len(BOT.user_docs)
    web_jobs._sent_at.clear()
    os.remove(job["result_path"])
    r = await client.post(f"/api/v1/jobs/{job['id']}/telegram", headers=origin)
    check("«📩 Telegramga yuborish» serverda nusxa bo'lmasa ham ishlaydi (file_id bilan)", r.status == 200
          and BOT.user_docs[-1] == (100, job["vault_file_id"]) and len(BOT.user_docs) == n + 1, (r.status, BOT.user_docs[n:]))

    check("«Yuklab olish» / qayta yuborishda eslatma takrorlanmaydi",
          len([m for m in BOT.msgs if "AI yordamida yaratilgan" in m[1]]) == 1, BOT.msgs)
    print("4) Fayl yo'q — chiroyli sahifa")
    BOT.big.add(job["vault_file_id"])
    r = await client.get(f"/api/v1/jobs/{job['id']}/file", headers=HTML)
    page = await r.text()
    check("katta fayl (ombordan qaytmaydi) — «Telegram orqali beriladi» sahifasi, tugma bilan",
          r.headers["Content-Type"].startswith("text/html") and "Fayl Telegram orqali beriladi" in page
          and f'data-tg-send="{job["id"]}"' in page and "{\"ok\"" not in page, page[:300])
    BOT.big.clear()
    r = await client.get("/api/v1/jobs/yoqishi123/file", headers=HTML)
    page = await r.text()
    check("muddati o'tgan / o'chirilgan — «Bu fayl endi mavjud emas» (xom JSON emas)", r.status == 404
          and "Bu fayl endi mavjud emas" in page and "Hujjatlarim" in page and "not_found" not in page, page[:200])
    r = await client.get("/api/v1/jobs/yoqishi123/file")
    check("API so'rovi (brauzer emas) — avvalgidek JSON", r.status == 404 and (await r.json())["code"] == "not_found")
    saved = client.session.cookie_jar.filter_cookies(server.make_url("/"))
    client.session.cookie_jar.clear()
    r = await client.get(f"/api/v1/jobs/{job['id']}/file", headers=HTML)
    check("kirilmagan — «Avval kiring» sahifasi", "Avval kiring" in await r.text())
    for m in saved.values():
        client.session.cookie_jar.update_cookies({m.key: m.value}, server.make_url("/"))
    await web_store.create_job("yoqol1", 100, "premium_presentation", "Yo'qolgan", {}, 0)
    await web_store.update_job("yoqol1", status="done", result_path=os.path.join(TMP, "yoq.pptx"), tg_sent=1)
    page = await (await client.get("/api/v1/jobs/yoqol1/file", headers=HTML)).text()
    check("omborsiz va serverda yo'q, lekin Telegramga yuborilgan — «Fayl Telegram chatingizda», «Botni ochish»",
          "Fayl Telegram chatingizda" in page and "t.me/Edufayl_bot" in page, page[:300])

    print("5) Tahrirdan keyin yangi nusxa omborga")
    job = await make_job(client, origin, "Tahrir sinovi")
    first = job["vault_file_id"]
    with open(job["result_path"], "ab") as fh:
        fh.write(b" tahrirlangan")
    web_jobs._sent_at.clear()
    await (await client.get(f"/api/v1/jobs/{job['id']}/file", headers=HTML)).read()
    await asyncio.sleep(0.3)
    job2 = await web_store.get_job(job["id"])
    check("tahrirlangan fayl omborga qayta yuklandi va Telegramga o'shasi ketdi",
          job2["vault_file_id"] != first and BOT.files[job2["vault_file_id"]].endswith(b" tahrirlangan")
          and BOT.user_docs[-1] == (100, job2["vault_file_id"]), (first, job2["vault_file_id"]))

    print("6) Muddatlar: serverdagi nusxa 3 kun, «Hujjatlarim» 30 kun")
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        await conn.execute("UPDATE web_jobs SET created_at = ? WHERE id = ?", (time.time() - 5 * 86400, job["id"]))
        await conn.commit()
    os.utime(job2["result_path"], (time.time() - 5 * 86400, time.time() - 5 * 86400))
    await web_jobs.purge()
    row = await web_store.get_job(job["id"])
    check("5 kunlik ish: serverdagi nusxa o'chdi, «Hujjatlarim» da qoldi", row is not None and not os.path.exists(row["result_path"]))
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        await conn.execute("UPDATE web_jobs SET created_at = ? WHERE id = ?", (time.time() - 31 * 86400, job["id"]))
        await conn.execute("UPDATE web_jobs SET created_at = ?, vault_file_id = '' WHERE id = 'eski123'", (time.time() - 4 * 86400,))
        await conn.commit()
    await web_jobs.purge()
    check("31 kunlik ish o'chdi; omborsiz 4 kunlik ish ham o'chdi", await web_store.get_job(job["id"]) is None
          and await web_store.get_job("eski123") is None)

    await client.close()
    print("\n✅ hammasi o'tdi" if not FAILS else f"\n❌ {len(FAILS)} ta xato: {FAILS}")
    sys.exit(1 if FAILS else 0)


asyncio.run(main())
