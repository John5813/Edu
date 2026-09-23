"""Diagramma ma'lumotidan jadval quradi — hisob-kitobni kod bajaradi.

Ilgari har bo'lim uchun ikkita alohida AI so'rovi bo'lardi: biri jadval,
biri diagramma uchun. Natijada jadvaldagi summa bilan diagrammadagi ustun
mos kelmasligi mumkin edi — ikkalasi ham modelning alohida javobi edi.
Byudjet jadvali esa umuman chaqirilmagani uchun bu ko'rinmay qolgan edi.

Endi model faqat raqamlarni beradi, jadval ham diagramma ham o'sha bitta
ma'lumotdan quriladi. Yig'indi, ulush, sof oqim va o'rtacha qiymat shu
yerda — Pythonda — hisoblanadi:

  • ustoz avvalo yig'indini tekshiradi, model esa qo'shishda xato qiladi;
  • jadval bilan diagramma bir xil raqamni ko'rsatishi kafolatlanadi.

`normalise` funksiyalari ma'lumotni chizuvchi kutgan holga ham keltiradi:
masalan byudjetda model miqdor va birlik narxini beradi, `amount` esa
ularning ko'paytmasi sifatida shu yerda paydo bo'ladi.
"""

import logging
import re
from typing import Dict, List, Optional

