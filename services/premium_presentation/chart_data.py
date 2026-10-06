"""Diagramma ma'lumotlari — FAQAT Claude'dan, haqiqiy raqamlar bilan.

Ilgari slaydni yozgan model diagramma raqamlarini o'zi to'qirdi: har mavzuda diagramma
chiqar, lekin raqamlar real emas edi. Endi tartib boshqacha:

1. Reja diagramma deb belgilagan slayd uchun Claude'dan (alohida chaqiruv) ma'lumot so'raladi:
   haqiqiy raqamlar, manbasi va yili bilan. Boshqa provayderlarga o'tilmaydi (`config`).
2. Ishonchli ma'lumot bo'lmasa — diagramma qo'yilmaydi, slayd boshqa blok bilan ochiladi.
3. Slayd yozuvchi modelga tayyor ma'lumot beriladi (u faqat izoh yozadi), keyin kod
   diagramma raqamlarini Claude bergan qiymatlarga majburan almashtiradi.
"""
import concurrent.futures
import html
import logging
import math
import re
from typing import Dict, List, Optional

from . import deck_logic, llm_client

log = logging.getLogger(__name__)

SOURCE_LABEL = {
    "uz": "Manba:", "ru": "Источник:", "en": "Source:",
    "kk": "Дереккөз:", "uz-cyrl": "Манба:",
}
_APPROX = {"uz": "taxminiy", "ru": "оценка", "en": "estimate", "kk": "болжам", "uz-cyrl": "тахминий"}
_KIND = {"line": "line", "chiziqli": "line", "bar": "bar", "ustunli": "bar",
         "donut": "donut", "halqa": "donut", "pie": "donut"}
_KIND_HINT = {"halqa": "donut (butunning ulushlari)", "chiziqli": "line (vaqt bo'yicha o'zgarish)",
              "ustunli": "bar (qiymatlarni solishtirish)"}
# Rejada diagramma bo'lmagan slaydga model o'zi yozib qo'ygan "yetim" diagramma.
_CHART_BLOCK = re.compile(
    r'<div\b[^>]*\bclass\s*=\s*(["\'])[^"\']*(?<![-\w])chart(?![-\w])[^"\']*\1[^>]*>\s*</div>',
    re.IGNORECASE | re.DOTALL)
MAX_WORKERS = 3
_YEAR = re.compile(r"^\D*((?:19|20)\d{2})\D*$")

SYSTEM = (
    "Sen statistik ma'lumotlar bo'yicha tahlilchisan: taqdimot slaydidagi diagramma uchun "
    "HAQIQIY raqamlarni berasan. Javobing faqat JSON."
)


def _prompt(topic: str, title: str, brief: str, kind: str, language: str) -> str:
    from services import timeframe
    return (
        f'Taqdimot mavzusi: "{topic}"\n'
        f'Slayd sarlavhasi: "{title}"\n'
        f"Slayd mazmuni: {brief}\n"
        f"Taxminiy diagramma turi: {_KIND_HINT.get(kind, kind)}\n\n"
        "Shu slayd uchun BITTA diagramma ma'lumotini ber.\n"
        "• Raqamlar rasmiy yoki taniqli manbalardan bo'lsin: milliy statistika organlari "
        "(O'zbekiston Statistika agentligi va h.k.), Jahon banki, BMT va uning agentliklari, XVF, "
        "OECD, Eurostat, yetakchi tadqiqot markazlari. Har qiymat sen bilgan haqiqiy ma'lumotga mos "
        "kelsin; aniq raqamni bilmasang yaxlitlangan qiymat ber va `approx` ni true qil.\n"
        "• Eng YANGI yillarni ol — sening bilimingdagi oxirgi yilgacha. Kelajak yillar faqat "
        "rasmiy prognoz bo'lsa beriladi va `forecast` true bo'ladi.\n"
        "• Mavzu O'zbekiston bilan bog'liq bo'lsa — O'zbekiston ma'lumoti; aks holda mavzuning "
        "o'z qamrovi (dunyo, mintaqa, soha).\n"
        "• Bu mavzuda ishonchli, tekshirsa bo'ladigan raqam yo'q bo'lsa `ok` ni false qil va "
        "`reason` ga sababini yoz: bunday slayd matn bilan ochiladi. Raqamni o'ylab topma.\n"
        "• 3-7 ta yorliq; ko'pi bilan 3 ta qator; bir diagrammada bitta birlik. `donut` uchun bitta "
        "qator, qiymatlar yig'indisi ≈ 100 (%). Qiymatlar oddiy sonlar.\n"
        f"{timeframe.year_rule(language)}\n"
        f"TIL TALABI (yorliqlar, qator nomlari, birlik, manba): {llm_client._language_instruction(language)}\n"
        'Faqat JSON: {"ok": true, "kind": "line|bar|donut", "labels": ["2019", "2020"], '
        '"series": [{"name": "...", "values": [1.5, 2.0]}], "unit": "%", "xlabel": "Yil", '
        '"source": "Tashkilot nomi, yil", "approx": false, "forecast": false, "reason": ""}'
    )


