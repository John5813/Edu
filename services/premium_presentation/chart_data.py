"""Diagramma ma'lumotlari — admin tanlagan AI dan, haqiqiy raqamlar bilan.

Ilgari slaydni yozgan model diagramma raqamlarini o'zi to'qirdi: har mavzuda diagramma
chiqar, lekin raqamlar real emas edi. Endi tartib boshqacha:

1. Reja diagramma deb belgilagan slayd uchun AI dan (alohida chaqiruv) ma'lumot so'raladi:
   haqiqiy raqamlar, manbasi va yili bilan. Boshqa provayderlarga o'tilmaydi (`config`).
2. Ishonchli ma'lumot bo'lmasa — diagramma qo'yilmaydi, slayd boshqa blok bilan ochiladi.
3. Slayd yozuvchi modelga tayyor ma'lumot beriladi (u faqat izoh yozadi), keyin kod
   diagramma raqamlarini AI bergan qiymatlarga majburan almashtiradi.
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
# AI ishonchli ma'lumot bermagan diagramma: oddiy model tuzgan namunaviy raqamlar halol belgilanadi.
ILLUSTRATIVE = {"uz": "Shartli misol", "ru": "Условный пример", "en": "Illustrative example",
                "kk": "Шартты мысал", "uz-cyrl": "Шартли мисол"}
FALLBACK_NOTE = (
    "Bu mavzu uchun ishonchli statistik ma'lumot topilmadi, shuning uchun diagramma uchun mavzuga mos, "
    "tushunchani ko'rsatuvchi NAMUNAVIY ma'lumotni o'zingiz tuzing (3-6 yorliq, bitta birlik; haqiqiy "
    "statistika deb ko'rsatmang, manba yoki 'tadqiqotlar ko'rsatdi' yozmang) va slaydning izohi oxiriga "
    "«Shartli misol.» deb yozing. Diagramma bloki slaydda bo'lishi shart.")
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
        "• 3-7 ta yorliq; har yorliq qisqa — 1-3 so'z (\"Qadimgi Rim\", \"2021\"), izoh qavs ichida emas; "
        "ko'pi bilan 3 ta qator; bir diagrammada bitta birlik. `donut` uchun bitta "
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
    """AI javobini tekshirib, tayyor ma'lumotga aylantiradi (yaroqsiz bo'lsa None)."""
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
    """Tanlangan AI dan bitta diagramma uchun haqiqiy ma'lumot so'raydi (bo'lmasa None)."""
    try:
        raw = llm_client._call_openrouter(SYSTEM, _prompt(topic, title, brief, kind, language),
                                          temperature=0.2, max_tokens=1500, kind="text")
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
    return (f"TAYYOR DIAGRAMMA (AI bergan HAQIQIY ma'lumot): {rows}"
            f"{' ' + data['unit'] if data.get('unit') else ''}. Manba: {data['source']}.{extra} "
            f"Slaydda aynan shu blokni qo'ying (raqamlarni o'zgartirmang): {block(data)} "
            "va ostiga shu raqamlardan kelib chiqadigan 2-4 gaplik izoh yozing: nima ko'rsatilgani, "
            "eng muhim o'zgarish va xulosa.")


# ──────────────────────────────────────────────────────────── reja bosqichi

_FALLBACK = "ikki_ustun"


def ground(outline: List[Dict], topic: str, language: str = "uz", level: int = 2,
           researcher=None) -> List[Dict]:
    """Rejadagi har diagramma slayd uchun AI dan haqiqiy ma'lumot olinadi.

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
            elif item.get("was"):
                # Kvota bo'yicha qo'shilgan diagramma: ma'lumot yo'q — slayd o'z kategoriyasida qoladi.
                item["category"] = item.pop("was")
                item.pop("chart_kind", None)
                log.info("%d-slayd: ishonchli ma'lumot yo'q — diagrammasiz (%s)",
                         index + 1, item["category"])
            else:
                # Reja o'zi diagramma deb belgilagan slayd: diagramma yo'qolmasin — oddiy model namunaviy
                # ma'lumot tuzadi, u "Shartli misol" deb belgilanadi.
                item["chart_fallback"] = True
                item["chart_note"] = FALLBACK_NOTE
                log.info("%d-slayd: AI ma'lumot bermadi — namunaviy diagramma (Shartli misol)", index + 1)
    return outline


# ───────────────────────────────────────────────────────── slayd bosqichi

_DATA_SOURCE = re.compile(r'\sdata-source\s*=\s*(["\']).*?\1', re.IGNORECASE | re.DOTALL)


def _label_illustrative(tag: str, language: str) -> str:
    """Model tuzgan diagramma blokiga "Shartli misol" belgisini qo'yadi (eski manba o'chadi)."""
    tag = _DATA_SOURCE.sub("", tag)
    label = ILLUSTRATIVE.get(language, ILLUSTRATIVE["uz"])
    return re.sub(r"\s*>\s*</div>\s*$", f' data-source="{_attr(label)}"></div>', tag, count=1) \
        if re.search(r">\s*</div>\s*$", tag) else tag


_LEAD_END = re.compile(r'(<p\b[^>]*\bclass\s*=\s*["\'][^"\']*\blead\b[^"\']*["\'][^>]*>.*?</p>)',
                       re.IGNORECASE | re.DOTALL)


def _is_cover(body: str) -> bool:
    return bool(re.search(r'<section\b[^>]*class\s*=\s*["\'][^"\']*\bdark\b', body, re.IGNORECASE))


def _insert(body: str, chart: str) -> str:
    """Diagramma blokini bosh gapdan keyin (bo'lmasa `body` boshiga) qo'yadi."""
    found = _LEAD_END.search(body)
    if found:
        return body[:found.end()] + chart + body[found.end():]
    opening = deck_logic._BODY_OPEN.search(body)
    if opening:
        return body[:opening.end()] + chart + body[opening.end():]
    return body


def enforce(body: str, item: Optional[Dict], language: str = "uz") -> str:
    """Slayddagi diagramma raqamlari: AI bergan ma'lumot yoki halol belgilangan namuna.

    Rejada AI ma'lumoti bor: slayddagi birinchi blok tayyor blokka almashadi, ortiqchalari tushadi.
    Ma'lumot yo'q: model tuzgan diagramma o'chirilmaydi (izohi unga tayanadi), balki "Shartli misol"
    deb belgilanadi — haqiqiy statistika kabi ko'rinmaydi.
    """
    if not body:
        return body
    data = (item or {}).get("chart")
    found = list(_CHART_BLOCK.finditer(body))
    if not found:
        # Model diagramma yozmadi (yoki qayta yozish qabul qilinmadi), lekin AI ma'lumot bergan:
        # blok kod tomonidan qo'yiladi — izohi "yuqoridagi diagramma" deb turib, diagramma yo'q qolmasin.
        return _insert(body, block(data)) if data and not _is_cover(body) else body
    out, pos = [], 0
    for number, match in enumerate(found):
        out.append(body[pos:match.start()])
        if data:
            if number == 0:
                out.append(block(data))
        else:
            out.append(_label_illustrative(match.group(0), language))
        pos = match.end()
    out.append(body[pos:])
    return "".join(out)


# ──────────────────────────────────────── rejasiz yozilgan ("yetim") diagrammalar

def strays(slides: List[str], outline: List[Dict]) -> List[int]:
    """Diagramma yozilgan, lekin AI ma'lumoti hali yo'q va urinilmagan slaydlar."""
    result = []
    for index, body in enumerate(slides):
        item = outline[index] if index < len(outline) else None
        if index == 0 or item is None or item.get("chart") or item.get("chart_tried"):
            continue
        if _CHART_BLOCK.search(body or ""):
            result.append(index)
    return result


def research_strays(slides: List[str], outline: List[Dict], topic: str, language: str = "uz",
                    researcher=None) -> List[int]:
    """Yetim diagrammalar uchun AI dan ma'lumot so'raydi; topilganlar indekslari qaytadi."""
    researcher = researcher or research
    todo = strays(slides, outline)
    if not todo:
        return []

    def job(index: int):
        item = outline[index]
        title = deck_logic.title_of(slides[index]) or item.get("title", "")
        brief = deck_logic.plain(slides[index])[:400] or item.get("brief", "")
        return index, researcher(topic, title, brief, "", language)

    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for index, data in pool.map(job, todo):
            item = outline[index]
            item["chart_tried"] = True
            if data:
                item["chart"], item["chart_note"] = data, note_for(data)
                found.append(index)
                log.info("%d-slayddagi diagramma uchun AI haqiqiy ma'lumot berdi", index + 1)
            else:
                item["chart_fallback"] = True
    return found
