"""Admin Mini App analytics from anonymized product, payment and campaign records."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

import aiosqlite

from database.database import DATABASE_FILE
from services.daily_stats import today_uzt

ATTRIBUTION_DAYS = 7
CAMPAIGN_FLOWS = ("new", "old", "paid_unused", "trial", "lapsed", "weekly")
FLOW_LABELS = {
    "new": "Yangi, foydalanmagan",
    "old": "Eski baza, foydalanmagan",
    "paid_unused": "To‘lagan, foydalanmagan",
    "trial": "Bepul sinovdan keyin",
    "lapsed": "Faoliyati pasaygan",
    "weekly": "Juma bonusi",
}
SERVICE_LABELS = {
    "presentation": "Taqdimot",
    "independent_work": "Mustaqil ish",
    "referat": "Referat",
    "tezis": "Tezis",
    "maqola": "Maqola",
    "course_work": "Kurs ishi",
    "diploma_work": "Diplom ishi",
    "bitiruv_ishi": "Bitiruv ishi",
    "dissertatsiya": "Dissertatsiya",
    "store_sale": "Tayyor ish savdosi",
}
_COST_SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_cost_settings (
    category TEXT NOT NULL,
    item_key TEXT NOT NULL,
    period_days INTEGER NOT NULL DEFAULT 0,
    amount INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (category, item_key, period_days)
)
"""


