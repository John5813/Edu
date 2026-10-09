"""Kunlik statistika: bugun /start bosganlardan nechtasi to'lov qildi, nechta to'lov eski mijozdan.

- admin «📈 Kunlik statistika» xabarida: bugun kelganlar, ulardan to'lov qilganlar (summa va foiz),
  eski mijozlar to'lovlari va jami;
- har kuni yuboriladigan Excel: yangi foydalanuvchilarda alohida «To'lovlar soni» va «To'lagan (so'm)»
  ustunlari, ikkinchi varaqda kunning barcha to'lovlari (yangi/eski mijoz);
- kun O'zbekiston vaqti bilan: UTC 20:00 dagi /start ertangi kunga tegishli;
- kutilayotgan yoki rad etilgan to'lov hisobga kirmaydi;
- umumiy statistikada 7 va 30 kunlik yangi foydalanuvchilar: to'lov qilganlar, to'lab foydalanganlar,
  to'lovsiz foydalanganlar va umuman foydalanmaganlar (balansdan yechimlar `balance_spends` da yoziladi).

    python test_kunlik_statistika.py
"""
import asyncio, io, os, sys, tempfile, types
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import aiosqlite
import database.database as dbmod
from database.database import Database, init_db

dbmod.DATABASE_FILE = os.path.join(tempfile.mkdtemp(), "t.db")
from services import daily_stats

NOW = datetime.now(timezone.utc).replace(tzinfo=None)
DAY = daily_stats.today_uzt()
# O'zbekiston kunining boshi (00:00 UZT) UTC da — kechagi 19:00.
START_UTC = datetime.strptime(DAY, "%Y-%m-%d") - timedelta(hours=5)


def at(hours_after_start: float) -> str:
    return (START_UTC + timedelta(hours=hours_after_start)).strftime("%Y-%m-%d %H:%M:%S")


async def setup():
    await init_db()
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as db:
        users = [
            # (telegram_id, ism, created_at)
            (1, "Yangi1", at(1)),        # bugun 01:00 UZT (UTC da kecha 20:00) — bugungi
            (2, "Yangi2", at(10)),
            (3, "Yangi3", at(12)),       # bugun keldi, to'lamadi
            (4, "Eski1", at(-30)),       # kecha
            (5, "Eski2", at(-24 * 40)),
            (6, "KechaKech", at(-0.5)),  # kecha 23:30 UZT — eski
        ]
        for tg, name, created in users:
            await db.execute("INSERT INTO users (telegram_id, first_name, username, language, balance, created_at) "
                             "VALUES (?, ?, ?, 'uz', 1000, ?)", (tg, name, name.lower(), created))
        await db.commit()
        ids = {row[1]: row[0] for row in await (await db.execute("SELECT id, telegram_id FROM users")).fetchall()}
        payments = [
            (ids[1], 10000, "approved", at(2), "bot"),
            (ids[1], 5000, "approved", at(3), "web"),
            (ids[2], 20000, "approved", at(11), "bot"),
            (ids[2], 7000, "pending", at(11.5), "bot"),     # hisobga kirmaydi
            (ids[3], 9000, "rejected", at(13), "bot"),      # hisobga kirmaydi
            (ids[4], 30000, "approved", at(9), "bot"),
            (ids[5], 15000, "approved", at(14), "web"),
            (ids[5], 15000, "approved", at(15), "bot"),
            (ids[6], 50000, "approved", at(-0.2), "bot"),   # kecha 23:48 UZT — bugungi emas
        ]
        for uid, amount, status, created, source in payments:
            await db.execute("INSERT INTO payments (user_id, amount, status, source, created_at) VALUES (?, ?, ?, ?, ?)",
                             (uid, amount, status, source, created))
        await db.commit()


