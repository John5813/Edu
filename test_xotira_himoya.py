"""Server xotirasi to'lib bot qotib qolmasligi va mijoz buyurtmasi yo'qolmasligi.

- heavy_gate: bir vaqtda ko'pi bilan `parallel()` ta og'ir ish; bo'sh xotira yetmasa ish boshlanmaydi (kutadi);
  mijoz ishi fon ishidan oldin; ichma-ich so'rov (bosqich → render, oqimga o'tgan ruxsat) qayta kutmaydi;
  hech narsa ishlamasa-yu xotira baribir kam bo'lsa — buyurtma abadiy osilmaydi; kutish bekor qilinsa navbat
  tozalanadi; brauzer/node jarayonlari Linux uchun "birinchi qurbon";
- render bosqichida navbatda kutish vaqt chegarasiga kirmaydi;
- bot_orders: pul olingan buyurtma bot o'chib qolsa — keyingi ishga tushishda pul qaytadi, mijozga uzr;
  hujjatlar (pul hali yechilmagan) — faqat xabar; tugagan buyurtmalar tegilmaydi;
- memory_watch: xotira kam bo'lsa adminga xabar (ketma-ket ikki o'qishda);
- navbat mijozga ko'rinmaydi: "navbatdagi o'rningiz", "oldingizda N ta" yo'q, faktlar almashadi.

    python test_xotira_himoya.py
"""
import asyncio
import os
import sys
import tempfile
import threading
import time
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


from services import heavy_gate as hg  # noqa: E402

print("1) Og'ir ishlar darvozasi")
with mock.patch.dict(os.environ, {"HEAVY_PARALLEL": ""}), \
        mock.patch.object(hg, "meminfo", return_value={"MemTotal": 1970}):
    check("2 GB serverda bir vaqtda bitta og'ir ish", hg.parallel() == 1, hg.parallel())
with mock.patch.dict(os.environ, {"HEAVY_PARALLEL": ""}), \
        mock.patch.object(hg, "meminfo", return_value={"MemTotal": 3900}):
    check("4 GB serverda ikkita", hg.parallel() == 2, hg.parallel())

# Bitta ish ishlayotganda ikkinchisi kutadi, birinchisi chiqqach kiradi.
order, inside = [], []
with mock.patch.object(hg, "parallel", return_value=1), mock.patch.object(hg, "available_mb", return_value=1500):
    release = threading.Event()

    def first():
        with hg.slot("brauzer 1", 450):
            order.append("1 kirdi")
            inside.append(1)
            release.wait(5)
            inside.remove(1)
            order.append("1 chiqdi")

    def second():
        with hg.slot("brauzer 2", 450):
            order.append("2 kirdi" + (" (1 ichida!)" if inside else ""))

    t1 = threading.Thread(target=first)
    t1.start()
    time.sleep(0.2)
    t2 = threading.Thread(target=second)
    t2.start()
    time.sleep(0.8)
    check("ikkinchi ish birinchisi tugaguncha boshlanmaydi", order == ["1 kirdi"], order)
    snap = hg.snapshot()
    check("admin uchun: 1 ishlayapti, 1 kutyapti", len(snap["active"]) == 1 and len(snap["waiting"]) == 1, snap)
    release.set()
    t1.join(5)
    t2.join(5)
    check("... keyin navbat bilan o'tadi", order == ["1 kirdi", "1 chiqdi", "2 kirdi"], order)

# Bo'sh xotira yetmasa ish boshlanmaydi; xotira bo'shagach boshlanadi.
memory = {"avail": 500}
with mock.patch.object(hg, "parallel", return_value=2), \
        mock.patch.object(hg, "available_mb", side_effect=lambda: memory["avail"]), \
        mock.patch.object(hg, "GRACE", 60.0):
    blocker = threading.Event()

    def holder():
        with hg.slot("LibreOffice", 350):
            blocker.wait(5)

    th = threading.Thread(target=holder)
    th.start()
    time.sleep(0.2)
    entered = threading.Event()

    def browser():
        with hg.slot("brauzer", 450):
            entered.set()

    tb = threading.Thread(target=browser)
    tb.start()
    time.sleep(1.0)
    check("bo'sh xotira yetmasa (500 MB < 450+250) — brauzer ochilmaydi, kutadi", not entered.is_set())
    memory["avail"] = 1200
    check("xotira bo'shagach — boshlanadi", entered.wait(3))
    blocker.set()
    th.join(5)
    tb.join(5)

