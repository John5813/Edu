"""Chuqur tadqiqot: 3D taqdimotdan oldin mavzu va mijoz savollari bo'yicha internetdan yangi, manbali ma'lumot.

AI faqat o'z xotirasidan yozganda raqamlar eskirgan (bilim chegarasigacha) va manbasiz bo'lardi, mijoz yozgan
savollar esa ba'zan yoritilmay qolardi. Endi qo'lda puxta tayyorlangan taqdimot kabi:

1. `savollar()` — AI mavzu va mijoz istaklaridan bo'limlar tuzadi: mijoz so'ragan HAR savol — alohida bo'lim
   (o'sha tartibda), keyin mavzuning asosiy qismlari; har bo'limga 1-2 qidiruv so'rovi (inglizcha — manba ko'p;
   O'zbekiston ma'lumoti uchun — o'zbek/rus tilida ham);
2. `qidir()` — Brave Search (bot rasm qidirishda ishlatadigan kalitlar): har so'rovga bir necha natija — sarlavha,
   matn parchalari, sana, manzil;
3. `faktlar()` — AI parchalardan fakt varaqasi va diagramma qatorlarini oladi (manbasi bilan). Kod har raqamni
   parchalarda bormi deb tekshiradi: parchada yo'q raqamli fakt yoki qator tashlab yuboriladi (AI to'qimasin).

Natija `reja.plan` ga beriladi: har bo'lim kamida bitta slayd, raqamlar shu faktlardan, diagrammalar shu
qatorlardan, izohlarda manba. Brave kaliti yoki AI ishlamasa — None: taqdimot avvalgidek yoziladi.
`KAT3D_TADQIQOT=0` — o'chirish.
"""
import html
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Sequence

from . import ai

log = logging.getLogger(__name__)

ON = os.getenv("KAT3D_TADQIQOT", "1") != "0"
BRAVE_WEB = "https://api.search.brave.com/res/v1/web/search"
PER_QUERY = 6                     # har so'rovga natija
MAX_QUERIES = 10
MAX_FACTS = 36
MAX_SERIES = 4
CORPUS_LIMIT = 24000              # AI ga beriladigan parchalar (belgi)

SECTIONS_SYSTEM = """You plan the research for an educational presentation. Split the work into sections:
first EVERY question or wish the client wrote (one section each, in the client's order, keep their meaning),
then the core parts of the topic that are still missing (definition and types, current statistics for the last
2-3 years, how it works, problems and solutions). If the topic has statistics, add a section with data for
Uzbekistan (compared with the world or neighbours). 4-8 sections in total.
For each section write 1-2 web search queries: precise, factual, in English (more sources); for Uzbekistan data
also one query in Russian or Uzbek. Ask for the latest data ("2025", "latest", "annual report").
Return ONLY JSON: {"sections": [{"title": "short section name in the client's language",
"queries": ["...", "..."]}]}"""

FACTS_SYSTEM = """You extract facts for an educational presentation from web search snippets. Use ONLY what the
snippets say: copy numbers, years and names exactly; never add numbers from memory. Prefer the newest data and
official sources (international organisations, governments, statistics agencies, companies' own reports). Skip
ads, opinions and doubtful pages.
Write each fact as one complete sentence in the client's language with its number and year, and the source
(organisation or site name) and URL. Group facts by section index. Up to {facts} facts.
"series": data for charts — only when the snippets give the SAME measure for 3-12 periods, countries or types
(e.g. growth % by year or month, share by region). Labels short (≤ 20 chars), values plain numbers.
Up to {series} series.
Return ONLY JSON: {{"facts": [{{"section": 0, "text": "...", "source": "IATA", "url": "https://..."}}],
"series": [{{"section": 0, "title": "...", "labels": ["..."], "values": [1.5], "unit": "%", "source": "...",
"url": "https://..."}}]}}"""


def enabled() -> bool:
    if not ON:
        return False
    try:
        from services import brave_keys

        return bool(brave_keys.current())
    except Exception:                         # noqa: BLE001
        return False


# ───────────────────────────────────────────── 1. bo'limlar va so'rovlar

def _fallback_sections(topic: str, preferences: str) -> List[dict]:
    """AI ishlamasa: mijoz istaklari (qator, nuqta-vergul, savol belgisi bo'yicha) — bo'limlar."""
    parts = [p.strip(" -•.") for p in re.split(r"[\n;?]+", preferences or "") if len(p.strip()) > 8][:6]
    sections = [{"title": p[:60], "queries": [f"{topic} {p}"[:150]]} for p in parts]
    return sections or [{"title": topic[:60], "queries": [topic, f"{topic} statistics 2025"]}]


