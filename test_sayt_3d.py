"""Saytdagi «🧊 3D taqdimot»: mavzu mosligi qarori, to'lovdan oldingi bepul tekshiruv, fayl nomi, ko'rinish.

- «Plural Noun» kabi mavzu (faqat ramziy kitob modeli) — rad (pul yechilmaydi / qaytadi);
- «qisman» mos, lekin mavzuning o'zini ko'rsatadigan modellar bor (dvigatel, Quyosh tizimi) — yaratiladi
  (#337 dagi «faqat to'liq mos» qoidasi bularni ham rad etardi);
- tekshiruv natijasi eslab qolinadi: buyurtma aynan shu qaror bilan bajariladi (AI qayta so'ralmaydi);
- fayl nomi qisqa va toza; saytda ko'rinish (zaxira rasmlar) yaratiladi; oldindan 8 slayd tanlangan.

    python test_sayt_3d.py
"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


import services.kat3d as kat3d  # noqa: E402
from services import three_d_gate, web_decks, web_kinds  # noqa: E402
from services.kat3d import qidiruv  # noqa: E402
from services.med3d import auto as med3d_auto  # noqa: E402
from services.web_jobs import JobError  # noqa: E402

BUILT, VIEWS, CALLS = [], [], {"kat": 0}


async def fake_build(topic, count, ids, **kw):
    BUILT.append(("catalog", topic, count, list(ids)))
    return "/tmp/3d.pptx", count


async def fake_med(topic, count, **kw):
    BUILT.append(("anatomy", topic, count, []))
    return "/tmp/3d.pptx", count


kat3d.build_deck = fake_build
med3d_auto.build_deck = fake_med
web_decks.create_view = lambda job_id, params, path, three_d=False: VIEWS.append((job_id, three_d)) or 8
MED_NO = {"ok": False, "checked": True}
PARAMS = {"topic": "Plural Noun", "slide_count": 8, "language": "en", "author": "", "preferences": "", "_job_id": "j1"}


async def run(kat, med=MED_NO, topic="Plural Noun"):
    three_d_gate._cache.clear()

    def top(t, language="uz"):
        CALLS["kat"] += 1
        return kat
    qidiruv.top = top
    med3d_auto.check_topic = lambda t, language="uz": med
    BUILT.clear(); VIEWS.clear()
    try:
        path, name = await web_kinds._three_d_run(dict(PARAMS, topic=topic), lambda *a: None)
        return None, name
    except JobError as exc:
        return exc, None


def kat(level, asosiy=(), yordamchi=(), ramziy=(), checked=True, coverage=None):
    direct = list(asosiy) + list(yordamchi)
    ids = direct + list(ramziy)
    return {"level": level, "ok": level != "none", "ids": ids if level != "none" else [], "asosiy": list(asosiy),
            "direct": direct, "checked": checked, "coverage": coverage}


async def main():
    print("1) Qaror")
    err, _ = await run(kat("partial", ramziy=["kitob", "kutubxona"]))
    check("faqat ramziy model («Plural Noun» → kitob) — rad, no_3d, taqdimot yasalmaydi",
          err is not None and err.code == "no_3d" and not BUILT, (err, BUILT))
    err, _ = await run(kat("none"))
    check("mos model yo'q — rad", err is not None and err.code == "no_3d" and not BUILT)
    err, name = await run(kat("full", ["a", "b", "c"]), topic="Avtomobil tuzilishi")
    check("to'liq mos — katalog bilan, so'ralgan slaydlar soni bilan", err is None and BUILT
          and BUILT[0][0] == "catalog" and BUILT[0][2] == 8 and BUILT[0][3] == ["a", "b", "c"], (err, BUILT))
    from services import katalog3d
    by = {}
    for mid, m in katalog3d.katalog().items():
        by.setdefault(m["nom_uz"], mid)
    volc = [by["Vulqon"], by["Etna vulqoni geologik xaritasi"]]
    books = [by["Eski kitob"], by["Charm muqovali oilaviy Injil"], by["Kopt ibodat kitobi"]]
    err, _ = await run(kat("partial", asosiy=volc[:1], yordamchi=volc[1:], ramziy=["globus"], coverage=60),
                       topic="Vulqonlar va zilzilalar")
    check("qisman (qamrov 60%), vulqon modellari bor — yaratiladi (#337 da rad edi)",
          err is None and BUILT and BUILT[0][0] == "catalog" and BUILT[0][3][:2] == volc, (err, BUILT))
    err, _ = await run(kat("partial", asosiy=books, coverage=40))
    check("«Plural Noun»: AI 3 ta kitobni «asosiy» degan, qamrov 40% — rad (haqiqiy AI sinovidagi holat)",
          err is not None and err.code == "no_3d" and not BUILT, (err, BUILT))
    err, _ = await run(kat("partial", asosiy=books, coverage=60))
    check("«Plural Noun»: AI qamrovni 60% desa ham — rad (kitob nomida mavzu so'zi yo'q)",
          err is not None and err.code == "no_3d" and not BUILT, (err, BUILT))
    err, _ = await run(kat("partial", asosiy=["tarozi1", "tarozi2", "tarozi3"], coverage=35), topic="Inflyatsiya")
    check("«Inflyatsiya»: tarozilar, qamrov 35% — rad", err is not None and not BUILT, BUILT)
    err, _ = await run(kat("partial", asosiy=["quyosh"], ramziy=["globus"]), topic="Quyosh")
    check("qisman va bevosita mos model faqat bitta — rad (bitta model 8 slaydga yetmaydi)", err is not None and not BUILT, BUILT)
    err, _ = await run(kat("none"), med={"ok": True, "checked": True, "organs": ["yurak"]}, topic="Yurak tuzilishi")
    check("anatomiya (AI tasdiqlagan) — 3D Anatomiya", err is None and BUILT and BUILT[0][0] == "anatomy", (err, BUILT))
    err, _ = await run(kat("none", checked=False), med={"ok": True, "checked": False}, topic="Yurak tuzilishi")
    check("AI javob bermadi — buyurtma avvalgidek (anatomiya, reja tuzilmasa pul qaytadi)",
          err is None and BUILT and BUILT[0][0] == "anatomy", (err, BUILT))
    unsure = three_d_gate.public(three_d_gate.decide({"ok": True, "checked": False}, {"ok": False, "ids": [], "checked": False}))
    check("… lekin to'lovdan oldingi tekshiruv «mos» deb va'da bermaydi", unsure["ok"] and not unsure["sure"]
          and "tekshirib bo'lmadi" in unsure["message"] and not unsure["names"], unsure)

    print("2) Tekshiruv natijasi eslab qolinadi")
    three_d_gate._cache.clear()
    qidiruv.top = lambda t, language="uz": (CALLS.__setitem__("kat", CALLS["kat"] + 1), kat("full", ["a", "b", "c"]))[1]
    med3d_auto.check_topic = lambda t, language="uz": MED_NO
    CALLS["kat"] = 0
    first = await three_d_gate.check("Avtomobil  tuzilishi", "uz")
    again = await three_d_gate.check("avtomobil tuzilishi", "uz")
    BUILT.clear()
    await web_kinds._three_d_run(dict(PARAMS, topic="Avtomobil tuzilishi", language="uz"), lambda *a: None)
    check("bir mavzu: AI bir marta so'raldi (tekshiruv + buyurtma)", CALLS["kat"] == 1 and first == again and BUILT, CALLS)

    print("3) Fayl nomi va ko'rinish")
    _, name = await run(kat("full", ["a", "b", "c"]), topic="Inson yuragining tuzilishi va qon aylanish tizimi")
    check("fayl nomi qisqa va toza (qavs, apostrof, ogohlantirishsiz)", name == "Inson_yuragining_tuzilishi_va_qon_3D.pptx", name)
    check("apostrof va belgilar olib tashlanadi", web_kinds.three_d_filename("O‘zbekiston: me'moriy (yodgorliklar)")
          == "Ozbekiston_memoriy_yodgorliklar_3D.pptx", web_kinds.three_d_filename("O‘zbekiston: me'moriy (yodgorliklar)"))
    check("saytda ko'rinish yaratiladi (3D belgisi bilan)", VIEWS == [("j1", True)], VIEWS)

    print("4) Anatomiya matni: muqova va punktlar")
    plan = {"slides": [{"text": "Yurak ko'krak qafasida joylashgan. U qonni haydaydi."},
                       {"text": "Yurak to'rt kameradan iborat. 1628-yilda U. Garvey qon aylanishini tasvirlagan. Klapanlar qonni bir tomonga o'tkazadi."},
                       {"text": "A. B. C. D. E. F. G."}, {"text": "Bitta gap."}]}
    med3d_auto.as_points(plan)
    s = [x["text"] for x in plan["slides"]]
    check("1-slayd — muqova: bitta qisqa jumla", s[0] == "Yurak ko'krak qafasida joylashgan.", s[0])
    check("matn punktlarga bo'linadi, qisqartma («U. Garvey») bo'linmaydi",
          s[1].split("\n") == ["• Yurak to'rt kameradan iborat.", "• 1628-yilda U. Garvey qon aylanishini tasvirlagan.",
                               "• Klapanlar qonni bir tomonga o'tkazadi."], s[1])
    check("bitta gap — o'zgarishsiz", s[3] == "Bitta gap.", s[3])

    print("5) Shakl")
    opts = web_kinds._three_d_options()
    check("oldindan 8 slayd tanlangan (4 emas)", opts.get("default_size") == "8"
          and any(z["key"] == "8" for z in opts["sizes"]), opts.get("default_size"))
    check("3D bilan yaxshi chiqadigan namuna mavzular", len(opts.get("examples") or []) >= 6, opts.get("examples"))
    js = open("webapp/site/static/studio.js", encoding="utf8").read()
    check("studio.js «default_size» ni hisobga oladi", "o.default_size" in js)
    check("normalize: slayd soni berilmasa — 8", web_kinds._three_d_normalize({"topic": "Yurak"})["slide_count"] == 8)

    print("\n✅ hammasi o'tdi" if not FAILS else f"\n❌ {len(FAILS)} ta xato: {FAILS}")
    sys.exit(1 if FAILS else 0)


asyncio.run(main())