# Hech narsa ishlamayapti, xotira baribir kam (bot o'zi katta) — buyurtma abadiy osilmaydi.
with mock.patch.object(hg, "parallel", return_value=1), mock.patch.object(hg, "available_mb", return_value=150), \
        mock.patch.object(hg, "GRACE", 0.5):
    t0 = time.time()
    with hg.slot("brauzer", 450):
        waited = time.time() - t0
    check("boshqa ish bo'lmasa, qisqa kutishdan keyin baribir boshlanadi", 0.4 <= waited < 3, waited)

# Ustuvorlik: mijoz ishi fon ishidan oldin.
with mock.patch.object(hg, "parallel", return_value=1), mock.patch.object(hg, "available_mb", return_value=1500):
    seq = []
    gate_open = threading.Event()

    def hold():
        with hg.slot("band", 100):
            gate_open.wait(5)

    def worker(label, prio):
        with hg.slot(label, 100, prio):
            seq.append(label)

    h = threading.Thread(target=hold)
    h.start()
    time.sleep(0.2)
    bg = threading.Thread(target=worker, args=("fon", hg.FON))
    bg.start()
    time.sleep(0.2)
    client = threading.Thread(target=worker, args=("mijoz", hg.ODDIY))
    client.start()
    time.sleep(0.2)
    gate_open.set()
    for t in (h, bg, client):
        t.join(5)
    check("mijoz ishi fon ishidan oldin o'tadi (fon oldin kelgan bo'lsa ham)", seq == ["mijoz", "fon"], seq)

    with hg.fon():
        check("fon() ichida sukut ustuvorlik — FON", hg._priority.get() == hg.FON)
    check("fon() dan keyin — oddiy", hg._priority.get() == hg.ODDIY)

# Ichma-ich: asinxron ruxsat oqimga o'tadi, ichidagi slot kutmaydi (aks holda parallel=1 da qotib qolardi).
with mock.patch.object(hg, "parallel", return_value=1), mock.patch.object(hg, "available_mb", return_value=1500):
    async def nested():
        async with hg.aslot("bosqich", 450):
            def inner():
                with hg.slot("render", 450):
                    return "ichkarida"
            return await asyncio.wait_for(asyncio.to_thread(inner), 3)

    try:
        check("bosqich ruxsati ichidagi render qayta kutmaydi (qotib qolmaydi)", asyncio.run(nested()) == "ichkarida")
    except asyncio.TimeoutError:
        check("bosqich ruxsati ichidagi render qayta kutmaydi (qotib qolmaydi)", False, "deadlock")
    check("ishdan keyin hech narsa band emas", not hg.snapshot()["active"] and not hg.snapshot()["waiting"],
          hg.snapshot())

# Kutish bekor qilinsa (mijoz vazifasi to'xtatildi) — navbatda "arvoh" qolmaydi.
with mock.patch.object(hg, "parallel", return_value=1), mock.patch.object(hg, "available_mb", return_value=1500):
    async def cancelled():
        hold_evt = asyncio.Event()

        async def holder():
            async with hg.aslot("band", 100):
                await hold_evt.wait()

        h = asyncio.create_task(holder())
        await asyncio.sleep(0.1)
        waiter = asyncio.create_task(hg.aslot("kutuvchi", 100).__aenter__())
        await asyncio.sleep(0.7)
        waiter.cancel()
        await asyncio.sleep(0.1)
        queued = len(hg.snapshot()["waiting"])
        hold_evt.set()
        await h
        return queued

    check("bekor qilingan kutish navbatdan o'chadi", asyncio.run(cancelled()) == 0)

# pipeline: render bosqichida kutish vaqt chegarasiga kirmaydi.
from services.premium_presentation import pipeline  # noqa: E402

