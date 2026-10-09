"""Qayta jalb: faol bo'lmagan mijozlarga ism bilan, tugmali xabarlar va 5 slaydli bepul taqdimot (botda).

- kim qaysi guruhga tushadi (yangi / eski baza / to'lagan-foydalanmagan / bepul sinovdan keyin / 14+ kun kelmagan),
  xabar vaqti, oraliq (20 soat), 5 xabardan keyin to'xtash, foydalansa yoki to'sib qo'ysa to'xtash;
- har xabar 4 tilda, tugmali, ism faqat haqiqiy bo'lsa; kechasi yuborilmaydi;
- eski bazadan kuniga cheklangan son, to'sganlar ko'paysa o'zi to'xtaydi va adminga aytadi;
- 5-xabardagi «48 soatda tugaydi» haqiqiy: muddatdan keyin bepul taqdimot yopiladi (bot ham, sayt ham);
- bepul sinovdan keyin birinchi to'lovga +20% bonus — bir marta, muddat ichida;
- tugma bosilgani yoziladi, sovg'a oqimi taqdimotni yuboradi, xato bo'lsa sovg'a qaytadi;
- admin: yoqish/o'chirish va natijalar hisoboti.

    python test_qayta_jalb.py
"""
import asyncio, os, sys, tempfile, time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("ADMIN_IDS", "1")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import aiosqlite
import database.database as dbmod
dbmod.DATABASE_FILE = os.path.join(tempfile.mkdtemp(), "t.db")
from database import free_trial
from database.database import Database, init_db
from services import reengage as R
from services import reengage_texts as T

H, D = R.HOUR, R.DAY
# Bugun soat 12:00 (O'zbekiston vaqti) — xabar yuboriladigan vaqt.
_today = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5)
NOON = (datetime(_today.year, _today.month, _today.day, 12, 0) - timedelta(hours=5)).replace(tzinfo=timezone.utc).timestamp()


def P(tg=10, **kw):
    kw.setdefault("created_at", NOON - 100 * D)
    return R.Person(tg, **kw)


def due(person, history=None, now=NOON, **kw):
    return [(d.flow, d.step) for d in R.plan(now, [person], {person.telegram_id: history or []}, **kw)]


def row(flow, step, at, status="sent", tg=10):
    return R.Row(0, tg, flow, step, at, status)


print("1) Kim qaysi guruhga tushadi")
fresh = P(created_at=NOON - 1 * H)
check("yangi kelgan: 2 soat o'tmaguncha xabar yo'q", due(fresh) == [])
fresh = P(created_at=NOON - 3 * H)
check("2 soatdan keyin — sovg'a (1-xabar)", due(fresh) == [("new", 0)])
history = [row("new", 0, NOON - 1 * H)]
check("1-xabardan keyin 20 soat o'tmaguncha — hech narsa", due(fresh, history, now=NOON + 10 * H) == [])
check("2-xabar 1-kuni (oraliq saqlanadi)", due(fresh, history, now=NOON + 23 * H) == [("new", 1)])
done5 = [row("new", i, NOON - (40 - 5 * i) * D) for i in range(5)]
check("5 ta xabardan keyin to'xtaydi", due(P(created_at=NOON - 41 * D), done5) == [])
check("foydalangan (balansdan yechim) — xabar yo'q", due(P(created_at=NOON - 3 * H, last_spend=NOON - H)) == [])
check("bonus bilan foydalangan, 20 kun kelmagan — eslatma", due(P(last_spend=NOON - 20 * D)) == [("lapsed", 0)])
check("eski baza: hech narsa qilmagan — sovg'a", due(P()) == [("old", 0)])
check("eski baza o'chirilgan bo'lsa — yo'q", due(P(), old_enabled=False) == [])
check("to'lagan, foydalanmagan (balans bor) — 24 soatdan keyin «hisobingizda X so'm»",
      due(P(paid=20000, balance=20000, last_paid=NOON - 30 * H)) == [("paid_unused", 0)])
