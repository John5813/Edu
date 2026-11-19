"""Yangi faktlar va yillar: arzon model (o'ylashsiz) eski yoki to'qilgan ma'lumot bermasin.

- statistika, iqtisod, siyosat va aniq faktli (shaxs, adabiyot, tarix) mavzularda — internetdan faktlar
  (`fresh_facts`), oddiy fan mavzularida — yo'q;
- faktlar slayd, diagramma va «yirik raqamlar» so'rovlariga boradi, boshqa taqdimotga o'tmaydi;
- «oxirgi to'liq yil» — o'tgan yil (joriy yil tugamagan); yil qoidasi raqam to'qishni taqiqlaydi;
- Brave 402 (kredit tugagan) — kalit limiti tugagan kabi, navbatdagi kalitga o'tiladi.

    python test_yangi_faktlar.py
"""
import asyncio, datetime, os, sys, tempfile
from unittest import mock

os.environ.setdefault("BOT_TOKEN", "1:x")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  XATO ") + name + ("" if ok else f" — {detail}"))
    if not ok:
        FAILS.append(name)


from services import timeframe
from services.premium_presentation import fresh_facts, prompts, chart_data

print("1) Qaysi mavzuga internet faktlari kerak")
for topic, want in [("O'zbekiston iqtisodiyoti: so'nggi yillardagi statistika", True),
                    ("O'zbekistonda siyosiy islohotlar va saylovlar", True),
                    ("Xudoyberdi To'xtaboyev - bolalarning sarguzasht va romannavis adibi", True),
                    ("Лев Толстой: жизнь и творчество", True), ("Amir Temur davlati", True),
                    ("Inflation in Kazakhstan", True), ("Pifagor teoremasi", False),
                    ("Fotosintez jarayoni", False), ("Kiberxavfsizlik asoslari", False)]:
    check(f"{topic}: {'ha' if want else 'yo`q'}", fresh_facts.needs(topic) == want)

print("2) Faktlar bloki va doirasi")
research = {"facts": [{"text": "2024-yilda YaIM 6,5% ga o'sdi.", "source": "stat.uz", "section": 0}],
            "series": [{"title": "YaIM o'sishi", "unit": "%", "labels": ["2023", "2024"], "values": [6.0, 6.5],
                        "source": "IMF"}]}
block = fresh_facts.block(research)
check("blokda fakt, qator va «aynan shu qiymat» qoidasi (o'zbekcha)", "6,5%" in block and "S1." in block
      and "AYNAN" in block and "to'qima" in block, block)
check("blok sarlavhasi taqdimot tilida (ru, en, kk)", "ФАКТЫ:" in fresh_facts.block(research, "ru")
      and "FACTS:" in fresh_facts.block(research, "en") and "ФАКТІЛЕР:" in fresh_facts.block(research, "kk"))
check("blok slayd so'roviga sig'adi", len(fresh_facts.block({"facts": [{"text": "x" * 300, "source": "s"}] * 40})) <= 3600)
check("faktsiz — diagramma so'roviga hech narsa qo'shilmaydi", fresh_facts.for_chart() == "")
with fresh_facts.scope():
    fresh_facts.remember(block, "uz")
    check("taqdimot ichida diagramma so'rovi faktlarni ko'radi", "6,5%" in fresh_facts.for_chart()
          and "6,5%" in chart_data._prompt("Iqtisod", "YaIM", "o'sish", "bar", "uz"))
check("taqdimot tugagach faktlar boshqa buyurtmaga o'tmaydi", fresh_facts.current() == "")


async def _no_research():
    with mock.patch.object(fresh_facts, "ON", True):
        return await fresh_facts.gather("Pifagor teoremasi")
check("oddiy fan mavzusida internetga so'rov yuborilmaydi", asyncio.run(_no_research()) == "")

print("3) Yillar")
with mock.patch.object(timeframe, "today", lambda: datetime.date(2026, 11, 19)):
    check("2026-yil noyabrida oxirgi to'liq yil — 2025 (joriy yil tugamagan)", timeframe.last_full_year() == 2025)
    rule = timeframe.year_rule("uz")
    check("yil qoidasi: joriy yil tugamagan, raqam to'qilmaydi, har raqamning yili",
          "hali tugamagan" in rule and "to'qima" in rule and "yili" in rule, rule)
    check("yil qoidasi: asar nomi, sana va iqtibos to'qilmaydi, «taxminiy iqtibos» yo'q",
          "Asar nomlari" in rule and "taxminiy iqtibos" in rule, rule)
    for lang in ("ru", "en", "kk"):
        r = prompts.year_rule(lang)
        check(f"{lang}: yil qoidasi 2025 bilan va to'qimaslik bandi bilan", "2025" in r and ("цитат" in r or "quote" in r
              or "дәйексөз" in r), r)
with mock.patch.object(timeframe, "today", lambda: datetime.date(2027, 2, 10)):
    check("fevralda oxirgi to'liq yil — ikki yil oldingi (o'tgan yil yakunlari hali e'lon qilinmagan)",
          timeframe.last_full_year() == 2025)

print("4) Brave kaliti krediti tugasa (402)")
from services import brave_keys
tmp = tempfile.mkdtemp()
with mock.patch.object(brave_keys, "PATH", os.path.join(tmp, "k.json")), \
        mock.patch.dict(os.environ, {"BRAVE_API_KEY": ""}):
    brave_keys.add("AAA"); brave_keys.add("BBB")
    brave_keys.report_failure("AAA", 402)
    doc = brave_keys._load()
    k = {x["key"]: x for x in doc["keys"]}
    check("402 — kalit shu oyga to'lgan deb belgilanadi (yaroqsiz emas — oy boshida qaytadi)",
          k["AAA"]["used"] >= brave_keys.LIMIT and not k["AAA"]["failed"], k["AAA"])
