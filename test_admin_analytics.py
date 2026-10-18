"""Admin analytics, Mini App authorization and cost estimates.

    python test_admin_analytics.py
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlencode

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:test")

import aiosqlite
import config
import database.database as dbmod
from database.database import init_db
from services import admin_analytics
from services.daily_stats import today_uzt

dbmod.DATABASE_FILE = os.path.join(tempfile.mkdtemp(), "admin-analytics.db")
admin_analytics.DATABASE_FILE = dbmod.DATABASE_FILE
FAILS = []


def check(name, condition, detail=""):
    print(("  ok   " if condition else "  XATO ") + name + ("" if condition else f" — {detail}"))
    if not condition:
        FAILS.append(name)


def init_data(user_id, auth_date=None):
    auth_date = int(auth_date if auth_date is not None else time.time())
    data = {
        "auth_date": str(auth_date),
        "query_id": "AAE-test",
        "user": json.dumps({"id": user_id, "first_name": "Admin"}, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


async def main():
    await init_db()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    created = now.strftime("%Y-%m-%d %H:%M:%S")
    clicked_at = time.time() - 3600
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as db:
        await db.execute(
            "INSERT INTO users (telegram_id,first_name,language,created_at) VALUES (1,'Test','uz',?)",
            (created,))
        await db.execute(
            "INSERT INTO users (telegram_id,first_name,language,created_at) VALUES (3,'Cohort','uz',?)",
            ((now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),))
        await db.execute(
            "INSERT INTO users (telegram_id,first_name,language,created_at) VALUES (2,'NoPay','uz',?)",
            (created,))
        user_id = (await (await db.execute("SELECT id FROM users WHERE telegram_id=1")).fetchone())[0]
        cohort_user_id = (await (await db.execute("SELECT id FROM users WHERE telegram_id=3")).fetchone())[0]
        await db.execute(
            "INSERT INTO payments (user_id,amount,status,source,created_at) VALUES (?,15000,'approved','bot',?)",
            (user_id, created))
        await db.execute(
            "INSERT INTO payments (user_id,amount,status,source,created_at) VALUES (?,9000,'pending','bot',?)",
            (user_id, created))
        await db.execute(
            "INSERT INTO document_stats (document_type,completed_at) VALUES ('presentation',?)", (created,))
        await db.execute(
            "INSERT INTO balance_spends (telegram_id,amount,created_at) VALUES (1,1000,?)", (created,))
        await db.execute(
            "INSERT INTO payments (user_id,amount,status,source,created_at) "
            "VALUES (?,10000,'approved','bot',?)",
            (cohort_user_id, (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")))
        await db.execute(
            "INSERT INTO balance_spends (telegram_id,amount,created_at) VALUES (3,1000,?)",
            ((now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),))
        await db.execute(
            "INSERT INTO payments (user_id,amount,status,source,created_at) "
            "VALUES (?,12000,'approved','bot',?)",
            (cohort_user_id, (now - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")))
        await db.execute(
            "INSERT INTO balance_spends (telegram_id,amount,created_at) VALUES (1,1000,?)", (created,))
        await db.execute(
            "CREATE TABLE ai_usage (day TEXT NOT NULL,kind TEXT NOT NULL,name TEXT NOT NULL,"
            "count INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(day,kind,name))")
        await db.execute(
            "INSERT INTO ai_usage (day,kind,name,count) VALUES (?, 'text','test-model',3)", (today_uzt(),))
        await db.execute(
            "CREATE TABLE IF NOT EXISTS nudges (id INTEGER PRIMARY KEY,telegram_id INTEGER,flow TEXT,step INTEGER,"
            "sent_at REAL,status TEXT,clicked_at REAL)")
        await db.execute(
            "INSERT INTO nudges (telegram_id,flow,step,sent_at,status,clicked_at) VALUES (1,'new',0,?,'sent',?)",
            (clicked_at - 60, clicked_at))
        await db.commit()

    report = await admin_analytics.dashboard(7)
    summary = report["summary"]
    check("tasdiqlangan tushum; kutilayotgan to‘lov hisoblanmaydi",
          summary["revenue"] == 37000 and summary["payments"] == 3, summary)
    check("mijozning umrbo‘yi tushumi va to‘lov konversiyasi",
          summary["avg_lifetime_revenue"] == 18500 and summary["new_payers"] == 2, summary)
    check("takror foydalanish koeffitsienti",
          summary["repeat_users"] == 1 and summary["spenders"] == 2
          and summary["repeat_use_rate"] == 50, summary)
    check("ilk to‘lov kohorti: ishlatish va ishlatgach qayta to‘lov to‘g‘ri ajratiladi",
          summary["cohort_first_payers"] == 2
          and summary["cohort_used_after_first_payment"] == 2
          and summary["cohort_repaid_after_use"] == 1
          and summary["cohort_repayment_after_use_rate"] == 50, summary)
    today_report = await admin_analytics.dashboard(1)
    check("bugungi davr va kundalik to‘lov kohorti ishlaydi",
          today_report["period"]["days"] == 1
          and today_report["period"]["start"] == today_uzt()
          and today_report["summary"]["cohort_first_payers"] == 1, today_report["period"])
    check("yakunlangan hujjatlar va AI ishlatilishi",
          next(row["count"] for row in report["services"] if row["key"] == "presentation") == 1
          and report["ai_usage"][0]["count"] == 3, (report["services"], report["ai_usage"]))
    campaign = next(row for row in report["campaigns"] if row["key"] == "new")
    check("7 kun ichida bosilgan qayta jalb xabaridan kelgan tushum bog‘lanadi",
          campaign["clicks"] == 1 and campaign["buyers"] == 1 and campaign["revenue"] == 15000, campaign)

    await admin_analytics.save_costs(1, {"presentation": 2500}, {"new": 3000})
    await admin_analytics.save_costs(7, {"presentation": 2500}, {"new": 3000})
    report = await admin_analytics.dashboard(7)
    check("tannarx va reklama xarajati foydadan ayriladi",
          report["summary"]["service_cost"] == 2500
          and report["summary"]["campaign_cost"] == 3000
          and report["summary"]["estimated_profit"] == 31500
          and report["summary"]["profit_complete"], report["summary"])

    async with aiosqlite.connect(dbmod.DATABASE_FILE) as db:
        await db.execute(
            "INSERT INTO ai_usage (day,kind,name,count) VALUES (?, 'image','black-forest-labs/FLUX.1-schnell',4)",
            (today_uzt(),))
        await db.commit()
    report = await admin_analytics.dashboard(7)
    check("narxi kiritilmagan rasm modeli foydani 'to‘liq emas' qiladi",
          not report["summary"]["profit_complete"] and report["summary"]["image_cost"] == 0
          and any(m.startswith("Rasm:") for m in report["summary"]["missing_costs"]),
          report["summary"])
    await admin_analytics.save_costs(
        7, {}, {}, {"black-forest-labs/FLUX.1-schnell": "0.0025"}, 12000)
    report = await admin_analytics.dashboard(7)
    check("rasm xarajati: soni × dollar narxi × kurs avtomatik hisoblanadi",
          report["summary"]["image_cost"] == 120 and report["summary"]["usd_rate"] == 12000
          and report["summary"]["profit_complete"]
          and report["summary"]["estimated_profit"] == 31500 - 120, report["summary"])

    # Narx o‘zgarishi faqat bugundan keyingi kunlarga ta’sir qiladi.

    stamp = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(dbmod.DATABASE_FILE) as db:
        await db.execute("INSERT INTO document_stats (document_type,completed_at) VALUES ('presentation',?)", (stamp,))
        await db.commit()
    await admin_analytics.save_costs(7, {"presentation": 4000}, {})
    report = await admin_analytics.dashboard(7)
    presentation = next(row for row in report["services"] if row["key"] == "presentation")
    check("xizmat narxi o‘zgarsa avvalgi kunlar hisobi o‘zgarmaydi",
          presentation["unit_cost"] == 4000 and presentation["estimated_cost"] == 2500 + 4000, presentation)
    try:
        await admin_analytics.save_costs(7, {}, {}, {"unknown/model": "1"})
        valid_image = False
    except ValueError:
        valid_image = True
    check("noma’lum rasm modeli va noto‘g‘ri narx qabul qilinmaydi", valid_image)
    try:
        await admin_analytics.save_costs(7, {"unknown-service": 1}, {})
        valid_unknown = False
    except ValueError:
        valid_unknown = True
    check("noma’lum xarajat kaliti qabul qilinmaydi", valid_unknown)

    config.ADMIN_IDS = [1]
    config.BOT_TOKEN = os.environ["BOT_TOKEN"]
    from webapp import api
    admin_request = SimpleNamespace(headers={"X-Telegram-Init-Data": init_data(1)})
    non_admin_request = SimpleNamespace(headers={"X-Telegram-Init-Data": init_data(2)})
    tampered_request = SimpleNamespace(headers={"X-Telegram-Init-Data": init_data(1) + "x"})
    expired_request = SimpleNamespace(headers={
        "X-Telegram-Init-Data": init_data(1, time.time() - 90000)})
    check("Telegram imzosi tekshirilgan admin initData qabul qilinadi",
          api._admin_init_data(admin_request) == 1)
    check("imzosi to‘g‘ri bo‘lsa ham admin bo‘lmagan foydalanuvchi rad qilinadi",
          api._admin_init_data(non_admin_request) is None)
    check("o‘zgartirilgan initData rad qilinadi", api._admin_init_data(tampered_request) is None)
    check("eskirgan initData rad qilinadi", api._admin_init_data(expired_request) is None)
    allowed_response = await api.admin_statistics(SimpleNamespace(
        headers=admin_request.headers, query={"days": "7"}))
    today_response = await api.admin_statistics(SimpleNamespace(
        headers=admin_request.headers, query={"days": "1"}))
    denied_response = await api.admin_statistics(SimpleNamespace(
        headers=non_admin_request.headers, query={"days": "7"}))
    check("statistika API admin uchun ishlaydi va admin bo‘lmaganlarga yopiq",
          allowed_response.status == 200 and today_response.status == 200 and denied_response.status == 403,
          (allowed_response.status, today_response.status, denied_response.status))

    from bot.handlers import admin
    admin.is_admin = lambda user_id: user_id == 1
    sent = []
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        answer=lambda text, **kwargs: sent.append((text, kwargs)) or asyncio.sleep(0))
    await admin.handle_statistics(message, None)
    button = sent[0][1]["reply_markup"].inline_keyboard[0][0] if sent else None
    check("📊 Statistika tugmasi Telegram Mini App’ni ochadi",
          bool(button and button.web_app.url.endswith("/admin/statistics")), sent)


asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