check("to'lagan, balansi oz — xabar yo'q", due(P(paid=2000, balance=2000, last_paid=NOON - 30 * H)) == [])
check("bepul sinovdan keyin, to'lamagan — bonus xabari", due(P(trial_at=NOON - 30 * H)) == [("trial", 0)])
check("bepul sinovdan 24 soat o'tmagan — hali yo'q", due(P(trial_at=NOON - 5 * H)) == [])
check("to'lab foydalangan, 20 kun kelmagan — eslatma", due(P(paid=10000, balance=0, last_paid=NOON - 20 * D)) == [("lapsed", 0)])
check("to'lab foydalangan, 5 kun oldin — yo'q", due(P(paid=10000, balance=0, last_paid=NOON - 5 * D)) == [])
check("botni to'sgan — boshqa xabar yo'q", due(P(), [row("old", 0, NOON - 3 * D, "blocked")]) == [])
check("to'sgandan keyin qaytib to'lab foydalangan — yana eslatma mumkin",
      due(P(paid=5000, balance=0, last_paid=NOON - 20 * D), [row("old", 0, NOON - 30 * D, "blocked")]) == [("lapsed", 0)])
check("admin bloklagan / admin — chetda", due(P(excluded=True)) == [])
people = [P(tg=i) for i in range(1, 6)] + [P(tg=99, trial_at=NOON - 30 * H)]
plan = R.plan(NOON, people, {}, old_budget=2)
check("eski bazadan kunlik chegara (2 ta) va sinovdan keyingilar birinchi",
      [(d.person.telegram_id, d.flow) for d in plan] == [(99, "trial"), (1, "old"), (2, "old")],
      [(d.person.telegram_id, d.flow) for d in plan])
check("bir aylanishdagi chegara", len(R.plan(NOON, [P(tg=i) for i in range(50)], {}, limit=7)) == 7)

print("2) Vaqt va ism")
check("kechasi (23:00) yuborilmaydi", R.quiet(NOON + 11 * H))
check("ertalab 9:30 yuborilmaydi, 10:00 da yuboriladi", R.quiet(NOON - 2.5 * H) and not R.quiet(NOON - 2 * H))
check("kunduz (12:00) yuboriladi", not R.quiet(NOON))
names = {"Javlonbek": "Javlonbek", "user123": "", "🔥Ali": "", "АЛИШЕР": "Алишер", "O'tkir": "O'tkir",
         "Ali Valiyev": "Ali", "": "", "A": "", "bot": "", "dilnoza": "Dilnoza", "Ғайрат": "Ғайрат"}
got = {k: R.clean_name(k) for k in names}
check("ism faqat haqiqiy bo'lsa (emoji, raqam, «user» — ismsiz)", got == names, got)

print("3) Matnlar: 4 tilda, har biri tugmali")
problems = []
for flow, key in R.STEPS.items():
    for step in range(len(R.OFFSETS[flow])):
        for lang in T.LANGS:
            for name in ("Javlonbek", ""):
                person = P(name=name, language=lang, balance=15000)
                text, buttons, extra = R.message_for(flow, step, person, NOON)
                if "{" in text or "}" in text:
                    problems.append((flow, step, lang, "o'rin qoldi", text[:60]))
                if not buttons:
                    problems.append((flow, step, lang, "tugma yo'q"))
                if name and name not in text:
                    problems.append((flow, step, lang, "ism yo'q"))
                if not name and (text.startswith(",") or ", ," in text):
                    problems.append((flow, step, lang, "ismsiz vergul", text[:40]))
                if any(t != "gift" and t not in __import__("bot.ad_buttons", fromlist=["x"]).TARGETS for t, _ in buttons):
                    problems.append((flow, step, lang, "noma'lum tugma"))
check("hamma xabar: o'rinlar to'ldirilgan, tugma bor, ism to'g'ri", not problems, problems[:5])
text, buttons, extra = R.message_for("new", 4, P(name="Ali"), NOON)
check("5-xabar: sovg'a muddati 48 soat va sanasi yozilgan", "48" in text and R._date(NOON + 48 * H, "uz") in text
      and extra["gift_until"] == NOON + 48 * H)
text, _, extra = R.message_for("trial", 0, P(tg=555, name="Ali"), NOON)
check("sinovdan keyin: +20% bonus va muddati (7 kun)", "+20%" in text and extra["bonus_until"] == NOON + 7 * D)
ru, _, _ = R.message_for("new", 0, P(name="Иван", language="ru"), NOON)
kk, _, _ = R.message_for("old", 0, P(name="Айгүл", language="kk"), NOON)
check("ruscha va qozoqcha matn o'z tilida", "здравствуйте" in ru and "сыйлық" in kk, (ru[:40], kk[:40]))
old_text, _, _ = R.message_for("old", 0, P(name="Ali"), NOON)
check("eski bazaga «hech narsa qilmadingiz» deyilmaydi", "hali birorta ish" not in old_text
      and "hali birorta ish" in R.message_for("new", 0, P(name="Ali"), NOON)[0])