with mock.patch.object(hg, "parallel", return_value=1), mock.patch.object(hg, "available_mb", return_value=1500), \
        mock.patch.dict(pipeline.STEP_TIMEOUTS, {"render": 1}):
    release_evt = threading.Event()

    def other_client():                                # boshqa mijozning brauzeri 1,5 s band (chegara 1 s)
        with hg.slot("boshqa mijoz brauzeri", 450):
            release_evt.wait(5)

    async def render_wait():
        loop = asyncio.get_running_loop()
        loop.call_later(1.5, release_evt.set)

        def render():
            with hg.slot("brauzer (taqdimot)", 450):
                return "tayyor"
        return await pipeline.run_step(loop, render, step="render", label="Slaydlar")

    other = threading.Thread(target=other_client)
    other.start()
    time.sleep(0.2)
    try:
        got = asyncio.run(render_wait())
    except RuntimeError as exc:
        got = str(exc)
    other.join(5)
    check("render navbatda 1,5 s kutdi, lekin 1 s chegara bilan bekor bo'lmadi", got == "tayyor", got)

# Kernel: brauzer/node — birinchi qurbon.
import subprocess  # noqa: E402

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
try:
    with mock.patch.object(hg, "VICTIMS", ("python",)):
        marked = hg.mark_children()
    score = open(f"/proc/{child.pid}/oom_score_adj").read().strip()
    check("bola jarayon oom_score_adj=1000 bilan belgilanadi", marked >= 1 and score == "1000", (marked, score))
    check("botning o'zi belgilanmaydi", open(f"/proc/{os.getpid()}/oom_score_adj").read().strip() != "1000")
finally:
    child.kill()
    child.wait()
top = hg.top_processes(3)
check("eng ko'p yeydigan jarayonlar ro'yxati", top and all(mb > 0 for _n, _p, mb in top), top)

print("2) Bot o'chib qolsa — buyurtma unutilmaydi")
import aiosqlite  # noqa: E402

from database import database as dbmod  # noqa: E402

TMP = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(TMP, "bot.db")
from database import bot_orders  # noqa: E402


async def scenario():
    await dbmod.init_db()
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        await conn.execute("INSERT INTO users (telegram_id, first_name, language, balance) VALUES (111, 'A', 'uz', 0)")
        await conn.execute("INSERT INTO users (telegram_id, first_name, language, balance) VALUES (222, 'B', 'ru', 5000)")
        await conn.commit()
    # Oldingi jarayon: ikki buyurtma ishlayotgan edi, biri tugagan.
    paid = await bot_orders.start(111, 111, "kat3d", "Amir Temur", 20000, "uz")
    done = await bot_orders.start(222, 222, "taqdimot", "Tugagan", 9000, "ru")
    await bot_orders.finish(done)
    stars = await bot_orders.start(222, 222, "loyiha_ishi", "Loyiha", 0, "ru")
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        await conn.execute("UPDATE bot_orders SET created_at = created_at - 10")
        # Hujjat: pul hali yechilmagan, oldingi jarayonda "generating" bo'lib qolgan.
        await conn.execute("INSERT INTO document_orders (user_id, document_type, topic, specifications, status) "
                           "VALUES ((SELECT id FROM users WHERE telegram_id = 111), 'referat', 'Fotosintez', '{}', "
                           "'generating')")
        await conn.commit()
    bot_orders.STARTED = time.time()
    await dbmod.init_db()                              # qayta ishga tushish: hujjat ham olinadi
    sent = []

    class Bot:
        async def send_message(self, chat_id, text, **kw):
            sent.append((chat_id, text))

    count = await bot_orders.recover(Bot())
    await asyncio.sleep(0.5)
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        async with conn.execute("SELECT telegram_id, balance FROM users ORDER BY telegram_id") as cur:
            balances = dict(await cur.fetchall())
        async with conn.execute("SELECT COUNT(*) FROM bot_orders") as cur:
            left = (await cur.fetchone())[0]
    again = await bot_orders.recover(Bot())
    # Yangi jarayonda boshlangan buyurtma qayta tiklashga tushmaydi.
    fresh = await bot_orders.start(111, 111, "taqdimot", "Yangi", 5000, "uz")
    taken = await bot_orders.take_interrupted()
    await bot_orders.finish(fresh)
    return paid, stars, count, sent, balances, left, again, taken


paid, stars, count, sent, balances, left, again, taken = asyncio.run(scenario())
check("3 ta uzilgan buyurtma topildi (taqdimot, loyiha, hujjat), tugagani yo'q", count == 3, (count, sent))
check("olingan pul qaytdi (20 000), olinmagan joyda balans o'zgarmadi",
      balances == {111: 20000, 222: 5000}, balances)
