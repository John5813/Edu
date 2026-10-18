"""Admin Mini App analytics from anonymized product, payment and campaign records."""

from datetime import datetime, timedelta, timezone
from typing import Dict

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


async def save_costs(days: int, service_costs: dict, campaign_costs: dict) -> None:
    """Save per-output service cost and period advertising spend."""
    if days not in (1, 7, 30, 90):
        raise ValueError("Davr 1, 7, 30 yoki 90 kun bo‘lishi kerak")
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(_COST_SCHEMA)
        allowed_services = set(SERVICE_LABELS)
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
                    continue
                if isinstance(raw_amount, bool) or not str(raw_amount).isdecimal():
                    raise ValueError("Xarajat butun, manfiy bo‘lmagan son bo‘lishi kerak")
                try:
                    amount = int(raw_amount)
                except (TypeError, ValueError):
                    raise ValueError("Xarajat butun son bo‘lishi kerak")
                if amount < 0 or amount > 1_000_000_000:
                    raise ValueError("Xarajat 0 va 1 milliard so‘m orasida bo‘lishi kerak")
                await db.execute(
                    "INSERT INTO admin_cost_settings (category,item_key,period_days,amount) "
                    "VALUES (?,?,?,?) ON CONFLICT(category,item_key,period_days) "
                    "DO UPDATE SET amount=excluded.amount,updated_at=CURRENT_TIMESTAMP",
                    (category, key, period, amount))
        await db.commit()


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

        services: Dict[str, int] = {}
        service_keys = set(SERVICE_LABELS)
        if await _has_table(db, "document_stats"):
            async with db.execute("SELECT DISTINCT document_type FROM document_stats") as cur:
                service_keys.update(str(row[0]) for row in await cur.fetchall() if row[0])
            async with db.execute(
                    "SELECT document_type key,COUNT(*) count FROM document_stats "
                    "WHERE date(completed_at,'+5 hours') BETWEEN ? AND ? GROUP BY document_type",
                    (start_day, end_day)) as cur:
                for row in await cur.fetchall():
                    services[str(row["key"])] = int(row["count"])
            async with db.execute(
                    "SELECT date(completed_at,'+5 hours') day,COUNT(*) count FROM document_stats "
                    "WHERE date(completed_at,'+5 hours') BETWEEN ? AND ? GROUP BY day",
                    (start_day, end_day)) as cur:
                for row in await cur.fetchall():
                    day_rows[row["day"]]["created"] += int(row["count"])
        if await _has_table(db, "store_orders"):
            store_sales = await _scalar(
                db, "SELECT COUNT(*) FROM store_orders WHERE status='paid' "
                "AND date(COALESCE(paid_at,created_at),'+5 hours') BETWEEN ? AND ?", (start_day, end_day))
            if store_sales:
                services["store_sale"] = store_sales
            service_keys.add("store_sale")
            async with db.execute(
                    "SELECT date(COALESCE(paid_at,created_at),'+5 hours') day,COUNT(*) count "
                    "FROM store_orders WHERE status='paid' AND date(COALESCE(paid_at,created_at),'+5 hours') "
                    "BETWEEN ? AND ? GROUP BY day", (start_day, end_day)) as cur:
                for row in await cur.fetchall():
                    day_rows[row["day"]]["created"] += int(row["count"])

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

        service_costs = await _costs(db, "service")
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
        "unit_cost": service_costs.get(key, 0),
        "estimated_cost": count * service_costs.get(key, 0),
        "cost_configured": key in service_costs,
    } for key, count in sorted(services.items(), key=lambda item: item[1], reverse=True)]
    missing_costs = [row["name"] for row in service_rows if row["count"] and not row["cost_configured"]]
    service_cost_total = sum(row["estimated_cost"] for row in service_rows)
    campaign_cost_total = sum(row["cost"] for row in campaign_rows)
    active_campaigns_missing_cost = any(row["sent"] and not row["cost_configured"] for row in campaign_rows)
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
                (period_revenue - service_cost_total - campaign_cost_total) / period_payers
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
            "campaign_cost": campaign_cost_total,
            "estimated_profit": period_revenue - service_cost_total - campaign_cost_total,
            "missing_costs": missing_costs,
            "campaign_cost_missing": active_campaigns_missing_cost,
            "profit_complete": not missing_costs and not active_campaigns_missing_cost,
        },
        "daily": list(day_rows.values()),
        "services": service_rows,
        "payment_sources": payment_sources,
        "acquisition": acquisition,
        "campaigns": campaign_rows,
        "ai_usage": ai_usage,
        "costs": {
            "services": service_costs,
            "campaigns": campaign_costs,
        },
    }