async def main():
    await setup()

    print("1) Hisob")
    s = await daily_stats.payment_breakdown(DAY)
    check("bugun /start bosganlar — 3 ta (UTC kechagi 20:00 ham bugunga kiradi)", s["started"] == 3, s)
    check("shulardan to'lov qilganlar — 2 ta, 35 000 so'm", (s["new_paid_users"], s["new_sum"]) == (2, 35000), s)
    check("yangi mijozlar to'lovlari soni — 3 ta", s["new_payments"] == 3, s)
    check("eski mijozlardan — 3 ta to'lov, 2 kishi, 60 000 so'm",
          (s["old_payments"], s["old_paid_users"], s["old_sum"]) == (3, 2, 60000), s)
    check("jami: 6 to'lov, 95 000 so'm, 4 kishi", (s["payments"], s["revenue"], s["paid_users"]) == (6, 95000, 4), s)
    check("konversiya foizi", daily_stats.conversion(s) == "66.7%", daily_stats.conversion(s))
    text = daily_stats.summary_text(s)
    check("xabar matnida yangi va eski ajratilgan",
          "Shulardan to'lov qilganlar: 2 ta (66.7%) — 35,000 so'm" in text
          and "Eski mijozlardan to'lovlar: 3 ta (2 kishi) — 60,000 so'm" in text, text)

    print("2) Admin «📈 Kunlik statistika»")
    from bot.handlers import admin
    sent = []
    msg = types.SimpleNamespace(from_user=types.SimpleNamespace(id=1), answer=lambda t, **k: sent.append(t) or asyncio.sleep(0))
    admin.is_admin = lambda uid: True
    await admin.handle_daily_statistics(msg, None)
    check("xabar yuborildi va yangi/eski to'lovlar bor", sent and "Shulardan to'lov qilganlar: 2 ta" in sent[0]
          and "Eski mijozlardan to'lovlar: 3 ta" in sent[0] and "Bugungi daromad: 95,000 so'm" in sent[0],
          sent[:1])

    print("3) Kunlik Excel")
    import openpyxl
    import main as app
    data = await app.generate_daily_excel(DAY)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb["Yangi foydalanuvchilar"]
    head = [c.value for c in ws[1]]
    check("alohida ustunlar: to'lovlar soni va to'lagan summa", "To'lovlar soni" in head and "To'lagan (so'm)" in head, head)
    rows = {r[1]: r for r in ws.iter_rows(min_row=2, values_only=True) if isinstance(r[1], int)}
    paid_col, count_col = head.index("To'lagan (so'm)"), head.index("To'lovlar soni")
    check("faqat bugun kelganlar (3 ta)", sorted(rows) == [1, 2, 3], sorted(rows))
    check("har birining to'lovi: 15 000 / 20 000 / 0 (kutilayotgani kirmaydi)",
          [rows[t][paid_col] for t in (1, 2, 3)] == [15000, 20000, 0]
          and [rows[t][count_col] for t in (1, 2, 3)] == [2, 1, 0], [rows[t] for t in (1, 2, 3)])
    values = [c for r in ws.iter_rows(values_only=True) for c in r if c is not None]
    check("jamlanma: to'lov qilganlar 2, summa 35 000", "Shulardan to'lov qilganlar:" in values and 35000 in values, values[-8:])
    ws2 = wb["Bugungi to'lovlar"]
    pays = [r for r in ws2.iter_rows(min_row=2, values_only=True) if isinstance(r[1], int)]
    check("ikkinchi varaq: bugungi 6 ta tasdiqlangan to'lov", len(pays) == 6, pays)
    check("mijoz yangi/eski belgisi to'g'ri", sorted((p[1], p[5]) for p in pays) ==
          [(1, "Yangi"), (1, "Yangi"), (2, "Yangi"), (4, "Eski"), (5, "Eski"), (5, "Eski")], pays)
    check("saytdan kelgan to'lov belgilangan", sum(1 for p in pays if p[6] == "Sayt") == 2)
    totals = [c for r in ws2.iter_rows(values_only=True) for c in r if isinstance(c, str)]
    check("jamlanma: yangi va eski mijozlardan", "3 ta — 35,000 so'm" in totals and "3 ta — 60,000 so'm" in totals, totals[-6:])

