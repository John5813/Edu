"""Statistik, iqtisodiy, siyosiy va aniq faktli (shaxs, adabiyot, tarix, joy) mavzularda taqdimotdan oldin internetdan yangi faktlar (Brave web qidiruvi).

Model bilimi ma'lum sanada tugaydi. Yil qoidasi esa «qator joriy yilgacha borsin» degani uchun arzon model
(DeepSeek V4 Flash, o'ylashsiz) 2024–2026-yillar raqamlarini to'qirdi: «2026-yilda YaIM 6,2%», «inflyatsiya 9,2%».
Endi bunday mavzularda avval 3D taqdimotdagi tadqiqot (`services.kat3d.tadqiqot`) ishlaydi: mavzu bo'limlarga
bo'linadi, Brave'da qidiriladi, parchalardan yili va manbasi bilan faktlar olinadi — har raqam parchada borligi
kod bilan tekshiriladi. Faktlar slaydlarni yozuvchi modelga manba matni bilan birga beriladi.

Brave kaliti yo'q yoki hech narsa topilmasa — bo'sh qator: taqdimot avvalgidek yoziladi (yil qoidasi baribir
«bilmagan yilga raqam to'qima, har raqamning yilini yoz» deydi). `PREMIUM_FRESH_FACTS=0` — o'chirish.
"""
import asyncio
import contextlib
import contextvars
import logging
import os
import re

log = logging.getLogger(__name__)

ON = os.getenv("PREMIUM_FRESH_FACTS", "1") != "0"
BUDGET_SEC = 90
# Brave web so'rovlari (har biri pullik, ~0,5 sent): 3D katalogdagi 10 ta o'rniga — 5 ta (har bo'limga bittadan).
MAX_QUERIES = int(os.getenv("PREMIUM_FRESH_QUERIES") or 5)
MAX_CHARS = 3600              # manba matni (slayd so'rovida 4000 belgigacha) ichida faktlarga ajratiladigan joy

# Yangi raqam kerak bo'ladigan mavzular: statistika, iqtisod, siyosat, aholi, bozor, reyting (uz, ru, en, kk).
_FRESH = re.compile(
    r"statist|iqtisod|yaim|ichki mahsulot|inflyats|byudjet|budjet|investits|eksport|import|savdo|bozor|narx|"
    r"aholi|demograf|ishsiz|bandlik|daromad|kambag|soliq|valyuta|kurs\b|bank|moliya|turizm|siyosat|saylov|"
    r"prezident|parlament|hukumat|islohot|geosiyos|xalqaro munosabat|urush|nizo|reyting|indeks|so.nggi yil|"
    r"hozirgi|zamonaviy holat|"
    r"статист|экономик|ввп|инфляц|бюджет|инвестиц|экспорт|импорт|торгов|рынок|цен|населени|демограф|безработ|"
    r"доход|бедност|налог|валют|банк|финанс|туризм|полит|выбор|президент|парламент|правительств|реформ|"
    r"геополит|международн|войн|конфликт|рейтинг|индекс|последн\w* год|"
    r"statistic|econom|\bgdp\b|inflation|budget|investment|export|import|trade|market|price|population|"
    r"demograph|unemploy|employment|income|poverty|tax|currency|banking|finance|tourism|politic|election|"
    r"president|parliament|government|reform|geopolit|international relations|\bwar\b|conflict|ranking|index|"
    r"recent years|current state|"
    r"статистика|экономика|халық|сайлау|саясат|нарық|бюджет|"
    # Aniq faktli mavzular: shaxs (hayoti, asarlari), adabiyot, tarix, joylar — arzon model sana, asar nomi va
    # iqtibos to'qirdi («Xudoyberdi To'xtaboyev 1946-yilda tug'ilgan», «Sehrli uzuk» degan asar).
    r"hayot|ijod|biograf|tarjimai hol|adib|shoir|yozuvchi|olim|alloma|mutafakkir|rassom|bastakor|sarkarda|"
    r"hukmdor|asarlari|romani|qissasi|dostoni|she.riyat|adabiyot|tarix|sulola|xonlig|davlati|imperiya|"
    r"jang|qo.zg.olon|inqilob|shahri|viloyati|mamlakati|"
    r"жизн|творчеств|биограф|писател|поэт|учён|учен|мыслител|художник|композитор|полковод|правител|"
    r"произведени|роман|поэм|литератур|истори|династ|ханств|импери|битв|восстани|революц|город|"
    r"\blife\b|biography|writer|poet|scientist|philosopher|painter|composer|ruler|\bworks\b|novel|"
    r"literature|history|dynasty|empire|battle|revolution|\bcity\b|"
    r"өмір|шығармашылы|ақын|жазушы|ғалым|тарих",
    re.IGNORECASE)