texts = {chat: [t for c, t in sent if c == chat] for chat in (111, 222)}
check("mijozga uzr: pul qaytgani aytildi", any("20,000" in t and "qaytarildi" in t for t in texts[111]), texts)
check("hujjat egasiga: pul yechilmagani aytildi", any("Fotosintez" in t and "yechilmagan" in t for t in texts[111]),
      texts)
check("rus tilida yozildi", any("Извините" in t for t in texts[222]), texts)
check("qatorlar o'chirildi, ikkinchi ishga tushishda qayta qaytarilmaydi", left == 0 and again == 0, (left, again))
check("yangi jarayonda boshlangan buyurtma tegilmaydi", taken == [], taken)

print("3) Xotira kam — adminga xabar")
from services import memory_watch  # noqa: E402

alerts = []
with mock.patch.object(memory_watch.admin_alerts, "alert", side_effect=lambda key, text: alerts.append((key, text))), \
        mock.patch.object(memory_watch.heavy_gate, "available_mb", return_value=180), \
        mock.patch.object(memory_watch.heavy_gate, "meminfo", return_value={"MemTotal": 1970, "MemAvailable": 180}), \
        mock.patch.object(memory_watch, "disk_free_gb", return_value=30.0):
    state = {}
    memory_watch.check_once(state)
    check("bitta past o'qish — hali xabar yo'q (qisqa sakrash)", not alerts, alerts)
    memory_watch.check_once(state)
    check("ketma-ket ikkinchisida — adminga xabar", alerts and alerts[0][0] == "memory_low" and "180 MB" in alerts[0][1],
          alerts)
alerts.clear()
with mock.patch.object(memory_watch.admin_alerts, "alert", side_effect=lambda key, text: alerts.append((key, text))), \
        mock.patch.object(memory_watch.heavy_gate, "available_mb", return_value=900), \
        mock.patch.object(memory_watch, "disk_free_gb", return_value=1.2):
    memory_watch.check_once({})
    check("diskda joy kam — xabar", alerts and alerts[0][0] == "disk_low", alerts)

print("4) Navbat mijozga ko'rinmaydi")
from bot import queue_service as qs  # noqa: E402
from bot import waiting  # noqa: E402


class FakeQueue:
    def __init__(self, pos):
        self.pos = pos
        self.active_task_id = None

    def position_of(self, task_id):
        return self.pos


for lang in ("uz", "ru", "en"):
    text = qs.build_initial_status_text(lang, "course_work", "Iqtisodiyot", 5)
    low = text.lower()
    check(f"[{lang}] boshlang'ich xabarda navbat yo'q",
          not any(w in low for w in ("navbat", "очеред", "queue", "oldingizda", "перед вами", "before you")), text)

edits = []


class FakeBot:
    async def edit_message_text(self, **kw):
        edits.append(kw["text"])

    async def send_message(self, **kw):
        edits.append("PING:" + kw.get("text", ""))


async def animate():
    done = asyncio.Event()
    async def fake_wait_for(aw, timeout):
        return await _fast_wait(aw)

    with mock.patch.object(asyncio, "wait_for", new=fake_wait_for):
        task = asyncio.create_task(qs.run_animated_status(FakeBot(), 1, 2, "t", "uz", "course_work", "Mavzu",
                                                          FakeQueue(3), done))
        await asyncio.sleep(0.05)
        done.set()
        await task


_ticks = {"n": 0}


async def _fast_wait(aw):
    _ticks["n"] += 1
    if _ticks["n"] <= 3:
        aw.close() if hasattr(aw, "close") else None
        raise asyncio.TimeoutError
    return await aw


asyncio.run(animate())
check("navbatda turganda ham xabar «tayyorlanmoqda» va fakt bilan yangilanadi",
      edits and all("tayyorlanmoqda" in e and "navbat" not in e.lower() for e in edits), edits)
check("«navbatingiz keldi» degan alohida xabar yuborilmaydi", not any(e.startswith("PING:") for e in edits), edits)
check("faktlar har xil (almashib turadi)", len(edits) >= 3 and len(set(edits)) == len(edits), edits)
check("kutish faktlari: har tilda kamida 15 ta", all(len(waiting.FACTS[l]) >= 15 for l in ("uz", "ru", "en")))

print()
print("HAMMASI OK" if not FAILS else f"XATOLAR: {len(FAILS)}")
sys.exit(1 if FAILS else 0)