def savollar(topic: str, preferences: str, language: str) -> List[dict]:
    user = f"Topic: {topic}\nClient's wishes and questions: {preferences or '(none)'}\nClient's language: {language}"
    try:
        data = ai.call_json(SECTIONS_SYSTEM, user, 1200, language=language, model=ai.SEARCH_MODEL,
                            where="3D katalog tadqiqot", temperature=0.2)
    except Exception as exc:                  # noqa: BLE001
        log.warning("3D tadqiqot: bo'limlar tuzilmadi (%s) — istaklardan", exc)
        return _fallback_sections(topic, preferences)
    out = []
    for sec in data.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        title = re.sub(r"\s+", " ", str(sec.get("title") or "")).strip()[:70]
        queries = [re.sub(r"\s+", " ", str(q)).strip()[:150] for q in (sec.get("queries") or []) if str(q).strip()]
        if title and queries:
            out.append({"title": title, "queries": queries[:2]})
    return out[:8] or _fallback_sections(topic, preferences)


# ───────────────────────────────────────────── 2. internetdan qidirish

def _lang_of(query: str) -> str:
    if re.search(r"[а-яё]", query, re.I):
        return "ru"
    return "en"


def _brave_web(query: str) -> List[dict]:
    """Brave web qidiruvi. Kalit rad etilsa (401/403/429) — navbatdagi kalit."""
    from services import brave_keys

    params = {"q": query, "count": str(PER_QUERY), "extra_snippets": "true", "safesearch": "strict",
              "search_lang": _lang_of(query)}
    url = BRAVE_WEB + "?" + urllib.parse.urlencode(params)
    tried = set()
    while True:
        key = brave_keys.take()
        if not key or key in tried:
            raise RuntimeError("Brave: ishlaydigan kalit qolmadi")
        tried.add(key)
        req = urllib.request.Request(url, headers={"Accept": "application/json", "X-Subscription-Token": key})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 429):
                brave_keys.report_failure(key, exc.code)
                continue
            raise
        out = []
        for r in ((data.get("web") or {}).get("results") or [])[:PER_QUERY]:
            text = " ".join([r.get("description") or ""] + list(r.get("extra_snippets") or []))
            text = html.unescape(re.sub(r"<[^>]+>", "", text))
            if len(text) < 40:
                continue
            out.append({"title": html.unescape(re.sub(r"<[^>]+>", "", r.get("title") or ""))[:160],
                        "url": r.get("url") or "",
                        "age": r.get("age") or r.get("page_age") or "", "text": re.sub(r"\s+", " ", text)[:1600]})
        return out


def qidir(sections: List[dict]) -> List[dict]:
    """Har bo'lim so'rovlari parallel; natija: [{"section", "title", "url", "age", "text"}] (takror manzilsiz)."""
    jobs = [(k, q) for k, sec in enumerate(sections) for q in sec["queries"]][:MAX_QUERIES]
    with ThreadPoolExecutor(max_workers=4) as pool:
        found = list(pool.map(lambda job: _safe(job[1]), jobs))
    seen, out = set(), []
    for (k, _), results in zip(jobs, found):
        for r in results:
            if r["url"] in seen:
                continue
            seen.add(r["url"])
            out.append(dict(r, section=k))
    return out


def _safe(query: str) -> List[dict]:
    try:
        return _brave_web(query)
    except Exception as exc:                  # noqa: BLE001
        log.warning("3D tadqiqot: qidiruv o'tmadi (%s): %s", query[:60], exc)
        return []


# ───────────────────────────────────────────── 3. faktlar va tekshiruv

_NUM = re.compile(r"\d[\d\s.,]*\d|\d")


def _norm_numbers(text: str) -> List[str]:
    """Matndagi raqamlar bir xil ko'rinishda: «87 461» → 87461, «3,4» → 3.4, «2 000» → 2000."""
    out = []
    for m in _NUM.findall(text or ""):
        s = m.replace(" ", "").replace(" ", "")
        if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):          # 87,461 — minglik vergul
            s = s.replace(",", "")
        s = s.replace(",", ".").rstrip(".")
        try:
            value = float(s)
        except ValueError:
            continue
        out.append(f"{value:g}")
    return out


def _scaled(numbers) -> set:
    """Parchadagi «98,000» o'zbekcha faktda «98 ming», «1,500,000» — «1,5 mln» bo'lib yozilishi mumkin."""
    out = set()
    for n in numbers:
        out.add(n)
        value = abs(float(n))
        for div in (1e3, 1e6, 1e9, 1e12):
            if value >= div:
                out.add(f"{round(value / div, 1):g}")
                out.add(f"{round(value / div, 2):g}")
    return out


def _grounded(values: Sequence, corpus_numbers: set, share: float) -> bool:
    nums = []
    for v in values:
        nums += _norm_numbers(str(v)) if not isinstance(v, (int, float)) else [f"{float(v):g}"]
    nums = [n for n in nums if n not in ("0", "1")]
    if not nums:
        return True
    hit = sum(1 for n in nums if n in corpus_numbers or n.lstrip("-") in corpus_numbers)
    return hit >= share * len(nums)


def _corpus(results: List[dict], sections: List[dict]) -> str:
    parts, size = [], 0
    for r in results:
        block = f"[{r['section']}] {r['title']} | {r['url']} | {r['age']}\n{r['text']}\n"
        if size + len(block) > CORPUS_LIMIT:
            break
        parts.append(block)
        size += len(block)
    head = "\n".join(f"Section {k}: {s['title']}" for k, s in enumerate(sections))
    return head + "\n\nSNIPPETS:\n" + "\n".join(parts)