_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_cost_history (
    category TEXT NOT NULL,
    item_key TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    amount REAL NOT NULL,
    PRIMARY KEY (category, item_key, effective_from)
)
"""
BASE_DAY = "0000-00-00"          # birinchi kiritilgan narx barcha o‘tgan kunlarga ham amal qiladi
DEFAULT_USD_RATE = 12_500
IMAGE_KIND = "image"


async def _history(db, category: str) -> Dict[str, list]:
    """{kalit: [(amal qila boshlagan sana, narx), ...]} — sana bo‘yicha o‘sish tartibida."""
    await db.execute(_HISTORY_SCHEMA)
    rows: Dict[str, list] = {}
    async with db.execute(
            "SELECT item_key,effective_from,amount FROM admin_cost_history WHERE category=? "
            "ORDER BY effective_from", (category,)) as cur:
        for key, since, amount in await cur.fetchall():
            rows.setdefault(str(key), []).append((str(since), float(amount)))
    return rows


def _rate_on(rows, fallback, day: str):
    """Shu kunga amal qilgan narx; tarix bo‘lmasa eski qo‘lda kiritilgan qiymat."""
    if not rows:
        return fallback
    value = None
    for since, amount in rows:
        if since <= day:
            value = amount
    return value


def _rate_now(rows, fallback):
    return rows[-1][1] if rows else fallback


async def _record_rate(db, category: str, key: str, amount: float, legacy=None) -> None:
    """Narx o‘zgarsa yangi qator qo‘shadi — eski kunlar hisobi o‘zgarmaydi."""
    await db.execute(_HISTORY_SCHEMA)
    async with db.execute(
            "SELECT amount FROM admin_cost_history WHERE category=? AND item_key=? "
            "ORDER BY effective_from DESC LIMIT 1", (category, key)) as cur:
        last = await cur.fetchone()
    query = "INSERT OR REPLACE INTO admin_cost_history (category,item_key,effective_from,amount) VALUES (?,?,?,?)"
    if last is None:
        if legacy is not None and float(legacy) != float(amount):
            await db.execute(query, (category, key, BASE_DAY, float(legacy)))
            await db.execute(query, (category, key, today_uzt(), float(amount)))
        else:
            await db.execute(query, (category, key, BASE_DAY, float(amount)))
    elif float(last[0]) != float(amount):
        await db.execute(query, (category, key, today_uzt(), float(amount)))


async def _forget_rate(db, category: str, key: str) -> None:
    await db.execute(_HISTORY_SCHEMA)
    await db.execute("DELETE FROM admin_cost_history WHERE category=? AND item_key=?", (category, key))


FREE_OFFERS = {
    "free_trial": "Bepul sinov (5 slayd)",
    "free_gift": "Tekin havola taqdimoti (10 slayd)",
}


def _uzt_day(epoch: float) -> str:
    return (datetime.fromtimestamp(float(epoch), timezone.utc) + timedelta(hours=5)).strftime("%Y-%m-%d")


async def _free_offers(db, start_day, end_day, since_epoch, end_epoch, service_rate) -> dict:
    """Bepul taqdimotlar: nechta odam oldi, AI xarajati, keyin to‘lov qilganlar va ulardan tushum.

    Tugamagan (hali yetkazilmagan) bot buyurtmalari sanalmaydi. Xarajat — admin kiritgan bitta taqdimot
    o‘rtacha narxi (sanaga bog‘liq tarix bilan). Tushum — bepul taqdimotdan keyin qilingan tasdiqlangan to‘lovlar.
    """
    sources = (
        ("free_trial", "free_trials",
         "SELECT ft.telegram_id,ft.job_id,ft.created_at FROM free_trials ft WHERE ft.created_at>=? "
         "AND ft.created_at<? AND NOT (ft.job_id LIKE 'bot-%' AND ft.job_id NOT LIKE 'bot-sent-%')"),
        ("free_gift", "gift_link_uses",
         "SELECT ft.telegram_id,ft.job_id,ft.created_at FROM gift_link_uses ft WHERE ft.created_at>=? "
         "AND ft.created_at<? AND NOT (ft.job_id LIKE 'bot-%' AND ft.job_id NOT LIKE 'bot-sent-%')"),
    )
    result = {"items": [], "site_trials_by_day": {}, "daily": {}}
    for key, table, query in sources:
        item = {"key": key, "name": FREE_OFFERS[key], "users": 0, "cost": 0, "unit_cost": None,
                "cost_configured": False, "unpriced": False, "payers": 0, "revenue": 0,
                "payments": 0, "net": 0}
        if await _has_table(db, table):
            async with db.execute(query, (since_epoch, end_epoch)) as cur:
                uses = [dict(row) for row in await cur.fetchall()]
            seen_payers = set()
            for use in uses:
                day = _uzt_day(use["created_at"])
                item["users"] += 1
                if key == "free_trial" and not str(use["job_id"]).startswith("bot-"):
                    by_day = result["site_trials_by_day"]
                    by_day[day] = by_day.get(day, 0) + 1
                rate = service_rate(key, day)
                if rate is None:
                    item["unpriced"] = True
                else:
                    item["cost"] += rate
                async with db.execute(
                        "SELECT COUNT(p.id),COALESCE(SUM(p.amount),0) FROM users u JOIN payments p "
                        "ON p.user_id=u.id WHERE u.telegram_id=? AND p.status='approved' "
                        "AND p.created_at>=datetime(?,'unixepoch')",
                        (use["telegram_id"], use["created_at"])) as cur:
                    count, amount = await cur.fetchone()
                if count and use["telegram_id"] not in seen_payers:
                    seen_payers.add(use["telegram_id"])
                    item["payers"] += 1
                    item["payments"] += int(count)
                    item["revenue"] += int(amount)
                result["daily"][day] = result["daily"].get(day, 0) + 1
        item["cost"] = round(item["cost"])
        item["net"] = item["revenue"] - item["cost"]
        item["conversion"] = round(item["payers"] * 100 / item["users"], 1) if item["users"] else 0
        item["cost_per_payer"] = round(item["cost"] / item["payers"]) if item["payers"] else None
        result["items"].append(item)
    return result


def _epoch(value) -> float:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).replace("T", " ")[:19]
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0


async def _has_table(db, name: str) -> bool:
    async with db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)) as cur:
        return await cur.fetchone() is not None


async def _scalar(db, query: str, args: tuple = ()) -> int:
    async with db.execute(query, args) as cur:
        row = await cur.fetchone()
    return int((row or [0])[0] or 0)


async def _costs(db, category: str, period_days: int = 0) -> Dict[str, int]:
    await db.execute(_COST_SCHEMA)
    async with db.execute(
            "SELECT item_key, amount FROM admin_cost_settings WHERE category=? AND period_days=?",
            (category, period_days)) as cur:
        return {str(key): int(amount) for key, amount in await cur.fetchall()}


def _usd_amount(raw) -> float:
    if isinstance(raw, bool):
        raise ValueError("Rasm narxi dollarda musbat son bo‘lishi kerak")
    try:
        amount = Decimal(str(raw).strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError("Rasm narxi dollarda musbat son bo‘lishi kerak")
    if not amount.is_finite() or amount < 0 or amount > 1000:
        raise ValueError("Rasm narxi 0 va 1000 dollar orasida bo‘lishi kerak")
    return float(round(amount, 6))


async def save_costs(days: int, service_costs: dict, campaign_costs: dict,
                     image_costs: Optional[dict] = None, usd_rate=None) -> None:
    """Save service cost, period advertising spend, per-image USD cost and the USD rate.

    Service, image and USD values keep dated history, so a price change affects only later days.
    """
    if days not in (1, 7, 30, 90):
        raise ValueError("Davr 1, 7, 30 yoki 90 kun bo‘lishi kerak")
    image_costs = {} if image_costs is None else image_costs
    if not isinstance(image_costs, dict):
        raise ValueError("Rasm narxlari ro‘yxati noto‘g‘ri")
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(_COST_SCHEMA)
        if usd_rate not in (None, ""):
            if isinstance(usd_rate, bool) or not str(usd_rate).isdecimal() \
                    or not 1_000 <= int(usd_rate) <= 1_000_000:
                raise ValueError("Dollar kursi 1 000 va 1 000 000 so‘m orasidagi butun son bo‘lishi kerak")
            await _record_rate(db, "usd_rate", "usd", int(usd_rate))
        if image_costs:
            known_models = set()
            if await _has_table(db, "ai_usage"):
                async with db.execute("SELECT DISTINCT name FROM ai_usage WHERE kind=?", (IMAGE_KIND,)) as cur:
                    known_models = {str(row[0]) for row in await cur.fetchall()}
            for model, raw_amount in image_costs.items():
                if model not in known_models:
                    raise ValueError("Noma’lum rasm modeli")
                if raw_amount is None or raw_amount == "":
                    await _forget_rate(db, "image_usd", model)
                else:
                    await _record_rate(db, "image_usd", model, _usd_amount(raw_amount))
        allowed_services = set(SERVICE_LABELS) | set(FREE_OFFERS)
        if await _has_table(db, "document_stats"):
            async with db.execute("SELECT DISTINCT document_type FROM document_stats") as cur:
                allowed_services.update(str(row[0]) for row in await cur.fetchall() if row[0])
        allowed_flows = set(CAMPAIGN_FLOWS)
        for costs, category, allowed, period in (
                (service_costs, "service", allowed_services, 0),
                (campaign_costs, "campaign", allowed_flows, days)):
            if not isinstance(costs, dict):
                raise ValueError("Xarajatlar ro‘yxati noto‘g‘ri")
            for key, raw_amount in costs.items():
                if key not in allowed:
                    raise ValueError("Noma’lum xizmat yoki kampaniya")
                if raw_amount is None or raw_amount == "":
                    await db.execute(
                        "DELETE FROM admin_cost_settings WHERE category=? AND item_key=? AND period_days=?",
                        (category, key, period))
                    if category == "service":
                        await _forget_rate(db, "service", key)
                    continue
                if isinstance(raw_amount, bool) or not str(raw_amount).isdecimal():
                    raise ValueError("Xarajat butun, manfiy bo‘lmagan son bo‘lishi kerak")
                try:
                    amount = int(raw_amount)
                except (TypeError, ValueError):
                    raise ValueError("Xarajat butun son bo‘lishi kerak")
                if amount < 0 or amount > 1_000_000_000:
                    raise ValueError("Xarajat 0 va 1 milliard so‘m orasida bo‘lishi kerak")
                if category == "service":
                    async with db.execute(
                            "SELECT amount FROM admin_cost_settings WHERE category=? AND item_key=? "
                            "AND period_days=0", (category, key)) as cur:
                        previous = await cur.fetchone()
                    await _record_rate(db, "service", key, amount, previous[0] if previous else None)
                await db.execute(
                    "INSERT INTO admin_cost_settings (category,item_key,period_days,amount) "
                    "VALUES (?,?,?,?) ON CONFLICT(category,item_key,period_days) "
                    "DO UPDATE SET amount=excluded.amount,updated_at=CURRENT_TIMESTAMP",
                    (category, key, period, amount))
        await db.commit()


def _model_name(model_id: str) -> str:
    """Admin uchun o'qiladigan nom: katalogdagi nom bo'lsa — u, aks holda ID ning oxirgi qismi."""
    from config import AI_MODELS, IMAGE_MODELS

    for info in list(AI_MODELS.values()) + list(IMAGE_MODELS.values()):
        if info.get("id") == model_id:
            return info.get("name") or model_id
    return model_id.split("/")[-1] if model_id else "—"


async def ai_config() -> list:
    """Hozir qaysi xizmatga qaysi AI sozlangan: [{service, kind, model, name, source}]."""
    from config import AI_MODELS, BOOK_TRANSLATE_MODELS, DEFAULT_AI_MODEL, PREMIUM_DEFAULT_AI_MODEL
    from database.database import Database
    from services.premium_presentation import config as pconfig

    rows = []

    def add(service: str, kind: str, model: str, source: str) -> None:
        rows.append({"service": service, "kind": kind, "model": model, "name": _model_name(model), "source": source})

    async def admin_text(getter, default_key: str) -> str:
        try:
            key = await getter()
        except Exception:
            key = default_key
        return AI_MODELS.get(key, AI_MODELS[default_key])["id"]

    main = await admin_text(Database.get_current_ai_model, DEFAULT_AI_MODEL)
    premium = await admin_text(Database.get_premium_ai_model, PREMIUM_DEFAULT_AI_MODEL)
    add("Hujjatlar va oddiy taqdimot", "text", main, "Admin panel")
    add("Zamonaviy taqdimot", "text", premium, "Admin panel")
    add("3D Pro", "text", premium, "Zamonaviy taqdimot modeli")
    try:
        from services.med3d import auto as med3d

        add("3D Anatomiya", "text", med3d.MODEL, "Doimiy (MED3D_MODEL)")
    except Exception:
        pass
    for service, chain in (("To'lov cheki", pconfig.OPENROUTER_RECEIPT_MODELS),
                           ("Kitob OCR", pconfig.OPENROUTER_OCR_MODELS),
                           ("Rasm tanlash", pconfig.OPENROUTER_PHOTO_MODELS),
                           ("Slayd tekshiruvi (ko'z)", pconfig.OPENROUTER_VISION_MODELS),
                           ("Kitob tarjimasi", BOOK_TRANSLATE_MODELS)):
        if chain:
            add(service, "text", chain[0], "Doimiy")
    try:
        from services import together_service

        for target, service in (("docs", "Hujjatlar"), ("presentation", "Oddiy taqdimot"),
                                ("premium", "Zamonaviy taqdimot"), ("med3d", "3D Anatomiya")):
            add(service, "image", await together_service.chosen_image_model(target), "Admin panel")
    except Exception:
        pass
    try:
        from services.pro3d import images as pro3d_images

        chain = pro3d_images.models()
        if chain:
            add("3D Pro", "image", chain[0], "Doimiy (PRO3D_IMAGE_MODELS)")
    except Exception:
        pass
    return rows


async def dashboard(days: int = 30) -> dict:
    """Return dashboard data for the selected UZT day window (1, 7, 30 or 90)."""
    days = days if days in (1, 7, 30, 90) else 30
    end_day = today_uzt()
    end_date = datetime.strptime(end_day, "%Y-%m-%d")
    first_date = end_date - timedelta(days=days - 1)
    start_day = first_date.strftime("%Y-%m-%d")
    since_epoch = (first_date - timedelta(hours=5)).replace(tzinfo=timezone.utc).timestamp()
    end_epoch = (end_date + timedelta(days=1) - timedelta(hours=5)).replace(
        tzinfo=timezone.utc).timestamp()

    day_rows = {
        (first_date + timedelta(days=i)).strftime("%Y-%m-%d"): {
            "date": (first_date + timedelta(days=i)).strftime("%Y-%m-%d"),
            "users": 0, "revenue": 0, "created": 0, "payments": 0,
        } for i in range(days)
    }
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(_COST_SCHEMA)

        total_users = await _scalar(db, "SELECT COUNT(*) FROM users")
        paying_users = await _scalar(db, "SELECT COUNT(DISTINCT user_id) FROM payments WHERE status='approved'")
        total_revenue = await _scalar(
            db, "SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='approved'")
        period_users = await _scalar(
            db, "SELECT COUNT(*) FROM users WHERE date(created_at,'+5 hours') BETWEEN ? AND ?",
            (start_day, end_day))
        period_payers = await _scalar(
            db, "SELECT COUNT(DISTINCT p.user_id) FROM payments p JOIN users u ON u.id=p.user_id "
            "WHERE p.status='approved' AND date(p.created_at,'+5 hours') BETWEEN ? AND ?",
            (start_day, end_day))
        period_revenue = await _scalar(
            db, "SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='approved' "
            "AND date(created_at,'+5 hours') BETWEEN ? AND ?", (start_day, end_day))
        total_payments = await _scalar(
            db, "SELECT COUNT(*) FROM payments WHERE status='approved' AND date(created_at,'+5 hours') BETWEEN ? AND ?",
            (start_day, end_day))
        repeat_payers = await _scalar(
            db, "SELECT COUNT(*) FROM (SELECT user_id FROM payments WHERE status='approved' "
            "GROUP BY user_id HAVING COUNT(*)>1)")
        repeat_users = await _scalar(
            db, "SELECT COUNT(*) FROM (SELECT telegram_id FROM balance_spends "
            "GROUP BY telegram_id HAVING COUNT(*)>1)") if await _has_table(db, "balance_spends") else 0
        spenders = await _scalar(db, "SELECT COUNT(DISTINCT telegram_id) FROM balance_spends") \
            if await _has_table(db, "balance_spends") else 0
        unconverted = await _scalar(
            db, "SELECT COUNT(*) FROM users u WHERE date(u.created_at,'+5 hours') BETWEEN ? AND ? "
            "AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.user_id=u.id AND p.status='approved')",
            (start_day, end_day))
        first_time_payers = await _scalar(
            db, "SELECT COUNT(DISTINCT p.user_id) FROM payments p JOIN users u ON u.id=p.user_id "
            "WHERE p.status='approved' AND date(p.created_at,'+5 hours') BETWEEN ? AND ? "
            "AND date(u.created_at,'+5 hours') BETWEEN ? AND ?",
            (start_day, end_day, start_day, end_day))
        cohort = {"first_payers": 0, "used_after_first_payment": 0, "repaid_after_use": 0}
        if await _has_table(db, "balance_spends"):
            async with db.execute(
                    "WITH first_payments AS ("
                    " SELECT p.user_id,u.telegram_id,MIN(p.created_at) AS first_paid_at"
                    " FROM payments p JOIN users u ON u.id=p.user_id"
                    " WHERE p.status='approved' GROUP BY p.user_id"
                    "), cohort AS ("
                    " SELECT * FROM first_payments"
                    " WHERE date(first_paid_at,'+5 hours') BETWEEN ? AND ?"
                    ")"
                    " SELECT COUNT(*) AS first_payers,"
                    " SUM(CASE WHEN EXISTS ("
                    "  SELECT 1 FROM balance_spends s"
                    "  WHERE s.telegram_id=cohort.telegram_id"
                    "   AND julianday(s.created_at)>=julianday(cohort.first_paid_at)"
                    " ) THEN 1 ELSE 0 END) AS used_after_first_payment,"
                    " SUM(CASE WHEN EXISTS ("
                    "  SELECT 1 FROM balance_spends s"
                    "  WHERE s.telegram_id=cohort.telegram_id"
                    "   AND julianday(s.created_at)>=julianday(cohort.first_paid_at)"
                    "   AND EXISTS (SELECT 1 FROM payments p2"
                    "    WHERE p2.user_id=cohort.user_id AND p2.status='approved'"
                    "     AND julianday(p2.created_at)>julianday(s.created_at))"
                    " ) THEN 1 ELSE 0 END) AS repaid_after_use"
                    " FROM cohort", (start_day, end_day)) as cur:
                row = await cur.fetchone()
                if row:
                    cohort = {key: int(row[key] or 0) for key in cohort}

        async with db.execute(
                "SELECT date(created_at,'+5 hours') day,COUNT(*) n FROM users "
                "WHERE date(created_at,'+5 hours') BETWEEN ? AND ? GROUP BY day", (start_day, end_day)) as cur:
            for row in await cur.fetchall():
                day_rows[row["day"]]["users"] = int(row["n"])
        async with db.execute(
                "SELECT date(created_at,'+5 hours') day,COUNT(*) n,SUM(amount) amount FROM payments "
                "WHERE status='approved' AND date(created_at,'+5 hours') BETWEEN ? AND ? GROUP BY day",
                (start_day, end_day)) as cur:
            for row in await cur.fetchall():
                day_rows[row["day"]]["payments"] = int(row["n"])
                day_rows[row["day"]]["revenue"] = int(row["amount"] or 0)

        service_costs = await _costs(db, "service")
        service_history = await _history(db, "service")
        image_history = await _history(db, "image_usd")
        usd_history = (await _history(db, "usd_rate")).get("usd")
        usd_now = int(_rate_now(usd_history, DEFAULT_USD_RATE))

        def service_rate(key: str, day: str):
            return _rate_on(service_history.get(key), service_costs.get(key), day)

        free_offers = await _free_offers(db, start_day, end_day, since_epoch, end_epoch, service_rate)
        # Saytdagi bepul sinov document_stats'da oddiy taqdimot bo‘lib yoziladi; tannarxi ikki marta sanalmasin.
        site_trials_by_day = free_offers["site_trials_by_day"]

        services: Dict[str, int] = {}
        service_spend: Dict[str, float] = {}
        unpriced_days: set = set()

        def add_service(key: str, day: str, count: int) -> None:
            services[key] = services.get(key, 0) + count
            if key == "presentation":
                count = max(count - site_trials_by_day.get(day, 0), 0)
            rate = service_rate(key, day)
            if rate is None:
                unpriced_days.add(key)
            else:
                service_spend[key] = service_spend.get(key, 0) + count * rate

        service_keys = set(SERVICE_LABELS)
        if await _has_table(db, "document_stats"):
            async with db.execute("SELECT DISTINCT document_type FROM document_stats") as cur:
                service_keys.update(str(row[0]) for row in await cur.fetchall() if row[0])
            async with db.execute(
                    "SELECT date(completed_at,'+5 hours') day,document_type key,COUNT(*) count "
                    "FROM document_stats WHERE date(completed_at,'+5 hours') BETWEEN ? AND ? "
                    "GROUP BY day,document_type", (start_day, end_day)) as cur:
                for row in await cur.fetchall():
                    add_service(str(row["key"]), row["day"], int(row["count"]))
                    day_rows[row["day"]]["created"] += int(row["count"])
        if await _has_table(db, "store_orders"):
            service_keys.add("store_sale")
            async with db.execute(
                    "SELECT date(COALESCE(paid_at,created_at),'+5 hours') day,COUNT(*) count "
                    "FROM store_orders WHERE status='paid' AND date(COALESCE(paid_at,created_at),'+5 hours') "
                    "BETWEEN ? AND ? GROUP BY day", (start_day, end_day)) as cur:
                for row in await cur.fetchall():
                    add_service("store_sale", row["day"], int(row["count"]))
                    day_rows[row["day"]]["created"] += int(row["count"])

        image_models: Dict[str, dict] = {}
        if await _has_table(db, "ai_usage"):
            async with db.execute("SELECT DISTINCT name FROM ai_usage WHERE kind=?", (IMAGE_KIND,)) as cur:
                for row in await cur.fetchall():
                    image_models[str(row[0])] = {"count": 0, "cost": 0.0, "unpriced": False}
            async with db.execute(
                    "SELECT day,name,SUM(count) count FROM ai_usage WHERE kind=? AND day BETWEEN ? AND ? "
                    "GROUP BY day,name", (IMAGE_KIND, start_day, end_day)) as cur:
                for row in await cur.fetchall():
                    item = image_models[str(row["name"])]
                    count = int(row["count"] or 0)
                    item["count"] += count
                    usd = _rate_on(image_history.get(str(row["name"])), None, row["day"])
                    rate = _rate_on(usd_history, DEFAULT_USD_RATE, row["day"])
                    if usd is None:
                        item["unpriced"] = item["unpriced"] or count > 0
                    else:
                        item["cost"] += count * usd * rate
        image_rows = [{
            "key": name,
            "name": name.rsplit("/", 1)[-1],
            "count": item["count"],
            "usd_unit": _rate_now(image_history.get(name), None),
            "cost_configured": name in image_history,
            "estimated_cost": round(item["cost"]),
            "unpriced": item["unpriced"],
        } for name, item in sorted(image_models.items(), key=lambda pair: -pair[1]["count"])]
        image_cost_total = sum(row["estimated_cost"] for row in image_rows)
        missing_images = [row["name"] for row in image_rows if row["unpriced"]]

        payment_sources = []
        async with db.execute(
                "SELECT CASE WHEN COALESCE(source,'')='' THEN 'Noma’lum' ELSE source END source,"
                "COUNT(*) payments,COALESCE(SUM(amount),0) revenue "
                "FROM payments WHERE status='approved' AND date(created_at,'+5 hours') BETWEEN ? AND ? "
                "GROUP BY source ORDER BY revenue DESC", (start_day, end_day)) as cur:
            payment_sources = [dict(row) for row in await cur.fetchall()]

        acquisition = []
        async with db.execute(
                "SELECT CASE WHEN u.referred_by IS NOT NULL THEN 'Tavsiya orqali' ELSE 'To‘g‘ridan-to‘g‘ri' END source,"
                "COUNT(DISTINCT u.id) users,COUNT(DISTINCT CASE WHEN p.id IS NOT NULL THEN u.id END) payers,"
                "COALESCE(SUM(p.amount),0) revenue FROM users u LEFT JOIN payments p ON p.user_id=u.id "
                "AND p.status='approved' AND date(p.created_at,'+5 hours') BETWEEN ? AND ? "
                "WHERE date(u.created_at,'+5 hours') BETWEEN ? AND ? GROUP BY source",
                (start_day, end_day, start_day, end_day)) as cur:
            acquisition = [dict(row) for row in await cur.fetchall()]

        ai_usage = []
        if await _has_table(db, "ai_usage"):
            async with db.execute(
                    "SELECT kind,name,COALESCE(SUM(count),0) count FROM ai_usage "
                    "WHERE day BETWEEN ? AND ? GROUP BY kind,name ORDER BY count DESC LIMIT 20",
                    (start_day, end_day)) as cur:
                ai_usage = [dict(row) for row in await cur.fetchall()]

        from services import ai_usage as usage_log

        try:
            ai_where = await usage_log.where_counts(start_day, end_day)
            for row in ai_where:
                row["label"] = _model_name(row["name"])
        except Exception:
            ai_where = []

        campaign_costs = await _costs(db, "campaign", days)
        campaign_rows = []
        if await _has_table(db, "nudges"):
            async with db.execute(
                    "SELECT id,telegram_id,flow,step,sent_at,status,clicked_at FROM nudges "
                    "WHERE sent_at>=? AND sent_at<? ORDER BY sent_at", (since_epoch, end_epoch)) as cur:
                nudges = [dict(row) for row in await cur.fetchall()]
            async with db.execute(
                    "SELECT u.telegram_id,p.amount,p.created_at FROM payments p JOIN users u ON u.id=p.user_id "
                    "WHERE p.status='approved' AND date(p.created_at,'+5 hours') BETWEEN ? AND ?",
                    (start_day, end_day)) as cur:
                paid_rows = [dict(row) for row in await cur.fetchall()]
            campaigns: Dict[str, dict] = {}
            clicked = []
            for nudge in nudges:
                if nudge["status"] != "sent":
                    continue
                flow = str(nudge["flow"])
                item = campaigns.setdefault(flow, {
                    "key": flow, "name": FLOW_LABELS.get(flow, flow), "sent": 0,
                    "clicks": 0, "buyers": 0, "revenue": 0, "buyer_ids": set(),
                })
                item["sent"] += 1
                if nudge["clicked_at"]:
                    click_at = float(nudge["clicked_at"])
                    if since_epoch <= click_at < end_epoch:
                        item["clicks"] += 1
                        clicked.append((int(nudge["telegram_id"]), click_at, flow))
            paid_by_user: Dict[int, list] = {}
            for pay in paid_rows:
                paid_by_user.setdefault(int(pay["telegram_id"]), []).append(
                    (_epoch(pay["created_at"]), int(pay["amount"])))
            for telegram_id, amount_rows in paid_by_user.items():
                for paid_at, amount in amount_rows:
                    eligible = [(click_at, flow) for tg, click_at, flow in clicked
                                if tg == telegram_id and click_at <= paid_at <= click_at + ATTRIBUTION_DAYS * 86400]
                    if eligible:
                        _, flow = max(eligible)
                        item = campaigns[flow]
                        item["revenue"] += amount
                        item["buyer_ids"].add(telegram_id)
            for key, item in campaigns.items():
                item["buyers"] = len(item.pop("buyer_ids"))
                item["cost"] = campaign_costs.get(key, 0)
                item["cost_configured"] = key in campaign_costs
                item["roi"] = round((item["revenue"] - item["cost"]) * 100 / item["cost"], 1) \
                    if item["cost"] else None
                item["click_rate"] = round(item["clicks"] * 100 / item["sent"], 1) if item["sent"] else 0
                campaign_rows.append(item)
        present_campaigns = {row["key"] for row in campaign_rows}
        for flow in CAMPAIGN_FLOWS:
            if flow not in present_campaigns:
                campaign_rows.append({
                    "key": flow, "name": FLOW_LABELS[flow], "sent": 0, "clicks": 0,
                    "buyers": 0, "revenue": 0, "cost": campaign_costs.get(flow, 0),
                    "cost_configured": flow in campaign_costs,
                    "roi": None, "click_rate": 0,
                })
        campaign_rows.sort(key=lambda row: row["revenue"], reverse=True)

    for key in service_keys:
        services.setdefault(key, 0)
    service_rows = [{
        "key": key,
        "name": SERVICE_LABELS.get(key, key.replace("_", " ").capitalize()),
        "count": count,
        "unit_cost": round(_rate_now(service_history.get(key), service_costs.get(key, 0)) or 0),
        "estimated_cost": round(service_spend.get(key, 0)),
        "cost_configured": key in service_history or key in service_costs,
        "unpriced": key in unpriced_days,
    } for key, count in sorted(services.items(), key=lambda item: item[1], reverse=True)]
    missing_costs = [row["name"] for row in service_rows if row["unpriced"]]
    missing_costs += [f"Rasm: {name}" for name in missing_images]
    free_rows = free_offers["items"]
    for row in free_rows:
        row["unit_cost"] = service_rate(row["key"], end_day)
        row["cost_configured"] = row["key"] in service_history or row["key"] in service_costs
        if row["unpriced"]:
            missing_costs.append(row["name"])
    free_cost_total = sum(row["cost"] for row in free_rows)
    service_cost_total = sum(row["estimated_cost"] for row in service_rows)
    campaign_cost_total = sum(row["cost"] for row in campaign_rows)
    total_cost = service_cost_total + image_cost_total + campaign_cost_total + free_cost_total
    active_campaigns_missing_cost = any(row["sent"] and not row["cost_configured"] for row in campaign_rows)
    try:
        config_rows = await ai_config()
    except Exception:
        config_rows = []

    return {
        "period": {"days": days, "start": start_day, "end": end_day},
        "summary": {
            "users": total_users,
            "new_users": period_users,
            "new_payers": first_time_payers,
            "period_payers": period_payers,
            "paying_users": paying_users,
            "revenue": period_revenue,
            "lifetime_revenue": total_revenue,
            "payments": total_payments,
            "avg_lifetime_revenue": round(total_revenue / paying_users) if paying_users else 0,
            "avg_revenue_per_user": round(total_revenue / total_users) if total_users else 0,
            "estimated_profit_per_payer": round(
                (period_revenue - total_cost) / period_payers
            ) if period_payers else 0,
            "repeat_payers": repeat_payers,
            "repeat_payment_rate": round(repeat_payers * 100 / paying_users, 1) if paying_users else 0,
            "repeat_users": repeat_users,
            "spenders": spenders,
            "repeat_use_rate": round(repeat_users * 100 / spenders, 1) if spenders else 0,
            "cohort_first_payers": cohort["first_payers"],
            "cohort_used_after_first_payment": cohort["used_after_first_payment"],
            "cohort_repaid_after_use": cohort["repaid_after_use"],
            "cohort_use_rate": round(
                cohort["used_after_first_payment"] * 100 / cohort["first_payers"], 1
            ) if cohort["first_payers"] else 0,
            "cohort_repayment_after_use_rate": round(
                cohort["repaid_after_use"] * 100 / cohort["used_after_first_payment"], 1
            ) if cohort["used_after_first_payment"] else 0,
            "unconverted_users": unconverted,
            "created": sum(row["created"] for row in day_rows.values()),
            "service_cost": service_cost_total,
            "free_cost": free_cost_total,
            "free_users": sum(row["users"] for row in free_rows),
            "free_payers": sum(row["payers"] for row in free_rows),
            "image_cost": image_cost_total,
            "usd_rate": usd_now,
            "campaign_cost": campaign_cost_total,
            "estimated_profit": period_revenue - total_cost,
            "missing_costs": missing_costs,
            "campaign_cost_missing": active_campaigns_missing_cost,
            "profit_complete": not missing_costs and not active_campaigns_missing_cost,
        },
        "daily": list(day_rows.values()),
        "services": service_rows,
        "image_models": image_rows,
        "free_offers": free_rows,
        "payment_sources": payment_sources,
        "acquisition": acquisition,
        "campaigns": campaign_rows,
        "ai_usage": ai_usage,
        "ai_where": ai_where,
        "ai_config": config_rows,
        "costs": {
            "services": service_costs,
            "campaigns": campaign_costs,
        },
    }