import inspect
from services import photo_search
from services.kat3d import tadqiqot
check("rasm qidiruvi 402 da keyingi kalitga o'tadi", "(401, 402, 403, 429)" in inspect.getsource(photo_search._brave))
check("web tadqiqot 402 da keyingi kalitga o'tadi", "(401, 402, 403, 429)" in inspect.getsource(tadqiqot._brave_web))

print("5) Model JSON'dan keyin yana JSON yoki matn yozsa")
from services.premium_presentation import llm_client
check("ikki obyekt birlashtiriladi (rasm tanlash yiqilmaydi)",
      llm_client._joined_objects('{"picks": [{"slot": 1, "ids": [3]}]}\n{"spare": [5, 6]}')
      == {"picks": [{"slot": 1, "ids": [3]}], "spare": [5, 6]})
check("obyektdan keyingi izoh tashlanadi", llm_client._joined_objects('{"query": "Amir Temur"} Izoh: ...') == {"query": "Amir Temur"})
check("buzilgan matn — None", llm_client._joined_objects("javob yo'q") is None)

print("6) Mijoz materiali: slaydga mos qism, reja istak va materialni ko'radi")
from services.premium_presentation import source_pick, html_slides
long_text = ("Kirish. Bu ma'ruza matni. " * 30 + "\n\n" + "Paxta yetishtirish va sug'orish tizimi haqida. " * 40
             + "\n\n" + "Bank tizimi va kredit siyosati. Markaziy bank foiz stavkasi 14 foiz. " * 40)
pick = source_pick.excerpt(long_text, "Bank tizimi va foiz stavkasi", 1500)
check("uzun materialdan slayd mavzusiga mos qism olinadi (boshi emas)", "Markaziy bank" in pick and "Paxta" not in pick
      and len(pick) <= 1500, pick[:120])
check("qisqa material butunligicha", source_pick.excerpt("Qisqa matn.", "x", 4000) == "Qisqa matn.")
check("mos so'z yo'q bo'lsa — boshidan", source_pick.excerpt(long_text, "zzzz qqqq", 300).startswith("Kirish"))
with fresh_facts.scope():
    fresh_facts.remember(block, "uz")
    ctx = html_slides._plan_context("Iqtisod", "uz", "Talabalar uchun sodda tilda", long_text)
    check("reja so'rovida mijoz istagi, materiali va faktlar bor", "Talabalar uchun sodda tilda" in ctx
          and "Mijoz bergan material" in ctx and "6,5%" in ctx, ctx[:200])
    outline = [{"title": "Bank tizimi", "brief": "foiz stavkasi", "category": "matn"}] * 3
    up = html_slides._user_prompt("Iqtisod", 1, 2, 3, outline, [], 2, long_text, "", "", language="uz")
    check("slayd so'rovida materialning mos qismi va faktlar alohida", "Markaziy bank" in up and "6,5%" in up
          and "FAKTLAR:" in up, up[-300:])

print("7) Diagramma va «yirik raqamlar» — faqat material yoki faktlardagi raqam (qattiq rejim)")
raw_ok = {"ok": True, "kind": "bar", "labels": ["2023", "2024"], "series": [{"name": "YaIM", "values": [6.0, 6.5]}],
          "source": "stat.uz", "unit": "%"}
raw_bad = dict(raw_ok, series=[{"name": "YaIM", "values": [5.6, 5.5]}])
with fresh_facts.scope():
    fresh_facts.remember(block, "uz")
    fresh_facts.set_material("", strict=True)
    with mock.patch.object(chart_data.llm_client, "_call_openrouter", lambda *a, **k: raw_bad):
        check("faktlarda yo'q raqamli diagramma qo'yilmaydi", chart_data.research("Iqtisod", "YaIM", "o'sish", "bar") is None)
    with mock.patch.object(chart_data.llm_client, "_call_openrouter", lambda *a, **k: raw_ok):
        check("faktlardagi raqamli diagramma qoladi", chart_data.research("Iqtisod", "YaIM", "o'sish", "bar") is not None)
    kpis = {"items": [{"value": "6,5", "unit": "%", "label": "YaIM o'sishi", "year": "2024"},
                      {"value": "6,0", "unit": "%", "label": "YaIM 2023", "year": "2023"},
                      {"value": "9,2", "unit": "%", "label": "Inflyatsiya", "year": "2026"}], "source": "stat.uz"}
    with mock.patch.object(chart_data, "validate_kpis", lambda raw: dict(kpis)), \
            mock.patch.object(chart_data.llm_client, "_call_openrouter", lambda *a, **k: {}):
        got = chart_data.research_kpis("Iqtisod", "Ko'rsatkichlar", "")
    check("«yirik raqamlar»dan faktlarda yo'q raqam olib tashlanadi", got and [i["value"] for i in got["items"]] == ["6,5"]
          if got and len(got["items"]) == 1 else got is None or "9,2" not in [i["value"] for i in got["items"]], got)
with fresh_facts.scope():
    fresh_facts.set_material("", strict=False)
    with mock.patch.object(chart_data.llm_client, "_call_openrouter", lambda *a, **k: raw_bad):
        check("oddiy fan mavzusi (qattiq emas) — avvalgidek", chart_data.research("Fizika", "Tezlik", "", "bar") is not None)

print("\n✅ hammasi o'tdi" if not FAILS else f"\n❌ {len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