from .specs import (
    ARTIFACT_BREAKEVEN,
    ARTIFACT_BUDGET,
    ARTIFACT_CASHFLOW,
    ARTIFACT_COSTS,
    ARTIFACT_FORECAST,
    ARTIFACT_MARKETING,
    ARTIFACT_RISKS,
    ARTIFACT_TIMELINE,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────── yordamchilar

def number(value) -> float:
    """Modelning "12 500 000 so'm" yoki "35,2" kabi javobidan sonni ajratadi.

    Ochiq funksiya: `content.py` ham modelning javobini shu bilan tekshiradi,
    shunda jadval va tekshiruv bir xil qoidaga tayanadi.
    """
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return 0.0
    # Probel, apostrof, "so'm", "%" — hammasi tashlanadi, faqat raqam qoladi.
    digits = re.sub(r"[^\d.,-]", "", text)
    # Vergul kasr ajratgichi bo'lishi mumkin ("35,2"), minglik ajratgich ham
    # ("1,200,000"). Bittagina vergul va nuqta bo'lmasa — kasr deb olamiz.
    if digits.count(",") == 1 and "." not in digits:
        digits = digits.replace(",", ".")
    else:
        digits = digits.replace(",", "")
    try:
        return float(digits)
    except ValueError:
        return 0.0


def _money(value: float) -> str:
    """Minglik ajratgich sifatida probel — hujjatlarda shu ko'rinish kutiladi."""
    return f"{round(value):,}".replace(",", " ")


def _decimal(value: float, places: int = 1) -> str:
    text = f"{value:.{places}f}".rstrip("0").rstrip(".")
    return (text or "0").replace(".", ",")


def _percent(value: float) -> str:
    return f"{_decimal(value)}%"


def _text(value) -> str:
    return " ".join(str(value or "").split())


def _columns(table: Dict[str, List[str]], language: str) -> List[str]:
    return table.get(language, table["uz"])


# ────────────────────────────────────────────────────────────── ustun nomlari

_BUDGET_COLUMNS = {
    "uz": ["Xarajat moddasi", "Miqdori", "Birlik narxi, so'm", "Jami, so'm"],
    "ru": ["Статья расходов", "Количество", "Цена за ед., сум", "Итого, сум"],
    "en": ["Cost item", "Quantity", "Unit price, so'm", "Total, so'm"],
}

_TIMELINE_COLUMNS = {
    "uz": ["Bosqich", "Muddati", "Mas'ul", "Kutilayotgan natija"],
    "ru": ["Этап", "Срок", "Ответственный", "Ожидаемый результат"],
    "en": ["Stage", "Duration", "Responsible", "Expected result"],
}

_RISK_COLUMNS = {
    "uz": ["Xavf", "Ehtimolligi", "Ta'siri", "Oldini olish chorasi"],
    "ru": ["Риск", "Вероятность", "Влияние", "Меры предотвращения"],
    "en": ["Risk", "Likelihood", "Impact", "Mitigation"],
}

_MARKETING_COLUMNS = {
    "uz": ["Targ'ibot kanali", "Byudjet, so'm", "Qamrov", "Konversiya",
           "Mijozlar", "1 mijoz narxi, so'm"],
    "ru": ["Канал продвижения", "Бюджет, сум", "Охват", "Конверсия",
           "Клиенты", "Цена 1 клиента, сум"],
    "en": ["Channel", "Budget, so'm", "Reach", "Conversion",
           "Customers", "Cost per customer, so'm"],
}

_COSTS_COLUMNS = {
    "uz": ["Chiqim moddasi", "Turi", "Yillik summa, so'm", "Ulushi"],
    "ru": ["Статья расходов", "Тип", "Сумма за год, сум", "Доля"],
    "en": ["Cost item", "Type", "Annual amount, so'm", "Share"],
}

_CASHFLOW_COLUMNS = {
    "uz": ["Davr", "Kirim", "Chiqim", "Sof oqim", "To'plangan oqim"],
    "ru": ["Период", "Поступления", "Расходы", "Чистый поток", "Накопленный поток"],
    "en": ["Period", "Inflow", "Outflow", "Net flow", "Cumulative flow"],
}

_BREAKEVEN_COLUMNS = {
    "uz": ["Ko'rsatkich", "Qiymati"],
    "ru": ["Показатель", "Значение"],
    "en": ["Indicator", "Value"],
}

# Zararsizlik jadvalining satrlari: birinchi to'rttasi berilgan, qolgani
# hisoblangan. Tartib hisob mantiqini takrorlaydi.
_BREAKEVEN_ROWS = {
    "uz": ["Doimiy xarajat (yillik)", "Bir birlik sotish narxi",
           "Bir birlik o'zgaruvchi xarajati", "Marjinal daromad (birlikka)",
           "Zararsizlik hajmi", "Zararsizlik tushumi", "Rejadagi hajm",
           "Xavfsizlik zaxirasi"],
    "ru": ["Постоянные затраты (в год)", "Цена реализации единицы",
           "Переменные затраты на единицу", "Маржинальный доход (на единицу)",
           "Безубыточный объём", "Безубыточная выручка", "Планируемый объём",
           "Запас финансовой прочности"],
    "en": ["Fixed costs (annual)", "Selling price per unit",
           "Variable cost per unit", "Contribution margin per unit",
           "Break-even volume", "Break-even revenue", "Planned volume",
           "Safety margin"],
}

_FORECAST_COLUMNS = {
    "uz": ["Davr", "Prognoz qiymati", "Eng past", "Eng yuqori", "O'sish"],
    "ru": ["Период", "Прогноз", "Минимум", "Максимум", "Рост"],
    "en": ["Period", "Forecast", "Low", "High", "Growth"],
}

_TOTAL_WORD = {"uz": "JAMI", "ru": "ИТОГО", "en": "TOTAL"}
_MONTH_WORD = {"uz": "oy", "ru": "мес.", "en": "month"}
_FIXED_WORD = {"uz": "doimiy", "ru": "постоянный", "en": "fixed"}
_VARIABLE_WORD = {"uz": "o'zgaruvchi", "ru": "переменный", "en": "variable"}


# ───────────────────────────────────────────────── normalizatsiya + jadvallar
#
# Har funksiya ikki ishni bajaradi: ma'lumotni chizuvchi kutgan holga
# keltiradi (joyida, `data` ichida) va jadvalni qaytaradi.

def _budget(data: dict, language: str) -> Optional[dict]:
    """Smeta: miqdor × birlik narxi = summa, oxirida yig'indi satri."""
    items = [item for item in (data.get("items") or []) if _text(item.get("name"))]
    if not items:
        return None

    rows = []
    total = 0.0
    for item in items:
        quantity = number(item.get("quantity"))
        unit_price = number(item.get("unit_price"))
        # Model miqdor va narxni bermasa, tayyor summadan orqaga qaytamiz:
        # eski javob shakli ham ishlashda davom etadi.
        amount = quantity * unit_price if quantity and unit_price else number(item.get("amount"))
        if amount <= 0:
            continue
        item["amount"] = amount          # diagramma shu maydonni o'qiydi
        total += amount

        unit = _text(item.get("unit"))
        quantity_cell = f"{_decimal(quantity)} {unit}".strip() if quantity else (unit or "1")
        rows.append([
            _text(item.get("name")),
            quantity_cell,
            _money(unit_price) if unit_price else _money(amount),
            _money(amount),
        ])

    if not rows:
        return None
    rows.append([_TOTAL_WORD.get(language, _TOTAL_WORD["uz"]), "", "", _money(total)])
    data["total"] = total
    return {"headers": _columns(_BUDGET_COLUMNS, language), "rows": rows,
            "last_row_bold": True}


def _timeline(data: dict, language: str) -> Optional[dict]:
    """Bosqichlar jadvali — muddat boshlanish va davomiylikdan hisoblanadi."""
    stages = [s for s in (data.get("stages") or []) if _text(s.get("name"))]
    if not stages:
        return None

    month = _MONTH_WORD.get(language, _MONTH_WORD["uz"])
    rows = []
    for stage in stages:
        start = int(number(stage.get("start")))
        duration = max(1, int(number(stage.get("duration")) or 1))
        first, last = start + 1, start + duration
        span = f"{first}-{month}" if first == last else f"{first}–{last}-{month}"
        rows.append([
            _text(stage.get("name")),
            span,
            _text(stage.get("owner")) or "—",
            _text(stage.get("result")) or "—",
        ])
    return {"headers": _columns(_TIMELINE_COLUMNS, language), "rows": rows}


def _risks(data: dict, language: str) -> Optional[dict]:
    rows = [
        [
            _text(risk.get("name")),
            _text(risk.get("likelihood")) or "—",
            _text(risk.get("impact")) or "—",
            _text(risk.get("mitigation")) or "—",
        ]
        for risk in (data.get("risks") or [])
        if _text(risk.get("name"))
    ]
    if not rows:
        return None
    return {"headers": _columns(_RISK_COLUMNS, language), "rows": rows}


def _marketing(data: dict, language: str) -> Optional[dict]:
    """Kanallar jadvali — bir mijoz narxi byudjet ÷ mijozlar soni."""
    channels = [c for c in (data.get("channels") or []) if _text(c.get("name"))]
    if not channels:
        return None

    rows = []
    budget_total = customers_total = 0.0
    for channel in channels:
        budget = number(channel.get("budget"))
        customers = number(channel.get("customers"))
        budget_total += budget
        customers_total += customers
        per_customer = budget / customers if customers else 0.0
        channel["cost_per_customer"] = per_customer
        rows.append([
            _text(channel.get("name")),
            _money(budget),
            _money(number(channel.get("reach"))),
            _text(channel.get("conversion")) or "—",
            _money(customers),
            _money(per_customer) if per_customer else "—",
        ])

    average = budget_total / customers_total if customers_total else 0.0
    rows.append([
        _TOTAL_WORD.get(language, _TOTAL_WORD["uz"]),
        _money(budget_total), "", "", _money(customers_total),
        _money(average) if average else "—",
    ])
    data["budget_total"] = budget_total
    data["customers_total"] = customers_total
    data["cost_per_customer"] = average
    return {"headers": _columns(_MARKETING_COLUMNS, language), "rows": rows,
            "last_row_bold": True}


def _costs(data: dict, language: str) -> Optional[dict]:
    """Chiqim tarkibi — ulush foizi summalardan hisoblanadi, modeldan emas."""
    items = [i for i in (data.get("items") or []) if _text(i.get("name"))]
    amounts = [(item, number(item.get("amount"))) for item in items]
    amounts = [(item, amount) for item, amount in amounts if amount > 0]
    if not amounts:
        return None

    total = sum(amount for _item, amount in amounts)
    fixed_word = _FIXED_WORD.get(language, _FIXED_WORD["uz"])
    variable_word = _VARIABLE_WORD.get(language, _VARIABLE_WORD["uz"])

    rows = []
    fixed_total = 0.0
    for item, amount in amounts:
        is_fixed = _is_fixed(item.get("kind"))
        if is_fixed:
            fixed_total += amount
        item["amount"] = amount
        item["fixed"] = is_fixed
        item["share"] = amount / total * 100
        rows.append([
            _text(item.get("name")),
            fixed_word if is_fixed else variable_word,
            _money(amount),
            _percent(item["share"]),
        ])

    rows.append([_TOTAL_WORD.get(language, _TOTAL_WORD["uz"]), "",
                 _money(total), "100%"])
    data["total"] = total
    data["fixed_total"] = fixed_total
    data["variable_total"] = total - fixed_total
    return {"headers": _columns(_COSTS_COLUMNS, language), "rows": rows,
            "last_row_bold": True}


_FIXED_HINTS = ("doimiy", "постоян", "fixed", "qat'iy", "qatiy")


def _is_fixed(kind) -> bool:
    return any(hint in _text(kind).lower() for hint in _FIXED_HINTS)


def _cashflow(data: dict, language: str) -> Optional[dict]:
    """Pul oqimi — sof va to'plangan oqim kirim-chiqimdan hisoblanadi."""
    periods = [p for p in (data.get("periods") or []) if _text(p.get("period"))]
    if not periods:
        return None

    rows = []
    cumulative = 0.0
    for entry in periods:
        income = number(entry.get("income"))
        expense = number(entry.get("expense"))
        net = income - expense
        cumulative += net
        entry["income"] = income
        entry["expense"] = expense
        entry["net"] = net
        entry["cumulative"] = cumulative
        rows.append([
            _text(entry.get("period")),
            _money(income),
            _money(expense),
            _money(net),
            _money(cumulative),
        ])

    # Qaysi davrda to'plangan oqim musbatga o'tadi — qoplanish muddati.
    payback = next((entry["period"] for entry in periods
                    if number(entry.get("cumulative")) >= 0), "")
    data["payback_period"] = payback
    return {"headers": _columns(_CASHFLOW_COLUMNS, language), "rows": rows}


def _breakeven(data: dict, language: str) -> Optional[dict]:
    """Zararsizlik hisobi jadvali — berilgan to'rt son va ulardan chiqadigani.

    Ustoz zararsizlik nuqtasini tekshirganda avval nimadan hisoblanganini
    qidiradi, shuning uchun kirish qiymatlari ham jadvalda turadi.
    """
    fixed = number(data.get("fixed"))
    price = number(data.get("price"))
    variable = number(data.get("variable"))
    if fixed <= 0 or price <= variable:
        return None

    margin = price - variable
    point = fixed / margin
    planned = number(data.get("planned"))
    money = _text(data.get("money_unit"))
    unit = _text(data.get("unit"))

    labels = _columns(_BREAKEVEN_ROWS, language)
    values = [
        f"{_decimal(fixed, 2)} {money}".strip(),
        f"{_decimal(price, 3)} {money}".strip(),
        f"{_decimal(variable, 3)} {money}".strip(),
        f"{_decimal(margin, 3)} {money}".strip(),
        f"{_money(point)} {unit}".strip(),
        f"{_decimal(point * price, 1)} {money}".strip(),
    ]
    if planned:
        values.append(f"{_money(planned)} {unit}".strip())
        values.append(_percent((planned - point) / planned * 100))
    else:
        labels = labels[:len(values)]

    data["breakeven_point"] = point
    data["breakeven_revenue"] = point * price
    data["margin_per_unit"] = margin
    return {"headers": _columns(_BREAKEVEN_COLUMNS, language),
            "rows": [[label, value] for label, value in zip(labels, values)]}


def _forecast(data: dict, language: str) -> Optional[dict]:
    """Prognoz jadvali — o'sish foizi qo'shni davrlardan hisoblanadi."""
    points = [p for p in (data.get("points") or []) if _text(p.get("period"))]
    if len(points) < 2:
        return None

    unit = _text(data.get("unit"))
    rows = []
    previous = None
    for point in points:
        value = number(point.get("value"))
        low = number(point.get("low")) or value
        high = number(point.get("high")) or value
        growth = "—" if previous in (None, 0) else _percent((value - previous) / previous * 100)
        rows.append([
            _text(point.get("period")),
            f"{_decimal(value, 1)} {unit}".strip(),
            _decimal(low, 1),
            _decimal(high, 1),
            growth,
        ])
        previous = value

    first, last = number(points[0].get("value")), number(points[-1].get("value"))
    if first:
        data["total_growth"] = (last - first) / first * 100
    return {"headers": _columns(_FORECAST_COLUMNS, language), "rows": rows}


_BUILDERS = {
    ARTIFACT_BREAKEVEN: _breakeven,
    ARTIFACT_FORECAST: _forecast,
    ARTIFACT_BUDGET: _budget,
    ARTIFACT_TIMELINE: _timeline,
    ARTIFACT_RISKS: _risks,
    ARTIFACT_MARKETING: _marketing,
    ARTIFACT_COSTS: _costs,
    ARTIFACT_CASHFLOW: _cashflow,
}


def derive(artifact: str, data: dict, language: str) -> Optional[dict]:
    """Artefakt ma'lumotini normallashtiradi va jadvalini qaytaradi.

    `data` joyida o'zgaradi: hisoblangan summa, ulush va sof oqim diagramma
    uchun ham kerak. Jadval qurilmasa `None` qaytadi va bo'lim faqat
    diagramma bilan chiqadi — bu xato emas.
    """
    builder = _BUILDERS.get(artifact)
    if builder is None or not isinstance(data, dict):
        return None
    try:
        return builder(data, language)
    except Exception as e:
        logger.warning("Jadval qurilmadi (%s): %s", artifact, e)
        return None