def _number(value) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", ".").replace(" ", "").replace("%", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def validate(raw: dict, language: str = "uz") -> Optional[Dict]:
    """Claude javobini tekshirib, tayyor ma'lumotga aylantiradi (yaroqsiz bo'lsa None)."""
    from services import timeframe
    if not isinstance(raw, dict) or raw.get("ok") is not True:
        return None
    kind = _KIND.get(str(raw.get("kind") or "bar").strip().lower(), "bar")
    labels = [str(x).strip() for x in (raw.get("labels") or []) if str(x).strip()]
    series = []
    for row in (raw.get("series") or [])[:3]:
        if not isinstance(row, dict):
            continue
        values = [_number(v) for v in (row.get("values") or [])]
        if len(values) != len(labels) or any(v is None for v in values):
            return None
        series.append((str(row.get("name") or "").strip(), values))
    source = re.sub(r"\s+", " ", str(raw.get("source") or "")).strip()
    if not (2 <= len(labels) <= 10) or not series or not source:
        return None
    if len(series) > 1 and kind == "donut":
        series = series[:1]
    if kind == "donut":
        values = series[0][1]
        if len(values) < 2 or any(v < 0 for v in values) or not 90 <= sum(values) <= 110:
            return None
    # Kelajak yillari faqat rasmiy prognoz bo'lsa.
    future = [m for m in (_YEAR.match(label) for label in labels)
              if m and int(m.group(1)) > timeframe.current_year()]
    if future and raw.get("forecast") is not True:
        return None
    if all(max(abs(v) for v in values) == 0 for _, values in series):
        return None
    unit = str(raw.get("unit") or "").strip()[:24]
    return {"kind": kind, "labels": labels, "series": series, "unit": unit,
            "xlabel": str(raw.get("xlabel") or "").strip()[:24],
            "source": source[:90], "approx": bool(raw.get("approx")),
            "forecast": bool(raw.get("forecast")),
            "label": SOURCE_LABEL.get(language, SOURCE_LABEL["uz"]), "lang": language}


def research(topic: str, title: str, brief: str, kind: str, language: str = "uz") -> Optional[Dict]:
    """Claude'dan bitta diagramma uchun haqiqiy ma'lumot so'raydi (bo'lmasa None)."""
    try:
        raw = llm_client._call_openrouter(SYSTEM, _prompt(topic, title, brief, kind, language),
                                          temperature=0.2, max_tokens=1500, kind="chart")
    except llm_client.NoCredits:
        raise
    except Exception as exc:
        log.warning("Diagramma ma'lumoti olinmadi (%s): %s", title, exc)
        return None
    data = validate(raw, language)
    if data is None:
        log.info("«%s» uchun ishonchli diagramma ma'lumoti yo'q: %s", title,
                 (raw or {}).get("reason") if isinstance(raw, dict) else "yaroqsiz javob")
    return data


# ───────────────────────────────────────────────────────────── HTML blok

def _attr(value: str) -> str:
    return html.escape(value, quote=True)