print("4) Bazadan to'liq aylanish")


class Bot:
    def __init__(self, blocked=()):
        self.sent, self.blocked = [], set(blocked)

    async def _send(self, chat_id, kind, text, markup):
        if chat_id in self.blocked:
            from aiogram.exceptions import TelegramForbiddenError
            raise TelegramForbiddenError(method=MagicMock(), message="Forbidden: bot was blocked by the user")
        self.sent.append((chat_id, kind, text, markup))

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kw):
        await self._send(chat_id, "text", text, reply_markup)

    async def send_photo(self, chat_id, photo, caption=None, parse_mode=None, reply_markup=None, **kw):
        await self._send(chat_id, "photo", caption, reply_markup)


def sql_time(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def setup():
    await init_db()
    users = [  # tg, ism, yaratilgan, balans
        (101, "Javlonbek", NOON - 5 * H, 0),          # yangi, foydalanmagan
        (102, "user777", NOON - 200 * D, 0),          # eski baza, ismsiz
        (103, "Dilnoza", NOON - 10 * D, 20000),       # to'lagan, foydalanmagan
        (104, "Aziz", NOON - 3 * D, 0),               # bepul sinovdan keyin
        (105, "Bek", NOON - 60 * D, 0),               # to'lab foydalangan, 30 kun kelmagan
        (106, "Sardor", NOON - 300 * D, 0),           # botni to'sgan
        (107, "Faol", NOON - 2 * D, 0),               # hozir foydalanyapti
    ]
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as db:
        for tg, name, created, balance in users:
            await db.execute("INSERT INTO users (telegram_id, first_name, language, balance, created_at) VALUES (?, ?, 'uz', ?, ?)",
                             (tg, name, balance, sql_time(created)))
        ids = {tg: i for i, tg in await (await db.execute("SELECT id, telegram_id FROM users")).fetchall()}
        await db.execute("INSERT INTO payments (user_id, amount, status, created_at) VALUES (?, 20000, 'approved', ?)",
                         (ids[103], sql_time(NOON - 2 * D)))
        await db.execute("INSERT INTO payments (user_id, amount, status, created_at) VALUES (?, 10000, 'approved', ?)",
                         (ids[105], sql_time(NOON - 30 * D)))
        await db.execute("INSERT INTO balance_spends (telegram_id, amount, created_at) VALUES (107, 3000, ?)", (sql_time(NOON - H),))
        await db.commit()
    await free_trial.claim(104, "job-1")
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as db:
        await db.execute("UPDATE free_trials SET created_at = ? WHERE telegram_id = 104", (NOON - 2 * D,))
        await db.commit()
    return ids


async def flow_tests():
    ids = await setup()
    bot = Bot(blocked={106})
    with patch.object(R, "SEND_PAUSE", 0):
        result = await R.tick(bot, now=NOON)
    who = {chat: text for chat, kind, text, markup in bot.sent}
    check("xabar ketdi: yangi, eski, to'lagan, sinovdan keyingi, kelmay qolgan (5 ta), faolga yo'q",
          sorted(who) == [101, 102, 103, 104, 105] and result == {"sent": 5, "blocked": 1, "failed": 0}, (sorted(who), result))
    check("ism bilan murojaat", "Javlonbek" in who[101] and "Dilnoza" in who[103])
    check("ismsiz mijozga — umumiy salom", who[102].startswith("👋 Assalomu alaykum!"), who[102][:40])
    check("to'laganga balansi aytiladi", "20 000 so'm" in who[103], who[103][:80])
    markups = [m for _, _, _, m in bot.sent]
    callbacks = [b.callback_data for m in markups for r in m.inline_keyboard for b in r]
    check("har xabarda tugma, hammasi nz:<xabar>:<maqsad>", all(m and m.inline_keyboard for m in markups)
          and all(c.startswith("nz:") for c in callbacks), callbacks)
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as db:
        rows = await (await db.execute("SELECT telegram_id, flow, status FROM nudges ORDER BY telegram_id")).fetchall()
        bonus = await (await db.execute("SELECT telegram_id, percent FROM reengage_bonus")).fetchall()
    check("bazaga yozildi (to'sgan — blocked)", (106, "old", "blocked") in rows and (101, "new", "sent") in rows, rows)
    check("sinovdan keyingiga +20% bonus berildi", bonus == [(104, 20)], bonus)

    bot2 = Bot()
    with patch.object(R, "SEND_PAUSE", 0):
        await R.tick(bot2, now=NOON + 2 * H)
        night = await R.tick(bot2, now=NOON + 11 * H)
    check("qayta aylanishda takror yo'q (20 soat), kechasi umuman yo'q", bot2.sent == [] and night["sent"] == 0)
    with patch.object(R, "SEND_PAUSE", 0):
        await R.tick(bot2, now=NOON + 4 * D)
    again = sorted(c for c, *_ in bot2.sent)
    check("keyingi kunlarda navbatdagi xabar; to'sganga yo'q", 106 not in again and 101 in again and 102 in again, again)

    print("5) Sovg'a muddati haqiqiy")
    check("muddat qo'yilmaguncha bepul taqdimot ochiq", await free_trial.available(101))
    await free_trial.set_deadline(101, time.time() + 48 * H)
    check("48 soat ichida ochiq", await free_trial.available(101))
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as db:
        await db.execute("UPDATE free_trial_deadlines SET expires_at = ? WHERE telegram_id = 101", (time.time() - 60,))
        await db.commit()
    check("muddat o'tgach yopiladi (sayt ham, bot ham)", not await free_trial.available(101)
          and not await free_trial.claim(101, "late"))

    print("6) Birinchi to'lovga +20% bonus")
    db = Database()
    user = await db.get_user(104)
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        await conn.execute("INSERT INTO payments (user_id, amount, status) VALUES (?, 20000, 'approved')", (ids[104],))
        await conn.commit()
    notify = Bot()
    bonus = await R.on_payment_approved(notify, db, user, 20000)
    fresh = await db.get_user(104)
    check("20 000 so'm to'lovga +4 000 so'm, mijozga xabar", bonus == 4000 and fresh.balance == 4000
          and notify.sent and "4 000" in notify.sent[0][2], (bonus, fresh.balance, notify.sent))
    check("ikkinchi marta bonus yo'q", await R.on_payment_approved(notify, db, user, 20000) == 0)
    await R.grant_bonus(103, NOON, time.time() + D)
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:      # 103 ilgari ham to'lagan — bu ikkinchi to'lov
        await conn.execute("INSERT INTO payments (user_id, amount, status) VALUES (?, 10000, 'approved')", (ids[103],))
        await conn.commit()
    check("birinchi bo'lmagan to'lovga bonus yo'q", await R.take_bonus(103, ids[103], 10000) == 0)
    await R.grant_bonus(101, NOON - 10 * D, time.time() - 60)
    check("muddati o'tgan bonus yo'q", await R.take_bonus(101, ids[101], 10000) == 0)

    print("7) Eski bazada to'sganlar ko'paysa o'zi to'xtaydi")
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        for i in range(R.PAUSE_MIN + 50):
            await conn.execute("INSERT INTO nudges (telegram_id, flow, step, sent_at, status) VALUES (?, 'old', 0, ?, ?)",
                               (90000 + i, NOON + 6 * D - H, "blocked" if i % 3 == 0 else "sent"))
        await conn.commit()
    admin = Bot()
    with patch.object(R, "SEND_PAUSE", 0):
        await R.tick(admin, now=NOON + 6 * D)
    check("eski baza to'lqini o'chirildi va adminga aytildi", not await db.get_feature_status(R.FEATURE_OLD)
          and any(chat == 1 and "to'xtatildi" in text for chat, _, text, _ in admin.sent), admin.sent[-1:])
    await db.set_feature_status(R.FEATURE, False)
    off = Bot()
    with patch.object(R, "SEND_PAUSE", 0):
        await R.tick(off, now=NOON + 30 * D)
    check("admin o'chirsa — hech kimga xabar yo'q", off.sent == [])
    await db.set_feature_status(R.FEATURE, True)

    print("7b) 2-xabar namuna rasmi bilan (rasm bir marta yuklanadi)")
    import config
    previews = tempfile.mkdtemp()
    os.makedirs(os.path.join(previews, "ABC1"))
    from PIL import Image
    Image.new("RGB", (40, 20), (10, 20, 30)).save(os.path.join(previews, "ABC1", "1.jpg"))
    shots = []

    class PhotoBot(Bot):
        async def send_photo(self, chat_id, photo, caption=None, parse_mode=None, reply_markup=None, **kw):
            shots.append(photo)
            return SimpleNamespace(photo=[SimpleNamespace(file_id="FILE-1")])
    with patch.object(config, "STORE_PREVIEW_DIR", previews):
        for tg in (201, 202):
            await R.deliver(PhotoBot(), R.Due(P(tg=tg, name="Ali"), "new", 1), NOON)
    check("namuna rasmi yuborildi, ikkinchisida file_id ishlatildi",
          len(shots) == 2 and not isinstance(shots[0], str) and shots[1] == "FILE-1", shots)

    print("8) Hisobot")
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        await conn.execute("UPDATE nudges SET clicked_at = sent_at + 60 WHERE telegram_id = 101")
        await conn.commit()
    text = await R.report(now=NOON + 6 * D)
    check("hisobotda guruhlar, bosilganlar va bonus", "Yangi, foydalanmagan" in text and "1-xabar" in text
          and "bonus berildi: 1 ta, 4,000 so'm" in text, text)
    return ids


async def handler_tests(ids):
    print("9) Tugma va sovg'a oqimi (botda bepul taqdimot)")
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    from bot.handlers import reengage as handler
    from bot.states import GiftStates

    db = Database()
    db.get_active_channels = AsyncMock(return_value=[])
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        row_id = (await (await conn.execute("SELECT id FROM nudges WHERE telegram_id = 102 LIMIT 1")).fetchone())[0]
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=102, user_id=102))
    said = []

    async def answer(text, **kw):
        said.append((text, kw.get("reply_markup")))
        return SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock(side_effect=lambda t, **k: said.append((t, k.get("reply_markup")))))

    message = SimpleNamespace(answer=answer, answer_document=AsyncMock(), bot=MagicMock(), chat=SimpleNamespace(id=102))
    callback = SimpleNamespace(data=f"nz:{row_id}:gift", answer=AsyncMock(), message=message,
                               from_user=SimpleNamespace(id=102), bot=MagicMock())
    await handler.nudge_button(callback, state, db, MagicMock())
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        clicked = (await (await conn.execute("SELECT clicked_at FROM nudges WHERE id = ?", (row_id,))).fetchone())[0]
    check("bosilgani yozildi", clicked is not None)
    check("sovg'a: mavzu so'raldi", said and "5 slaydli bepul taqdimot" in said[-1][0]
          and await state.get_state() == GiftStates.waiting_for_topic.state, said[-1:])

    tmp = tempfile.NamedTemporaryFile(suffix=".pptx", delete=False); tmp.write(b"x"); tmp.close()
    topic = SimpleNamespace(text="Suv aylanishi", from_user=SimpleNamespace(id=102), answer=answer,
                            answer_document=AsyncMock(), bot=MagicMock(), chat=SimpleNamespace(id=102))
    with patch.object(handler, "_build", AsyncMock(return_value=tmp.name)) as build:
        await handler.gift_topic(topic, state, db)
    check("taqdimot tayyorlandi va yuborildi", build.await_args.args[0] == "Suv aylanishi" and topic.answer_document.await_count == 1)
    offer = said[-1]
    check("keyin to'liq taqdimot va to'lov tugmalari", "Bepul taqdimotingiz tayyor" in offer[0]
          and [b.callback_data for r in offer[1].inline_keyboard for b in r] == ["ad:taqdimot", "ad:tolov"], offer)
    check("sovg'a ishlatildi (qayta berilmaydi), fayl o'chirildi", not await free_trial.available(102) and not os.path.exists(tmp.name))
    said.clear()
    await handler.start_gift(message, state, db, 102)
    check("ikkinchi marta: «avval foydalangansiz» va to'liq taqdimot taklifi", "foydalangansiz" in said[-1][0], said[-1:])

    state3 = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=103, user_id=103))
    await state3.set_state(GiftStates.waiting_for_topic)
    broken = SimpleNamespace(text="Iqtisodiyot", from_user=SimpleNamespace(id=103), answer=answer,
                             answer_document=AsyncMock(), bot=MagicMock(), chat=SimpleNamespace(id=103))
    with patch.object(handler, "_build", AsyncMock(side_effect=RuntimeError("model"))):
        await handler.gift_topic(broken, state3, db)
    check("xato bo'lsa sovg'a qaytadi va «qayta urinish» tugmasi", await free_trial.available(103)
          and "Qayta urinish" in str(said[-1][1]), said[-1:])

    opened = []
    with patch("bot.ad_buttons.open_section", AsyncMock(side_effect=lambda *a, **k: opened.append(a[3]))):
        cb = SimpleNamespace(data=f"nz:{row_id}:pul", answer=AsyncMock(), message=message,
                             from_user=SimpleNamespace(id=102), bot=MagicMock())
        await handler.nudge_button(cb, state, db, MagicMock())
    check("boshqa tugma botning bo'limini ochadi («Pul ishlab topish»)", opened == ["pul"], opened)

    print("9b) Bot yangilansa (qayta ishga tushsa) tizim noldan boshlanmaydi")
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        before = (await (await conn.execute("SELECT COUNT(*) FROM nudges")).fetchone())[0]
        job = (await (await conn.execute("SELECT job_id FROM free_trials WHERE telegram_id = 102")).fetchone())[0]
    check("yetkazilgan sovg'a «yuborildi» deb belgilandi", job.startswith(free_trial.BOT_DONE), job)
    # Qayta ishga tushish: xotiradagi hamma narsa yo'qoladi, faqat baza qoladi.
    R._BONUS_CACHE.clear(); R._PHOTO_IDS.clear()
    await free_trial.claim(105, free_trial.BOT_PENDING + "uzildi")      # tayyorlanayotgan payt bot to'xtadi
    restored = await free_trial.release_unfinished_bot()
    check("uzilgan sovg'a mijozga qaytdi, yetkazilgani qaytmadi", restored == 1 and await free_trial.available(105)
          and not await free_trial.available(102))
    repeat = Bot()
    with patch.object(R, "SEND_PAUSE", 0):
        await R.tick(repeat, now=NOON + 4 * D + 2 * H)          # oxirgi aylanishdan 2 soat keyin, qayta ishga tushgach
    check("qayta ishga tushgach hech kimga takror xabar ketmadi", repeat.sent == [], [c for c, *_ in repeat.sent])
    _, _, extra = R.message_for("trial", 1, (await R.load(NOON))[0][0].__class__(104), NOON + 3 * D)
    check("bonus muddati bazadan tiklandi (yangi 7 kun boshlanmaydi)", extra["bonus_until"] < NOON + 3 * D + 7 * D
          and extra["bonus_until"] == R._BONUS_CACHE.get(104), (extra, R._BONUS_CACHE.get(104)))
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as conn:
        after = (await (await conn.execute("SELECT COUNT(*) FROM nudges")).fetchone())[0]
    check("yuborilganlar tarixi saqlanib qoldi", after == before, (before, after))

    print("10) Admin")
    from bot.keyboards import get_admin_keyboard, get_feature_management_keyboard
    kb = get_feature_management_keyboard(True, True, True, True, False)
    data = [b.callback_data for r in kb.inline_keyboard for b in r]
    check("funksiyalar boshqaruvida yoqish/o'chirish", "toggle_reengage_off" in data and "toggle_reengage_old_on" in data, data)
    check("admin menyusida «🔁 Qayta jalb»", any(b.text == "🔁 Qayta jalb" for r in get_admin_keyboard().keyboard for b in r))
    from bot.handlers import admin
    cb = SimpleNamespace(data="toggle_reengage_old_on", answer=AsyncMock(), from_user=SimpleNamespace(id=1),
                         message=SimpleNamespace(edit_text=AsyncMock()))
    await admin.toggle_reengage(cb, db)
    check("eski baza qayta yoqildi", await db.get_feature_status(R.FEATURE_OLD))
    out = []
    msg = SimpleNamespace(from_user=SimpleNamespace(id=1), answer=lambda t, **k: out.append(t) or asyncio.sleep(0))
    await admin.handle_reengage_report(msg, db)
    check("hisobot xabari", out and "Qayta jalb xabarlari" in out[0] and "yoqilgan" in out[0], out[:1])
    main_src = open("main.py").read()
    check("main.py: router va fon jarayoni ulangan", "reengage_handler.router" in main_src and "reengage.run(bot)" in main_src)
    admin_src = open("bot/handlers/admin.py").read()
    check("to'lov tasdiqlashning uchala yo'lida bonus", admin_src.count("reengage.on_payment_approved(") == 3)


async def main():
    ids = await flow_tests()
    await handler_tests(ids)

asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
