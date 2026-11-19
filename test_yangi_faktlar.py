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

print("\n✅ hammasi o'tdi" if not FAILS else f"\n❌ {len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