def block(data: Dict) -> str:
    """Tekshirilgan ma'lumotdan `.chart` bloki (uni `deck_charts` chizadi)."""
    series = "|".join(f"{name}: " + ",".join(_fmt(v) for v in values) if name
                      else ",".join(_fmt(v) for v in values) for name, values in data["series"])
    source = f'{data["label"]} {data["source"]}'
    if data.get("approx"):
        source += f' ({_APPROX.get(data.get("lang"), _APPROX["uz"])})'
    parts = [f'class="chart"', f'data-kind="{data["kind"]}"',
             f'data-labels="{_attr(",".join(data["labels"]))}"',
             f'data-series="{_attr(series)}"']
    if data.get("unit"):
        parts.append(f'data-unit="{_attr(data["unit"])}"')
    if data.get("xlabel") and data["kind"] != "donut":
        parts.append(f'data-xlabel="{_attr(data["xlabel"])}"')
    parts.append(f'data-source="{_attr(source)}"')
    return "<div " + " ".join(parts) + "></div>"


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.4g}"


def note_for(data: Dict) -> str:
    """Slayd yozuvchi modelga beriladigan tayyor ma'lumot tavsifi."""
    rows = "; ".join(f"{name or 'qiymat'}: " + ", ".join(f"{l}={_fmt(v)}" for l, v in zip(data["labels"], values))
                     for name, values in data["series"])
    extra = " Raqamlar taxminiy (yaxlitlangan)." if data.get("approx") else ""
    extra += " Bu rasmiy prognoz." if data.get("forecast") else ""
    return (f"TAYYOR DIAGRAMMA (Claude bergan HAQIQIY ma'lumot): {rows}"
            f"{' ' + data['unit'] if data.get('unit') else ''}. Manba: {data['source']}.{extra} "
            f"Slaydda aynan shu blokni qo'ying (raqamlarni o'zgartirmang): {block(data)} "
            "va ostiga shu raqamlardan kelib chiqadigan 2-4 gaplik izoh yozing: nima ko'rsatilgani, "
            "eng muhim o'zgarish va xulosa.")


# ──────────────────────────────────────────────────────────── reja bosqichi

_FALLBACK = "ikki_ustun"


def ground(outline: List[Dict], topic: str, language: str = "uz", level: int = 2,
           researcher=None) -> List[Dict]:
    """Rejadagi har diagramma slayd uchun Claude'dan haqiqiy ma'lumot olinadi.

    Ma'lumot topilsa — `item["chart"]` va `item["chart_note"]` (yozuvchi modelga ko'rsatma);
    topilmasa — slayd diagrammasiz kategoriyaga qaytariladi (`was` yoki `ikki_ustun`).
    """
    researcher = researcher or research
    indices = [i for i, item in enumerate(outline) if item.get("category") == "diagramma"]
    if not indices:
        return outline

    def job(index: int):
        item = outline[index]
        kind = item.get("chart_kind") or deck_logic.chart_kind_for(
            f"{item['title']} {item['brief']}", index)
        return index, researcher(topic, item["title"], item["brief"], kind, language)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for index, data in pool.map(job, indices):
            item = outline[index]
            if data:
                item["chart"] = data
                item["chart_note"] = note_for(data)
                log.info("%d-slayd diagrammasi: haqiqiy ma'lumot (%s)", index + 1, data["source"])
            else:
                item["category"] = item.pop("was", None) or _FALLBACK
                item.pop("chart_kind", None)
                log.info("%d-slayd: ishonchli ma'lumot yo'q — diagrammasiz (%s)",
                         index + 1, item["category"])
    return outline


# ───────────────────────────────────────────────────────── slayd bosqichi

def enforce(body: str, item: Optional[Dict]) -> str:
    """Slayddagi diagramma raqamlari faqat Claude bergan ma'lumot bo'lsin.

    Rejada ma'lumot bor: slayddagi birinchi blok tayyor blokka almashadi, ortiqchalari tushadi.
    Rejada ma'lumot yo'q: model o'zi yozib qo'ygan diagramma (to'qilgan raqamli) olib tashlanadi.
    """
    if not body:
        return body
    data = (item or {}).get("chart")
    found = list(_CHART_BLOCK.finditer(body))
    if not found:
        return body
    out, pos = [], 0
    for number, match in enumerate(found):
        out.append(body[pos:match.start()])
        if data and number == 0:
            out.append(block(data))
        pos = match.end()
    out.append(body[pos:])
    return "".join(out)