# Hamma ichki prompt taqdimot tilida (o'zbekcha so'rovga o'zbekcha ko'rsatma) — faktlar ham mijoz tilida keladi.
_TEXT = {
    "uz": {"head": ("INTERNETDAN YANGI FAKTLAR (har birining yili va manbasi bilan) — so'nggi yillar raqamlarini faqat "
                    "shulardan ol. Bu faktlarda biror ko'rsatkich va yil uchun qiymat bo'lsa, uni hamma joyda (matn, "
                    "yirik raqamlar, diagramma) AYNAN shunday yoz; o'sha ko'rsatkich va yilga boshqa raqam yozma. "
                    "Shu yerdagi ko'rsatkichlarni afzal ko'r. Bu yerda yo'q yillarga raqam to'qima: aniq bilgan eski "
                    "ma'lumotingni yili bilan yoz («2023-yil ma'lumotiga ko'ra»). Asar nomlari, sanalar, mukofotlar va "
                    "iqtiboslar — faqat shu faktlardan yoki aniq bilganingdan; ularni hech qachon to'qima."),
           "facts": "FAKTLAR:", "series": "MA'LUMOT QATORLARI (diagramma uchun):",
           "chart": "Bu faktlarda shu ko'rsatkich bo'lsa, aynan ularning qiymati va yillarini ol; o'sha ko'rsatkich "
                    "va yilga boshqa qiymat to'qima."},
    "ru": {"head": ("СВЕЖИЕ ФАКТЫ ИЗ ИНТЕРНЕТА (у каждого — год и источник) — цифры за последние годы бери только "
                    "отсюда. Если здесь есть значение показателя за год, пиши ИМЕННО его везде (текст, крупные цифры, "
                    "диаграммы); не пиши другое число для того же показателя и года. Предпочитай показатели отсюда. "
                    "Для лет, которых здесь нет, не выдумывай цифры: используй старые данные, в которых уверен, с "
                    "годом («по данным за 2023 год»). Названия произведений, даты, награды и цитаты — только отсюда "
                    "или если ты в них уверен; никогда их не выдумывай."),
           "facts": "ФАКТЫ:", "series": "РЯДЫ ДАННЫХ (для диаграмм):",
           "chart": "Если в этих фактах есть этот показатель, бери именно их значения и годы; не выдумывай другие "
                    "значения для того же показателя и года."},
    "en": {"head": ("FRESH FACTS FROM THE WEB (each with its year and source) — take recent figures only from here. "
                    "If these facts give a value for an indicator and year, use EXACTLY that value everywhere (text, "
                    "key numbers and charts); never write a different number for the same indicator and year. Prefer "
                    "the indicators covered here. For years not covered here do not invent numbers: use older data "
                    "you are sure of and always write its year (\"according to 2023 data\"). Names of works, dates, "
                    "awards and quotes — only from these facts or what you are certain of; never invent them."),
           "facts": "FACTS:", "series": "DATA SERIES (for charts):",
           "chart": "If these facts contain this indicator, use exactly their values and years; do not invent other "
                    "values for the same indicator and year."},
    "kk": {"head": ("ИНТЕРНЕТТЕН ЖАҢА ФАКТІЛЕР (әрқайсысының жылы мен дереккөзі бар) — соңғы жылдардың сандарын "
                    "тек осыдан ал. Мұнда көрсеткіш пен жылдың мәні болса, оны барлық жерде (мәтін, ірі сандар, "
                    "диаграмма) ДӘЛ солай жаз; сол көрсеткіш пен жылға басқа сан жазба. Мұнда жоқ жылдарға сан "
                    "ойдан шығарма: нақты білетін ескі деректі жылымен жаз («2023 жылғы деректер бойынша»). "
                    "Шығарма атаулары, күндер, марапаттар мен дәйексөздер — тек осы фактілерден немесе нақты "
                    "білгеніңнен; оларды ешқашан ойдан шығарма."),
           "facts": "ФАКТІЛЕР:", "series": "ДЕРЕКТЕР ҚАТАРЛАРЫ (диаграмма үшін):",
           "chart": "Бұл фактілерде осы көрсеткіш болса, дәл олардың мәндері мен жылдарын ал; сол көрсеткіш пен "
                    "жылға басқа мән ойдан шығарма."},
}


def _text(language: str) -> dict:
    return _TEXT.get({"uz-cyrl": "uz", "uz-yangi": "uz"}.get(language, language), _TEXT["uz"])