async def cohorts():
    print("4) 7 va 30 kunlik yangi foydalanuvchilar")
    from database import free_trial
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as db:
        # Balanslar haqiqiydek: tasdiqlangan to'lov balansga tushgan.
        for tg, bal in ((1, 15000), (2, 20000), (3, 0), (4, 30000), (5, 30000), (6, 50000)):
            await db.execute("UPDATE users SET balance = ? WHERE telegram_id = ?", (bal, tg))
        for tg, name, created, bal in ((7, "Hafta", at(-24 * 5), 10000), (8, "Bonusli", at(-24 * 10), 5000),
                                       (9, "Jim", at(-24 * 20), 0), (10, "Sinov", at(-24 * 3), 0)):
            await db.execute("INSERT INTO users (telegram_id, first_name, language, balance, created_at) "
                             "VALUES (?, ?, 'uz', ?, ?)", (tg, name, bal, created))
        await db.commit()
        uid7 = (await (await db.execute("SELECT id FROM users WHERE telegram_id = 7")).fetchone())[0]
        await db.execute("INSERT INTO payments (user_id, amount, status, created_at) VALUES (?, 10000, 'approved', ?)",
                         (uid7, at(-24 * 5 + 1)))
        await db.commit()
    check("balansdan yechim yoziladi (atomik yechish)", await Database.charge_balance(1, 5000))
    await Database.charge_balance(7, 10000)
    await Database.update_user_balance(8, -5000)          # bonus bilan foydalandi
    await Database.update_user_balance(2, 3000)           # balansga qo'shish — yechim emas
    await free_trial.claim(10, "job-x")                   # saytdagi bepul sinov
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as db:
        spends = await (await db.execute("SELECT telegram_id, amount FROM balance_spends ORDER BY id")).fetchall()
    check("yechimlar jadvali: faqat yechimlar (1, 7, 8)", spends == [(1, 5000), (7, 10000), (8, 5000)], spends)

    week = await daily_stats.cohort(7, DAY)
    check("7 kun: /start bosganlar 7 ta", week["started"] == 7, week)
    check("7 kun: to'lov qilganlar 5 ta, 125 000 so'm", (week["paid_users"], week["paid_sum"]) == (5, 125000), week)
    check("7 kun: to'lab foydalanganlar 2, to'lab foydalanmaganlar 3", (week["paid_used"], week["paid_unused"]) == (2, 3), week)
    check("7 kun: to'lovsiz foydalangan 1 (bepul sinov), umuman foydalanmagan 1",
          (week["free_used"], week["unused"]) == (1, 1), week)
    month = await daily_stats.cohort(30, DAY)
    check("30 kun: 9 ta, bonus bilan foydalangan va jim qolgan ham kiradi, 40 kunlik kirmaydi",
          (month["started"], month["free_used"], month["unused"], month["paid_users"]) == (9, 2, 2, 5), month)
    text = daily_stats.cohort_text(week)
    check("matn", "Oxirgi 7 kun — /start bosganlar: 7 ta" in text and "To'lov qilib foydalanganlar: 2 ta" in text
          and "Umuman foydalanmaganlar: 1 ta" in text, text)

    from bot.handlers import admin
    sent = []
    msg = types.SimpleNamespace(from_user=types.SimpleNamespace(id=1), answer=lambda t, **k: sent.append(t) or asyncio.sleep(0))
    await admin.handle_statistics(msg, None)
    check("«📊 Statistika»: 7 va 30 kunlik bo'limlar", sent and "Oxirgi 7 kun" in sent[0] and "Oxirgi 30 kun" in sent[0]
          and "Umuman foydalanmaganlar" in sent[0], sent[:1])


asyncio.run(main())
asyncio.run(cohorts())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