def faktlar(topic: str, sections: List[dict], results: List[dict], language: str) -> dict:
    corpus = _corpus(results, sections)
    system = FACTS_SYSTEM.format(facts=MAX_FACTS, series=MAX_SERIES)
    user = f"Topic: {topic}\nClient's language: {ai.language_rule(language)}\n\n{corpus}"
    data = ai.call_json(system, user, 4500, language=language, model=ai.SEARCH_MODEL, where="3D katalog tadqiqot",
                        temperature=0.1)
    numbers = _scaled({n for r in results for n in _norm_numbers(r["text"] + " " + r["title"])})
    urls = {r["url"] for r in results}
    facts, dropped = [], 0
    for f in data.get("facts") or []:
        if not isinstance(f, dict) or not str(f.get("text") or "").strip():
            continue
        text = re.sub(r"\s+", " ", str(f["text"])).strip()[:300]
        if not _grounded([text], numbers, 0.5):              # parchada yo'q raqam — to'qilgan bo'lishi mumkin
            dropped += 1
            continue
        url = str(f.get("url") or "")
        facts.append({"section": _int(f.get("section")), "text": text, "source": str(f.get("source") or "")[:60],
                      "url": url if url in urls else ""})
    series = []
    for s in data.get("series") or []:
        if not isinstance(s, dict):
            continue
        labels = [str(x).strip()[:20] for x in (s.get("labels") or []) if str(x).strip()][:12]
        values = []
        for v in (s.get("values") or [])[:len(labels)]:
            try:
                values.append(float(str(v).replace(",", ".").replace("%", "").strip()))
            except ValueError:
                values.append(None)
        pairs = [(lb, v) for lb, v in zip(labels, values) if v is not None]
        if len(pairs) < 3 or not _grounded([v for _, v in pairs], numbers, 0.66):
            dropped += 1
            continue
        series.append({"section": _int(s.get("section")), "title": str(s.get("title") or "")[:60],
                       "labels": [p[0] for p in pairs], "values": [p[1] for p in pairs],
                       "unit": str(s.get("unit") or "")[:12], "source": str(s.get("source") or "")[:60]})
    if dropped:
        log.info("3D tadqiqot: parchalarda tasdiqlanmagan %d ta fakt/qator tashlandi", dropped)
    return {"facts": facts[:MAX_FACTS], "series": series[:MAX_SERIES]}


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _sources(facts: List[dict], series: List[dict], results: List[dict]) -> List[dict]:
    """Taqdimotda ishlatilgan manbalar (takrorsiz): avval faktlarda ko'rsatilganlari."""
    by_url = {r["url"]: r for r in results}
    out, seen = [], set()
    for item in list(facts) + list(series):
        url = item.get("url") or ""
        name = item.get("source") or (by_url.get(url) or {}).get("title", "")
        key = url or name
        if key and key not in seen:
            seen.add(key)
            out.append({"name": name[:80], "url": url})
    return out[:10]


def tayyorla(topic: str, preferences: str = "", language: str = "uz", budget: float = 150.0) -> Optional[dict]:
    """Bo'limlar → qidiruv → faktlar. Natija: {"sections", "facts", "series", "sources"} yoki None."""
    if not enabled():
        return None
    t0 = time.time()
    sections = savollar(topic, preferences, language)
    results = qidir(sections)
    if not results:
        log.warning("3D tadqiqot: internetdan hech narsa topilmadi")
        return None
    if time.time() - t0 > budget:
        return None
    try:
        found = faktlar(topic, sections, results, language)
    except Exception as exc:                  # noqa: BLE001
        log.warning("3D tadqiqot: faktlar ajratilmadi (%s)", exc)
        return None
    if not found["facts"]:
        return None
    out = {"sections": [s["title"] for s in sections], "facts": found["facts"], "series": found["series"]}
    out["sources"] = _sources(found["facts"], found["series"], results)
    log.info("3D tadqiqot: %d bo'lim, %d natija, %d fakt, %d qator, %.0f s", len(sections), len(results),
             len(out["facts"]), len(out["series"]), time.time() - t0)
    return out


def matn(research: dict) -> str:
    """Reja uchun: bo'limlar, faktlar (manbasi bilan) va diagramma qatorlari."""
    lines = ["SECTIONS (cover each, in this order):"]
    lines += [f"{k + 1}. {t}" for k, t in enumerate(research["sections"])]
    lines.append("\nFACTS (fresh, from the web):")
    for f in research["facts"]:
        sec = f["section"] + 1 if 0 <= f["section"] < len(research["sections"]) else "-"
        lines.append(f"- [{sec}] {f['text']} ({f['source'] or 'web'})")
    if research.get("series"):
        lines.append("\nDATA SERIES (use as charts):")
        for k, s in enumerate(research["series"], 1):
            pairs = ", ".join(f"{lb}: {v:g}" for lb, v in zip(s["labels"], s["values"]))
            lines.append(f"S{k}. {s['title']} ({s['unit']}) — {pairs} — source: {s['source']}")
    return "\n".join(lines)