# Shu taqdimotning faktlari: diagramma va «yirik raqamlar» so'rovlari ham ko'radi (`chart_data`).
_CURRENT: contextvars.ContextVar = contextvars.ContextVar("fresh_facts", default="")
_LANG: contextvars.ContextVar = contextvars.ContextVar("fresh_facts_lang", default="uz")
# Mijozning o'z materiali (fayl, matn, havola) va «qattiq» rejim: raqam faqat material yoki faktlardan.
_MATERIAL: contextvars.ContextVar = contextvars.ContextVar("fresh_material", default="")
_STRICT: contextvars.ContextVar = contextvars.ContextVar("fresh_strict", default=False)


def current() -> str:
    """Joriy taqdimotning faktlar bloki (bo'lmasa — bo'sh)."""
    return _CURRENT.get()


@contextlib.contextmanager
def scope():
    """Bitta taqdimot doirasi: ichida `remember()` qilingan faktlar boshqa buyurtmaga o'tmaydi."""
    tokens = (_CURRENT.set(""), _MATERIAL.set(""), _STRICT.set(False))
    try:
        yield
    finally:
        for var, token in zip((_CURRENT, _MATERIAL, _STRICT), tokens):
            var.reset(token)


def remember(block_text: str, language: str = "uz") -> None:
    _CURRENT.set(block_text or "")
    _LANG.set(language or "uz")


def set_material(text: str, strict: bool) -> None:
    """Mijoz materiali va qattiq rejim (statistika/shaxs/tarix mavzusi yoki mijoz materiali bor)."""
    _MATERIAL.set(text or "")
    _STRICT.set(bool(strict))


def strict() -> bool:
    """Diagramma va «yirik raqamlar» raqamlari faqat material yoki faktlardan bo'lishi shartmi."""
    return _STRICT.get()


def grounded(values, share: float = 0.6) -> bool:
    """Raqamlarning kamida `share` qismi mijoz materialida yoki internet faktlarida bormi (yillar hisobga olinmaydi)."""
    from services.kat3d import tadqiqot

    corpus = f"{_CURRENT.get()}\n{_MATERIAL.get()}"
    if not corpus.strip():
        return False
    numbers = tadqiqot._scaled(tadqiqot._norm_numbers(corpus))
    return tadqiqot._grounded(list(values), numbers, share)


def for_chart() -> str:
    """Diagramma/raqamlar so'roviga qo'shimcha: faktlar bo'lsa — ulardagi qiymatlar majburiy."""
    facts = current()
    if not facts:
        return ""
    return "\n\n" + facts + "\n" + _text(_LANG.get())["chart"]


def needs(topic: str, preferences: str = "") -> bool:
    """Mavzuga yangi raqamlar kerakmi (statistika, iqtisod, siyosat ...)."""
    return bool(_FRESH.search(f"{topic} {preferences}"))


def block(research: dict, language: str = "uz") -> str:
    """Tadqiqot natijasi → slayd so'roviga qo'shiladigan matn (faktlar va diagramma qatorlari, yili va manbasi)."""
    T = _text(language)
    lines = [T["head"], "", T["facts"]]
    lines += [f"- {f['text']} ({f.get('source') or 'web'})" for f in research.get("facts") or []]
    series = research.get("series") or []
    if series:
        lines += ["", T["series"]]
        for k, s in enumerate(series, 1):
            # «;» bilan: «6, 2024» kabi vergul raqam tekshiruvida bitta raqam bo'lib o'qilmasin.
            pairs = "; ".join(f"{lb}: {v:g}" for lb, v in zip(s["labels"], s["values"]))
            lines.append(f"S{k}. {s['title']} ({s['unit']}) — {pairs} — {s.get('source') or 'web'}")
    text = "\n".join(lines)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS].rsplit("\n", 1)[0]


async def gather(topic: str, preferences: str = "", language: str = "uz") -> str:
    """Kerak bo'lsa — internetdan faktlar bloki, aks holda bo'sh qator. Xato ko'tarmaydi."""
    if not ON or not needs(topic, preferences):
        return ""
    try:
        from services.kat3d import tadqiqot

        if not tadqiqot.enabled():
            return ""
        research = await asyncio.wait_for(
            asyncio.to_thread(tadqiqot.tayyorla, topic, preferences, language, BUDGET_SEC, MAX_QUERIES),
            BUDGET_SEC + 30)
    except Exception as exc:                  # noqa: BLE001 — faktsiz ham taqdimot yoziladi
        log.warning("Yangi faktlar olinmadi (%s): %s", topic[:60], exc)
        return ""
    if not research or not research.get("facts"):
        return ""
    log.info("Yangi faktlar: %d fakt, %d qator — «%s»", len(research["facts"]), len(research.get("series") or []),
             topic[:60])
    return block(research, language)
